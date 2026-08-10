from pathlib import Path

import pytest

from desk_pet.memory.context import (
    ContextDocumentError,
    build_context_instructions,
    build_realtime_context_instructions,
    load_runtime_context,
)


def _write_document(path: Path, *, status: str, body: str) -> None:
    path.write_text(
        f"---\nstatus: {status}\n---\n\n{body}\n",
        encoding="utf-8",
    )


def test_loads_approved_persona_and_profile(tmp_path: Path) -> None:
    persona = tmp_path / "persona.md"
    profile = tmp_path / "profile.md"
    _write_document(persona, status="approved", body="DeskBob is chirpy.")
    _write_document(profile, status="approved", body="Brayden uses Windows.")

    context = load_runtime_context(
        persona_path=persona,
        user_profile_path=profile,
        maximum_characters=1000,
    )
    instructions = build_context_instructions(context)

    assert context.persona == "DeskBob is chirpy."
    assert context.user_profile == "Brayden uses Windows."
    assert '"approved_user_profile": "Brayden uses Windows."' in instructions


def test_unapproved_profile_is_never_loaded(tmp_path: Path) -> None:
    persona = tmp_path / "persona.md"
    profile = tmp_path / "profile-draft.md"
    _write_document(persona, status="approved", body="DeskBob is chirpy.")
    _write_document(profile, status="draft", body="Unreviewed private claim.")

    context = load_runtime_context(
        persona_path=persona,
        user_profile_path=profile,
        maximum_characters=1000,
    )

    assert context.user_profile == ""


def test_realtime_context_keeps_identity_but_drops_large_routine_sections() -> None:
    from desk_pet.memory.context import RuntimeContext

    context = RuntimeContext(
        persona="DeskBob is chirpy.",
        user_profile=(
            "## Identity\n- Brayden is in ECE.\n\n"
            "## Routine and support context\n- Private long-term detail.\n\n"
            "## Work\n- Works on inference systems."
        ),
    )

    instructions = build_realtime_context_instructions(context)

    assert "Brayden is in ECE" in instructions
    assert "Works on inference systems" in instructions
    assert "Private long-term detail" not in instructions


def test_missing_optional_profile_does_not_block_startup(tmp_path: Path) -> None:
    persona = tmp_path / "persona.md"
    _write_document(persona, status="approved", body="DeskBob is chirpy.")

    context = load_runtime_context(
        persona_path=persona,
        user_profile_path=tmp_path / "missing-profile.md",
        maximum_characters=1000,
    )

    assert context.user_profile == ""


def test_unapproved_persona_is_rejected(tmp_path: Path) -> None:
    persona = tmp_path / "persona.md"
    _write_document(persona, status="draft", body="Unreviewed persona.")

    with pytest.raises(ContextDocumentError, match="not approved"):
        load_runtime_context(
            persona_path=persona,
            user_profile_path=tmp_path / "profile.md",
            maximum_characters=1000,
        )


def test_runtime_context_has_a_hard_size_limit(tmp_path: Path) -> None:
    persona = tmp_path / "persona.md"
    _write_document(persona, status="approved", body="x" * 20)

    with pytest.raises(ContextDocumentError, match="exceeds 10 characters"):
        load_runtime_context(
            persona_path=persona,
            user_profile_path=tmp_path / "profile.md",
            maximum_characters=10,
        )
