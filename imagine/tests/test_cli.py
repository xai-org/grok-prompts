import json
from pathlib import Path

import pytest

from grok_imagine.cli import run
from grok_imagine.client import ImagineClient
from grok_imagine.errors import ImagineApiError
from support import API_KEY, FIXED, RecordingTransport, write_png


def test_edit_command_writes_paths(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    image = write_png(tmp_path / "portrait.png")
    http = RecordingTransport()
    client = ImagineClient(API_KEY, transport=http, clock=lambda: FIXED)
    code = run(
        [
            "edit",
            str(image),
            "--prompt",
            "Add a navy wool coat. Keep the same crop.",
            "--out",
            str(tmp_path / "out"),
            "--aspect-ratio",
            "3:2",
            "--resolution",
            "2k",
            "--count",
            "1",
        ],
        client=client,
    )

    assert code == 0
    payload = http.posts[0]["payload"]
    assert payload["aspect_ratio"] == "3:2"
    assert payload["resolution"] == "2k"
    assert payload["image"]["url"].startswith("data:image/png;base64,")
    captured = capsys.readouterr()
    assert captured.err == ""
    lines = captured.out.splitlines()
    assert lines[0].endswith(".png")
    assert lines[1].endswith(".json")
    assert API_KEY not in captured.out
    metadata = json.loads(Path(lines[1]).read_text(encoding="utf-8"))
    assert metadata["resolution"] == "2k"
    assert metadata["aspect_ratio"] == "3:2"


def test_generate_command_passes_refs(tmp_path: Path) -> None:
    ref = write_png(tmp_path / "face.png")
    http = RecordingTransport()
    client = ImagineClient(API_KEY, transport=http, clock=lambda: FIXED)
    code = run(
        [
            "generate",
            "--prompt",
            "Standing on a rainy street at night.",
            "--ref",
            str(ref),
            "--out",
            str(tmp_path / "out"),
            "--quality",
            "low",
            "--no-face-lock",
        ],
        client=client,
    )
    assert code == 0
    payload = http.posts[0]["payload"]
    assert http.posts[0]["url"].endswith("/images/edits")
    assert payload["quality"] == "low"
    assert payload["prompt"] == "Standing on a rainy street at night."
    assert len(payload["images"]) == 1


def test_missing_key_is_reported_without_a_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    image = write_png(tmp_path / "portrait.png")
    code = run(["edit", str(image), "--prompt", "Add a hat.", "--out", str(tmp_path / "out")])
    assert code == 1
    err = capsys.readouterr().err
    assert "XAI_API_KEY" in err
    assert "Bearer" not in err
    assert API_KEY not in err


def test_api_failure_returns_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    image = write_png(tmp_path / "portrait.png")
    http = RecordingTransport(error=ImagineApiError(429, f"slow down {API_KEY}"))
    client = ImagineClient(API_KEY, transport=http, clock=lambda: FIXED)
    code = run(
        ["edit", str(image), "--prompt", "Add a hat.", "--out", str(tmp_path / "out")],
        client=client,
    )
    assert code == 1
    err = capsys.readouterr().err
    assert "429" in err
    assert API_KEY not in err
    assert "[redacted]" in err


def test_help_exits_cleanly() -> None:
    with pytest.raises(SystemExit) as caught:
        run(["--help"])
    assert caught.value.code == 0
    with pytest.raises(SystemExit) as edit_help:
        run(["edit", "--help"])
    assert edit_help.value.code == 0
