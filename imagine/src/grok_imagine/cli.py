"""Command line for face-locked Grok Imagine edits and generations."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from grok_imagine.client import ImagineClient, RunResult
from grok_imagine.constants import (
    ASPECT_RATIOS,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_IMAGES,
    QUALITIES,
    RESOLUTIONS,
    __version__,
)
from grok_imagine.errors import ImagineError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="imagine",
        description=(
            "Edit a photo or generate a new one with xAI Grok Imagine, "
            "using reference images and a face-lock prompt so the same person stays recognizable."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    edit = commands.add_parser(
        "edit",
        help="Edit one image. The image is the identity anchor.",
        description=(
            "Edit one source image. The file is sent as the edit `image` input, "
            "and the face-lock sentence is appended after your instruction."
        ),
    )
    edit.add_argument("image", type=Path, help="Source image (JPEG, PNG, or WebP).")
    _add_common(edit)

    generate = commands.add_parser(
        "generate",
        help="Generate an image, optionally from reference faces.",
        description=(
            "Generate an image. Each --ref is a photo of the same person and is sent "
            "on the edit endpoint as an identity reference. Omit --ref for text-only generation."
        ),
    )
    generate.add_argument(
        "--ref",
        action="append",
        type=Path,
        dest="refs",
        default=None,
        help="Reference photo of the person. Repeat for up to 5 photos of the same person.",
    )
    _add_common(generate)
    return parser


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--prompt", required=True, help="What the picture should show, or the edit to make.")
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=1,
        help=f"How many images to request (1-{MAX_IMAGES}).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("imagine-out"),
        help="Directory for images and the metadata JSON. Created if needed. Default: imagine-out",
    )
    parser.add_argument("--aspect-ratio", choices=ASPECT_RATIOS, help="Output aspect ratio. Default: API chooses.")
    parser.add_argument("--resolution", choices=RESOLUTIONS, help="1k, 2k, or 1.5k. Default: API chooses (1k).")
    parser.add_argument(
        "--quality",
        choices=QUALITIES,
        help="low, medium, or auto. Default: omit, so the API uses auto.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Image model. Default: {DEFAULT_MODEL}.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"HTTP timeout in seconds. Default: {int(DEFAULT_TIMEOUT_SECONDS)}.",
    )
    parser.add_argument(
        "--no-face-lock",
        action="store_true",
        help="Send the prompt unchanged. Reference images are still uploaded.",
    )


def run(argv: Sequence[str] | None = None, *, client: ImagineClient | None = None) -> int:
    """Run the CLI. Returns a process status code and prints saved paths."""

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        active = client if client is not None else ImagineClient.from_env()
        result = _dispatch(args, active)
    except ImagineError as exc:
        print(exc, file=sys.stderr)
        return 1
    for image in result.images:
        print(image.path)
    print(result.metadata_path)
    return 0


def _dispatch(args: argparse.Namespace, client: ImagineClient) -> RunResult:
    match args.command:
        case "edit":
            return client.edit(
                image=args.image,
                prompt=args.prompt,
                out_dir=args.out,
                count=args.count,
                aspect_ratio=args.aspect_ratio,
                resolution=args.resolution,
                quality=args.quality,
                model=args.model,
                face_lock=not args.no_face_lock,
                timeout=args.timeout,
            )
        case "generate":
            return client.generate(
                prompt=args.prompt,
                out_dir=args.out,
                refs=args.refs or [],
                count=args.count,
                aspect_ratio=args.aspect_ratio,
                resolution=args.resolution,
                quality=args.quality,
                model=args.model,
                face_lock=not args.no_face_lock,
                timeout=args.timeout,
            )
        case other:
            raise ImagineError(f"Unknown command {other!r}.")


def main() -> None:
    sys.exit(run())
