from pathlib import Path

import cv2
import numpy as np

from apainting.compiler import assign_paths_to_units
from apainting.schemas import PathRecord, ScenePlan


def test_unit_map_grounding_never_uses_bbox(tmp_path: Path):
    unit_map = np.zeros((100, 100), dtype=np.uint8)
    unit_map[:, :50] = 1
    unit_map[:, 50:] = 2
    (tmp_path / "analysis").mkdir()
    cv2.imwrite(str(tmp_path / "analysis" / "unit_map.png"), unit_map)
    scene = ScenePlan.model_validate(
        {
            "unit_map_path": "analysis/unit_map.png",
            "units": [
                {
                    "id": "left",
                    "label": "left",
                    "kind": "other",
                    "root": {"x": 0, "y": 500},
                    "direction": "free",
                    "grammar": "contour_first",
                    "priority": 0,
                    "layer": 0,
                    "mask_value": 1,
                },
                {
                    "id": "right",
                    "label": "right",
                    "kind": "other",
                    "root": {"x": 1000, "y": 500},
                    "direction": "free",
                    "grammar": "contour_first",
                    "priority": 1,
                    "layer": 0,
                    "mask_value": 2,
                },
            ],
        }
    )
    paths = [
        PathRecord(id="P1", points=[(10, 10), (20, 20)], length=15, bbox=(10, 10, 20, 20), centroid=(15, 15)),
        PathRecord(id="P2", points=[(70, 10), (80, 20)], length=15, bbox=(70, 10, 80, 20), centroid=(75, 15)),
    ]
    by_unit, unresolved, _ = assign_paths_to_units(paths, scene, 100, 100, tmp_path)
    assert [p.id for p in by_unit["left"]] == ["P1"]
    assert [p.id for p in by_unit["right"]] == ["P2"]
    assert not unresolved
