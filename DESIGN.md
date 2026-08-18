# Design notes

## Why this is a compiler, not a historical-order detector

A finished raster image does not contain a unique time sequence. APainting therefore defines a repeatable house style for this fixed image distribution and compiles each image into a plausible program.

## Two supported AI modes

### Codex-in-the-loop

Codex sees the uploaded image plus generated grid/component atlases and writes `scene_plan.json`. This is useful during development and requires no separate inference call from the application.

### API automation

The same schema is produced by a vision-capable OpenAI model through the Responses API. This is the correct mode for a one-click product or batch pipeline.

## Compiler stages

```text
source image
  -> paper / dark line / pastel accent separation
  -> line skeleton and path tracing
  -> grid + component atlas
  -> AI ScenePlan (Drawing Units, roots, flow, dependencies)
  -> path-to-unit grounding
  -> connected local Focus Sessions
  -> local grammar and path orientation
  -> episode-level schedule
  -> source-sampled brush deposition
  -> MP4 + browser player + contact sheet
```

## House drawing grammar

- `upper_branch`: entry/trunk -> dominant curve -> major forks -> minor forks -> leaves/flowers -> local accents.
- `flora_cluster`: root -> main stems/blades -> branches/leaves -> flowers -> local accents.
- `tree_cluster`: trunk -> major branches -> secondary branches/needles.
- `mountain_mass`: dominant silhouette -> overlapping ridges -> internal contour lines.
- `river`: far horizon/spine -> banks -> near flow lines/ripples.
- `stone_cluster`: far-to-near outer contours -> inner cracks.
- `water_lily_cluster`: support/central contour -> petals/pads -> local accents.

## Why local source sampling is used

The geometry determines when and where the brush moves, but pixels under the current local footprint are sampled from the source. This preserves thin antialiasing, pastel transparency, and the exact final style without globally revealing the hidden image.

## Next production milestones

1. Replace bbox-only grounding with AI-assisted component/token assignment.
2. Add local conflict review for crossing branches and ambiguous ownership.
3. Add amodal continuation proposals for visually interrupted stems.
4. Move browser playback from pre-rendered MP4 to event-driven Canvas/SVG for interactive editing.
5. Add a small human correction UI for unit membership, roots, and session splits.
