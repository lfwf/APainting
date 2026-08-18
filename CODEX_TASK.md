# Codex task: APainting image-to-replay execution

For a normal attached-image replay request, **do not invent a new plan**. Use `CODEX_IMAGE_TASK.md` as the already-approved operational plan.

Fast path:

```bash
apainting codex-start IMAGE --out runs/latest
# Read runs/latest/CODEX_RUNBOOK.md
# Author scene_plan.json from source + Visual Token Atlas (token_ids preferred)
apainting validate runs/latest --stage pass1
# Author structure_plan.json from analysis/unit_views/*.png
apainting validate runs/latest --stage pass2
apainting finalize runs/latest --duration 18 --max-height 1080
apainting serve runs/latest --port 8000
```

Hard contracts:

- Pass 1 = macro Drawing Unit semantics + executable `token_ids`/unit map ownership.
- No bbox ownership fallback.
- Pass 1 target: >=95% weighted visual-token path-length coverage; unresolved crossing tokens may be reviewed locally.
- Pass 2 = hierarchy/progress only inside frozen Pass-1 units.
- Pass 2 must cover every `subdivide=true` unit.
- `finalize` must create playable video + `outputs/inspection_1_3_5.png`.
- Fix failed stages locally; do not restart with design/specification work.

See `examples/STREAM_EXAMPLE.md` and `examples/MOUNTAIN_EXAMPLE.md` for concrete reasoning patterns.
