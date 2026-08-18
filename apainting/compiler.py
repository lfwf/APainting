from __future__ import annotations

import heapq
import math
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

from .image_ops import resample_polyline
from .schemas import (
    AccentRecord,
    Direction,
    Grammar,
    PathRecord,
    ReplayEvent,
    ReplayPlan,
    ScenePlan,
    StructureGuide,
    StructurePlan,
    StructureRole,
    UnitPlan,
)
from .vectorize import build_path_adjacency


def _root_px(unit: UnitPlan, width: int, height: int) -> np.ndarray:
    return np.array([unit.root.x / 1000 * width, unit.root.y / 1000 * height], dtype=np.float32)


def _load_indexed_unit_map(run_dir: Path, scene: ScenePlan, width: int, height: int) -> np.ndarray | None:
    if not scene.unit_map_path:
        return None
    path = run_dir / scene.unit_map_path
    unit_map = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if unit_map is None:
        raise FileNotFoundError(f"unit map not found: {path}")
    if unit_map.shape != (height, width):
        raise ValueError(f"unit map has shape {unit_map.shape}, expected {(height, width)}")
    return unit_map


def _token_owner(scene: ScenePlan) -> dict[str, str]:
    result: dict[str, str] = {}
    for unit in scene.units:
        for token_id in unit.token_ids:
            if token_id in result and result[token_id] != unit.id:
                raise ValueError(f"visual token {token_id} is assigned to multiple units")
            result[token_id] = unit.id
    return result


def _mask_value_owner(scene: ScenePlan) -> dict[int, str]:
    return {u.mask_value: u.id for u in scene.units if u.mask_value is not None}


def _sample_path_labels(path: PathRecord, unit_map: np.ndarray) -> Counter[int]:
    h, w = unit_map.shape
    samples = resample_polyline(path.points, spacing=1.0)
    labels: Counter[int] = Counter()
    for x, y in samples:
        if 0 <= x < w and 0 <= y < h:
            value = int(unit_map[y, x])
            if value:
                labels[value] += 1
    return labels


def assign_paths_to_units(
    paths: list[PathRecord],
    scene: ScenePlan,
    width: int,
    height: int,
    run_dir: Path,
) -> tuple[dict[str, list[PathRecord]], list[str], dict[str, dict[str, float | str]]]:
    """Ground geometry to semantic units without any bbox ownership fallback.

    Priority:
    1) explicit AI/Codex visual-token ownership;
    2) indexed pixel-level unit map overlap;
    3) same-token propagation from already grounded sibling paths.

    Anything else remains unresolved and is reported instead of being silently attached
    to the nearest rectangle/centroid.
    """
    result: dict[str, list[PathRecord]] = {u.id: [] for u in scene.units}
    diagnostics: dict[str, dict[str, float | str]] = {}
    token_owner = _token_owner(scene)
    value_owner = _mask_value_owner(scene)
    unit_map = _load_indexed_unit_map(run_dir, scene, width, height)

    unresolved: list[PathRecord] = []
    for path in paths:
        if path.token_id and path.token_id in token_owner:
            uid = token_owner[path.token_id]
            result[uid].append(path)
            diagnostics[path.id] = {"unit_id": uid, "method": "visual_token", "confidence": 1.0}
            continue

        if unit_map is not None:
            votes = _sample_path_labels(path, unit_map)
            valid = [(count, value) for value, count in votes.items() if value in value_owner]
            valid.sort(reverse=True)
            sample_count = max(1, len(resample_polyline(path.points, spacing=1.0)))
            if valid:
                top_count, top_value = valid[0]
                second_count = valid[1][0] if len(valid) > 1 else 0
                coverage = top_count / sample_count
                margin = (top_count - second_count) / sample_count
                # Semantic maps can be deliberately thin. Require enough actual path support,
                # but never infer from bounding boxes when the map is silent.
                if coverage >= 0.35 or (coverage >= 0.18 and margin >= 0.12 and top_count >= 5):
                    uid = value_owner[top_value]
                    result[uid].append(path)
                    diagnostics[path.id] = {
                        "unit_id": uid,
                        "method": "unit_map",
                        "confidence": float(min(1.0, coverage + max(margin, 0.0))),
                    }
                    continue
        unresolved.append(path)

    # Propagate only within a persistent visual token when its grounded siblings strongly agree.
    token_votes: dict[str, Counter[str]] = defaultdict(Counter)
    for uid, members in result.items():
        for path in members:
            if path.token_id:
                token_votes[path.token_id][uid] += 1

    still_unresolved: list[PathRecord] = []
    for path in unresolved:
        if path.token_id and token_votes.get(path.token_id):
            counts = token_votes[path.token_id]
            uid, count = counts.most_common(1)[0]
            total = sum(counts.values())
            if count / max(total, 1) >= 0.75:
                result[uid].append(path)
                diagnostics[path.id] = {
                    "unit_id": uid,
                    "method": "token_propagation",
                    "confidence": float(count / max(total, 1)),
                }
                continue
        still_unresolved.append(path)
        diagnostics[path.id] = {"unit_id": "", "method": "unresolved", "confidence": 0.0}

    return result, [p.id for p in still_unresolved], diagnostics


def _accent_global_pixels(accent: AccentRecord, run_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    local = cv2.imread(str(run_dir / accent.mask_path), cv2.IMREAD_GRAYSCALE)
    if local is None:
        raise FileNotFoundError(run_dir / accent.mask_path)
    y_local, x_local = np.where(local > 0)
    x0, y0, _, _ = accent.bbox
    return x_local + x0, y_local + y0


def _min_distance_to_path_points(point: np.ndarray, paths: list[PathRecord]) -> float:
    best = float("inf")
    for path in paths:
        pts = np.asarray(resample_polyline(path.points, spacing=4.0), dtype=np.float32)
        if len(pts) == 0:
            continue
        best = min(best, float(np.linalg.norm(pts - point[None, :], axis=1).min()))
    return best


def assign_accents_to_units(
    accents: list[AccentRecord],
    scene: ScenePlan,
    by_unit: dict[str, list[PathRecord]],
    width: int,
    height: int,
    run_dir: Path,
) -> tuple[dict[str, list[AccentRecord]], list[str]]:
    """Bind pastel accents to semantic owners, never to a bbox or session center."""
    result: dict[str, list[AccentRecord]] = {u.id: [] for u in scene.units}
    value_owner = _mask_value_owner(scene)
    unit_map = _load_indexed_unit_map(run_dir, scene, width, height)
    unresolved: list[str] = []
    diag = math.hypot(width, height)

    for accent in accents:
        assigned: str | None = None
        if unit_map is not None:
            xs, ys = _accent_global_pixels(accent, run_dir)
            valid = (xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)
            xs = xs[valid]
            ys = ys[valid]
            if len(xs):
                values = unit_map[ys, xs]
                counts = Counter(int(v) for v in values if int(v) in value_owner)
                if counts:
                    value, count = counts.most_common(1)[0]
                    if count / len(xs) >= 0.25:
                        assigned = value_owner[value]

        # If a semantic fill mask does not cover the interior accent, attach it to the
        # nearest *already semantically owned* line geometry. This is not bbox grounding.
        if assigned is None:
            center = np.asarray(accent.centroid, dtype=np.float32)
            candidates: list[tuple[float, str]] = []
            for uid, unit_paths in by_unit.items():
                if not unit_paths:
                    continue
                candidates.append((_min_distance_to_path_points(center, unit_paths), uid))
            if candidates:
                candidates.sort()
                best_d, best_uid = candidates[0]
                second_d = candidates[1][0] if len(candidates) > 1 else float("inf")
                if best_d <= max(24.0, diag * 0.035) and (second_d - best_d >= 3.0 or best_d < 8.0):
                    assigned = best_uid

        if assigned is None:
            unresolved.append(accent.id)
        else:
            result[assigned].append(accent)
    return result, unresolved


def topological_unit_order(scene: ScenePlan) -> list[str]:
    by_id = {u.id: u for u in scene.units}
    indegree = {u.id: 0 for u in scene.units}
    edges: dict[str, set[str]] = defaultdict(set)
    for dep in scene.dependencies:
        if dep.after not in edges[dep.before]:
            edges[dep.before].add(dep.after)
            indegree[dep.after] += 1
    heap: list[tuple[int, int, str]] = []
    for uid, degree in indegree.items():
        if degree == 0:
            u = by_id[uid]
            heapq.heappush(heap, (u.priority, u.layer, uid))
    order: list[str] = []
    while heap:
        _, _, uid = heapq.heappop(heap)
        order.append(uid)
        for nxt in edges.get(uid, ()):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                u = by_id[nxt]
                heapq.heappush(heap, (u.priority, u.layer, nxt))
    if len(order) != len(scene.units):
        return [u.id for u in sorted(scene.units, key=lambda x: (x.priority, x.layer, x.id))]
    return order


def dependency_violations(scene: ScenePlan, unit_order: list[str]) -> list[dict[str, str]]:
    """Return AI dependency suggestions reversed by a manual macro-unit order.

    Manual ordering is intentionally allowed: a user may prefer a different staging than the
    AI suggestion. We surface the reversals to the UI instead of silently preventing the edit.
    """
    pos = {uid: i for i, uid in enumerate(unit_order)}
    result: list[dict[str, str]] = []
    for dep in scene.dependencies:
        if pos.get(dep.before, -1) > pos.get(dep.after, -1):
            result.append({"before": dep.before, "after": dep.after, "reason": dep.reason})
    return result


def _validated_unit_order(scene: ScenePlan, override: list[str] | None) -> list[str]:
    if override is None:
        return topological_unit_order(scene)
    known = [u.id for u in scene.units]
    if len(override) != len(known) or len(set(override)) != len(override):
        raise ValueError("manual unit order must contain every Drawing Unit exactly once")
    missing = set(known) - set(override)
    unknown = set(override) - set(known)
    if missing or unknown:
        raise ValueError(f"invalid manual unit order; missing={sorted(missing)}, unknown={sorted(unknown)}")
    return list(override)


def _connected_components(path_ids: list[str], adjacency: dict[str, set[str]]) -> list[list[str]]:
    unseen = set(path_ids)
    comps: list[list[str]] = []
    while unseen:
        start = unseen.pop()
        q = [start]
        comp = [start]
        while q:
            cur = q.pop()
            for nxt in adjacency.get(cur, set()):
                if nxt in unseen:
                    unseen.remove(nxt)
                    q.append(nxt)
                    comp.append(nxt)
        comps.append(comp)
    return comps


def _merge_tiny_components(
    comps: list[list[str]], path_map: dict[str, PathRecord], max_components: int = 12
) -> list[list[str]]:
    if len(comps) <= max_components:
        return comps
    work = [list(c) for c in comps]
    while len(work) > max_components:
        sizes = [sum(path_map[p].length for p in c) for c in work]
        idx = int(np.argmin(sizes))
        src = work[idx]
        src_center = np.mean([path_map[p].centroid for p in src], axis=0)
        best_j = None
        best_d = float("inf")
        for j, comp in enumerate(work):
            if j == idx:
                continue
            center = np.mean([path_map[p].centroid for p in comp], axis=0)
            d = float(np.linalg.norm(src_center - center))
            if d < best_d:
                best_d = d
                best_j = j
        assert best_j is not None
        work[best_j].extend(src)
        work.pop(idx)
    return work


def _role_for_path(path: PathRecord, lengths: np.ndarray, grammar: Grammar, root_distance: float) -> str:
    q50 = float(np.quantile(lengths, 0.50)) if len(lengths) else 0.0
    q80 = float(np.quantile(lengths, 0.80)) if len(lengths) else 0.0
    if grammar in {
        Grammar.botanical_growth,
        Grammar.branch_growth,
        Grammar.tree_growth,
        Grammar.river_flow,
        Grammar.mountain_contour,
        Grammar.bouquet_growth,
    }:
        if path.length >= q80:
            return "backbone"
        if path.length >= q50 or root_distance < 0.12:
            return "structure"
        if path.length >= max(7.0, q50 * 0.45):
            return "attachment"
        return "detail"
    if path.length >= q80:
        return "structure"
    if path.length < max(7.0, q50 * 0.4):
        return "detail"
    return "attachment"


def _direction_key(path: PathRecord, unit: UnitPlan, width: int, height: int) -> float:
    cx, cy = path.centroid
    d = unit.direction
    if d == Direction.bottom_up:
        return -cy
    if d == Direction.top_down:
        return cy
    if d == Direction.left_to_right:
        return cx
    if d == Direction.right_to_left:
        return -cx
    if d == Direction.far_to_near:
        return cy
    root = _root_px(unit, width, height)
    return float(np.linalg.norm(np.asarray([cx, cy]) - root))


def _orient_path(points: list[tuple[int, int]], target: np.ndarray) -> list[tuple[int, int]]:
    if len(points) < 2:
        return points
    a = np.asarray(points[0], dtype=np.float32)
    b = np.asarray(points[-1], dtype=np.float32)
    return points if np.linalg.norm(a - target) <= np.linalg.norm(b - target) else list(reversed(points))


def _session_distance_to_accent(group: dict[str, object], accent: AccentRecord) -> float:
    if group.get("accepts_accent", True) is False:
        return float("inf")
    point = np.asarray(accent.centroid, dtype=np.float32)
    member_paths = group.get("paths", [])
    assert isinstance(member_paths, list)
    if not member_paths:
        return float("inf")
    return _min_distance_to_path_points(point, member_paths)



def _guide_points_px(guide: StructureGuide, width: int, height: int) -> np.ndarray:
    return np.asarray(
        [[p.x / 1000.0 * width, p.y / 1000.0 * height] for p in guide.points],
        dtype=np.float32,
    )


def _project_point_to_polyline(point: np.ndarray, polyline: np.ndarray) -> tuple[float, float, np.ndarray]:
    """Return distance, normalized arc progress, and nearest point on a polyline."""
    if len(polyline) == 0:
        return float("inf"), 0.0, point.copy()
    if len(polyline) == 1:
        d = float(np.linalg.norm(point - polyline[0]))
        return d, 0.0, polyline[0].copy()
    segs = polyline[1:] - polyline[:-1]
    lens = np.linalg.norm(segs, axis=1)
    total = float(lens.sum())
    best_d = float("inf")
    best_progress = 0.0
    best_point = polyline[0].copy()
    prefix = 0.0
    for i, (a, v, seg_len) in enumerate(zip(polyline[:-1], segs, lens)):
        if seg_len <= 1e-6:
            prefix += float(seg_len)
            continue
        t = float(np.clip(np.dot(point - a, v) / (seg_len * seg_len), 0.0, 1.0))
        q = a + t * v
        d = float(np.linalg.norm(point - q))
        if d < best_d:
            best_d = d
            best_point = q
            best_progress = (prefix + t * float(seg_len)) / max(total, 1e-6)
        prefix += float(seg_len)
    return best_d, float(np.clip(best_progress, 0.0, 1.0)), best_point


def _guide_tangent_at_progress(polyline: np.ndarray, progress: float) -> np.ndarray:
    if len(polyline) < 2:
        return np.asarray([1.0, 0.0], dtype=np.float32)
    segs = polyline[1:] - polyline[:-1]
    lens = np.linalg.norm(segs, axis=1)
    total = float(lens.sum())
    target = float(np.clip(progress, 0.0, 1.0)) * max(total, 1e-6)
    prefix = 0.0
    for v, seg_len in zip(segs, lens):
        if prefix + float(seg_len) >= target and seg_len > 1e-6:
            return v / float(seg_len)
        prefix += float(seg_len)
    v = segs[-1]
    n = float(np.linalg.norm(v))
    return v / max(n, 1e-6)


def _path_samples_axis(path: PathRecord) -> tuple[np.ndarray, np.ndarray]:
    samples = np.asarray(resample_polyline(path.points, spacing=5.0), dtype=np.float32)
    if len(samples) == 0:
        samples = np.asarray([path.centroid], dtype=np.float32)
    if len(samples) >= 2:
        centered = samples - samples.mean(axis=0, keepdims=True)
        try:
            _, _, vh = np.linalg.svd(centered, full_matrices=False)
            axis = vh[0].astype(np.float32)
        except np.linalg.LinAlgError:
            axis = samples[-1] - samples[0]
    else:
        axis = np.asarray([1.0, 0.0], dtype=np.float32)
    an = float(np.linalg.norm(axis))
    axis = axis / max(an, 1e-6)
    return samples, axis


def _samples_to_guide(samples: np.ndarray, axis: np.ndarray, guide_pts: np.ndarray) -> tuple[float, float, float]:
    vals: list[tuple[float, float]] = []
    for pt in samples:
        d, t, _ = _project_point_to_polyline(pt, guide_pts)
        vals.append((d, t))
    vals.sort(key=lambda x: x[0])
    k = max(1, min(len(vals), max(2, len(vals) // 4)))
    d = float(np.mean([x[0] for x in vals[:k]]))
    t = float(np.median([x[1] for x in vals[:k]]))
    gt = _guide_tangent_at_progress(guide_pts, t)
    alignment = float(abs(np.dot(axis, gt)))
    return d, t, alignment


def _path_to_guide(path: PathRecord, guide: StructureGuide, width: int, height: int) -> tuple[float, float, float]:
    """Public/debug helper; structured compilation uses cached samples and guide pixels."""
    samples, axis = _path_samples_axis(path)
    return _samples_to_guide(samples, axis, _guide_points_px(guide, width, height))

def _structure_role_to_replay(role: StructureRole) -> str:
    if role == StructureRole.backbone:
        return "backbone"
    if role in {StructureRole.primary_structure, StructureRole.secondary_structure}:
        return "structure"
    if role == StructureRole.terminal:
        return "attachment"
    return "detail"


def _structure_unit_map(structure: StructurePlan | None) -> dict[str, list[StructureGuide]]:
    if structure is None:
        return {}
    return {u.unit_id: list(u.guides) for u in structure.units if u.guides}


def _compile_structured_sessions(
    unit: UnitPlan,
    unit_paths: list[PathRecord],
    guides: list[StructureGuide],
    width: int,
    height: int,
    session_index: int,
) -> tuple[list[dict[str, object]], int, dict[str, int]]:
    """Compile an already-owned semantic unit using AI-authored structural guides.

    The guides only influence *intra-unit* role, focus grouping and progress. They can never
    move a path to another semantic unit, which keeps macro ownership separate from hierarchy.
    """
    if not guides:
        return [], session_index, {}
    lengths = np.asarray([p.length for p in unit_paths], dtype=np.float32)
    q35 = float(np.quantile(lengths, 0.35)) if len(lengths) else 0.0
    q60 = float(np.quantile(lengths, 0.60)) if len(lengths) else 0.0
    diag = math.hypot(width, height)
    min_dim = float(min(width, height))

    guide_by_id = {g.id: g for g in guides}
    guide_group_order: dict[str, int] = {}
    for g in guides:
        guide_group_order[g.focus_group] = min(guide_group_order.get(g.focus_group, 10**9), g.order)

    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    guide_counts: Counter[str] = Counter()
    root = _root_px(unit, width, height)
    guide_cache = [
        (g, _guide_points_px(g, width, height), max(3.0, g.influence_radius / 1000.0 * min_dim))
        for g in guides
    ]

    for p in unit_paths:
        samples, axis = _path_samples_axis(p)
        matches: list[tuple[float, float, float, float, StructureGuide]] = []
        for g, guide_pts, radius_px in guide_cache:
            d, t, alignment = _samples_to_guide(samples, axis, guide_pts)
            norm_d = d / radius_px
            # Prefer a believable dominant spine for long aligned paths, but never let this
            # override a clearly closer branch guide. This repairs guide-junction fragmentation.
            bonus = 0.0
            if g.role == StructureRole.backbone and p.length >= q60 and alignment >= 0.55:
                bonus = 0.28
            elif g.role == StructureRole.primary_structure and alignment >= 0.50:
                bonus = 0.10
            score = norm_d - bonus
            matches.append((score, norm_d, t, alignment, g))
        matches.sort(key=lambda x: (x[0], x[4].order))
        _, norm_d, t, alignment, guide = matches[0]
        guide_counts[guide.id] += 1
        progress = guide.progress_start + t * (guide.progress_end - guide.progress_start)
        core_radius = 0.62
        # Long paths close to a guide are treated as the actual structural stroke. Short or
        # distant paths become attachments/details supported by that guide.
        required_alignment = 0.55 if guide.role == StructureRole.backbone else 0.38
        if (
            norm_d <= core_radius
            and alignment >= required_alignment
            and p.length >= max(6.0, q35 * 0.70)
        ):
            role = _structure_role_to_replay(guide.role)
        else:
            if guide.role == StructureRole.detail or p.length < max(6.0, q35 * 0.72):
                role = "detail"
            elif (
                guide.role not in {StructureRole.terminal, StructureRole.detail}
                and p.length >= max(6.0, q35)
                and norm_d <= 1.10
            ):
                role = "structure"
            else:
                role = "attachment"
        phase = {"backbone": 0, "structure": 1, "attachment": 2, "detail": 3}[role]
        # A small root-distance tie-break keeps the early support region stable.
        root_dist = float(np.linalg.norm(np.asarray(p.centroid) - root) / max(diag, 1.0))
        grouped[guide.focus_group].append(
            {
                "path": p,
                "role": role,
                "phase": phase,
                "progress": float(np.clip(progress, 0.0, 1.0)),
                "guide_id": guide.id,
                "guide_order": guide.order,
                "root_dist": root_dist,
            }
        )

    groups: list[dict[str, object]] = []
    for focus_group, records in sorted(grouped.items(), key=lambda kv: (guide_group_order[kv[0]], kv[0])):
        session_id = f"S{session_index:04d}"
        session_index += 1
        remaining = list(records)
        pen = root.copy()
        ordered_events: list[ReplayEvent] = []
        while remaining:
            min_phase = min(int(r["phase"]) for r in remaining)
            phase_records = [r for r in remaining if int(r["phase"]) == min_phase]
            min_progress = min(float(r["progress"]) for r in phase_records)
            # Keep progress monotonic, but allow local routing among nearby progress candidates.
            window = 0.12 if min_phase <= 1 else 0.18
            candidates = [r for r in phase_records if float(r["progress"]) <= min_progress + window]
            def route_cost(r: dict[str, object]) -> tuple[float, float, float]:
                p = r["path"]
                assert isinstance(p, PathRecord)
                a = np.asarray(p.points[0], dtype=np.float32)
                b = np.asarray(p.points[-1], dtype=np.float32)
                travel = float(min(np.linalg.norm(a - pen), np.linalg.norm(b - pen)))
                return (travel, float(r["progress"]), -p.length)
            chosen = min(candidates, key=route_cost)
            remaining.remove(chosen)
            p = chosen["path"]
            assert isinstance(p, PathRecord)
            oriented = _orient_path(p.points, pen)
            role = str(chosen["role"])
            ordered_events.append(
                ReplayEvent(
                    id="E00000",
                    event_type="stroke",
                    unit_id=unit.id,
                    session_id=session_id,
                    path_id=p.id,
                    points=oriented,
                    role=role,  # type: ignore[arg-type]
                    progress=float(chosen["progress"]),
                    structure_guide_id=str(chosen["guide_id"]),
                    frame_weight=max(1.0, p.length),
                )
            )
            pen = np.asarray(oriented[-1], dtype=np.float32)
        groups.append(
            {
                "session_id": session_id,
                "focus_group": focus_group,
                "events": ordered_events,
                "paths": [r["path"] for r in records],
            }
        )
    return groups, session_index, dict(guide_counts)

def compile_replay_plan(
    scene: ScenePlan,
    paths: list[PathRecord],
    accents: list[AccentRecord],
    width: int,
    height: int,
    run_dir: Path,
    structure: StructurePlan | None = None,
    unit_order_override: list[str] | None = None,
) -> ReplayPlan:
    by_unit, unresolved_paths, ownership_diag = assign_paths_to_units(
        paths, scene, width, height, run_dir
    )
    accents_by_unit, unresolved_accents = assign_accents_to_units(
        accents, scene, by_unit, width, height, run_dir
    )
    unit_order = _validated_unit_order(scene, unit_order_override)
    unit_map = {u.id: u for u in scene.units}
    path_map = {p.id: p for p in paths}
    structure_by_unit = _structure_unit_map(structure)
    gap = max(4.0, min(width, height) * 0.005)
    adjacency = build_path_adjacency(paths, gap=gap)

    events: list[ReplayEvent] = []
    session_index = 1
    unit_path_counts: dict[str, int] = {}
    structure_guide_path_counts: dict[str, dict[str, int]] = {}
    structured_unit_count = 0

    for uid in unit_order:
        unit = unit_map[uid]
        unit_paths = by_unit.get(uid, [])
        unit_path_counts[uid] = len(unit_paths)
        if not unit_paths:
            continue
        root = _root_px(unit, width, height)
        unit_guides = structure_by_unit.get(uid, [])
        session_groups: list[dict[str, object]] = []
        if unit_guides:
            raw_groups, session_index, guide_counts = _compile_structured_sessions(
                unit, unit_paths, unit_guides, width, height, session_index
            )
            # Second-pass semantics are used as a real hierarchy, not just a ranking score:
            # first establish the owned unit's structural scaffold, then locally complete each
            # focus group with attachments/details/accent. This prevents flowers/leaves near a
            # trunk from appearing before the supporting branches elsewhere in the same unit.
            scaffold_events: list[ReplayEvent] = []
            local_groups: list[dict[str, object]] = []
            for group in raw_groups:
                gevents = group["events"]
                assert isinstance(gevents, list)
                structural = [e for e in gevents if isinstance(e, ReplayEvent) and e.role in {"backbone", "structure"}]
                local = [e for e in gevents if isinstance(e, ReplayEvent) and e.role not in {"backbone", "structure"}]
                scaffold_events.extend(structural)
                local_groups.append(
                    {
                        "session_id": group["session_id"],
                        "focus_group": group.get("focus_group", ""),
                        "events": local,
                        "paths": group.get("paths", []),
                        "accepts_accent": True,
                    }
                )
            session_groups = []
            if scaffold_events:
                scaffold_id = f"{raw_groups[0]['session_id']}_scaffold" if raw_groups else f"S{session_index:04d}_scaffold"
                scaffold_events = [e.model_copy(update={"session_id": scaffold_id}) for e in scaffold_events]
                session_groups.append(
                    {
                        "session_id": scaffold_id,
                        "focus_group": "structural_scaffold",
                        "events": scaffold_events,
                        "paths": [],
                        "accepts_accent": False,
                    }
                )
            session_groups.extend(local_groups)
            structure_guide_path_counts[uid] = guide_counts
            structured_unit_count += 1
        else:
            ids = [p.id for p in unit_paths]
            comps = _connected_components(ids, adjacency)
            comps = _merge_tiny_components(comps, path_map, max_components=10 if unit.subdivide else 1)

            def comp_key(comp: list[str]) -> float:
                center = np.mean([path_map[p].centroid for p in comp], axis=0)
                return float(np.linalg.norm(center - root))

            comps.sort(key=comp_key)
            for comp in comps:
                session_id = f"S{session_index:04d}"
                session_index += 1
                comp_paths = [path_map[p] for p in comp]
                lengths = np.array([p.length for p in comp_paths], dtype=np.float32)
                diag = math.hypot(width, height)

                ranked: list[tuple[int, float, float, PathRecord, str]] = []
                for p in comp_paths:
                    root_dist = float(np.linalg.norm(np.asarray(p.centroid) - root) / max(diag, 1.0))
                    role = _role_for_path(p, lengths, unit.grammar, root_dist)
                    phase = {"backbone": 0, "structure": 1, "attachment": 2, "detail": 3}[role]
                    ranked.append((phase, root_dist, _direction_key(p, unit, width, height), p, role))
                ranked.sort(key=lambda item: (item[0], item[1], item[2], -item[3].length))

                pen = root.copy()
                remaining = list(ranked)
                ordered: list[tuple[PathRecord, str]] = []
                while remaining:
                    min_phase = min(item[0] for item in remaining)
                    candidates = [item for item in remaining if item[0] == min_phase]
                    best = min(
                        candidates,
                        key=lambda item: min(
                            np.linalg.norm(np.asarray(item[3].points[0]) - pen),
                            np.linalg.norm(np.asarray(item[3].points[-1]) - pen),
                        ),
                    )
                    remaining.remove(best)
                    p, role = best[3], best[4]
                    oriented = _orient_path(p.points, pen)
                    ordered.append((p.model_copy(update={"points": oriented}), role))
                    pen = np.asarray(oriented[-1], dtype=np.float32)

                group_events: list[ReplayEvent] = []
                for p, role in ordered:
                    group_events.append(
                        ReplayEvent(
                            id="E00000",
                            event_type="stroke",
                            unit_id=uid,
                            session_id=session_id,
                            path_id=p.id,
                            points=p.points,
                            role=role,  # type: ignore[arg-type]
                            frame_weight=max(1.0, p.length),
                        )
                    )
                session_groups.append(
                    {
                        "session_id": session_id,
                        "events": group_events,
                        "paths": comp_paths,
                    }
                )

        # Accent is attached to the closest *owned line structure* inside the same semantic unit.
        # It appears only after that local session's lines, preventing orphan pastel blobs.
        for accent in accents_by_unit.get(uid, []):
            if not session_groups:
                continue
            nearest = min(session_groups, key=lambda group: _session_distance_to_accent(group, accent))
            nearest_events = nearest["events"]
            assert isinstance(nearest_events, list)
            nearest_events.append(
                ReplayEvent(
                    id="E00000",
                    event_type="accent",
                    unit_id=uid,
                    session_id=str(nearest["session_id"]),
                    accent_id=accent.id,
                    role="accent",
                    frame_weight=max(8.0, math.sqrt(accent.area) * 2.0),
                )
            )

        for group in session_groups:
            group_events = group["events"]
            assert isinstance(group_events, list)
            events.extend(group_events)

    events = [event.model_copy(update={"id": f"E{i:05d}"}) for i, event in enumerate(events, start=1)]
    return ReplayPlan(
        width=width,
        height=height,
        source_path="assets/source.png",
        paper_path="assets/paper.png",
        foreground_mask_path="assets/foreground_strength.png",
        accent_records=accents,
        events=events,
        unit_order=unit_order,
        metadata={
            "path_count": len(paths),
            "grounded_path_count": len(paths) - len(unresolved_paths),
            "unresolved_path_count": len(unresolved_paths),
            "unresolved_path_ids": unresolved_paths,
            "accent_count": len(accents),
            "unresolved_accent_count": len(unresolved_accents),
            "unresolved_accent_ids": unresolved_accents,
            "event_count": len(events),
            "unit_count": len(scene.units),
            "unit_path_counts": unit_path_counts,
            "ownership_methods": dict(Counter(str(v["method"]) for v in ownership_diag.values())),
            "strategy": scene.strategy,
            "semantic_grounding": "visual_token_or_indexed_unit_map_no_bbox_fallback",
            "structure_plan_used": structure is not None,
            "structured_unit_count": structured_unit_count,
            "structure_guide_path_counts": structure_guide_path_counts,
            "intra_unit_planning": "ai_structure_guides_then_geometry" if structure is not None else "geometry_fallback",
            "unit_order_mode": "manual_override" if unit_order_override is not None else "ai_topological",
            "dependency_violations": dependency_violations(scene, unit_order),
        },
    )
