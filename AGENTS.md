# APainting repository instructions

## Fast execution mode for attached-image replay tasks

When the user attaches an image and asks to generate/load an APainting replay, this is an **execution task using the existing application**, not a request to design or implement software.

For that task:

- Read `CODEX_IMAGE_TASK.md` and execute it directly.
- Do **not** create brainstorming documents, design specs, implementation plans, plan-review documents, Git branches, or worktrees.
- Do **not** ask the user to approve the macro-unit count/order before execution. Choose a reasonable plan, validate it, and continue.
- Do not stop after `prepare`, Pass 1, or Pass 2. Continue through `finalize` until a playable preview and 1s/3s/5s evidence exist, unless an actual command/data error blocks progress.
- Prefer the deterministic stage checks (`apainting validate`) over prose review.
- Default Pass 1 grounding to `token_ids`; only use indexed `unit_map.png` when the visual token representation genuinely cannot express ownership. Never hand-author broad bbox/polygon/corridor approximations merely because they are easier to code.
- When a validation stage fails, repair only that stage and rerun it. Do not redesign the architecture.

The user can paste the exact trigger prompt from `CODEX_ONE_SHOT_PROMPT.txt`.

## Core architecture contract

- The target distribution is fixed: warm-paper botanical single-line illustration with sparse pastel accents.
- Preserve process fidelity: clean paper at the start, no future content leakage, and local details/colors should appear near their owning session.
- Never solve quality problems by adding a global end-of-video reveal.
- AI should plan semantic units and relationships; deterministic code should trace paths and execute events.
- Keep early grouping reversible. Avoid irreversible unions based on one weak geometric contact.
- Prefer simple episode-level scheduling over a complex global optimizer until unit ownership and roots are correct.
- After renderer changes, inspect contact sheets and at least three intermediate video times; final-frame-only tests are insufficient.
- Do not add one-off rules tied to a specific filename, coordinate, flower, tree, or sample image.
- Use two AI passes: pass 1 owns macro Drawing Units; pass 2 infers hierarchy/progress only inside those already-owned Units.
- `bbox_hint` may be used for crops/debug but must never decide path ownership.
- Structure guides must not reassign paths between units. If macro ownership is wrong, fix semantic token/mask ownership; if internal order is wrong, fix the StructurePlan.

## Playback editing contract

- `playback_settings.json.unit_order` is a presentation-level macro ordering override.
- Never use a macro order edit to change `token_ids`, `unit_map`, ownership, or `structure_plan.json`.
- Manual order may intentionally reverse an AI dependency suggestion; report the reversal, do not silently undo the user's order.
