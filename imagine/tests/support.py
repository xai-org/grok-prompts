"""Shared fixtures for HTTP-level image client tests."""

import base64
from datetime import datetime, timezone

from grok_imagine.constants import USER_AGENT

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
PNG_B64 = base64.b64encode(PNG_BYTES).decode("ascii")
API_KEY = "test-key-not-a-real-secret"
FIXED = datetime(2026, 11, 15, 18, 0, tzinfo=timezone.utc)


def png_response(count: int = 1) -> dict:
    return {
        "model": "grok-imagine-image-2.0",
        "data": [{"b64_json": PNG_B64, "mime_type": "image/png"} for _ in range(count)],
        "usage": {"total_tokens": 12},
    }


class RecordingTransport:
    """Stands in for urllib and records the JSON the client tried to send."""

    def __init__(self, response: dict | None = None, download: bytes = PNG_BYTES, error: Exception | None = None):
        self.posts: list[dict] = []
        self.gets: list[dict] = []
        self.response = png_response() if response is None else response
        self.download = download
        self.error = error

    def post_json(self, url, payload, headers, timeout):
        self.posts.append(
            {"url": url, "payload": dict(payload), "headers": dict(headers), "timeout": timeout}
        )
        if self.error is not None:
            raise self.error
        return self.response

    def get_bytes(self, url, headers, timeout):
        self.gets.append({"url": url, "headers": dict(headers), "timeout": timeout})
        return self.download, "image/png"


def write_png(path):
    path.write_bytes(PNG_BYTES)
    return path


def assert_key_stays_out(payload: dict, headers: dict) -> None:
    assert headers["Authorization"] == f"Bearer {API_KEY}"
    assert headers["User-Agent"] == USER_AGENT
    blob = str(payload)
    assert API_KEY not in blob
    assert "Bearer" not in blob
