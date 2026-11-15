"""Mock urllib so the real transport is exercised without the network."""

import json
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError

import pytest

from grok_imagine.client import UrllibTransport, _HttpsRedirect, _NoRedirect
from grok_imagine.errors import ImagineApiError, ImagineError
from support import API_KEY


class _Body:
    def __init__(self, payload: bytes, headers: dict[str, str] | None = None) -> None:
        self._payload = payload
        self.headers = headers or {"Content-Type": "application/json"}

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_Body":
        return self

    def __exit__(self, *_args: object) -> bool:
        return False


def test_post_json_sends_bearer_only_to_the_api_host(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["authorization"] = request.get_header("Authorization")
        captured["content_type"] = request.get_header("Content-type")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _Body(json.dumps({"data": [{"b64_json": "aaaa", "mime_type": "image/png"}]}).encode())

    monkeypatch.setattr("grok_imagine.client._open_post", fake_urlopen)
    body = UrllibTransport().post_json(
        "https://api.x.ai/v1/images/generations",
        {"model": "grok-imagine-image-2.0", "prompt": "A lantern."},
        {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        12,
    )

    assert captured["url"] == "https://api.x.ai/v1/images/generations"
    assert captured["timeout"] == 12
    assert captured["authorization"] == f"Bearer {API_KEY}"
    assert captured["content_type"] == "application/json"
    assert captured["body"]["prompt"] == "A lantern."
    assert body["data"][0]["mime_type"] == "image/png"


def test_http_error_redacts_the_key_and_keeps_the_status(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout=None):
        raise HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            Message(),
            BytesIO(f"invalid key {API_KEY}".encode()),
        )

    monkeypatch.setattr("grok_imagine.client._open_post", fake_urlopen)
    with pytest.raises(ImagineApiError) as caught:
        UrllibTransport().post_json(
            "https://api.x.ai/v1/images/edits",
            {"prompt": "x"},
            {"Authorization": f"Bearer {API_KEY}"},
            5,
        )
    assert caught.value.status == 401
    assert API_KEY not in str(caught.value)
    assert "[redacted]" in caught.value.detail


def test_refuses_to_send_the_key_to_another_host() -> None:
    with pytest.raises(ImagineError, match="Refusing to send the API key to evil.example"):
        UrllibTransport().post_json(
            "https://evil.example/v1/images/generations",
            {},
            {"Authorization": f"Bearer {API_KEY}"},
            5,
        )


def test_download_rejects_non_https_and_does_not_attach_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout=None):
        assert request.get_header("Authorization") is None
        assert API_KEY not in str(request.header_items())
        return _Body(b"\x89PNG", {"Content-Type": "image/png; charset=binary"})

    monkeypatch.setattr("grok_imagine.client._open_get", fake_urlopen)
    with pytest.raises(ImagineError, match="not https"):
        UrllibTransport().get_bytes("http://cdn.example/a.png", {"User-Agent": "grok-imagine/0.1"}, 5)
    data, mime = UrllibTransport().get_bytes(
        "https://cdn.example/a.png",
        {"User-Agent": "grok-imagine/0.1"},
        5,
    )
    assert data == b"\x89PNG"
    assert mime == "image/png"


def test_post_redirects_are_not_followed() -> None:
    with pytest.raises(ImagineError, match="redirect 302"):
        _NoRedirect().redirect_request(None, None, 302, "Found", Message(), "https://evil.example/steal")


def test_download_redirects_must_stay_on_https() -> None:
    with pytest.raises(ImagineError, match="non-https"):
        _HttpsRedirect().redirect_request(None, None, 302, "Found", Message(), "http://cdn.example/a.png")
