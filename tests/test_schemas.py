from apainting.schemas import ScenePlan


def test_scene_plan_validation_without_bbox():
    plan = ScenePlan.model_validate(
        {
            "coordinate_space": "normalized_1000",
            "style": "botanical_single_line_stationery",
            "strategy": "scaffold_then_local_completion",
            "unit_map_path": "analysis/unit_map.png",
            "units": [
                {
                    "id": "river",
                    "label": "river",
                    "kind": "river",
                    "root": {"x": 500, "y": 250},
                    "direction": "far_to_near",
                    "grammar": "river_flow",
                    "priority": 1,
                    "layer": 1,
                    "subdivide": True,
                    "mask_value": 1,
                    "token_ids": [],
                }
            ],
            "dependencies": [],
        }
    )
    assert plan.units[0].id == "river"
    assert plan.units[0].bbox_hint is None
