import pytest

from grok_imagine.errors import ImagineError
from grok_imagine.prompt import FACE_TRAITS, face_lock_prompt, prepare_prompt


def test_edit_lock_leads_with_the_instruction() -> None:
    instruction = "Replace the background with a sunlit greenhouse."
    sent = face_lock_prompt(instruction, mode="edit", reference_count=1)

    assert sent.startswith(instruction)
    assert sent.index(instruction) < sent.index("facial features")
    assert "facial features" in sent
    assert "skin tone" in sent
    assert "hairline" in sent
    assert "proportions" in sent
    assert FACE_TRAITS in sent
    assert "<IMAGE_" not in sent


def test_generate_lock_names_each_reference() -> None:
    instruction = "Seated at a cafe window in morning light, wearing a charcoal coat."
    sent = prepare_prompt(instruction, mode="generate", reference_count=2, face_lock=True)

    assert sent.startswith(instruction)
    assert "<IMAGE_0>" in sent
    assert "<IMAGE_1>" in sent
    assert "same person" in sent
    assert "not a different subject" in sent
    assert "facial features, skin tone, hairline, and proportions" in sent


def test_single_reference_uses_singular_token() -> None:
    sent = prepare_prompt("A studio portrait.", mode="generate", reference_count=1, face_lock=True)
    assert "reference image <IMAGE_0>" in sent
    assert "<IMAGE_1>" not in sent
    assert "not a different subject" not in sent


def test_generate_without_references_is_unchanged() -> None:
    instruction = "  A red paper lantern over a quiet street.  "
    assert prepare_prompt(instruction, mode="generate", reference_count=0, face_lock=True) == (
        "A red paper lantern over a quiet street."
    )


def test_no_face_lock_keeps_the_instruction() -> None:
    instruction = "Turn the coat navy."
    assert prepare_prompt(instruction, mode="edit", reference_count=1, face_lock=False) == instruction


def test_empty_prompt_is_rejected() -> None:
    with pytest.raises(ImagineError, match="empty"):
        prepare_prompt("   ", mode="edit", reference_count=1, face_lock=True)


def test_too_many_references_are_rejected() -> None:
    with pytest.raises(ImagineError, match="At most 5"):
        face_lock_prompt("A portrait.", mode="generate", reference_count=6)
