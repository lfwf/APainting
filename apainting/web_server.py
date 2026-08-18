from __future__ import annotations

import json
import shutil
import subprocess
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .compiler import dependency_violations, topological_unit_order
from .pipeline import compile_plan, render
from .project_state import (
    list_order_history,
    load_history_snapshot,
    load_playback_settings,
    save_playback_settings,
    validate_unit_order,
)
from .schemas import ReplayPlan, ScenePlan
from .web_ui import write_web_ui


class OrderRequest(BaseModel):
    unit_order: list[str]
    render_preview: bool = True


class RestoreRequest(BaseModel):
    history_id: str
    render_preview: bool = True


class ExportRequest(BaseModel):
    profile: str = Field(default="1080p", pattern=r"^(1080p|source)$")
    fps: int = Field(default=30, ge=12, le=60)
    duration: float = Field(default=18.0, ge=2.0, le=120.0)


def _load_scene(run_dir: Path) -> ScenePlan:
    path = run_dir / "scene_plan.json"
    if not path.exists():
        raise FileNotFoundError("scene_plan.json is required")
    return ScenePlan.model_validate_json(path.read_text(encoding="utf-8"))


def _current_order(run_dir: Path, scene: ScenePlan) -> list[str]:
    ai_order = topological_unit_order(scene)
    settings = load_playback_settings(run_dir)
    raw = settings.get("unit_order")
    if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
        try:
            return validate_unit_order(list(raw), [u.id for u in scene.units])
        except ValueError:
            return ai_order
    replay_path = run_dir / "replay_plan.json"
    if replay_path.exists():
        try:
            replay = ReplayPlan.model_validate_json(replay_path.read_text(encoding="utf-8"))
            return validate_unit_order(replay.unit_order, [u.id for u in scene.units])
        except Exception:
            pass
    return ai_order


def _unit_shares(run_dir: Path) -> dict[str, float]:
    path = run_dir / "replay_plan.json"
    if not path.exists():
        return {}
    try:
        replay = ReplayPlan.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    totals: dict[str, float] = {}
    total = 0.0
    for e in replay.events:
        totals[e.unit_id] = totals.get(e.unit_id, 0.0) + float(e.frame_weight)
        total += float(e.frame_weight)
    if total <= 0:
        return {}
    return {k: v / total * 100.0 for k, v in totals.items()}


def create_app(run_dir: Path) -> FastAPI:
    run_dir = run_dir.resolve()
    write_web_ui(run_dir)
    app = FastAPI(title="APainting Studio", version="4")
    lock = threading.Lock()

    for name in ("outputs", "assets", "analysis"):
        path = run_dir / name
        path.mkdir(parents=True, exist_ok=True)
        app.mount(f"/{name}", StaticFiles(directory=str(path)), name=name)

    @app.get("/")
    def home() -> FileResponse:
        return FileResponse(run_dir / "outputs" / "index.html")

    @app.get("/api/project")
    def project() -> dict[str, object]:
        scene = _load_scene(run_dir)
        ai_order = topological_unit_order(scene)
        current = _current_order(run_dir, scene)
        shares = _unit_shares(run_dir)
        replay_path = run_dir / "replay_plan.json"
        event_count = 0
        if replay_path.exists():
            try:
                event_count = len(ReplayPlan.model_validate_json(replay_path.read_text(encoding="utf-8")).events)
            except Exception:
                pass
        return {
            "units": [
                {
                    "id": u.id,
                    "label": u.label,
                    "kind": u.kind.value,
                    "direction": u.direction.value,
                    "grammar": u.grammar.value,
                    "priority": u.priority,
                    "layer": u.layer,
                    "share_percent": shares.get(u.id),
                }
                for u in scene.units
            ],
            "ai_order": ai_order,
            "current_order": current,
            "dependencies": [d.model_dump() for d in scene.dependencies],
            "dependency_violations": dependency_violations(scene, current),
            "history": list_order_history(run_dir),
            "event_count": event_count,
            "video_url": "/outputs/replay.mp4",
        }

    @app.post("/api/unit-order")
    def update_order(req: OrderRequest) -> dict[str, object]:
        with lock:
            try:
                scene = _load_scene(run_dir)
                order = validate_unit_order(req.unit_order, [u.id for u in scene.units])
                save_playback_settings(run_dir, order, source="web_manual", archive=True)
                replay = compile_plan(run_dir)
                report = None
                if req.render_preview:
                    report = render(run_dir, fps=24, duration=12.0, max_height=720, output_name="replay.mp4")
                write_web_ui(run_dir)
                return {
                    "ok": True,
                    "unit_order": replay.unit_order,
                    "dependency_violations": dependency_violations(scene, replay.unit_order),
                    "render_report": report,
                }
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/history/restore")
    def restore_history(req: RestoreRequest) -> dict[str, object]:
        with lock:
            try:
                scene = _load_scene(run_dir)
                snapshot = load_history_snapshot(run_dir, req.history_id)
                raw = snapshot.get("unit_order")
                if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
                    raise ValueError("history snapshot has no valid unit_order")
                order = validate_unit_order(list(raw), [u.id for u in scene.units])
                save_playback_settings(
                    run_dir,
                    order,
                    source="history_restore",
                    note=f"restored {req.history_id}",
                    archive=True,
                )
                replay = compile_plan(run_dir)
                report = None
                if req.render_preview:
                    report = render(run_dir, fps=24, duration=12.0, max_height=720, output_name="replay.mp4")
                return {"ok": True, "unit_order": replay.unit_order, "render_report": report}
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/export")
    def export_video(req: ExportRequest) -> dict[str, object]:
        with lock:
            try:
                compile_plan(run_dir)
                if req.profile == "source":
                    max_height = 0
                    filename = "replay_source_hd.mp4"
                else:
                    max_height = 1080
                    filename = "replay_1080p.mp4"

                raw_name = f".{Path(filename).stem}_raw.mp4"
                report = render(
                    run_dir,
                    fps=req.fps,
                    duration=req.duration,
                    max_height=max_height,
                    output_name=raw_name,
                    auxiliary=False,
                )
                raw_path = run_dir / "outputs" / raw_name
                final_path = run_dir / "outputs" / filename
                ffmpeg = shutil.which("ffmpeg")
                if ffmpeg:
                    cmd = [
                        ffmpeg, "-y", "-loglevel", "error", "-i", str(raw_path),
                        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(final_path),
                    ]
                    subprocess.run(cmd, check=True)
                    raw_path.unlink(missing_ok=True)
                    raw_path.with_suffix(".json").unlink(missing_ok=True)
                    report["codec"] = "h264/libx264"
                    report["quality"] = "crf18"
                else:
                    raw_path.replace(final_path)
                    raw_path.with_suffix(".json").replace(final_path.with_suffix(".json"))
                    report["codec"] = "mp4v (ffmpeg unavailable)"
                report["output"] = filename
                final_path.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
                return {"ok": True, "filename": filename, "url": f"/outputs/{filename}", "report": report}
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


def serve(run_dir: Path, host: str = "127.0.0.1", port: int = 8000) -> None:
    import uvicorn

    app = create_app(run_dir)
    uvicorn.run(app, host=host, port=port, log_level="info")
