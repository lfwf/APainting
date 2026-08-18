from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .pipeline import ai_plan, ai_structure, compile_plan, prepare, render


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


if __name__ == "__main__":
    main()
