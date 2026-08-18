from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from skimage.morphology import skeletonize


def load_rgb(path: Path) -> np.ndarray:
    image = Image.open(path).convert("RGB")
    return np.asarray(image)


def save_rgb(path: Path, rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), mode="RGB").save(path)


def save_mask(path: Path, mask: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((mask.astype(np.uint8) * 255), mode="L").save(path)


def estimate_border_color(rgb: np.ndarray, border_fraction: float = 0.05) -> np.ndarray:
    h, w = rgb.shape[:2]
    b = max(2, int(min(h, w) * border_fraction))
    samples = np.concatenate(
        [
            rgb[:b].reshape(-1, 3),
            rgb[-b:].reshape(-1, 3),
            rgb[:, :b].reshape(-1, 3),
            rgb[:, -b:].reshape(-1, 3),
        ],
        axis=0,
    )
    return np.median(samples, axis=0)



def _remove_small_components(mask: np.ndarray, min_area: int) -> np.ndarray:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = np.zeros_like(mask, dtype=bool)
    for component_id in range(1, count):
        if stats[component_id, cv2.CC_STAT_AREA] >= min_area:
            keep |= labels == component_id
    return keep

def extract_layers(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return line mask, accent mask, and a clean synthetic paper background.

    The thresholds intentionally target the fixed input distribution: warm paper,
    thin dark lines, and sparse low-saturation pastel accents.
    """
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    border = estimate_border_color(rgb).astype(np.float32)
    border_lab = cv2.cvtColor(border.reshape(1, 1, 3).astype(np.uint8), cv2.COLOR_RGB2LAB)[0, 0].astype(np.float32)

    local_bg = cv2.GaussianBlur(gray, (0, 0), sigmaX=5.0, sigmaY=5.0)
    dark_delta = local_bg.astype(np.int16) - gray.astype(np.int16)
    global_dark = border.mean() - gray.astype(np.float32)

    line = (dark_delta > 5) & (global_dark > 12)
    line |= gray < 185
    line = cv2.morphologyEx(line.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)) > 0
    line = _remove_small_components(line, min_area=6)

    ab_delta = np.sqrt((lab[..., 1] - border_lab[1]) ** 2 + (lab[..., 2] - border_lab[2]) ** 2)
    rgb_delta = np.linalg.norm(rgb.astype(np.float32) - border, axis=2)
    accent = (ab_delta > 5.0) & (rgb_delta > 8.0) & (gray > 115)
    accent &= ~cv2.dilate(line.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    accent = cv2.morphologyEx(accent.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)) > 0
    accent = cv2.morphologyEx(accent.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)) > 0
    accent = _remove_small_components(accent, min_area=8)

    paper = synthesize_paper(rgb, line | accent)
    return line.astype(bool), accent.astype(bool), paper


def synthesize_paper(rgb: np.ndarray, foreground: np.ndarray) -> np.ndarray:
    """Build a future-content-free warm paper texture.

    It uses border color plus multi-scale noise instead of inpainting the artwork,
    so hidden strokes cannot leak into early frames.
    """
    h, w = rgb.shape[:2]
    base = estimate_border_color(rgb).astype(np.float32)
    rng = np.random.default_rng(20260818)
    fine = rng.normal(0.0, 1.4, size=(h, w)).astype(np.float32)
    coarse = cv2.GaussianBlur(rng.normal(0.0, 1.0, size=(h, w)).astype(np.float32), (0, 0), 12.0)
    texture = fine * 0.45 + coarse * 1.6
    paper = np.empty((h, w, 3), dtype=np.float32)
    for c in range(3):
        paper[..., c] = base[c] + texture
    # Keep broad illumination from the source, while suppressing all drawing detail.
    source_low = cv2.GaussianBlur(rgb.astype(np.float32), (0, 0), 40.0)
    low_mean = source_low.reshape(-1, 3).mean(axis=0)
    illumination = np.mean(source_low - low_mean, axis=2)
    illumination = np.clip(illumination, -3.0, 3.0)
    paper += illumination[..., None] * 0.35
    return np.clip(paper, 0, 255).astype(np.uint8)


def make_grid_overlay(rgb: np.ndarray, step: int = 100) -> np.ndarray:
    image = Image.fromarray(rgb).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = image.size
    font = ImageFont.load_default()
    for n in range(0, 1001, step):
        x = round(n / 1000 * (w - 1))
        y = round(n / 1000 * (h - 1))
        draw.line([(x, 0), (x, h)], fill=(60, 90, 150, 70), width=1)
        draw.line([(0, y), (w, y)], fill=(60, 90, 150, 70), width=1)
        if n < 1000:
            draw.text((x + 2, 2), str(n), fill=(40, 60, 100, 180), font=font)
            draw.text((2, y + 2), str(n), fill=(40, 60, 100, 180), font=font)
    return np.asarray(Image.alpha_composite(image, overlay).convert("RGB"))


def skeleton_from_mask(line_mask: np.ndarray) -> np.ndarray:
    return skeletonize(line_mask).astype(bool)


def foreground_strength(rgb: np.ndarray, paper: np.ndarray) -> np.ndarray:
    delta = np.linalg.norm(rgb.astype(np.float32) - paper.astype(np.float32), axis=2)
    strength = np.clip((delta - 2.0) / 18.0, 0.0, 1.0)
    return (strength * 255).astype(np.uint8)



def draw_component_atlas(line_mask: np.ndarray, max_labels: int = 120) -> np.ndarray:
    """Render coherent geometric supertokens for AI/Codex inspection.

    A light dilation joins antialiasing gaps without trying to declare semantic truth.
    """
    dilated = cv2.dilate(line_mask.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=1)
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(dilated, connectivity=8)
    h, w = line_mask.shape
    canvas = np.full((h, w, 3), 250, dtype=np.uint8)
    valid = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= 12]
    palette = _palette(max(len(valid), 1))
    font_scale = max(0.3, min(w, h) / 1800.0)
    for rank, component_id in enumerate(valid):
        color = palette[rank]
        component = labels == component_id
        # Restrict color to the original thin line mask so the atlas does not look like morphology blobs.
        canvas[component & line_mask] = color
        if rank < max_labels:
            cx, cy = centroids[component_id]
            cv2.putText(
                canvas,
                f"C{rank+1:03d}",
                (int(cx), int(cy)),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                (25, 25, 25),
                1,
                cv2.LINE_AA,
            )
    return canvas

def draw_atlas(rgb: np.ndarray, paths: list[dict], max_labels: int = 160) -> np.ndarray:
    h, w = rgb.shape[:2]
    canvas = np.full((h, w, 3), 250, dtype=np.uint8)
    palette = _palette(max(len(paths), 1))
    font_scale = max(0.3, min(w, h) / 1800.0)
    for i, path in enumerate(paths):
        pts = np.array(path["points"], dtype=np.int32).reshape(-1, 1, 2)
        color = tuple(int(v) for v in palette[i])
        if len(pts) >= 2:
            cv2.polylines(canvas, [pts], False, color, thickness=3, lineType=cv2.LINE_AA)
        elif len(pts) == 1:
            cv2.circle(canvas, tuple(pts[0, 0]), 2, color, -1, cv2.LINE_AA)
        if i < max_labels:
            cx, cy = path["centroid"]
            cv2.putText(
                canvas,
                path["id"],
                (int(cx), int(cy)),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                (20, 20, 20),
                1,
                cv2.LINE_AA,
            )
    return canvas


def _palette(n: int) -> np.ndarray:
    hsv = np.zeros((n, 1, 3), dtype=np.uint8)
    for i in range(n):
        hsv[i, 0] = ((i * 47) % 180, 190, 230)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)[:, 0, :]


def path_length(points: list[tuple[int, int]]) -> float:
    if len(points) < 2:
        return 0.0
    arr = np.asarray(points, dtype=np.float32)
    return float(np.linalg.norm(np.diff(arr, axis=0), axis=1).sum())


def resample_polyline(points: list[tuple[int, int]], spacing: float = 1.5) -> list[tuple[int, int]]:
    if len(points) < 2:
        return points
    pts = np.asarray(points, dtype=np.float32)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cumulative = np.concatenate([[0.0], np.cumsum(seg)])
    total = cumulative[-1]
    if total <= spacing:
        return [tuple(map(int, pts[0])), tuple(map(int, pts[-1]))]
    samples = np.arange(0.0, total + spacing, spacing)
    x = np.interp(samples, cumulative, pts[:, 0])
    y = np.interp(samples, cumulative, pts[:, 1])
    return [(int(round(a)), int(round(b))) for a, b in zip(x, y)]


def draw_token_atlas(rgb: np.ndarray, paths: list[dict], tokens: list[dict]) -> np.ndarray:
    """Render persistent visual-token IDs for AI/Codex grounding."""
    h, w = rgb.shape[:2]
    canvas = np.full((h, w, 3), 250, dtype=np.uint8)
    token_index = {t["id"]: i for i, t in enumerate(tokens)}
    palette = _palette(max(len(tokens), 1))
    path_by_id = {p["id"]: p for p in paths}
    font_scale = max(0.3, min(w, h) / 1800.0)
    for token in tokens:
        idx = token_index[token["id"]]
        color = tuple(int(v) for v in palette[idx])
        for pid in token["path_ids"]:
            path = path_by_id.get(pid)
            if not path:
                continue
            pts = np.array(path["points"], dtype=np.int32).reshape(-1, 1, 2)
            if len(pts) >= 2:
                cv2.polylines(canvas, [pts], False, color, thickness=3, lineType=cv2.LINE_AA)
            elif len(pts) == 1:
                cv2.circle(canvas, tuple(pts[0, 0]), 2, color, -1, cv2.LINE_AA)
        cx, cy = token["centroid"]
        cv2.putText(
            canvas,
            token["id"],
            (int(cx), int(cy)),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            (20, 20, 20),
            1,
            cv2.LINE_AA,
        )
    return canvas


def colorize_indexed_unit_map(unit_map: np.ndarray, values_to_labels: dict[int, str]) -> np.ndarray:
    """Create a human-inspection visualization of an indexed semantic unit map."""
    h, w = unit_map.shape
    out = np.full((h, w, 3), 247, dtype=np.uint8)
    values = sorted(values_to_labels)
    palette = _palette(max(len(values), 1))
    for i, value in enumerate(values):
        out[unit_map == value] = palette[i]
    return out
