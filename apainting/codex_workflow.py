from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .image_ops import load_rgb, save_rgb
from .compiler import assign_paths_to_units
from .schemas import PathRecord, ReplayPlan, ScenePlan, StructurePlan, VisualTokenRecord


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _token_records(run_dir: Path) -> list[VisualTokenRecord]:
    path = run_dir / "analysis" / "visual_tokens.json"
    if not path.exists():
        return []
    return [VisualTokenRecord.model_validate(x) for x in _read_json(path)]


def _path_records_raw(run_dir: Path) -> list[dict[str, object]]:
    path = run_dir / "analysis" / "paths.json"
    return _read_json(path) if path.exists() else []


def _write_unassigned_token_view(run_dir: Path, scene: ScenePlan, tokens: list[VisualTokenRecord]) -> Path:
    source = load_rgb(run_dir / "assets" / "source.png")
    overlay = source.copy()
    used = {token for unit in scene.units for token in unit.token_ids}
    unassigned = {t.id for t in tokens if t.id not in used}
    paths = _path_records_raw(run_dir)
    centers: dict[str, list[tuple[float, float]]] = {}

    for path in paths:
        token_id = path.get("token_id")
        if token_id not in unassigned:
            continue
        pts = np.asarray(path["points"], dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(overlay, [pts], False, (235, 55, 35), thickness=4, lineType=cv2.LINE_AA)
        centroid = path.get("centroid")
        if isinstance(centroid, list) and len(centroid) == 2:
            centers.setdefault(str(token_id), []).append((float(centroid[0]), float(centroid[1])))
        elif isinstance(centroid, tuple) and len(centroid) == 2:
            centers.setdefault(str(token_id), []).append((float(centroid[0]), float(centroid[1])))

    for token_id, pts in centers.items():
        cx = int(round(sum(p[0] for p in pts) / len(pts)))
        cy = int(round(sum(p[1] for p in pts) / len(pts)))
        cv2.putText(overlay, token_id, (cx + 4, cy - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 30, 20), 1, cv2.LINE_AA)

    out = run_dir / "analysis" / "pass1_unassigned_tokens.png"
    save_rgb(out, overlay)
    return out


def _write_unit_views(run_dir: Path, scene: ScenePlan, by_unit: dict[str, list[PathRecord]] | None = None) -> list[Path]:
    source = load_rgb(run_dir / "assets" / "source.png")
    out_dir = run_dir / "analysis" / "unit_views"
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []

    if by_unit is None:
        raw = _path_records_raw(run_dir)
        token_owner = {token_id: unit.id for unit in scene.units for token_id in unit.token_ids}
        by_unit = {u.id: [] for u in scene.units}
        for item in raw:
            token_id = item.get("token_id")
            uid = token_owner.get(str(token_id)) if token_id else None
            if uid:
                by_unit[uid].append(PathRecord.model_validate(item))

    for unit in scene.units:
        # Keep the full composition visible, but fade it heavily so the owned geometry reads clearly.
        faded = np.clip(source.astype(np.float32) * 0.30 + 255.0 * 0.70, 0, 255).astype(np.uint8)
        overlay = faded.copy()
        for path in by_unit.get(unit.id, []):
            pts = np.asarray(path.points, dtype=np.int32).reshape(-1, 1, 2)
            cv2.polylines(overlay, [pts], False, (20, 35, 45), thickness=3, lineType=cv2.LINE_AA)
        root_x = int(round(unit.root.x / 1000 * source.shape[1]))
        root_y = int(round(unit.root.y / 1000 * source.shape[0]))
        cv2.circle(overlay, (root_x, root_y), 8, (230, 70, 35), -1, cv2.LINE_AA)
        cv2.putText(
            overlay,
            f"{unit.id} | {unit.direction.value} | root",
            (18, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (25, 25, 25),
            1,
            cv2.LINE_AA,
        )
        out = out_dir / f"{unit.id}.png"
        save_rgb(out, overlay)
        outputs.append(out)
    return outputs


def validate_stage(
    run_dir: Path,
    stage: str = "all",
    min_path_grounding: float = 0.95,
    require_structure_all: bool = True,
) -> dict[str, object]:
    run_dir = run_dir.resolve()
    result: dict[str, object] = {"stage": stage, "ok": True, "errors": [], "warnings": []}
    errors: list[str] = result["errors"]  # type: ignore[assignment]
    warnings: list[str] = result["warnings"]  # type: ignore[assignment]

    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        errors.append("manifest.json missing; run `apainting codex-start IMAGE --out RUN_DIR` first")
        result["ok"] = False
        return result
    manifest = _read_json(manifest_path)
    result["manifest"] = {
        "path_count": manifest.get("path_count"),
        "visual_token_count": manifest.get("visual_token_count"),
        "accent_count": manifest.get("accent_count"),
    }

    if stage in {"prepare", "all"}:
        required = [
            run_dir / "assets" / "source.png",
            run_dir / "analysis" / "visual_token_atlas.png",
            run_dir / "analysis" / "visual_tokens.json",
            run_dir / "analysis" / "paths.json",
        ]
        missing = [str(p.relative_to(run_dir)) for p in required if not p.exists()]
        if missing:
            errors.append(f"prepare artifacts missing: {missing}")

    scene: ScenePlan | None = None
    if stage in {"pass1", "pass2", "compiled", "final", "all"}:
        scene_path = run_dir / "scene_plan.json"
        if not scene_path.exists():
            errors.append("scene_plan.json missing")
        else:
            try:
                scene = ScenePlan.model_validate_json(scene_path.read_text(encoding="utf-8"))
            except Exception as exc:  # pydantic produces useful detail
                errors.append(f"scene_plan.json invalid: {exc}")

    if scene is not None:
        tokens = _token_records(run_dir)
        known_tokens = {t.id for t in tokens}
        token_owner: dict[str, str] = {}
        duplicate_tokens: list[str] = []
        unknown_tokens: list[str] = []
        for unit in scene.units:
            for token_id in unit.token_ids:
                if token_id not in known_tokens:
                    unknown_tokens.append(token_id)
                if token_id in token_owner and token_owner[token_id] != unit.id:
                    duplicate_tokens.append(token_id)
                token_owner[token_id] = unit.id
        if duplicate_tokens:
            errors.append(f"tokens assigned to multiple units: {sorted(set(duplicate_tokens))[:30]}")
        if unknown_tokens:
            errors.append(f"unknown token ids: {sorted(set(unknown_tokens))[:30]}")

        uses_token_grounding = any(u.token_ids for u in scene.units)
        uses_unit_map = bool(scene.unit_map_path)
        if not uses_token_grounding and not uses_unit_map:
            errors.append("Pass 1 has no executable grounding: use token_ids (preferred) or indexed unit_map.png; bbox_hint is not grounding")

        empty_units = [u.id for u in scene.units if not u.token_ids and not (uses_unit_map and u.mask_value is not None)]
        if empty_units:
            errors.append(f"units without ownership evidence: {empty_units}")

        if uses_unit_map:
            unit_map_path = run_dir / str(scene.unit_map_path)
            if not unit_map_path.exists():
                errors.append(f"unit_map_path does not exist: {scene.unit_map_path}")

        # Run the same semantic grounding logic the compiler will use, but stop before scheduling.
        by_unit: dict[str, list[PathRecord]] | None = None
        if not errors:
            try:
                path_records = [PathRecord.model_validate(x) for x in _path_records_raw(run_dir)]
                by_unit, unresolved_paths, _ = assign_paths_to_units(
                    path_records,
                    scene,
                    int(manifest.get("width", 0)),
                    int(manifest.get("height", 0)),
                    run_dir,
                )
                total_length = sum(p.length for p in path_records) or 1.0
                unresolved_set = set(unresolved_paths)
                grounded_length = sum(p.length for p in path_records if p.id not in unresolved_set)
                path_length_coverage = grounded_length / total_length
                result["pass1"] = {
                    "unit_count": len(scene.units),
                    "assigned_token_count": len(token_owner),
                    "total_token_count": len(tokens),
                    "path_length_grounding": path_length_coverage,
                    "unresolved_path_count": len(unresolved_paths),
                    "unassigned_token_count": len(known_tokens - set(token_owner)),
                    "grounding_mode": "token_ids" if uses_token_grounding else "unit_map",
                }
                if path_length_coverage < min_path_grounding:
                    errors.append(
                        f"Pass 1 path-length grounding {path_length_coverage:.3f} < {min_path_grounding:.3f}; inspect analysis/pass1_unassigned_tokens.png and assign only visually certain tokens"
                    )
                elif path_length_coverage < 0.985:
                    warnings.append(f"Pass 1 path-length grounding is {path_length_coverage:.3f}; review remaining ambiguous geometry if visually important")
            except Exception as exc:
                errors.append(f"Pass 1 grounding check failed: {exc}")
        _write_unassigned_token_view(run_dir, scene, tokens)
        _write_unit_views(run_dir, scene, by_unit=by_unit)

    if stage in {"pass2", "compiled", "final", "all"} and scene is not None:
        structure_path = run_dir / "structure_plan.json"
        if not structure_path.exists():
            errors.append("structure_plan.json missing")
        else:
            try:
                structure = StructurePlan.model_validate_json(structure_path.read_text(encoding="utf-8"))
                scene_ids = {u.id for u in scene.units}
                structure_ids = {u.unit_id for u in structure.units}
                unknown = sorted(structure_ids - scene_ids)
                if unknown:
                    errors.append(f"StructurePlan references unknown macro units: {unknown}")
                if require_structure_all:
                    required = {u.id for u in scene.units if u.subdivide}
                    missing = sorted(required - structure_ids)
                    if missing:
                        errors.append(f"Pass 2 missing subdivided units: {missing}")
                empty = [u.unit_id for u in structure.units if not u.guides]
                if empty:
                    errors.append(f"StructurePlan units with no guides: {empty}")
                result["pass2"] = {
                    "covered_unit_count": len(structure_ids & scene_ids),
                    "scene_unit_count": len(scene_ids),
                    "guide_count": sum(len(u.guides) for u in structure.units),
                }
            except Exception as exc:
                errors.append(f"structure_plan.json invalid: {exc}")

    if stage in {"compiled", "final", "all"}:
        replay_path = run_dir / "replay_plan.json"
        if not replay_path.exists():
            errors.append("replay_plan.json missing; run `apainting finalize RUN_DIR` or `apainting compile RUN_DIR`")
        else:
            try:
                replay = ReplayPlan.model_validate_json(replay_path.read_text(encoding="utf-8"))
                unresolved = int(replay.metadata.get("unresolved_path_count", 0))
                total_paths = int(manifest.get("path_count", 0))
                grounding = 1.0 - unresolved / max(total_paths, 1)
                unresolved_accents = int(replay.metadata.get("unresolved_accent_count", 0))
                result["compiled"] = {
                    "event_count": len(replay.events),
                    "unit_order": replay.unit_order,
                    "path_grounding_ratio": grounding,
                    "unresolved_path_count": unresolved,
                    "unresolved_accent_count": unresolved_accents,
                }
                if grounding < min_path_grounding:
                    errors.append(f"compiled path grounding {grounding:.3f} < {min_path_grounding:.3f}")
                if unresolved_accents:
                    warnings.append(f"{unresolved_accents} accent components remain unresolved; inspect before final export")
            except Exception as exc:
                errors.append(f"replay_plan.json invalid: {exc}")

    if stage in {"final", "all"}:
        video = run_dir / "outputs" / "replay.mp4"
        inspection = run_dir / "outputs" / "inspection_1_3_5.png"
        if not video.exists():
            errors.append("outputs/replay.mp4 missing")
        if not inspection.exists():
            warnings.append("outputs/inspection_1_3_5.png missing; run `apainting inspect RUN_DIR`")

    result["ok"] = not errors
    out = run_dir / "analysis" / f"validation_{stage}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def inspect_video(run_dir: Path, times: Iterable[float] = (1.0, 3.0, 5.0), video_name: str = "replay.mp4") -> dict[str, object]:
    video_path = run_dir / "outputs" / video_name
    if not video_path.exists():
        raise FileNotFoundError(video_path)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / max(fps, 1e-6)
    samples: list[tuple[float, np.ndarray]] = []
    for t in times:
        t = max(0.0, min(float(t), max(0.0, duration - 1.0 / max(fps, 1.0))))
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if ok:
            samples.append((t, cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    cap.release()
    if not samples:
        raise RuntimeError("could not extract inspection frames")

    target_h = 420
    tiles: list[Image.Image] = []
    font = ImageFont.load_default()
    for t, rgb in samples:
        h, w = rgb.shape[:2]
        target_w = max(1, int(round(w * target_h / h)))
        image = Image.fromarray(rgb).resize((target_w, target_h))
        tile = Image.new("RGB", (target_w, target_h + 34), "white")
        tile.paste(image, (0, 34))
        draw = ImageDraw.Draw(tile)
        draw.text((8, 10), f"{t:g}s", fill="black", font=font)
        tiles.append(tile)
    sheet = Image.new("RGB", (sum(t.width for t in tiles), max(t.height for t in tiles)), "white")
    x = 0
    for tile in tiles:
        sheet.paste(tile, (x, 0))
        x += tile.width
    out = run_dir / "outputs" / "inspection_1_3_5.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    report = {"video": str(video_path), "duration": duration, "fps": fps, "times": [t for t, _ in samples], "output": str(out)}
    (run_dir / "outputs" / "inspection_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def build_runbook(run_dir: Path) -> Path:
    manifest = _read_json(run_dir / "manifest.json")
    token_tiles = manifest.get("token_tiles", [])
    tile_lines = "\n".join(f"- `{x}`" for x in token_tiles) if token_tiles else "- `analysis/visual_token_atlas.png`"
    text = f"""# APainting Codex execution runbook (generated for this run)

This is an **execution task**, not a code-design task. The architecture is already approved.
Do not create specs, implementation plans, worktrees, or review documents. Do not ask the user to confirm unit count/order before running.
Proceed until a playable preview exists unless an actual hard error blocks execution.

## Run facts

- input: `{manifest.get('input')}`
- size: {manifest.get('width')} x {manifest.get('height')}
- paths: {manifest.get('path_count')}
- visual tokens: {manifest.get('visual_token_count')}
- accents: {manifest.get('accent_count')}

## Pass 1 — macro Drawing Units and ownership

Inspect:
- `analysis/source_grid.png`
- `analysis/visual_token_atlas.png`
{tile_lines}

Write `scene_plan.json`.

**Default to `token_ids`. Do not hand-paint semantic polygons/corridors unless the token atlas truly cannot express ownership.**
Do not use `bbox_hint` for ownership. A unit should usually represent a drawable macro region, not every individual flower.
For this fixed botanical style, 5–10 macro units is often a useful starting range, but choose what the image actually supports.
Do not ask the user to approve the count: choose, write the file, and validate.

Then run:

```bash
apainting validate {run_dir} --stage pass1
```

Pass 1 is accepted when weighted token coverage is >= 95% and there are no duplicate/unknown token assignments.
If it fails, inspect `analysis/pass1_unassigned_tokens.png`, fix only unresolved/incorrect token ownership, and rerun validation.

## Pass 2 — hierarchy inside each frozen macro Unit

After Pass 1 validation, inspect:
- `analysis/unit_views/*.png`
- the original source image

Write `structure_plan.json` for every `subdivide=true` unit.
Pass 2 may define only: backbone/main contour, primary structure, secondary structure, terminals/details, focus_group, progress.
**Pass 2 must never reassign a path/token to another macro Unit.**

Then run:

```bash
apainting validate {run_dir} --stage pass2
```

If it fails, fix only the named missing/invalid Unit guides.

## Finalize — one command

```bash
apainting finalize {run_dir} --duration 18 --max-height 1080
```

This compiles, checks grounding, renders, and extracts `1s / 3s / 5s` inspection frames.
Review:
- `outputs/inspection_1_3_5.png`
- `outputs/contact_sheet.png`
- `analysis/uncertain_paths.png` if present

Reject only for concrete process-fidelity failures: future-content leakage, unsupported terminal detail before structure, orphan accent, large unrelated revisit, or clearly wrong ownership.
Fix the smallest responsible layer; do not redesign the architecture.

## Load Studio

```bash
apainting serve {run_dir} --port 8000
```

Then report only:
- Studio URL
- preview video path
- 1/3/5 inspection image path
- path grounding ratio / unresolved counts
- current macro unit order

Do not create more design documents unless the user explicitly asks to modify the application itself.
"""
    out = run_dir / "CODEX_RUNBOOK.md"
    out.write_text(text, encoding="utf-8")
    return out


def status(run_dir: Path) -> dict[str, object]:
    run_dir = run_dir.resolve()
    stages = {
        "prepared": (run_dir / "manifest.json").exists(),
        "pass1_scene_plan": (run_dir / "scene_plan.json").exists(),
        "pass2_structure_plan": (run_dir / "structure_plan.json").exists(),
        "compiled": (run_dir / "replay_plan.json").exists(),
        "rendered": (run_dir / "outputs" / "replay.mp4").exists(),
        "inspected": (run_dir / "outputs" / "inspection_1_3_5.png").exists(),
    }
    return {"run_dir": str(run_dir), "stages": stages, "next": next((k for k, v in stages.items() if not v), "serve_or_export")}
