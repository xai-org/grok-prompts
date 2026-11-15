"""Face-lock prompt template.

The image API has no separate face-embedding input. Identity is anchored by
sending the photos on ``POST /v1/images/edits`` and by saying, after the user's
instruction, which traits must stay put. The instruction comes first: the
prompting guide notes that an edit which opens with "keep everything" barely
changes the picture.
"""

from typing import Literal, assert_never

from grok_imagine.constants import IMAGE_TOKEN_PREFIX, MAX_REFERENCE_IMAGES
from grok_imagine.errors import ImagineError

Mode = Literal["edit", "generate"]

FACE_TRAITS = "facial features, skin tone, hairline, and proportions"


def prepare_prompt(
    instruction: str,
    *,
    mode: Mode,
    reference_count: int,
    face_lock: bool,
) -> str:
    """Return the prompt that will be sent to the API.

    Face lock is applied for every edit, and for generation only when at least
    one reference image is attached. Generation without references is plain
    text-to-image, so the instruction is sent unchanged.
    """

    text = instruction.strip()
    if not text:
        raise ImagineError("Prompt is empty.")
    if reference_count < 0:
        raise ImagineError("reference_count cannot be negative.")

    lock = face_lock and (mode == "edit" or reference_count > 0)
    if not lock:
        return text
    return face_lock_prompt(text, mode=mode, reference_count=reference_count)


def face_lock_prompt(instruction: str, *, mode: Mode, reference_count: int) -> str:
    """Append the identity instruction. ``instruction`` must already be stripped."""

    match mode:
        case "edit":
            return (
                f"{instruction}\n\n"
                "Preserve the identity of the person in this image. "
                f"Keep their {FACE_TRAITS} the same, "
                "and do not replace them with a different person."
            )
        case "generate":
            if reference_count < 1:
                raise ImagineError("Face lock on generate needs at least one reference image.")
            if reference_count > MAX_REFERENCE_IMAGES:
                raise ImagineError(
                    f"At most {MAX_REFERENCE_IMAGES} reference images can be sent in one edit."
                )
            tokens = ", ".join(f"{IMAGE_TOKEN_PREFIX}{index}>" for index in range(reference_count))
            label = "reference image" if reference_count == 1 else "reference images"
            same_person = ""
            if reference_count > 1:
                same_person = (
                    " Every reference image is another photograph of this same person,"
                    " not a different subject."
                )
            return (
                f"{instruction}\n\n"
                f"The subject is the same person shown in the {label} {tokens}. "
                f"Preserve their {FACE_TRAITS} so the face stays recognizable as that person. "
                f"Do not substitute a different face.{same_person}"
            )
        case _ as unreachable:
            assert_never(unreachable)
