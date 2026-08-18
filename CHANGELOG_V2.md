# v2 semantic-grounding change

## Removed

- BBox-based `assign_paths_to_units`.
- BBox-based `assign_accents_to_units`.
- Nearest-session-center accent binding.

## Added

- Persistent visual super-tokens (`C####`).
- Visual-token atlas and six zoom tiles.
- Indexed semantic `unit_map.png` interface.
- Token ownership interface in `ScenePlan`.
- Strict unresolved-path reporting instead of silent spatial fallback.
- Same-token propagation only after strong semantic agreement.
- Accent ownership from semantic unit map or already-owned line geometry.
- Accent-to-session binding using distance to the session's actual line geometry.
- Grounding diagnostics and `uncertain_paths.png`.

## Validation on the two supplied landscape images

Using visually authored semantic unit maps to stand in for Codex/AI segmentation:

- riverscape: 2751 / 2752 paths grounded; 0 unresolved accents.
- mountain: 2408 / 2415 paths grounded; 0 unresolved accents.

Visual checks at 1s / 3s / 5s show:

- the riverscape no longer shows isolated lower iris pastel blobs while only the top branch is being drawn;
- the mountain 1s frame no longer draws the left pine as part of the mountain unit;
- unit transitions remain deterministic and source-backed.

The next bottleneck is intra-unit Focus Session / topology quality, not macro bbox ownership.
