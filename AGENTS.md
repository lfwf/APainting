# APainting repository instructions

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
- Structure guides must not reassign paths between units. If macro ownership is wrong, fix the semantic mask/token ownership; if internal order is wrong, fix the StructurePlan.

## V4 editing contract

- `playback_settings.json.unit_order` is a presentation-level macro ordering override.
- Never use a macro order edit to change `token_ids`, `unit_map`, ownership, or `structure_plan.json`.
- Manual order may intentionally reverse an AI dependency suggestion; report the reversal, do not silently undo the user's order.
