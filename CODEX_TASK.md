# Codex task: APainting two-pass compiler

For each new image:

1. Run `apainting prepare IMAGE --out RUN_DIR`.
2. Inspect the source image and Visual Token Atlas.
3. Produce/verify `scene_plan.json` with real Drawing Unit ownership. Never use bbox as ownership.
4. Run `apainting ai-structure RUN_DIR` when API mode is available, or author `structure_plan.json` from visual inspection.
5. In the second pass, keep macro ownership frozen. Add only coarse intra-unit guides:
   - backbone / trunk / main contour;
   - primary and secondary structures;
   - terminal flower/leaf/detail groups;
   - focus_group;
   - drawing progress.
6. Run `apainting compile RUN_DIR` and `apainting render RUN_DIR`.
7. Inspect 1s / 3s / 5s plus unit-switch frames. Reject versions with future-content leakage, orphan accent, unsupported terminal details, or large local revisits.

Do not repair a semantic error by changing nearest-bbox weights. If macro ownership is uncertain, surface the token for visual review. If macro ownership is correct but the replay is fragmented, fix `structure_plan.json` instead.

## V4 local editor

After a run has `scene_plan.json`, optional `structure_plan.json`, `replay_plan.json`, and a preview video:

```bash
apainting serve runs/demo --port 8000
```

Use the Studio to reorder **whole Drawing Units**. A user-edited order is authoritative for macro playback staging and is persisted in `playback_settings.json`. Do not rewrite semantic ownership or the structure plan merely because the user changes macro order.
