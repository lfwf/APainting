from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .pipeline import ai_plan, ai_structure, compile_plan, prepare, render
from .codex_workflow import build_runbook, inspect_video, status, validate_stage


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="apainting", description="Codex-assisted botanical drawing replay compiler")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("prepare", help="Extract masks, paths, grid, and atlas")
    p.add_argument("image", type=Path)
    p.add_argument("--out", type=Path, required=True)

    p = sub.add_parser("ai-plan", help="Create scene_plan.json with the OpenAI Responses API")
    p.add_argument("run_dir", type=Path)
    p.add_argument("--model", default=os.environ.get("APAINTING_MODEL"))

    p = sub.add_parser("ai-structure", help="Second AI pass: infer intra-unit structural guides")
    p.add_argument("run_dir", type=Path)
    p.add_argument("--model", default=os.environ.get("APAINTING_MODEL"))

    p = sub.add_parser("compile", help="Compile semantic + optional structure plan into replay_plan.json")
    p.add_argument("run_dir", type=Path)

    p = sub.add_parser("render", help="Render replay_plan.json to MP4 and contact sheet")
    p.add_argument("run_dir", type=Path)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--duration", type=float, default=18.0)
    p.add_argument("--max-height", type=int, default=1080)

    p = sub.add_parser("auto", help="Prepare, AI-plan, compile, and render")
    p.add_argument("image", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--model", default=os.environ.get("APAINTING_MODEL"))
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--duration", type=float, default=18.0)
    p.add_argument("--max-height", type=int, default=1080)

    p = sub.add_parser("serve", help="Serve APainting Studio with editable macro-unit order")
    p.add_argument("run_dir", type=Path)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)

    p = sub.add_parser("codex-start", help="Prepare a run and generate a deterministic Codex execution runbook")
    p.add_argument("image", type=Path)
    p.add_argument("--out", type=Path, required=True)

    p = sub.add_parser("validate", help="Validate a Codex execution stage without redesigning the run")
    p.add_argument("run_dir", type=Path)
    p.add_argument("--stage", choices=["prepare", "pass1", "pass2", "compiled", "final", "all"], default="all")
    p.add_argument("--min-path-grounding", type=float, default=0.95)
    p.add_argument("--allow-missing-structure-units", action="store_true")

    p = sub.add_parser("inspect", help="Extract fixed intermediate frames from the preview video")
    p.add_argument("run_dir", type=Path)
    p.add_argument("--times", nargs="+", type=float, default=[1.0, 3.0, 5.0])
    p.add_argument("--video", default="replay.mp4")

    p = sub.add_parser("status", help="Show the current run stage and the next required artifact")
    p.add_argument("run_dir", type=Path)

    p = sub.add_parser("finalize", help="Validate, compile, render, and create 1/3/5s inspection evidence")
    p.add_argument("run_dir", type=Path)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--duration", type=float, default=18.0)
    p.add_argument("--max-height", type=int, default=1080)
    p.add_argument("--min-path-grounding", type=float, default=0.95)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    if args.command == "prepare":
        print(json.dumps(prepare(args.image, args.out), indent=2))
    elif args.command == "ai-plan":
        print(ai_plan(args.run_dir, args.model).model_dump_json(indent=2))
    elif args.command == "ai-structure":
        print(ai_structure(args.run_dir, args.model).model_dump_json(indent=2))
    elif args.command == "compile":
        print(compile_plan(args.run_dir).model_dump_json(indent=2))
    elif args.command == "render":
        print(json.dumps(render(args.run_dir, args.fps, args.duration, args.max_height), indent=2))
    elif args.command == "auto":
        prepare(args.image, args.out)
        ai_plan(args.out, args.model)
        ai_structure(args.out, args.model)
        compile_plan(args.out)
        print(json.dumps(render(args.out, args.fps, args.duration, args.max_height), indent=2))
    elif args.command == "serve":
        from .web_server import serve

        print(f"Serving APainting Studio at http://{args.host}:{args.port}/")
        serve(args.run_dir, host=args.host, port=args.port)
    elif args.command == "codex-start":
        manifest = prepare(args.image, args.out)
        runbook = build_runbook(args.out)
        print(json.dumps({"manifest": manifest, "runbook": str(runbook), "next": "Read CODEX_RUNBOOK.md and create scene_plan.json"}, ensure_ascii=False, indent=2))
    elif args.command == "validate":
        result = validate_stage(
            args.run_dir,
            stage=args.stage,
            min_path_grounding=args.min_path_grounding,
            require_structure_all=not args.allow_missing_structure_units,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok"):
            raise SystemExit(2)
    elif args.command == "inspect":
        print(json.dumps(inspect_video(args.run_dir, times=args.times, video_name=args.video), ensure_ascii=False, indent=2))
    elif args.command == "status":
        print(json.dumps(status(args.run_dir), ensure_ascii=False, indent=2))
    elif args.command == "finalize":
        pre = validate_stage(args.run_dir, stage="pass2", min_path_grounding=args.min_path_grounding, require_structure_all=True)
        if not pre.get("ok"):
            print(json.dumps(pre, ensure_ascii=False, indent=2))
            raise SystemExit(2)
        compile_plan(args.run_dir)
        compiled = validate_stage(args.run_dir, stage="compiled", min_path_grounding=args.min_path_grounding, require_structure_all=True)
        if not compiled.get("ok"):
            print(json.dumps(compiled, ensure_ascii=False, indent=2))
            raise SystemExit(2)
        render_report = render(args.run_dir, args.fps, args.duration, args.max_height)
        render(args.run_dir, args.fps, args.duration, args.max_height, output_name="replay.webm", auxiliary=False)
        inspection = inspect_video(args.run_dir, times=(1.0, 3.0, 5.0))
        final = validate_stage(args.run_dir, stage="final", min_path_grounding=args.min_path_grounding, require_structure_all=True)
        print(json.dumps({"validation": final, "render": render_report, "inspection": inspection}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
