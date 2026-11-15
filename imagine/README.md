# Grok Imagine face lock

A small command-line tool that calls the [xAI image API](https://docs.x.ai/developers/model-capabilities/imagine) to edit a photo, or to generate a new one, while keeping a person's face consistent with one or more reference photos.

It is part of this repository and uses the same [AGPL-3.0 license](../LICENSE).

Checked against the docs on 15 November 2026 (those pages were last updated 13 November 2026).

## What it calls

| | |
| --- | --- |
| Model | `grok-imagine-image-2.0` |
| Text-to-image | `POST https://api.x.ai/v1/images/generations` |
| Edit, and any request with reference images | `POST https://api.x.ai/v1/images/edits` |

The key is read from the `XAI_API_KEY` environment variable. It is sent only as `Authorization: Bearer …` on `POST` requests to `api.x.ai`, and those requests do not follow redirects. It is not accepted as a flag, not written into the metadata JSON, and not attached when a result image is downloaded from a temporary URL.

Images are requested as `response_format: b64_json` and saved locally. Result URLs from this API are temporary, so a URL is used only if the response has no base64 payload.

### Why this is HTTPS, not `xai-sdk`

The official Python SDK ([`xai-sdk`](https://github.com/xai-org/xai-sdk-python), 1.21.0 on PyPI when this was written) does support editing. `Client.image.sample` and `sample_batch` take `image_url` or `image_urls` (and the file-id equivalents) and call the gRPC `GenerateImage` RPC.

This tool uses the JSON endpoints instead, because that is the contract the HTTP docs describe and the one the tests mock:

- One source edit is the `image` object. Several references are the `images` array (max 5), which the model addresses as `<IMAGE_0>`, `<IMAGE_1>`, and so on. The two fields are mutually exclusive.
- The REST aspect-ratio list includes `21:9`, `5:2`, and `auto`. The SDK's aspect-ratio map on current main does not.
- REST quality is `low`, `medium`, or `auto`. The SDK accepts `low` and `medium`, and its default when the field is omitted is `medium`. On the HTTP API, omitting quality means `auto`, which the docs say currently serves `low` for generation and `medium` for edits. This tool omits quality unless you pass `--quality`.

The OpenAI SDK's `images.edit()` is not a substitute. It posts `multipart/form-data`, and the xAI edit endpoint requires `application/json`.

## Face lock

There is no separate face-embedding or landmark API. Identity is anchored in two ways:

1. **Native image input.** `edit` sends the source file as `image` on `/v1/images/edits`. `generate --ref` sends each photo in the `images` array on that same endpoint, including when there is only one reference, so the prompt can name `<IMAGE_0>`. `generate` without `--ref` is ordinary text-to-image and does not lock a face.
2. **Prompt template.** Your instruction is sent first. A short identity sentence is appended after it. The [prompting guide](https://docs.x.ai/developers/model-capabilities/images/prompting-guide) notes that an edit which opens with "keep everything" barely moves, so the template does not say that. It asks the model to preserve **facial features, skin tone, hairline, and proportions**, and not to substitute a different person.

For two or more `--ref` photos the template also says every reference is another photograph of the **same** person. That matches this tool's job. It is the wrong instruction if you meant to composite different people; pass `--no-face-lock` and name `<IMAGE_0>` onward yourself.

`edit` takes one source image. That image is both the picture being changed and the identity anchor. To pin a face from several angles, use `generate --ref`, then `edit` the result for follow-up changes.

An edit of `portrait.png` with the prompt "Replace the background with a sunlit greenhouse." is sent as:

```text
Replace the background with a sunlit greenhouse.

Preserve the identity of the person in this image. Keep their facial features, skin tone, hairline, and proportions the same, and do not replace them with a different person.
```

The template locks the face, not the rest of the picture. If the pose, crop, clothes, or background should stay, say that in the instruction.

## Limits

These are limits of the API and of this approach, not just of the CLI.

- At most **5** reference images per request, and **1–10** outputs (`-n` / `--count`).
- Inputs must be **JPEG, PNG, or WebP**. The type is taken from the file bytes when the magic number is recognized.
- Aspect ratios: `1:1`, `3:4`, `4:3`, `9:16`, `16:9`, `2:3`, `3:2`, `9:19.5`, `19.5:9`, `9:20`, `20:9`, `1:2`, `2:1`, `21:9`, `5:2`, `auto`. If you omit it on an edit, the output follows the first input image.
- Resolutions: `1k` (the API default), `1.5k`, `2k`.
- Quality: `low`, `medium`, `auto`. Pin `medium` and `2k` when the face has to stay recognizable in fine detail. That costs more.
- Edits are billed for **each input image and each output**. Pricing is on the [image overview](https://docs.x.ai/developers/model-capabilities/imagine).
- This is not a biometric lock. Large changes in pose, age, lighting, or style can still drift the face. Judge the picture against the reference; do not treat a match as guaranteed.
- The tool does not poll deferred requests (`deferred: true`, `GET /v1/images/{request_id}`). Each call waits for the synchronous response, with a default timeout of 180 seconds.
- Only use photos you have the right to use.

## Setup

Python 3.10+ and [uv](https://docs.astral.sh/uv/). From this directory:

```bash
uv sync
export XAI_API_KEY="your key from console.x.ai"
```

Do not commit the key or put it in a command line.

From the repository root the same environment works as:

```bash
uv run --project imagine imagine --help
```

## Examples

Edit one portrait. The source file is the face anchor:

```bash
uv run imagine edit portrait.png \
  --prompt "Replace the background with a sunlit greenhouse. Keep the same head angle and crop." \
  --aspect-ratio 3:4 \
  --out imagine-out
```

Generate a new scene from two photos of the same person, and ask for two variations:

```bash
uv run imagine generate \
  --prompt "A 35mm photograph of this person seated at a cafe window in morning light, wearing a charcoal coat." \
  --ref face-front.jpg \
  --ref face-three-quarter.jpg \
  --count 2 \
  --aspect-ratio 3:2 \
  --resolution 1k \
  --out imagine-out
```

Text-only generation (no face lock):

```bash
uv run imagine generate \
  --prompt "A red paper lantern over a quiet street at dusk." \
  --aspect-ratio 16:9 \
  --out imagine-out
```

`--no-face-lock` still uploads `--ref` images, but sends your prompt unchanged.

Each run writes the images and one JSON file into `--out` (default `imagine-out/`):

```text
imagine-out/edit-20261115T180000000000Z-0.jpg
imagine-out/edit-20261115T180000000000Z.json
```

The JSON records the operation, endpoint, model, your prompt, the prompt actually sent, whether face lock was applied, reference paths and SHA-256 digests, the requested count, aspect ratio, resolution, quality, timestamp, output filenames, and token usage when the API returns it. It does not contain image bytes or the API key.

Paths are printed to stdout, one per line, metadata last. Failures go to stderr and exit 1.

## Tests

Unit tests mock the HTTP layer. They do not need a key.

```bash
uv run pytest
```

If `XAI_API_KEY` is set, one live generation and one live edit (two image calls, `1k`, `quality=low`) can be run explicitly:

```bash
uv run pytest -m live -o addopts=
```

A normal `uv run pytest` does not run that test, so it will not spend credits. Do not commit the images it writes; pytest keeps them in a temporary directory.
