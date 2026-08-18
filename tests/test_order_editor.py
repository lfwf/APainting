from pathlib import Path

from apainting.compiler import _validated_unit_order, dependency_violations
from apainting.project_state import list_order_history, load_playback_settings, save_playback_settings
from apainting.schemas import Dependency, Direction, Grammar, NormPoint, ScenePlan, UnitKind, UnitPlan


def _scene() -> ScenePlan:
    def unit(uid: str, priority: int) -> UnitPlan:
        return UnitPlan(
            id=uid,
            label=uid,
            kind=UnitKind.other,
            root=NormPoint(x=500, y=500),
            direction=Direction.free,
            grammar=Grammar.contour_first,
            priority=priority,
            layer=0,
        )
    return ScenePlan(
        units=[unit("mountain", 0), unit("river", 1), unit("left_pines", 2), unit("right_pines", 3)],
        dependencies=[Dependency(before="mountain", after="left_pines", reason="background first")],
    )


def test_manual_order_can_override_ai_order() -> None:
    scene = _scene()
    order = ["mountain", "left_pines", "right_pines", "river"]
    assert _validated_unit_order(scene, order) == order
    assert dependency_violations(scene, order) == []


def test_dependency_reversal_is_reported_not_blocked() -> None:
    scene = _scene()
    order = ["left_pines", "mountain", "right_pines", "river"]
    assert _validated_unit_order(scene, order) == order
    assert dependency_violations(scene, order)[0]["before"] == "mountain"


def test_settings_and_history(tmp_path: Path) -> None:
    order = ["mountain", "left_pines", "right_pines", "river"]
    save_playback_settings(tmp_path, order, source="test", archive=True)
    assert load_playback_settings(tmp_path)["unit_order"] == order
    history = list_order_history(tmp_path)
    assert len(history) == 1
    assert history[0]["unit_order"] == order
