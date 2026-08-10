from desk_pet.agent.tool_routing import should_offer_external_tools


def _messages(*user_texts: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": text} for text in user_texts]


def test_clear_local_conversation_skips_external_tools() -> None:
    assert not should_offer_external_tools(_messages("Say hello in one sentence."))
    assert not should_offer_external_tools(_messages("Hey DeskBob"))
    assert not should_offer_external_tools(_messages("Thanks!"))


def test_external_signal_overrides_local_wording() -> None:
    assert should_offer_external_tools(_messages("Say what's on my calendar today."))
    assert should_offer_external_tools(_messages("Please say the Toronto weather."))


def test_ambiguous_requests_keep_external_tools_available() -> None:
    assert should_offer_external_tools(_messages("Help me pick an outfit."))
    assert should_offer_external_tools(_messages("What am I holding?"))
    assert should_offer_external_tools(_messages("Who runs Cerebras?"))
