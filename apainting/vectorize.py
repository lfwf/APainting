from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
from skimage.measure import label, regionprops

from .image_ops import path_length, resample_polyline
from .schemas import AccentRecord, PathRecord, VisualTokenRecord

_NEIGHBORS = [
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
]


def trace_skeleton(skeleton: np.ndarray, min_length: float = 5.0) -> list[PathRecord]:
    coords = set(map(tuple, np.argwhere(skeleton)))  # (y, x)
    if not coords:
        return []

    adjacency: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for y, x in coords:
        adjacency[(y, x)] = [
            (y + dy, x + dx)
            for dy, dx in _NEIGHBORS
            if (y + dy, x + dx) in coords
        ]

    nodes = {p for p, ns in adjacency.items() if len(ns) != 2}
    visited_edges: set[frozenset[tuple[int, int]]] = set()
    raw_paths: list[list[tuple[int, int]]] = []

    def walk(start: tuple[int, int], nxt: tuple[int, int]) -> list[tuple[int, int]]:
        path = [start, nxt]
        prev, cur = start, nxt
        visited_edges.add(frozenset((prev, cur)))
        while cur not in nodes:
            candidates = [p for p in adjacency[cur] if p != prev]
            if not candidates:
                break
            nxt2 = candidates[0]
            edge = frozenset((cur, nxt2))
            if edge in visited_edges:
                break
            path.append(nxt2)
            visited_edges.add(edge)
            prev, cur = cur, nxt2
        return path

    for node in sorted(nodes):
        for nxt in adjacency[node]:
            edge = frozenset((node, nxt))
            if edge not in visited_edges:
                raw_paths.append(walk(node, nxt))

    # Handle closed loops that have no degree != 2 node.
    for start in sorted(coords):
        for nxt in adjacency[start]:
            edge = frozenset((start, nxt))
            if edge in visited_edges:
                continue
            loop = [start, nxt]
            visited_edges.add(edge)
            prev, cur = start, nxt
            while True:
                candidates = [p for p in adjacency[cur] if p != prev]
                if not candidates:
                    break
                nxt2 = candidates[0]
                edge2 = frozenset((cur, nxt2))
                if edge2 in visited_edges:
                    break
                loop.append(nxt2)
                visited_edges.add(edge2)
                prev, cur = cur, nxt2
                if cur == start:
                    break
            raw_paths.append(loop)

    records: list[PathRecord] = []
    for raw in raw_paths:
        xy = np.array([(x, y) for y, x in raw], dtype=np.int32)
        if len(xy) < 2:
            continue
        length = path_length([tuple(p) for p in xy])
        if length < min_length:
            continue
        epsilon = max(0.6, min(2.5, length * 0.006))
        simplified = cv2.approxPolyDP(xy.reshape(-1, 1, 2), epsilon, False).reshape(-1, 2)
        points = [tuple(map(int, p)) for p in simplified]
        if len(points) < 2:
            points = [tuple(map(int, xy[0])), tuple(map(int, xy[-1]))]
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        records.append(
            PathRecord(
                id=f"P{len(records)+1:04d}",
                points=points,
                length=path_length(points),
                bbox=(min(xs), min(ys), max(xs), max(ys)),
                centroid=(float(np.mean(xs)), float(np.mean(ys))),
            )
        )
    return records


def build_visual_tokens(
    line_mask: np.ndarray,
    paths: list[PathRecord],
    dilation_px: int = 3,
    min_component_area: int = 10,
) -> tuple[list[PathRecord], list[VisualTokenRecord]]:
    """Attach each path to a visual super-token.

    A token is a locally connected line component after only a tiny dilation. It is NOT
    semantic truth; it is a visual RPC handle that Codex/AI can point at. Crucially,
    semantic ownership later comes from token IDs or an indexed unit map, never bbox.
    """
    kernel = np.ones((max(1, dilation_px), max(1, dilation_px)), np.uint8)
    dilated = cv2.dilate(line_mask.astype(np.uint8), kernel, iterations=1)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(dilated, connectivity=8)

    valid_components = [
        cid for cid in range(1, count) if stats[cid, cv2.CC_STAT_AREA] >= min_component_area
    ]
    component_to_token = {cid: f"C{rank+1:04d}" for rank, cid in enumerate(valid_components)}

    grouped: dict[str, list[PathRecord]] = defaultdict(list)
    updated: list[PathRecord] = []
    h, w = line_mask.shape

    for path in paths:
        samples = resample_polyline(path.points, spacing=1.0)
        votes: Counter[int] = Counter()
        for x, y in samples:
            if 0 <= x < w and 0 <= y < h:
                cid = int(labels[y, x])
                if cid in component_to_token:
                    votes[cid] += 1
        token_id: str | None = None
        if votes:
            cid, _ = votes.most_common(1)[0]
            token_id = component_to_token[cid]
        else:
            cx, cy = map(int, map(round, path.centroid))
            if 0 <= cx < w and 0 <= cy < h:
                cid = int(labels[cy, cx])
                token_id = component_to_token.get(cid)
        new_path = path.model_copy(update={"token_id": token_id})
        updated.append(new_path)
        if token_id is not None:
            grouped[token_id].append(new_path)

    tokens: list[VisualTokenRecord] = []
    for token_id in sorted(grouped):
        members = grouped[token_id]
        x0 = min(p.bbox[0] for p in members)
        y0 = min(p.bbox[1] for p in members)
        x1 = max(p.bbox[2] for p in members)
        y1 = max(p.bbox[3] for p in members)
        total = sum(p.length for p in members)
        weights = np.array([max(p.length, 1e-3) for p in members], dtype=np.float32)
        centers = np.array([p.centroid for p in members], dtype=np.float32)
        centroid = np.average(centers, axis=0, weights=weights)
        tokens.append(
            VisualTokenRecord(
                id=token_id,
                path_ids=[p.id for p in members],
                bbox=(x0, y0, x1, y1),
                centroid=(float(centroid[0]), float(centroid[1])),
                path_length=float(total),
            )
        )
    return updated, tokens


def extract_accent_components(
    accent_mask: np.ndarray,
    out_dir: Path,
    min_area: int = 8,
) -> list[AccentRecord]:
    out_dir.mkdir(parents=True, exist_ok=True)
    labeled = label(accent_mask, connectivity=2)
    records: list[AccentRecord] = []
    for region in regionprops(labeled):
        if region.area < min_area:
            continue
        y0, x0, y1, x1 = region.bbox
        mask = (labeled[y0:y1, x0:x1] == region.label).astype(np.uint8) * 255
        aid = f"A{len(records)+1:04d}"
        rel = Path("assets") / "accents" / f"{aid}.png"
        cv2.imwrite(str(out_dir / f"{aid}.png"), mask)
        records.append(
            AccentRecord(
                id=aid,
                mask_path=str(rel),
                bbox=(x0, y0, x1 - 1, y1 - 1),
                centroid=(float(region.centroid[1]), float(region.centroid[0])),
                area=int(region.area),
            )
        )
    return records


def build_path_adjacency(paths: list[PathRecord], gap: float) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    endpoints: dict[str, np.ndarray] = {
        p.id: np.array([p.points[0], p.points[-1]], dtype=np.float32) for p in paths
    }
    for i, a in enumerate(paths):
        ax0, ay0, ax1, ay1 = a.bbox
        for b in paths[i + 1 :]:
            bx0, by0, bx1, by1 = b.bbox
            if bx0 > ax1 + gap or ax0 > bx1 + gap or by0 > ay1 + gap or ay0 > by1 + gap:
                continue
            d = np.linalg.norm(endpoints[a.id][:, None, :] - endpoints[b.id][None, :, :], axis=2).min()
            if d <= gap:
                adjacency[a.id].add(b.id)
                adjacency[b.id].add(a.id)
    for p in paths:
        adjacency.setdefault(p.id, set())
    return adjacency
