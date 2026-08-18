# APainting Codex MVP v3

## Core change

v3 adds a true second visual pass after macro Drawing Unit ownership is frozen.

```text
Image
→ AI/Codex macro Unit ownership (mask/token IDs)
→ AI/Codex intra-unit StructurePlan
→ geometry grounding to real paths
→ structural scaffold
→ focus-group local completion
→ local accent
→ replay
```

The second pass outputs coarse normalized polyline guides such as:

- backbone / trunk / river spine / mountain silhouette
- primary structure
- secondary structure
- terminal flower/leaf groups
- progress along each guide
- focus_group and local order

These guides can never reassign a path to another macro Unit. They affect only the order of paths that are already semantically owned.

## Why this matters

v2 solved the large error class caused by bbox ownership. v3 targets the next problem: a correct Unit could still be drawn internally as disconnected fragments. The compiler now separates:

1. structural scaffold inside a Unit;
2. local completion of each focus group;
3. accent only after its local supporting structure.

## New command

```bash
apainting ai-structure RUN_DIR
```

This reads `scene_plan.json` and produces `structure_plan.json`.

The full automatic flow is now:

```bash
apainting prepare input.png --out runs/demo
apainting ai-plan runs/demo
apainting ai-structure runs/demo
apainting compile runs/demo
apainting render runs/demo --duration 18
```

`apainting auto` performs both AI passes before compilation.
