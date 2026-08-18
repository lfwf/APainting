from __future__ import annotations

from pathlib import Path

import apainting.renderer as renderer
from apainting.web_server import _preview_url
from apainting.web_ui import EDITOR_HTML


def test_webm_writer_uses_vp9_codec(monkeypatch, tmp_path: Path) -> None:
    calls: dict[str, object] = {}

    class FakeWriter:
        def isOpened(self) -> bool:
            return True

    def fake_fourcc(*letters: str) -> int:
        calls["fourcc"] = "".join(letters)
        return 123

    def fake_writer(path: str, fourcc: int, fps: int, size: tuple[int, int]) -> FakeWriter:
        calls.update(path=path, codec_value=fourcc, fps=fps, size=size)
        return FakeWriter()

    monkeypatch.setattr(renderer.cv2, "VideoWriter_fourcc", fake_fourcc)
    monkeypatch.setattr(renderer.cv2, "VideoWriter", fake_writer)

    writer = renderer._open_video_writer(tmp_path / "preview.webm", 24, (608, 1080))

    assert writer.isOpened()
    assert calls["fourcc"] == "VP90"
    assert calls["path"] == str(tmp_path / "preview.webm")


def test_project_prefers_browser_compatible_webm_preview(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (outputs / "replay.mp4").write_bytes(b"mp4")
    assert _preview_url(tmp_path) == "/outputs/replay.mp4"

    (outputs / "replay.webm").write_bytes(b"webm")
    assert _preview_url(tmp_path) == "/outputs/replay.webm"


def test_studio_uses_project_video_url_and_large_viewer() -> None:
    assert 'src="/outputs/replay.mp4"' not in EDITOR_HTML
    assert "project.video_url" in EDITOR_HTML
    assert 'id="fullscreenBtn"' in EDITOR_HTML
    assert "height:min(80vh,1100px)" in EDITOR_HTML
