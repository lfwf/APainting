# V5 — Codex execution workflow

V5 does not change the semantic compiler architecture. It makes local Codex execution deterministic and much faster:

- added `CODEX_IMAGE_TASK.md` with a no-confirmation, no-spec execution runbook;
- added `CODEX_ONE_SHOT_PROMPT.txt` for the user to paste together with an attached image;
- added two worked examples for stream/botanical and mountain/river scenes;
- added `apainting codex-start` to prepare a run and generate a run-specific `CODEX_RUNBOOK.md`;
- added `apainting validate --stage pass1/pass2/...` with hard stage assertions;
- Pass-1 validation writes `analysis/pass1_unassigned_tokens.png` and `analysis/unit_views/*.png`;
- added `apainting finalize` to validate → compile → render → extract 1s/3s/5s in one command;
- added `apainting inspect` and `apainting status`;
- emphasized token ownership as the default Codex-native grounding interface, avoiding manually authored semantic corridors.
