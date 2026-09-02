from app.cleanup import strip_engine_echo


def test_strip_engine_echo_removes_hud_block_and_keeps_prose():
    text = "# Turno 3\n**HUD**\nLocal: pátio\n\nVocê atravessa o pátio.\n**Chloe** | Oi."
    clean, dropped = strip_engine_echo(text)
    assert clean == "Você atravessa o pátio.\n**Chloe** | Oi."
    assert dropped == 3


def test_strip_engine_echo_removes_separator_only_lines():
    text = "Ashlee sorri.\n---\n****\n\n***\nChloe olha para você."
    clean, dropped = strip_engine_echo(text)
    assert clean == "Ashlee sorri.\n\nChloe olha para você."
    assert dropped == 3


def test_strip_engine_echo_removes_player_echo_line():
    text = "**Você** | vou até a Chloe\nEla levanta os olhos."
    clean, dropped = strip_engine_echo(text)
    assert clean == "Ela levanta os olhos."
    assert dropped == 1


def test_strip_engine_echo_keeps_npc_speech_that_contains_hud_word():
    text = "**Chloe** | Local: aqui não é lugar de conversa."
    clean, dropped = strip_engine_echo(text)
    assert clean == text
    assert dropped == 0


def test_strip_engine_echo_keeps_indentation_around_dropped_line():
    text = "    Ele espera.\nHora: 07:52\n    Ainda espera."
    clean, dropped = strip_engine_echo(text)
    assert clean == "    Ele espera.\n    Ainda espera."
    assert dropped == 1


def test_strip_engine_echo_returns_unchanged_text_with_zero_count():
    text = "Narração comum.\n**Chloe** | Oi.\n\nOutra linha."
    clean, dropped = strip_engine_echo(text)
    assert clean == text
    assert dropped == 0


def test_strip_engine_echo_is_idempotent_on_mixed_text():
    text = (
        "# Turno 3\n**HUD**\nLocal: pátio\nHora: 07:52\nClima: limpo\n\n"
        "**Você** | vou até a Chloe\nVocê atravessa o pátio.\n**Chloe** | Oi."
    )
    once, _ = strip_engine_echo(text)
    twice, _ = strip_engine_echo(once)
    assert once == twice
