"""JSON client for the xAI image generation and edit endpoints.

The official Python SDK (``xai-sdk``) can edit too: ``Client.image.sample`` and
``sample_batch`` take ``image_url`` or ``image_urls`` and call the gRPC
``GenerateImage`` RPC. This tool uses the documented HTTPS endpoints instead,
so the body matches the JSON reference (``image`` versus ``images``,
``response_format: b64_json``, quality ``auto``, and the full aspect-ratio
list) and tests can mock that HTTP layer.

Docs: https://docs.x.ai/developers/rest-api-reference/inference/images
"""

import base64
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, assert_never

from grok_imagine.constants import (
    API_BASE,
    ASPECT_RATIOS,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    EDITS_PATH,
    GENERATIONS_PATH,
    MAX_IMAGES,
    MAX_REFERENCE_IMAGES,
    QUALITIES,
    RESOLUTIONS,
    USER_AGENT,
)
from grok_imagine.errors import ImagineApiError, ImagineError
from grok_imagine.prompt import Mode, prepare_prompt

API_HOST = "api.x.ai"
_SUFFIX_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_MIME_EXTENSION = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


@dataclass(frozen=True)
class ImageRef:
    """A local image that was sent, without its bytes."""

    path: str
    sha256: str


@dataclass(frozen=True)
class SavedImage:
    path: Path
    mime_type: str
    source: str


@dataclass(frozen=True)
class RunResult:
    metadata_path: Path
    images: tuple[SavedImage, ...]
    prompt_sent: str
    endpoint: str
    face_lock: bool


class HttpTransport(Protocol):
    """The HTTP surface the client needs. Tests substitute their own."""

    def post_json(
        self,
        url: str,
        payload: Mapping[str, Any],
        headers: Mapping[str, str],
        timeout: float,
    ) -> dict[str, Any]:
        """POST a JSON body and return the decoded object."""

    def get_bytes(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout: float,
    ) -> tuple[bytes, str | None]:
        """GET a URL and return the body plus an optional Content-Type."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Do not follow POST redirects. ``Authorization`` would be forwarded."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ImagineError(f"The image API returned redirect {code}, which was not followed.")


class _HttpsRedirect(urllib.request.HTTPRedirectHandler):
    """Allow image-download redirects only when the target stays on https."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlparse(newurl).scheme != "https":
            raise ImagineError("Refusing to follow a non-https image redirect.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_POST_OPENER = urllib.request.build_opener(_NoRedirect)
_GET_OPENER = urllib.request.build_opener(_HttpsRedirect)


def _open_post(request: urllib.request.Request, timeout: float):
    return _POST_OPENER.open(request, timeout=timeout)


def _open_get(request: urllib.request.Request, timeout: float):
    return _GET_OPENER.open(request, timeout=timeout)


class UrllibTransport:
    """``urllib`` implementation of :class:`HttpTransport`.

    The API key is attached only to ``POST`` requests whose host is
    ``api.x.ai``, and those requests do not follow redirects. Image URLs
    returned by the API are temporary CDN links, so downloads send a
    User-Agent and nothing else.
    """

    def post_json(
        self,
        url: str,
        payload: Mapping[str, Any],
        headers: Mapping[str, str],
        timeout: float,
    ) -> dict[str, Any]:
        _require_api_url(url)
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=dict(headers),
            method="POST",
        )
        secret = _bearer_secret(headers)
        try:
            with _open_post(request, timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = _snippet(exc.read(), secret)
            raise ImagineApiError(exc.code, detail) from None
        except urllib.error.URLError as exc:
            raise ImagineError(f"Could not reach the image API: {exc.reason}") from None
        except TimeoutError:
            raise ImagineError("The image API request timed out.") from None
        return _decode_json_object(raw, secret)

    def get_bytes(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout: float,
    ) -> tuple[bytes, str | None]:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ImagineError("Refusing to download an image URL that is not https.")
        request = urllib.request.Request(url, headers=dict(headers), method="GET")
        try:
            with _open_get(request, timeout) as response:
                content_type = response.headers.get("Content-Type")
                return response.read(), _mime_from_header(content_type)
        except urllib.error.HTTPError as exc:
            raise ImagineError(f"Could not download the generated image ({exc.code}).") from None
        except urllib.error.URLError as exc:
            raise ImagineError(f"Could not download the generated image: {exc.reason}") from None
        except TimeoutError:
            raise ImagineError("Downloading the generated image timed out.") from None


def redact(text: str, secret: str) -> str:
    """Remove the API key from text that might be printed."""

    if secret and secret in text:
        return text.replace(secret, "[redacted]")
    return text


class ImagineClient:
    """Calls the image API and writes the images plus a metadata JSON file."""

    def __init__(
        self,
        api_key: str,
        *,
        transport: HttpTransport | None = None,
        base_url: str = API_BASE,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        key = api_key.strip()
        if not key:
            raise ImagineError(
                "XAI_API_KEY is empty. Set it to an xAI API key. "
                "The key is not read from flags or files."
            )
        self._api_key = key
        self._transport = transport if transport is not None else UrllibTransport()
        self._base_url = base_url.rstrip("/")
        self._clock = clock if clock is not None else _utc_now

    def __repr__(self) -> str:
        return f"ImagineClient(base_url={self._base_url!r})"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "ImagineClient":
        """Build a client from ``XAI_API_KEY``. The key is never stored on disk."""

        env = os.environ if environ is None else environ
        key = env.get("XAI_API_KEY", "").strip()
        if not key:
            raise ImagineError(
                "Set XAI_API_KEY to an xAI API key. The key is not read from flags or files."
            )
        return cls(key)

    def edit(
        self,
        *,
        image: Path,
        prompt: str,
        out_dir: Path,
        count: int = 1,
        aspect_ratio: str | None = None,
        resolution: str | None = None,
        quality: str | None = None,
        model: str = DEFAULT_MODEL,
        face_lock: bool = True,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> RunResult:
        """Edit one source image. The source is the identity anchor."""

        part, source = _load_image(image)
        return self._run(
            mode="edit",
            prompt=prompt,
            out_dir=out_dir,
            count=count,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            quality=quality,
            model=model,
            face_lock=face_lock,
            timeout=timeout,
            parts=[part],
            single_image=True,
            input_image=source,
            references=(),
        )

    def generate(
        self,
        *,
        prompt: str,
        out_dir: Path,
        refs: Sequence[Path] = (),
        count: int = 1,
        aspect_ratio: str | None = None,
        resolution: str | None = None,
        quality: str | None = None,
        model: str = DEFAULT_MODEL,
        face_lock: bool = True,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> RunResult:
        """Generate an image. Reference photos are sent to the edit endpoint.

        With no ``refs`` this is ``POST /v1/images/generations``. With one or
        more refs (max 5) this is ``POST /v1/images/edits`` and the ``images``
        array is the native identity anchor. Those refs are treated as photos
        of the same person.
        """

        if len(refs) > MAX_REFERENCE_IMAGES:
            raise ImagineError(
                f"At most {MAX_REFERENCE_IMAGES} reference images can be sent in one edit."
            )
        loaded = [_load_image(path) for path in refs]
        parts = [part for part, _ref in loaded]
        references = tuple(ref for _part, ref in loaded)
        return self._run(
            mode="generate",
            prompt=prompt,
            out_dir=out_dir,
            count=count,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            quality=quality,
            model=model,
            face_lock=face_lock,
            timeout=timeout,
            parts=parts,
            single_image=False,
            input_image=None,
            references=references,
        )

    def _run(
        self,
        *,
        mode: Mode,
        prompt: str,
        out_dir: Path,
        count: int,
        aspect_ratio: str | None,
        resolution: str | None,
        quality: str | None,
        model: str,
        face_lock: bool,
        timeout: float,
        parts: Sequence[dict[str, str]],
        single_image: bool,
        input_image: ImageRef | None,
        references: Sequence[ImageRef],
    ) -> RunResult:
        _check_count(count)
        _check_timeout(timeout)
        _check_choice("aspect_ratio", aspect_ratio, ASPECT_RATIOS)
        _check_choice("resolution", resolution, RESOLUTIONS)
        _check_choice("quality", quality, QUALITIES)
        model_name = model.strip()
        if not model_name:
            raise ImagineError("Model name is empty.")

        prompt_sent = prepare_prompt(
            prompt,
            mode=mode,
            reference_count=len(parts),
            face_lock=face_lock,
        )
        locked = face_lock and (mode == "edit" or len(parts) > 0)
        path = _request_path(mode, reference_count=len(parts))
        endpoint = f"{self._base_url}{path}"
        payload = _build_payload(
            model=model_name,
            prompt_sent=prompt_sent,
            count=count,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            quality=quality,
            parts=parts,
            single_image=single_image,
        )
        body = self._post(endpoint, payload, timeout)
        saved = _materialize_images(body, self._transport, timeout)
        response_model = body.get("model")
        return _write_run(
            out_dir=out_dir,
            mode=mode,
            endpoint=endpoint,
            model=model_name,
            prompt=prompt.strip(),
            prompt_sent=prompt_sent,
            face_lock=locked,
            references=references,
            input_image=input_image,
            count=count,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            quality=quality,
            images=saved,
            usage=body.get("usage") if isinstance(body.get("usage"), dict) else None,
            response_model=response_model if isinstance(response_model, str) else None,
            clock=self._clock,
        )

    def _post(self, url: str, payload: Mapping[str, Any], timeout: float) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        try:
            body = self._transport.post_json(url, payload, headers, timeout)
        except ImagineApiError as exc:
            detail = redact(exc.detail, self._api_key)
            if detail != exc.detail:
                raise ImagineApiError(exc.status, detail) from None
            raise
        except ImagineError as exc:
            message = redact(str(exc), self._api_key)
            if message != str(exc):
                raise ImagineError(message) from None
            raise
        if not isinstance(body, dict):
            raise ImagineError("Image API response was not a JSON object.")
        if "error" in body and "data" not in body:
            raise ImagineError(f"Image API returned an error: {_error_text(body['error'], self._api_key)}")
        return body


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _request_path(mode: Mode, *, reference_count: int) -> str:
    """Pick the REST path. References always go to the edit endpoint."""

    match mode:
        case "edit":
            return EDITS_PATH
        case "generate":
            if reference_count > 0:
                return EDITS_PATH
            return GENERATIONS_PATH
        case unreachable:
            assert_never(unreachable)


def _build_payload(
    *,
    model: str,
    prompt_sent: str,
    count: int,
    aspect_ratio: str | None,
    resolution: str | None,
    quality: str | None,
    parts: Sequence[dict[str, str]],
    single_image: bool,
) -> dict[str, Any]:
    """Build a generations or edits body.

    ``image`` and ``images`` are mutually exclusive on ``/v1/images/edits``.
    A single edit uses ``image``. Reference-guided generation uses ``images``
    even for one photo, so the prompt can address ``<IMAGE_0>``.
    """

    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt_sent,
        "n": count,
        "response_format": "b64_json",
    }
    if aspect_ratio is not None:
        payload["aspect_ratio"] = aspect_ratio
    if resolution is not None:
        payload["resolution"] = resolution
    if quality is not None:
        payload["quality"] = quality
    if single_image:
        if len(parts) != 1:
            raise ImagineError("An edit takes exactly one source image.")
        payload["image"] = parts[0]
    elif parts:
        payload["images"] = list(parts)
    if "image" in payload and "images" in payload:
        raise ImagineError("Refusing to send both image and images.")
    return payload


def _load_image(path: Path) -> tuple[dict[str, str], ImageRef]:
    file_path = Path(path)
    if not file_path.is_file():
        raise ImagineError(f"Image not found: {file_path}")
    data = file_path.read_bytes()
    if not data:
        raise ImagineError(f"Image is empty: {file_path}")
    mime = _mime_for(data, file_path.suffix)
    encoded = base64.b64encode(data).decode("ascii")
    part = {"type": "image_url", "url": f"data:{mime};base64,{encoded}"}
    ref = ImageRef(path=str(file_path), sha256=hashlib.sha256(data).hexdigest())
    return part, ref


def _mime_for(data: bytes, suffix: str) -> str:
    sniffed = _sniff_mime(data)
    if sniffed is not None:
        return sniffed
    guessed = _SUFFIX_MIME.get(suffix.lower())
    if guessed is not None:
        return guessed
    raise ImagineError("Unsupported image type. Use JPEG, PNG, or WebP.")


def _sniff_mime(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _check_count(count: int) -> None:
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_IMAGES:
        raise ImagineError(f"count must be an integer from 1 to {MAX_IMAGES}.")


def _check_timeout(timeout: float) -> None:
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ImagineError("timeout must be a positive number of seconds.")


def _check_choice(name: str, value: str | None, allowed: tuple[str, ...]) -> None:
    if value is not None and value not in allowed:
        choices = ", ".join(allowed)
        raise ImagineError(f"Unsupported {name} {value!r}. Expected one of: {choices}.")


def _materialize_images(
    body: Mapping[str, Any],
    transport: HttpTransport,
    timeout: float,
) -> list[tuple[bytes, str, str]]:
    data = body.get("data")
    if not isinstance(data, list) or not data:
        raise ImagineError(
            "The image API returned no images. The prompt or the reference may have been filtered."
        )
    images: list[tuple[bytes, str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            raise ImagineError("The image API returned a data entry that was not an object.")
        images.append(_one_image(item, transport, timeout))
    return images


def _one_image(
    item: Mapping[str, Any],
    transport: HttpTransport,
    timeout: float,
) -> tuple[bytes, str, str]:
    encoded = item.get("b64_json")
    declared = item.get("mime_type")
    mime = declared if isinstance(declared, str) and declared else None
    if isinstance(encoded, str) and encoded:
        raw = _decode_b64(encoded)
        return raw, mime or _sniff_mime(raw) or "image/jpeg", "b64_json"
    url = item.get("url")
    if isinstance(url, str) and url:
        # Do not send the API key to the image host.
        raw, fetched_mime = transport.get_bytes(url, {"User-Agent": USER_AGENT}, timeout)
        if not raw:
            raise ImagineError("The generated image URL was empty.")
        resolved = mime or fetched_mime or _sniff_mime(raw) or "image/jpeg"
        return raw, resolved, "url"
    raise ImagineError("An image response had neither b64_json nor url.")


def _decode_b64(value: str) -> bytes:
    encoded = value.split("base64,", 1)[1] if "base64," in value else value
    try:
        return base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ImagineError("The image API returned invalid base64.") from None


def _write_run(
    *,
    out_dir: Path,
    mode: Mode,
    endpoint: str,
    model: str,
    prompt: str,
    prompt_sent: str,
    face_lock: bool,
    references: Sequence[ImageRef],
    input_image: ImageRef | None,
    count: int,
    aspect_ratio: str | None,
    resolution: str | None,
    quality: str | None,
    images: Sequence[tuple[bytes, str, str]],
    usage: Mapping[str, Any] | None,
    response_model: str | None,
    clock: Callable[[], datetime],
) -> RunResult:
    directory = Path(out_dir)
    if directory.exists() and not directory.is_dir():
        raise ImagineError(f"Output path is not a directory: {directory}")
    directory.mkdir(parents=True, exist_ok=True)

    now = clock()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    stem = f"{mode}-{stamp}"
    saved: list[SavedImage] = []
    for index, (raw, mime, source) in enumerate(images):
        extension = _MIME_EXTENSION.get(mime.split(";", 1)[0].strip().lower(), ".img")
        file_path = directory / f"{stem}-{index}{extension}"
        if file_path.exists():
            raise ImagineError(f"Refusing to overwrite {file_path}.")
        file_path.write_bytes(raw)
        saved.append(SavedImage(path=file_path, mime_type=mime, source=source))

    metadata = {
        "operation": mode,
        "endpoint": endpoint,
        "model": model,
        "prompt": prompt,
        "prompt_sent": prompt_sent,
        "face_lock": face_lock,
        "references": [{"path": ref.path, "sha256": ref.sha256} for ref in references],
        "input_image": None
        if input_image is None
        else {"path": input_image.path, "sha256": input_image.sha256},
        "count_requested": count,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "quality": quality,
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "response_model": response_model,
        "images": [
            {"file": image.path.name, "mime_type": image.mime_type, "source": image.source}
            for image in saved
        ],
        "usage": usage,
    }
    metadata_path = directory / f"{stem}.json"
    if metadata_path.exists():
        raise ImagineError(f"Refusing to overwrite {metadata_path}.")
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return RunResult(
        metadata_path=metadata_path,
        images=tuple(saved),
        prompt_sent=prompt_sent,
        endpoint=endpoint,
        face_lock=face_lock,
    )


def _require_api_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != API_HOST:
        host = parsed.hostname or "(missing host)"
        raise ImagineError(f"Refusing to send the API key to {host}.")


def _bearer_secret(headers: Mapping[str, str]) -> str:
    auth = headers.get("Authorization", "")
    prefix = "Bearer "
    if auth.startswith(prefix):
        return auth[len(prefix) :]
    return ""


def _snippet(raw: bytes, secret: str) -> str:
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return "empty response body"
    if len(text) > 300:
        text = text[:300] + "..."
    return redact(text, secret)


def _decode_json_object(raw: bytes, secret: str) -> dict[str, Any]:
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise ImagineError(f"Image API response was not JSON: {_snippet(raw, secret)}") from None
    if not isinstance(body, dict):
        raise ImagineError("Image API response was not a JSON object.")
    return body


def _mime_from_header(value: str | None) -> str | None:
    if not value:
        return None
    mime = value.split(";", 1)[0].strip().lower()
    if mime.startswith("image/"):
        return mime
    return None


def _error_text(error: Any, secret: str) -> str:
    if isinstance(error, str):
        return redact(error[:300], secret)
    if isinstance(error, dict):
        message = error.get("message") or error.get("error") or error.get("code")
        if isinstance(message, str):
            return redact(message[:300], secret)
    return "see the API response"
