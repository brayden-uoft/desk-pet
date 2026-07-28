from desk_pet.audio.speech_text import text_for_speech


def test_markdown_links_keep_labels_but_drop_urls() -> None:
    text = (
        "The update came from "
        "[Reuters](https://proxy.example/default/https/www.reuters.com/) "
        "and [AP](https://ap.org/news-highlights/)."
    )

    assert text_for_speech(text) == "The update came from Reuters and AP."


def test_bare_and_angle_bracket_urls_are_not_spoken() -> None:
    text = "Details: https://example.com/very/long/path and <https://other.example/news>."

    spoken = text_for_speech(text)

    assert "http" not in spoken
    assert ".com" not in spoken
    assert spoken == "Details: and."


def test_markdown_formatting_is_simplified_for_speech() -> None:
    assert text_for_speech("Quick **world pulse** with `five` items.") == (
        "Quick world pulse with five items."
    )
