from __future__ import annotations

import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .image_ops import load_rgb, resample_polyline, save_rgb
from .schemas import ReplayPlan


def _load_mask(path: Path) -> np.ndarray:
    value = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if value is None:
        raise FileNotFoundError(path)
    return value


def _blend_from_source(canvas: np.ndarray, source: np.ndarray, alpha: np.ndarray) -> None:
    a = (alpha.astype(np.float32) / 255.0)[..., None]
    canvas[:] = np.clip(canvas.astype(np.float32) * (1.0 - a) + source.astype(np.float32) * a, 0, 255).astype(np.uint8)


def _write_frame(writer: cv2.VideoWriter, rgb: np.ndarray, scale: float) -> None:
    frame = rgb
    if scale != 1.0:
        frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))


def render_video(
    run_dir: Path,
    plan: ReplayPlan,
    output_path: Path,
    fps: int = 30,
    duration: float = 18.0,
    max_height: int = 1080,
    final_hold: float = 1.0,
    write_auxiliary: bool = True,
) -> dict[str, float | int | str]:
    source = load_rgb(run_dir / plan.source_path)
    paper = load_rgb(run_dir / plan.paper_path)
    strength = _load_mask(run_dir / plan.foreground_mask_path)
    h, w = source.shape[:2]
    if (w, h) != (plan.width, plan.height):
        raise ValueError("plan dimensions do not match source")

    scale = 1.0 if max_height <= 0 else min(1.0, max_height / h)
    out_size = (max(2, int(round(w * scale))), max(2, int(round(h * scale))))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        out_size,
    )
    if not writer.isOpened():
        raise RuntimeError("could not open MP4 writer; install an OpenCV build with MP4 support")

    canvas = paper.copy()
    total_frames = max(1, int(duration * fps))
    total_weight = sum(e.frame_weight for e in plan.events) or 1.0
    frames_written = 0
    accent_map = {a.id: a for a in plan.accent_records}
    snapshots: dict[int, np.ndarray] = {}
    snapshot_targets = {20, 40, 60, 80, 100}

    def maybe_snapshot() -> None:
        progress = int(round(frames_written / max(total_frames, 1) * 100))
        for target in sorted(snapshot_targets):
            if progress >= target and target not in snapshots:
                snapshots[target] = canvas.copy()

    carry = 0.0
    for event in plan.events:
        exact_frames = total_frames * event.frame_weight / total_weight
        event_frames = int(exact_frames)
        carry += exact_frames - event_frames
        if carry >= 1.0:
            event_frames += 1
            carry -= 1.0

        if event.event_type == "stroke":
            points = resample_polyline(event.points, spacing=1.2)
            if len(points) < 2:
                continue
            arr = np.asarray(points, dtype=np.int32)
            margin = 7
            x0 = max(0, int(arr[:, 0].min()) - margin)
            y0 = max(0, int(arr[:, 1].min()) - margin)
            x1 = min(w - 1, int(arr[:, 0].max()) + margin)
            y1 = min(h - 1, int(arr[:, 1].max()) + margin)
            local_points = [(x - x0, y - y0) for x, y in points]
            cumulative = np.zeros((y1 - y0 + 1, x1 - x0 + 1), dtype=np.uint8)
            canvas_roi = canvas[y0 : y1 + 1, x0 : x1 + 1]
            source_roi = source[y0 : y1 + 1, x0 : x1 + 1]
            strength_roi = strength[y0 : y1 + 1, x0 : x1 + 1]
            if event_frames == 0:
                pts = np.array(local_points, dtype=np.int32).reshape(-1, 1, 2)
                cv2.polylines(cumulative, [pts], False, 255, thickness=5, lineType=cv2.LINE_AA)
                alpha = cv2.GaussianBlur(cumulative, (0, 0), 0.65)
                alpha = cv2.multiply(alpha, strength_roi, scale=1 / 255.0)
                _blend_from_source(canvas_roi, source_roi, alpha)
                continue
            previous_count = 1
            for frame_idx in range(event_frames):
                count = max(2, int(round((frame_idx + 1) / event_frames * len(local_points))))
                segment = np.array(local_points[previous_count - 1 : count], dtype=np.int32).reshape(-1, 1, 2)
                if len(segment) >= 2:
                    cv2.polylines(cumulative, [segment], False, 255, thickness=5, lineType=cv2.LINE_AA)
                else:
                    cv2.circle(cumulative, tuple(segment[0, 0]), 2, 255, -1, cv2.LINE_AA)
                previous_count = count
                alpha = cv2.GaussianBlur(cumulative, (0, 0), 0.65)
                alpha = cv2.multiply(alpha, strength_roi, scale=1 / 255.0)
                _blend_from_source(canvas_roi, source_roi, alpha)
                _write_frame(writer, canvas, scale)
                frames_written += 1
                maybe_snapshot()
        else:
            if event.accent_id is None:
                continue
            record = accent_map[event.accent_id]
            x0, y0, x1, y1 = record.bbox
            local = _load_mask(run_dir / record.mask_path)
            ys, xs = np.where(local > 0)
            if len(xs) == 0:
                continue
            seed_x = float(xs.mean())
            seed_y = float(ys.mean())
            dist = np.sqrt((xs - seed_x) ** 2 + (ys - seed_y) ** 2)
            max_dist = float(dist.max()) or 1.0
            canvas_roi = canvas[y0 : y1 + 1, x0 : x1 + 1]
            source_roi = source[y0 : y1 + 1, x0 : x1 + 1]
            if event_frames == 0:
                _blend_from_source(canvas_roi, source_roi, local)
                continue
            for frame_idx in range(event_frames):
                threshold = (frame_idx + 1) / event_frames * max_dist
                partial = np.zeros_like(local, dtype=np.uint8)
                partial[ys[dist <= threshold], xs[dist <= threshold]] = 255
                partial = cv2.GaussianBlur(partial, (0, 0), 0.75)
                _blend_from_source(canvas_roi, source_roi, partial)
                _write_frame(writer, canvas, scale)
                frames_written += 1
                maybe_snapshot()

    # Hold the final program state. We deliberately do not reveal arbitrary global residual pixels.
    for _ in range(max(1, int(final_hold * fps))):
        _write_frame(writer, canvas, scale)
        frames_written += 1
    snapshots[100] = canvas.copy()
    writer.release()

    coverage = float(np.mean(np.linalg.norm(canvas.astype(np.float32) - paper.astype(np.float32), axis=2) > 2.5))
    source_foreground = float(np.mean(strength > 20))
    report: dict[str, float | int | str] = {
        "frames": frames_written,
        "fps": fps,
        "duration_seconds": frames_written / fps,
        "rendered_nonpaper_ratio": coverage,
        "source_foreground_ratio": source_foreground,
        "event_count": len(plan.events),
        "width": out_size[0],
        "height": out_size[1],
        "output": str(output_path.name),
    }
    if write_auxiliary:
        save_rgb(run_dir / "outputs" / "final_program_frame.png", canvas)
        _make_contact_sheet(run_dir, snapshots)
        (run_dir / "outputs" / "render_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    else:
        sidecar = output_path.with_suffix(".json")
        sidecar.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _make_contact_sheet(run_dir: Path, snapshots: dict[int, np.ndarray]) -> None:
    if not snapshots:
        return
    ordered = [(p, snapshots[p]) for p in sorted(snapshots)]
    thumbs = []
    for percent, image in ordered:
        h, w = image.shape[:2]
        target_h = 320
        target_w = int(w * target_h / h)
        thumb = Image.fromarray(image).resize((target_w, target_h))
        tile = Image.new("RGB", (target_w, target_h + 30), "white")
        tile.paste(thumb, (0, 30))
        draw = ImageDraw.Draw(tile)
        draw.text((8, 8), f"{percent}%", fill="black", font=ImageFont.load_default())
        thumbs.append(tile)
    sheet = Image.new("RGB", (sum(t.width for t in thumbs), max(t.height for t in thumbs)), "white")
    x = 0
    for tile in thumbs:
        sheet.paste(tile, (x, 0))
        x += tile.width
    out = run_dir / "outputs" / "contact_sheet.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
