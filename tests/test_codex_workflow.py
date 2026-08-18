from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from apainting.codex_workflow import build_runbook, status, validate_stage
from apainting.schemas import Direction, Grammar, NormPoint, ScenePlan, UnitKind, UnitPlan


def _make_run(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    (run / "analysis").mkdir(parents=True)
    (run / "assets").mkdir(parents=True)
    (run / "outputs").mkdir(parents=True)
    image = np.full((40, 30, 3), 245, dtype=np.uint8)
    cv2.imwrite(str(run / "assets" / "source.png"), image)
    (run / "manifest.json").write_text(
        json.dumps({"input": "demo.png", "width": 30, "height": 40, "path_count": 2, "visual_token_count": 2, "accent_count": 0, "token_tiles": []}),
        encoding="utf-8",
    )
    (run / "analysis" / "visual_tokens.json").write_text(
        json.dumps([
            {"id": "C0001", "path_ids": ["P0001"], "bbox": [1, 1, 10, 10], "centroid": [5, 5], "path_length": 10.0},
            {"id": "C0002", "path_ids": ["P0002"], "bbox": [12, 12, 20, 20], "centroid": [16, 16], "path_length": 10.0},
        ]),
        encoding="utf-8",
    )
    (run / "analysis" / "paths.json").write_text(
        json.dumps([
            {"id": "P0001", "points": [[1, 1], [10, 10]], "length": 10.0, "bbox": [1, 1, 10, 10], "centroid": [5.0, 5.0], "token_id": "C0001"},
            {"id": "P0002", "points": [[12, 12], [20, 20]], "length": 10.0, "bbox": [12, 12, 20, 20], "centroid": [16.0, 16.0], "token_id": "C0002"},
        ]),
        encoding="utf-8",
    )
    cv2.imwrite(str(run / "analysis" / "visual_token_atlas.png"), image)
    return run


def test_pass1_validation_and_runbook(tmp_path: Path) -> None:
    run = _make_run(tmp_path)
    scene = ScenePlan(
        units=[
            UnitPlan(
                id="flora",
                label="flora",
                kind=UnitKind.flora_cluster,
                root=NormPoint(x=500, y=900),
                direction=Direction.bottom_up,
                grammar=Grammar.botanical_growth,
                priority=0,
                layer=0,
                subdivide=True,
                token_ids=["C0001", "C0002"],
            )
        ]
    )
    (run / "scene_plan.json").write_text(scene.model_dump_json(indent=2), encoding="utf-8")
    result = validate_stage(run, stage="pass1")
    assert result["ok"] is True
    assert result["pass1"]["path_length_grounding"] == 1.0
    assert (run / "analysis" / "unit_views" / "flora.png").exists()
    assert (run / "analysis" / "pass1_unassigned_tokens.png").exists()
    runbook = build_runbook(run)
    assert runbook.exists()
    text = runbook.read_text(encoding="utf-8")
    assert "Do not create specs" in text
    assert "token_ids" in text


def test_status_reports_next_stage(tmp_path: Path) -> None:
    run = _make_run(tmp_path)
    info = status(run)
    assert info["stages"]["prepared"] is True
    assert info["next"] == "pass1_scene_plan"
