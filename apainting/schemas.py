from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

NormCoord = Annotated[int, Field(ge=0, le=1000)]


class UnitKind(str, Enum):
    upper_branch = "upper_branch"
    flora_cluster = "flora_cluster"
    flower_cluster = "flower_cluster"
    tree_cluster = "tree_cluster"
    mountain_mass = "mountain_mass"
    river = "river"
    water_ripples = "water_ripples"
    stone_cluster = "stone_cluster"
    water_lily_cluster = "water_lily_cluster"
    central_subject = "central_subject"
    bouquet = "bouquet"
    airborne_ornament = "airborne_ornament"
    other = "other"


class Direction(str, Enum):
    bottom_up = "bottom_up"
    top_down = "top_down"
    left_to_right = "left_to_right"
    right_to_left = "right_to_left"
    center_out = "center_out"
    far_to_near = "far_to_near"
    along_structure = "along_structure"
    free = "free"


class Grammar(str, Enum):
    botanical_growth = "botanical_growth"
    branch_growth = "branch_growth"
    tree_growth = "tree_growth"
    mountain_contour = "mountain_contour"
    river_flow = "river_flow"
    stone_contour = "stone_contour"
    human_contour = "human_contour"
    bouquet_growth = "bouquet_growth"
    contour_first = "contour_first"
    ornament_late = "ornament_late"


class NormPoint(BaseModel):
    x: NormCoord
    y: NormCoord


class NormBBox(BaseModel):
    """Optional diagnostic/crop hint only. Never used for semantic ownership."""

    x0: NormCoord
    y0: NormCoord
    x1: NormCoord
    y1: NormCoord

    @model_validator(mode="after")
    def validate_order(self) -> "NormBBox":
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("bbox must satisfy x1>x0 and y1>y0")
        return self


class UnitPlan(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    label: str
    kind: UnitKind
    root: NormPoint
    direction: Direction
    grammar: Grammar
    priority: int = Field(ge=0, le=100)
    layer: int = Field(ge=0, le=10)
    subdivide: bool = True
    notes: str = ""

    # Semantic ownership. Either an indexed unit map or visual-token IDs may ground a unit.
    # bbox is intentionally only a visual/crop hint and is never consumed by the compiler.
    mask_value: int | None = Field(default=None, ge=1, le=255)
    token_ids: list[str] = Field(default_factory=list)
    bbox_hint: NormBBox | None = None


class Dependency(BaseModel):
    before: str
    after: str
    reason: str = ""


class ScenePlan(BaseModel):
    coordinate_space: Literal["normalized_1000"] = "normalized_1000"
    style: Literal["botanical_single_line_stationery"] = "botanical_single_line_stationery"
    strategy: Literal[
        "scaffold_then_local_completion",
        "dominant_unit_then_local_completion",
        "local_completion_only",
    ] = "scaffold_then_local_completion"

    # Optional indexed semantic map. Pixel 0 = unassigned/background; non-zero values are
    # matched against UnitPlan.mask_value. This is the preferred Codex/manual interface.
    unit_map_path: str | None = None
    units: list[UnitPlan] = Field(min_length=1, max_length=24)
    dependencies: list[Dependency] = Field(default_factory=list)
    rationale: str = ""

    @model_validator(mode="after")
    def validate_ids(self) -> "ScenePlan":
        ids = [u.id for u in self.units]
        if len(ids) != len(set(ids)):
            raise ValueError("unit ids must be unique")
        known = set(ids)
        for dep in self.dependencies:
            if dep.before not in known or dep.after not in known:
                raise ValueError(f"dependency references unknown unit: {dep}")
            if dep.before == dep.after:
                raise ValueError("self dependency is not allowed")
        values = [u.mask_value for u in self.units if u.mask_value is not None]
        if len(values) != len(set(values)):
            raise ValueError("mask_value must be unique across units")
        return self


class StructureRole(str, Enum):
    backbone = "backbone"
    primary_structure = "primary_structure"
    secondary_structure = "secondary_structure"
    terminal = "terminal"
    detail = "detail"


class StructureGuide(BaseModel):
    """Coarse AI-authored structural guide used only *inside* an already-owned Drawing Unit.

    It never changes semantic unit ownership. The geometry compiler snaps real paths to the
    nearest guide and uses the guide for focus grouping, structural role, and progress.
    """

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    role: StructureRole
    points: list[NormPoint] = Field(min_length=2, max_length=24)
    focus_group: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    order: int = Field(ge=0, le=100)
    progress_start: float = Field(default=0.0, ge=0.0, le=1.0)
    progress_end: float = Field(default=1.0, ge=0.0, le=1.0)
    influence_radius: int = Field(default=70, ge=10, le=250)
    notes: str = ""

    @model_validator(mode="after")
    def validate_progress(self) -> "StructureGuide":
        if self.progress_end < self.progress_start:
            raise ValueError("progress_end must be >= progress_start")
        return self


class UnitStructurePlan(BaseModel):
    unit_id: str
    guides: list[StructureGuide] = Field(default_factory=list, max_length=32)
    notes: str = ""


class StructurePlan(BaseModel):
    coordinate_space: Literal["normalized_1000"] = "normalized_1000"
    units: list[UnitStructurePlan] = Field(default_factory=list)
    rationale: str = ""

    @model_validator(mode="after")
    def validate_structure(self) -> "StructurePlan":
        unit_ids = [u.unit_id for u in self.units]
        if len(unit_ids) != len(set(unit_ids)):
            raise ValueError("structure unit_ids must be unique")
        for unit in self.units:
            ids = [g.id for g in unit.guides]
            if len(ids) != len(set(ids)):
                raise ValueError(f"guide ids must be unique inside unit {unit.unit_id}")
        return self


class PathRecord(BaseModel):
    id: str
    points: list[tuple[int, int]]
    length: float
    bbox: tuple[int, int, int, int]
    centroid: tuple[float, float]
    token_id: str | None = None


class VisualTokenRecord(BaseModel):
    id: str
    path_ids: list[str]
    bbox: tuple[int, int, int, int]
    centroid: tuple[float, float]
    path_length: float


class AccentRecord(BaseModel):
    id: str
    mask_path: str
    bbox: tuple[int, int, int, int]
    centroid: tuple[float, float]
    area: int


class ReplayEvent(BaseModel):
    id: str
    event_type: Literal["stroke", "accent"]
    unit_id: str
    session_id: str
    path_id: str | None = None
    accent_id: str | None = None
    points: list[tuple[int, int]] = Field(default_factory=list)
    role: Literal["backbone", "structure", "attachment", "detail", "accent"]
    progress: float | None = Field(default=None, ge=0.0, le=1.0)
    structure_guide_id: str | None = None
    frame_weight: float = Field(gt=0)


class ReplayPlan(BaseModel):
    width: int
    height: int
    source_path: str
    paper_path: str
    foreground_mask_path: str
    accent_records: list[AccentRecord]
    events: list[ReplayEvent]
    unit_order: list[str]
    metadata: dict[str, object] = Field(default_factory=dict)


def dump_model(model: BaseModel, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json(indent=2), encoding="utf-8")
