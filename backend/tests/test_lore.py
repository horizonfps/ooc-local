from app.lore import (
    LORE_BUDGET_TOKENS,
    build_scan_text,
    keyword_matches,
    lore_ids,
    normalize_text,
    render_lore,
    select_lore,
)
from app.llm.base import ChatMessage
from app.scenario import LoreEntry, load_scenario

WORLD_MD = "# Mundo\n\nUma escola nas montanhas.\n"

SCENARIO_YAML = """\
name: Exemplo Lore
tagline: uma tagline
locale: pt-br
"""

DEFAULT_START = """\
name: Começo
prologue: prologo
opening_scene: Você acorda no dormitório.
hud:
  location: dormitorio
  time: "08:00"
  weather: clear
"""

ALUNO_YAML = """\
name: Aluno
role: aluno
appearance: baixo
personality: quieto
voice: baixa
mind:
  feeling: cansado
  goal: passar despercebido
"""

CADERNO_YAML = """\
title: O caderno
keywords: [caderno, diário]
body: Um caderno preto cheio de anotações.
scope: keyword
priority: 0
"""

GREMIO_YAML = """\
title: Sala do grêmio
keywords: [sala do grêmio]
body: A sala onde o grêmio se reúne.
scope: keyword
priority: 5
"""

REGRAS_YAML = """\
title: Regras
body: Regras gerais da escola.
scope: always
priority: 0
"""

ANTIGO_YAML = """\
title: Antigo
body: Uma entrada antiga que não deveria aparecer.
scope: always
enabled: false
"""

LOREBOOK = {
    "caderno.yaml": CADERNO_YAML,
    "gremio.yaml": GREMIO_YAML,
    "regras.yaml": REGRAS_YAML,
    "antigo.yaml": ANTIGO_YAML,
}


def _write_scenario(root, scenario_id="exemplo-lore", *, lorebook=None):
    scenario_path = root / scenario_id
    scenario_path.mkdir(parents=True)
    (scenario_path / "scenario.yaml").write_text(SCENARIO_YAML, encoding="utf-8")
    (scenario_path / "world.md").write_text(WORLD_MD, encoding="utf-8")

    starts_dir = scenario_path / "starts"
    starts_dir.mkdir()
    (starts_dir / "default.yaml").write_text(DEFAULT_START, encoding="utf-8")

    characters_dir = scenario_path / "characters"
    characters_dir.mkdir()
    (characters_dir / "aluno.yaml").write_text(ALUNO_YAML, encoding="utf-8")

    if lorebook:
        lorebook_dir = scenario_path / "lorebook"
        lorebook_dir.mkdir()
        for filename, content in lorebook.items():
            (lorebook_dir / filename).write_text(content, encoding="utf-8")

    return scenario_path


def _load(monkeypatch, tmp_path, *, lorebook=None):
    scenario_id = "exemplo-lore"
    _write_scenario(tmp_path, scenario_id, lorebook=LOREBOOK if lorebook is None else lorebook)
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)
    return load_scenario(scenario_id)


def _entry(**overrides):
    data = {"title": "t", "body": "body", "scope": "always", "priority": 0}
    data.update(overrides)
    return LoreEntry.model_validate(data)


# --- normalize_text / keyword_matches --------------------------------------


def test_normalize_text_strips_accents_and_case():
    assert normalize_text("Diário DO Grêmio") == "diario do gremio"


def test_keyword_matches_happy_case_and_accent():
    assert keyword_matches("caderno", "o Caderno preto") is True
    assert keyword_matches("diário", "abriu o diario") is True


def test_keyword_matches_multi_word():
    assert keyword_matches("sala do grêmio", "fui até a Sala do Gremio") is True


def test_keyword_matches_right_boundary():
    assert keyword_matches("caderno", "os cadernos") is False


def test_keyword_matches_left_boundary():
    assert keyword_matches("caderno", "macaderno") is False


def test_keyword_matches_trailing_punctuation():
    assert keyword_matches("caderno", "o caderno.") is True


def test_keyword_matches_hyphen_is_boundary():
    assert keyword_matches("preto", "caderno-preto") is True


def test_keyword_matches_blank_or_empty_or_dash():
    assert keyword_matches("   ", "qualquer coisa") is False
    assert keyword_matches("", "qualquer coisa") is False
    assert keyword_matches("—", "qualquer coisa") is False


def test_keyword_matches_empty_scan_text_only_always_survives():
    assert keyword_matches("caderno", "") is False


# --- select_lore -------------------------------------------------------------


def test_select_lore_happy_path_order_by_priority_then_id(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    selected = select_lore(scenario, "peguei o caderno na mesa")
    assert [entry.title for entry in selected] == ["O caderno", "Regras"]


def test_select_lore_higher_priority_first(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    selected = select_lore(scenario, "fui à sala do grêmio")
    assert [entry.title for entry in selected] == ["Sala do grêmio", "Regras"]


def test_select_lore_empty_scan_text_only_always(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    selected = select_lore(scenario, "")
    assert [entry.title for entry in selected] == ["Regras"]


def test_select_lore_disabled_entry_never_returned(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    selected = select_lore(scenario, "qualquer coisa antiga")
    assert all(entry.title != "Antigo" for entry in selected)


def test_select_lore_only_second_keyword_matches(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    selected = select_lore(scenario, "abriu o diario secreto")
    assert any(entry.title == "O caderno" for entry in selected)


def test_select_lore_budget_cuts_at_third_entry(monkeypatch, tmp_path):
    body = "x" * 1600
    lorebook = {
        "a.yaml": f"title: t\nbody: |\n  {body}\nscope: always\npriority: 0\n",
        "b.yaml": f"title: t\nbody: |\n  {body}\nscope: always\npriority: 0\n",
        "c.yaml": f"title: t\nbody: |\n  {body}\nscope: always\npriority: 0\n",
    }
    scenario = _load(monkeypatch, tmp_path, lorebook=lorebook)
    selected = select_lore(scenario, "")
    assert len(selected) == 2
    from app.compact import estimate_tokens

    assert estimate_tokens(render_lore(selected)) <= LORE_BUDGET_TOKENS


def test_select_lore_single_entry_too_big_returns_empty(monkeypatch, tmp_path):
    body = "x" * 8000
    lorebook = {"huge.yaml": f"title: t\nbody: |\n  {body}\nscope: always\npriority: 0\n"}
    scenario = _load(monkeypatch, tmp_path, lorebook=lorebook)
    assert select_lore(scenario, "") == []


def test_select_lore_no_lorebook_returns_empty(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, lorebook={})
    assert select_lore(scenario, "qualquer coisa") == []


def test_select_lore_deterministic(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    scan_text = "peguei o caderno na sala do gremio"
    first = select_lore(scenario, scan_text)
    second = select_lore(scenario, scan_text)
    assert [entry.title for entry in first] == [entry.title for entry in second]


# --- lore_ids ------------------------------------------------------------


def test_lore_ids_matches_selection_order(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    selected = select_lore(scenario, "peguei o caderno na mesa")
    assert lore_ids(scenario, selected) == ["caderno", "regras"]


def test_lore_ids_empty_list(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    assert lore_ids(scenario, []) == []


def test_lore_ids_ignores_foreign_entry(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    foreign = _entry(title="foreign")
    assert lore_ids(scenario, [foreign]) == []


# --- render_lore -----------------------------------------------------------


def test_render_lore_happy_path():
    entries = [
        _entry(title="O caderno", body="corpo do caderno"),
        _entry(title="Regras", body="corpo das regras"),
    ]
    assert render_lore(entries) == "### O caderno\ncorpo do caderno\n\n### Regras\ncorpo das regras"


def test_render_lore_empty_list_is_none():
    assert render_lore([]) is None


def test_render_lore_title_newline_and_body_strip():
    entry = _entry(title="Título\ncom quebra", body="  espaço em volta  ")
    rendered = render_lore([entry])
    assert rendered == "### Título com quebra\nespaço em volta"


def test_render_lore_neutralizes_headings():
    entry = _entry(body="## Regras da casa\ntexto")
    rendered = render_lore([entry])
    assert rendered.split("\n", 1)[1].startswith("##### Regras da casa")


def test_render_lore_heading_level_saturates_at_six():
    entry = _entry(body="###### já no nível 6\ntexto")
    rendered = render_lore([entry])
    assert "###### já no nível 6" in rendered


def test_render_lore_empty_body_has_no_trailing_blank_line():
    entry = _entry(body="")
    rendered = render_lore([entry])
    assert rendered == "### t\n"


# --- build_scan_text ---------------------------------------------------------


def test_build_scan_text_uses_last_four_messages_plus_current():
    window = [ChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"msg{i}") for i in range(10)]
    scan_text = build_scan_text(window, "mensagem atual")
    assert scan_text == "msg6\nmsg7\nmsg8\nmsg9\nmensagem atual"


def test_build_scan_text_empty_window_returns_only_current_message():
    assert build_scan_text([], "mensagem atual") == "mensagem atual"
