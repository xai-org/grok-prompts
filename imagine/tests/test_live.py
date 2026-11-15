"""One real generation and one real edit.

Skipped unless XAI_API_KEY is set. The default pytest options exclude this
module (`-m 'not live'`) so a normal test run never spends credits. Run it
explicitly with:

    uv run pytest -m live -o addopts=

That is two image calls. Do not raise the counts here.
"""

import os
from pathlib import Path

import pytest

from grok_imagine.client import ImagineClient

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("XAI_API_KEY"), reason="XAI_API_KEY is not set"),
]


def test_live_generate_then_edit(tmp_path: Path) -> None:
    client = ImagineClient.from_env()
    generated = client.generate(
        prompt=(
            "A studio portrait photograph of a fictional adult with short black hair, "
            "neutral expression, plain gray background, soft even light, head and shoulders."
        ),
        out_dir=tmp_path / "generate",
        count=1,
        resolution="1k",
        quality="low",
        aspect_ratio="1:1",
        face_lock=False,
    )
    assert generated.images[0].path.stat().st_size > 1000
    assert generated.metadata_path.is_file()

    edited = client.edit(
        image=generated.images[0].path,
        prompt="Add thin round wire glasses. Keep the same pose and plain background.",
        out_dir=tmp_path / "edit",
        count=1,
        resolution="1k",
        quality="low",
        aspect_ratio="1:1",
    )
    assert edited.face_lock is True
    assert edited.images[0].path.stat().st_size > 1000
    assert edited.images[0].path != generated.images[0].path
