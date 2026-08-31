from app.tags import parse_tags


def test_removes_stat_tag_and_returns_valid_tag():
    text, tags = parse_tags("O sino toca. [STAT:reputacao:+1]")
    assert text == "O sino toca."
    assert len(tags) == 1
    assert tags[0].kind == "STAT"
    assert tags[0].args == ["reputacao", "+1"]
    assert tags[0].valid is True


def test_line_with_only_tag_disappears_without_blank_paragraph():
    text, tags = parse_tags("Primeiro paragrafo.\n[SPRITE:chloe:sad]\nSegundo paragrafo.")
    assert text == "Primeiro paragrafo.\nSegundo paragrafo."
    assert len(tags) == 1


def test_blank_line_between_paragraphs_is_preserved():
    text, _ = parse_tags("Primeiro paragrafo.\n\nSegundo paragrafo.")
    assert text == "Primeiro paragrafo.\n\nSegundo paragrafo."


def test_sprite_tag_between_paragraphs_preserves_blank_line_separator():
    text, tags = parse_tags("Primeiro.\n[SPRITE:chloe:sad]\n\nSegundo.")
    assert text == "Primeiro.\n\nSegundo."
    assert len(tags) == 1


def test_bracketed_prose_is_not_a_tag():
    text, tags = parse_tags("Ele ri [risos] e sai.")
    assert text == "Ele ri [risos] e sai."
    assert tags == []


def test_lowercase_bracket_is_not_a_tag():
    text, tags = parse_tags("Ele diz [stat:reputacao:+1] algo.")
    assert text == "Ele diz [stat:reputacao:+1] algo."
    assert tags == []


def test_sic_and_number_in_brackets_are_not_tags():
    text, tags = parse_tags("Ele disse [sic] e contou ate [3].")
    assert text == "Ele disse [sic] e contou ate [3]."
    assert tags == []


def test_stat_wrong_arity_is_invalid_but_removed():
    text, tags = parse_tags("[STAT:reputacao]")
    assert text == ""
    assert len(tags) == 1
    assert tags[0].valid is False


def test_stat_non_numeric_value_is_invalid():
    text, tags = parse_tags("[STAT:reputacao:muito]")
    assert text == ""
    assert len(tags) == 1
    assert tags[0].valid is False


def test_unknown_well_formed_tag_is_removed_and_valid():
    text, tags = parse_tags("Antes [FOO:bar] depois")
    assert text == "Antes depois"
    assert len(tags) == 1
    assert tags[0].kind == "FOO"
    assert tags[0].valid is True


def test_no_double_space_or_space_before_punctuation_after_removal():
    text, tags = parse_tags("O sino [STAT:reputacao:+1] toca.")
    assert text == "O sino toca."
    assert len(tags) == 1


def test_three_tags_same_paragraph_no_double_space():
    text, tags = parse_tags(
        "Chloe [SPRITE:chloe:sad] entra na sala [BG:quarto] e sente algo [STAT:reputacao:+1]."
    )
    assert text == "Chloe entra na sala e sente algo."
    assert [t.kind for t in tags] == ["SPRITE", "BG", "STAT"]
    assert all(t.valid for t in tags)


def test_unclosed_bracket_leaves_text_untouched():
    text, tags = parse_tags("...e entao [SPR")
    assert text == "...e entao [SPR"
    assert tags == []


def test_empty_string_returns_empty_text_and_no_tags():
    assert parse_tags("") == ("", [])


def test_whitespace_only_string_returns_empty_text_and_no_tags():
    text, tags = parse_tags("   ")
    assert text == ""
    assert tags == []


def test_speaker_line_is_untouched_by_parser():
    text, tags = parse_tags("**Chloe** | Oi. [STAT:reputacao:+1]\nA sala esta silenciosa. [BG:sala]")
    assert text == "**Chloe** | Oi.\nA sala esta silenciosa."
    assert [t.kind for t in tags] == ["STAT", "BG"]


def test_parse_tags_is_idempotent():
    original = "Chloe [SPRITE:chloe:sad] entra.\n[BG:sala]\n\nDepois [STAT:reputacao:+1] disso."
    once, _ = parse_tags(original)
    twice, _ = parse_tags(once)
    assert once == twice


def test_tags_returned_in_order_of_appearance():
    text, tags = parse_tags("[BG:sala] [STAT:reputacao:+1] [SPRITE:chloe:sad]")
    assert [t.kind for t in tags] == ["BG", "STAT", "SPRITE"]
