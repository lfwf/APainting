# APainting Codex MVP v5

A two-pass AI-assisted drawing compiler specialized for elegant botanical single-line stationery illustrations.


## Recommended Codex-native workflow (V5)

For the common case where you attach an image directly to Codex and want Codex itself to use its vision, do **not** ask it to design a solution first. Paste `CODEX_ONE_SHOT_PROMPT.txt` together with the image. The repository instructions route the task through an existing deterministic runbook.

```bash
apainting codex-start input.png --out runs/latest
# Codex reads runs/latest/CODEX_RUNBOOK.md and writes scene_plan.json
apainting validate runs/latest --stage pass1
# Codex writes structure_plan.json using analysis/unit_views/*.png
apainting validate runs/latest --stage pass2
apainting finalize runs/latest --duration 18 --max-height 1080
apainting serve runs/latest --port 8000
```

The key change is that Pass 1 defaults to **Visual Token ownership**, not manually painted semantic polygons. Validation tells Codex exactly what remains unresolved, so it fixes only that layer instead of entering a new design/review cycle.

Useful commands:

```bash
apainting status runs/latest
apainting inspect runs/latest --times 1 3 5
apainting validate runs/latest --stage final
```

See `CODEX_IMAGE_TASK.md`, `examples/STREAM_EXAMPLE.md`, and `examples/MOUNTAIN_EXAMPLE.md`.

## Architecture

```text
Static image
  ↓
Geometry extraction
  ↓
Visual Token Atlas
  ↓
AI pass 1: Drawing Unit semantics + ownership
  ↓
scene_plan.json
  ↓
AI pass 2: intra-unit hierarchy + progress guides
  ↓
structure_plan.json
  ↓
Deterministic geometry compiler
  ↓
structural scaffold → local completion → local accent
  ↓
source-sampled replay
```

### Pass 1: semantic ownership

`scene_plan.json` defines Drawing Units and grounds them using either:

- `token_ids`, or
- an indexed `unit_map.png` + `mask_value`.

`bbox_hint` is diagnostic/cropping metadata only. It is never used by the compiler to decide ownership.

### Pass 2: structure inside an already-owned Unit

`structure_plan.json` contains coarse normalized polyline guides. A guide has:

- `role`: `backbone`, `primary_structure`, `secondary_structure`, `terminal`, `detail`;
- `points`: approximate normalized-1000 polyline points;
- `focus_group`: local completion episode;
- `order`;
- `progress_start` / `progress_end`;
- `influence_radius`.

The geometry compiler snaps real paths to these guides. A StructurePlan **cannot move a path between macro Units**.

## Install

```bash
python -m pip install -e .
```

FFmpeg should be available on PATH for MP4 rendering.

## Codex/manual workflow

```bash
apainting prepare input.png --out runs/demo
```

Inspect:

- `analysis/source_grid.png`
- `analysis/visual_token_atlas.png`
- `analysis/token_tiles/`

Create or verify `scene_plan.json`. Then create `structure_plan.json` using the second visual pass. Finally:

```bash
apainting compile runs/demo
apainting render runs/demo --duration 18
```

Open `runs/demo/outputs/index.html` or the generated `replay.mp4`.

## API-assisted two-pass workflow

Set an OpenAI API key and model, then:

```bash
export OPENAI_API_KEY=...
export APAINTING_MODEL=gpt-5.6

apainting prepare input.png --out runs/demo
apainting ai-plan runs/demo
apainting ai-structure runs/demo
apainting compile runs/demo
apainting render runs/demo --duration 18
```

Or:

```bash
apainting auto input.png --out runs/demo --duration 18
```

## Validation artifacts

Compilation can generate:

- `analysis/unit_map_preview.png`
- `analysis/uncertain_paths.png`
- `analysis/structure_guides_overlay.png`
- `replay_plan.json`

Rendering generates:

- `outputs/replay.mp4`
- `outputs/contact_sheet.png`
- `outputs/final_program_frame.png`
- `outputs/index.html`

For acceptance, inspect at minimum 1s / 3s / 5s and unit-switch frames. The target is process fidelity: clean future paper, semantic ownership, supporting structure before terminal detail, local accent after local line structure, and low unnecessary revisit.

## V4 Web Studio: edit macro Drawing Unit order

V4 adds a local FastAPI editor. The AI-generated semantic ownership and V3 intra-unit
structure remain unchanged; the user may only reorder whole Drawing Units.

```bash
apainting serve runs/demo --port 8000
```

Open `http://127.0.0.1:8000/`.

The Studio includes:

- play / pause;
- seek bar and current / total time;
- 0.25x–2x playback speed and loop;
- drag-and-drop macro Drawing Unit order;
- one-click reset to the AI/topological order;
- automatic order-history snapshots and restore;
- 720p quick preview after an order edit;
- 1080p or source-resolution MP4 export.

Manual order is stored in `playback_settings.json`. It is an explicit override of the AI
macro order. The editor warns when the manual order reverses an AI dependency suggestion,
but does not silently block the user's choice. Macro ownership and the V3 structure plan
are never changed by this operation.
