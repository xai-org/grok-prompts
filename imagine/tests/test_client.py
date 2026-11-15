import hashlib
import json
from pathlib import Path

import pytest

from grok_imagine.client import ImagineClient
from grok_imagine.constants import API_BASE
from grok_imagine.errors import ImagineApiError, ImagineError
from support import (
    API_KEY,
    FIXED,
    PNG_B64,
    PNG_BYTES,
    RecordingTransport,
    assert_key_stays_out,
    png_response,
    write_png,
)


def _client(tmp_path: Path, transport: RecordingTransport | None = None) -> tuple[ImagineClient, RecordingTransport]:
    http = transport or RecordingTransport()
    client = ImagineClient(API_KEY, transport=http, clock=lambda: FIXED)
    return client, http


def test_edit_posts_the_source_image_and_face_lock(tmp_path: Path) -> None:
    image = write_png(tmp_path / "portrait.png")
    client, http = _client(tmp_path)
    result = client.edit(
        image=image,
        prompt="Replace the background with a sunlit greenhouse.",
        out_dir=tmp_path / "out",
        aspect_ratio="3:4",
        resolution="1k",
        count=1,
    )

    assert len(http.posts) == 1
    call = http.posts[0]
    assert call["url"] == f"{API_BASE}/images/edits"
    payload = call["payload"]
    assert_key_stays_out(payload, call["headers"])
    assert payload["model"] == "grok-imagine-image-2.0"
    assert payload["n"] == 1
    assert payload["response_format"] == "b64_json"
    assert payload["aspect_ratio"] == "3:4"
    assert payload["resolution"] == "1k"
    assert "quality" not in payload
    assert "images" not in payload
    assert payload["image"]["type"] == "image_url"
    assert payload["image"]["url"].startswith("data:image/png;base64,")
    assert "portrait.png" not in payload["image"]["url"]
    assert payload["prompt"].startswith("Replace the background")
    assert "facial features, skin tone, hairline, and proportions" in payload["prompt"]
    assert result.face_lock is True
    assert result.images[0].path.read_bytes() == PNG_BYTES
    assert result.endpoint.endswith("/images/edits")

    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    text = result.metadata_path.read_text(encoding="utf-8")
    assert API_KEY not in text
    assert PNG_B64 not in text
    assert metadata["operation"] == "edit"
    assert metadata["prompt"] == "Replace the background with a sunlit greenhouse."
    assert metadata["face_lock"] is True
    assert metadata["input_image"]["path"].endswith("portrait.png")
    assert metadata["input_image"]["sha256"] == hashlib.sha256(PNG_BYTES).hexdigest()
    assert metadata["references"] == []
    assert metadata["images"][0]["source"] == "b64_json"
    assert metadata["images"][0]["file"] == result.images[0].path.name
    assert metadata["timestamp"] == "2026-11-15T18:00:00.000000Z"
    assert metadata["usage"] == {"total_tokens": 12}
    assert metadata["response_model"] == "grok-imagine-image-2.0"


def test_generate_with_refs_uses_the_images_array(tmp_path: Path) -> None:
    front = write_png(tmp_path / "front.png")
    side = write_png(tmp_path / "side.png")
    http = RecordingTransport(response=png_response(2))
    client, _http = _client(tmp_path, http)
    result = client.generate(
        prompt="Seated at a cafe window.",
        refs=[front, side],
        out_dir=tmp_path / "out",
        count=2,
        quality="medium",
    )

    assert len(result.images) == 2
    payload = http.posts[0]["payload"]
    assert http.posts[0]["url"].endswith("/images/edits")
    assert "image" not in payload
    assert len(payload["images"]) == 2
    assert payload["quality"] == "medium"
    assert "<IMAGE_0>" in payload["prompt"]
    assert "<IMAGE_1>" in payload["prompt"]
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["operation"] == "generate"
    assert metadata["input_image"] is None
    assert [item["path"] for item in metadata["references"]] == [str(front), str(side)]
    assert metadata["count_requested"] == 2
    assert metadata["face_lock"] is True


def test_generate_without_refs_is_text_to_image(tmp_path: Path) -> None:
    client, http = _client(tmp_path)
    result = client.generate(
        prompt="A red paper lantern over a quiet street.",
        out_dir=tmp_path / "out",
    )

    payload = http.posts[0]["payload"]
    assert http.posts[0]["url"].endswith("/images/generations")
    assert "image" not in payload
    assert "images" not in payload
    assert payload["prompt"] == "A red paper lantern over a quiet street."
    assert result.face_lock is False


def test_no_face_lock_still_uploads_references(tmp_path: Path) -> None:
    image = write_png(tmp_path / "face.png")
    client, http = _client(tmp_path)
    client.generate(
        prompt="Composite these into a park scene.",
        refs=[image],
        out_dir=tmp_path / "out",
        face_lock=False,
    )
    payload = http.posts[0]["payload"]
    assert payload["prompt"] == "Composite these into a park scene."
    assert "images" in payload
    assert "facial features" not in payload["prompt"]


def test_url_fallback_downloads_without_the_api_key(tmp_path: Path) -> None:
    image = write_png(tmp_path / "face.png")
    http = RecordingTransport(response={"data": [{"url": "https://cdn.example/out.png"}]})
    client, _http = _client(tmp_path, http)
    result = client.edit(image=image, prompt="Add round glasses.", out_dir=tmp_path / "out")

    assert http.gets[0]["url"] == "https://cdn.example/out.png"
    assert "Authorization" not in http.gets[0]["headers"]
    assert API_KEY not in str(http.gets[0]["headers"])
    assert result.images[0].path.read_bytes() == PNG_BYTES
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["images"][0]["source"] == "url"


def test_b64_is_preferred_over_a_url(tmp_path: Path) -> None:
    image = write_png(tmp_path / "face.png")
    http = RecordingTransport(
        response={"data": [{"b64_json": PNG_B64, "url": "https://cdn.example/out.png", "mime_type": "image/png"}]}
    )
    client, _http = _client(tmp_path, http)
    client.edit(image=image, prompt="Add a hat.", out_dir=tmp_path / "out")
    assert http.gets == []


def test_limits_fail_before_http(tmp_path: Path) -> None:
    image = write_png(tmp_path / "face.png")
    client, http = _client(tmp_path)
    with pytest.raises(ImagineError, match="At most 5"):
        client.generate(
            prompt="A portrait.",
            refs=[tmp_path / f"{index}.png" for index in range(6)],
            out_dir=tmp_path / "out",
        )
    with pytest.raises(ImagineError, match="count must"):
        client.edit(image=image, prompt="A portrait.", out_dir=tmp_path / "out", count=11)
    with pytest.raises(ImagineError, match="aspect_ratio"):
        client.edit(image=image, prompt="A portrait.", out_dir=tmp_path / "out", aspect_ratio="7:1")
    assert http.posts == []


def test_rejects_unsupported_and_missing_files(tmp_path: Path) -> None:
    gif = tmp_path / "anim.gif"
    gif.write_bytes(b"GIF89a" + b"\x00" * 16)
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    client, http = _client(tmp_path)
    with pytest.raises(ImagineError, match="Unsupported image type"):
        client.edit(image=gif, prompt="Add a hat.", out_dir=tmp_path / "out")
    with pytest.raises(ImagineError, match="empty"):
        client.edit(image=empty, prompt="Add a hat.", out_dir=tmp_path / "out")
    with pytest.raises(ImagineError, match="not found"):
        client.edit(image=tmp_path / "missing.png", prompt="Add a hat.", out_dir=tmp_path / "out")
    assert http.posts == []


def test_api_error_redacts_the_key(tmp_path: Path) -> None:
    image = write_png(tmp_path / "face.png")
    http = RecordingTransport(error=ImagineApiError(400, f"bad prompt {API_KEY}"))
    client, _http = _client(tmp_path, http)
    with pytest.raises(ImagineApiError, match="400") as caught:
        client.edit(image=image, prompt="Add a hat.", out_dir=tmp_path / "out")
    assert API_KEY not in str(caught.value)
    assert "[redacted]" in str(caught.value)
    assert "secret" not in repr(client)


def test_error_object_without_images(tmp_path: Path) -> None:
    image = write_png(tmp_path / "face.png")
    http = RecordingTransport(response={"error": {"message": f"filtered {API_KEY}"}})
    client, _http = _client(tmp_path, http)
    with pytest.raises(ImagineError, match="filtered") as caught:
        client.edit(image=image, prompt="Add a hat.", out_dir=tmp_path / "out")
    assert API_KEY not in str(caught.value)


def test_from_env_requires_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    with pytest.raises(ImagineError, match="XAI_API_KEY") as caught:
        ImagineClient.from_env()
    assert "Bearer" not in str(caught.value)
    built = ImagineClient.from_env({"XAI_API_KEY": f"  {API_KEY}  "})
    assert API_KEY not in repr(built)


def test_jpeg_bytes_win_over_a_wrong_suffix(tmp_path: Path) -> None:
    jpeg = tmp_path / "photo.png"
    jpeg.write_bytes(b"\xff\xd8\xff" + b"\x00" * 8)
    client, http = _client(tmp_path)
    client.edit(image=jpeg, prompt="Add a hat.", out_dir=tmp_path / "out")
    assert http.posts[0]["payload"]["image"]["url"].startswith("data:image/jpeg;base64,")
