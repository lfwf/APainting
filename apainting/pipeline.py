from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from .compiler import compile_replay_plan
from .image_ops import (
    colorize_indexed_unit_map,
    draw_atlas,
    draw_token_atlas,
    extract_layers,
    foreground_strength,
    load_rgb,
    make_grid_overlay,
    save_mask,
    save_rgb,
    skeleton_from_mask,
)
from .planner import create_scene_plan, create_structure_plan
from .project_state import load_playback_settings, validate_unit_order
from .renderer import render_video
from .web_ui import write_web_ui
from .schemas import AccentRecord, PathRecord, ReplayPlan, ScenePlan, StructurePlan, VisualTokenRecord, dump_model
from .vectorize import build_visual_tokens, extract_accent_components, trace_skeleton


def _save_token_tiles(token_atlas: np.ndarray, out_dir: Path, rows: int = 3, cols: int = 2) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    h, w = token_atlas.shape[:2]
    paths: list[str] = []
    for r in range(rows):
        for c in range(cols):
            y0 = int(round(r * h / rows))
            y1 = int(round((r + 1) * h / rows))
            x0 = int(round(c * w / cols))
            x1 = int(round((c + 1) * w / cols))
            crop = token_atlas[y0:y1, x0:x1]
            path = out_dir / f"token_atlas_r{r+1}_c{c+1}.png"
            save_rgb(path, crop)
            paths.append(str(path.relative_to(out_dir.parent.parent)))
    return paths


def prepare(input_path: Path, run_dir: Path) -> dict[str, object]:
    input_path = input_path.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    assets = run_dir / "assets"
    analysis = run_dir / "analysis"
    outputs = run_dir / "outputs"
    assets.mkdir(exist_ok=True)
    analysis.mkdir(exist_ok=True)
    outputs.mkdir(exist_ok=True)

    rgb = load_rgb(input_path)
    h, w = rgb.shape[:2]
    line_mask, accent_mask, paper = extract_layers(rgb)
    skeleton = skeleton_from_mask(line_mask)
    paths = trace_skeleton(skeleton, min_length=max(4.0, min(w, h) * 0.004))
    paths, tokens = build_visual_tokens(line_mask, paths)
    accents = extract_accent_components(accent_mask, assets / "accents")

    save_rgb(assets / "source.png", rgb)
    save_rgb(assets / "paper.png", paper)
    save_mask(analysis / "line_mask.png", line_mask)
    save_mask(analysis / "accent_mask.png", accent_mask)
    save_mask(analysis / "skeleton.png", skeleton)
    strength = foreground_strength(rgb, paper)
    cv2.imwrite(str(assets / "foreground_strength.png"), strength)
    save_rgb(analysis / "source_grid.png", make_grid_overlay(rgb))
    atlas = draw_atlas(rgb, [p.model_dump() for p in paths])
    save_rgb(analysis / "path_atlas.png", atlas)
    token_atlas = draw_token_atlas(
        rgb,
        [p.model_dump() for p in paths],
        [t.model_dump() for t in tokens],
    )
    save_rgb(analysis / "visual_token_atlas.png", token_atlas)
    token_tiles = _save_token_tiles(token_atlas, analysis / "token_tiles")

    (analysis / "paths.json").write_text(
        json.dumps([p.model_dump() for p in paths], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (analysis / "visual_tokens.json").write_text(
        json.dumps([t.model_dump() for t in tokens], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (analysis / "accents.json").write_text(
        json.dumps([a.model_dump() for a in accents], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    template = {
        "coordinate_space": "normalized_1000",
        "style": "botanical_single_line_stationery",
        "strategy": "scaffold_then_local_completion",
        "unit_map_path": None,
        "units": [
            {
                "id": "replace_me",
                "label": "replace me",
                "kind": "other",
                "root": {"x": 500, "y": 500},
                "direction": "along_structure",
                "grammar": "contour_first",
                "priority": 10,
                "layer": 1,
                "subdivide": True,
                "notes": "Codex must assign visual token IDs or create an indexed unit_map.png; bbox is never semantic ownership.",
                "mask_value": None,
                "token_ids": [],
                "bbox_hint": None,
            }
        ],
        "dependencies": [],
        "rationale": "",
    }
    (run_dir / "scene_plan.template.json").write_text(
        json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    structure_template = {
        "coordinate_space": "normalized_1000",
        "units": [
            {
                "unit_id": "replace_after_scene_plan",
                "guides": [
                    {
                        "id": "main_spine",
                        "role": "backbone",
                        "points": [{"x": 500, "y": 800}, {"x": 500, "y": 300}],
                        "focus_group": "main_spine",
                        "order": 0,
                        "progress_start": 0.0,
                        "progress_end": 1.0,
                        "influence_radius": 70,
                        "notes": "Second-pass AI structural guide; never changes macro ownership."
                    }
                ],
                "notes": "Delete or replace after macro ScenePlan is grounded."
            }
        ],
        "rationale": "Second-pass intra-unit hierarchy only."
    }
    (run_dir / "structure_plan.template.json").write_text(
        json.dumps(structure_template, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    manifest = {
        "input": str(input_path),
        "width": w,
        "height": h,
        "path_count": len(paths),
        "visual_token_count": len(tokens),
        "accent_count": len(accents),
        "token_tiles": token_tiles,
        "prepared": True,
        "ownership_contract": "token_ids or indexed unit map; no bbox fallback",
        "hierarchy_contract": "optional second-pass structure_plan.json guides affect only intra-unit order",
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_web_ui(run_dir)
    return manifest


def ai_plan(run_dir: Path, model: str | None = None) -> ScenePlan:
    token_tiles = sorted((run_dir / "analysis" / "token_tiles").glob("*.png"))
    plan = create_scene_plan(
        run_dir / "analysis" / "source_grid.png",
        token_tiles or [run_dir / "analysis" / "visual_token_atlas.png"],
        model=model,
    )
    dump_model(plan, run_dir / "scene_plan.json")
    return plan



def ai_structure(run_dir: Path, model: str | None = None) -> StructurePlan:
    scene = ScenePlan.model_validate_json((run_dir / "scene_plan.json").read_text(encoding="utf-8"))
    supports: list[Path] = []
    for candidate in [
        run_dir / "analysis" / "unit_map_preview.png",
        run_dir / "analysis" / "visual_token_atlas.png",
    ]:
        if candidate.exists():
            supports.append(candidate)
    plan = create_structure_plan(
        run_dir / "analysis" / "source_grid.png",
        scene,
        support_images=supports,
        model=model,
    )
    known = {u.id for u in scene.units}
    unknown = [u.unit_id for u in plan.units if u.unit_id not in known]
    if unknown:
        raise ValueError(f"structure plan references unknown units: {unknown}")
    dump_model(plan, run_dir / "structure_plan.json")
    return plan


def _write_structure_visual(run_dir: Path, structure: StructurePlan | None, width: int, height: int) -> None:
    if structure is None:
        return
    source = load_rgb(run_dir / "assets" / "source.png")
    overlay = source.copy()
    palette = [
        (225, 70, 45),
        (55, 135, 220),
        (50, 170, 100),
        (180, 90, 200),
        (220, 160, 45),
        (50, 180, 185),
    ]
    idx = 0
    for unit in structure.units:
        for guide in unit.guides:
            pts = np.asarray(
                [[round(p.x / 1000 * width), round(p.y / 1000 * height)] for p in guide.points],
                dtype=np.int32,
            ).reshape(-1, 1, 2)
            color = palette[idx % len(palette)]
            idx += 1
            cv2.polylines(overlay, [pts], False, color, thickness=3, lineType=cv2.LINE_AA)
            x, y = pts[0, 0]
            cv2.putText(
                overlay,
                guide.id,
                (int(x) + 4, int(y) - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.35,
                color,
                1,
                cv2.LINE_AA,
            )
    save_rgb(run_dir / "analysis" / "structure_guides_overlay.png", overlay)

def _write_grounding_visuals(run_dir: Path, scene: ScenePlan, replay: ReplayPlan) -> None:
    if scene.unit_map_path:
        path = run_dir / scene.unit_map_path
        unit_map = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if unit_map is not None:
            labels = {u.mask_value: u.id for u in scene.units if u.mask_value is not None}
            colorized = colorize_indexed_unit_map(unit_map, labels)  # type: ignore[arg-type]
            save_rgb(run_dir / "analysis" / "unit_map_preview.png", colorized)

    # Show only unresolved path geometry in red for quick Codex review.
    unresolved = set(replay.metadata.get("unresolved_path_ids", []))
    if unresolved:
        source = load_rgb(run_dir / "assets" / "source.png")
        overlay = source.copy()
        paths = json.loads((run_dir / "analysis" / "paths.json").read_text(encoding="utf-8"))
        for p in paths:
            if p["id"] not in unresolved:
                continue
            pts = np.array(p["points"], dtype=np.int32).reshape(-1, 1, 2)
            cv2.polylines(overlay, [pts], False, (235, 55, 35), thickness=4, lineType=cv2.LINE_AA)
        save_rgb(run_dir / "analysis" / "uncertain_paths.png", overlay)


def compile_plan(run_dir: Path) -> ReplayPlan:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    scene = ScenePlan.model_validate_json((run_dir / "scene_plan.json").read_text(encoding="utf-8"))
    paths = [
        PathRecord.model_validate(x)
        for x in json.loads((run_dir / "analysis" / "paths.json").read_text(encoding="utf-8"))
    ]
    accents = [
        AccentRecord.model_validate(x)
        for x in json.loads((run_dir / "analysis" / "accents.json").read_text(encoding="utf-8"))
    ]
    structure_path = run_dir / "structure_plan.json"
    structure = (
        StructurePlan.model_validate_json(structure_path.read_text(encoding="utf-8"))
        if structure_path.exists()
        else None
    )
    if structure is not None:
        known = {u.id for u in scene.units}
        unknown = [u.unit_id for u in structure.units if u.unit_id not in known]
        if unknown:
            raise ValueError(f"structure plan references unknown units: {unknown}")
    settings = load_playback_settings(run_dir)
    order_override = None
    raw_order = settings.get("unit_order")
    if isinstance(raw_order, list) and all(isinstance(x, str) for x in raw_order):
        order_override = validate_unit_order(list(raw_order), [u.id for u in scene.units])

    replay = compile_replay_plan(
        scene,
        paths,
        accents,
        width=int(manifest["width"]),
        height=int(manifest["height"]),
        run_dir=run_dir,
        structure=structure,
        unit_order_override=order_override,
    )
    dump_model(replay, run_dir / "replay_plan.json")
    _write_grounding_visuals(run_dir, scene, replay)
    _write_structure_visual(run_dir, structure, int(manifest["width"]), int(manifest["height"]))
    return replay


def render(
    run_dir: Path,
    fps: int = 30,
    duration: float = 18.0,
    max_height: int = 1080,
    output_name: str = "replay.mp4",
    auxiliary: bool = True,
) -> dict[str, object]:
    replay = ReplayPlan.model_validate_json((run_dir / "replay_plan.json").read_text(encoding="utf-8"))
    report = render_video(
        run_dir,
        replay,
        run_dir / "outputs" / output_name,
        fps=fps,
        duration=duration,
        max_height=max_height,
        write_auxiliary=auxiliary,
    )
    write_web_ui(run_dir)
    return report
