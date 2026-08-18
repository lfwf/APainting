# V4

- Replaced the static browser player with APainting Studio (FastAPI + local web UI).
- Added drag-and-drop Drawing Unit order editing.
- Added `playback_settings.json` as an explicit manual macro-order override.
- The compiler now supports a complete `unit_order_override`; no semantic ownership changes.
- Added AI-dependency reversal warnings instead of silently preventing manual staging.
- Added automatic unit-order history snapshots and restore.
- Added play/pause, seek, playback speed, and loop controls.
- Added 720p quick-preview regeneration after reordering.
- Added 1080p and source-resolution MP4 export endpoints.
