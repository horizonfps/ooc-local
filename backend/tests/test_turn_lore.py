import json

import pytest
from fastapi.testclient import TestClient

from app import main, turn
from app.config import Config
from app.llm.openai_compat import OpenAICompatProvider

WORLD_MD = "# Mundo\n\nUma escola.\n"

SCENARIO_YAML = """\
name: Exemplo Escola
tagline: uma tagline
locale: pt-br
"""

DEFAULT_START = """\
name: Começo
prologue: prologo default
opening_scene: cena
hud:
  location: patio
  time: "07:50"
"""

CHLOE_YAML = """\
name: Chloe
role: aluna
appearance: baixa
personality: extrovertida
voice: animada
mind:
  feeling: curiosa
  goal: descobrir segredo
"""

CADERNO_YAML = """\
title: O caderno de capa preta
keywords: [caderno, diario]
scope: keyword
priority: 10
enabled: true
body: >
  O caderno é um brochurão de capa preta com páginas numeradas à mão.
"""

CADERNO_DISABLED_YAML = """\
title: O caderno de capa preta
keywords: [caderno, diario]
scope: keyword
priority: 10
enabled: false
body: >
  O caderno é um brochurão de capa preta com páginas numeradas à mão.
"""

CADERNO_HEADING_YAML = """\
title: O caderno de capa preta
keywords: [caderno]
scope: keyword
priority: 10
enabled: true
body: |
  O caderno é um brochurão de capa preta.

  ## Subtitulo

  Mais detalhe sobre o caderno.
"""

GREMIO_YAML = """\
title: A sala do grêmio
keywords: [gremio]
scope: keyword
priority: 0
enabled: true
body: >
  A sala do grêmio fica ao lado da quadra.
"""

REGRAS_ALWAYS_YAML = """\
title: Regras da escola
scope: always
priority: 5
enabled: true
body: >
  A escola tem toque às 7h50 e proíbe celular em sala.
"""

COMMANDS_YAML = """\
- name: fofoca
  description: espalha uma fofoca
  prompt: espalhe uma fofoca sobre o personagem atual
"""


def _write_scenario(root, scenario_id="exemplo-escola", *, lorebook=None, commands=None):
    scenario_path = root / scenario_id
    scenario_path.mkdir(parents=True)
    (scenario_path / "scenario.yaml").write_text(SCENARIO_YAML, encoding="utf-8")
    (scenario_path / "world.md").write_text(WORLD_MD, encoding="utf-8")

    starts_dir = scenario_path / "starts"
    starts_dir.mkdir()
    (starts_dir / "default.yaml").write_text(DEFAULT_START, encoding="utf-8")

    characters_dir = scenario_path / "characters"
    characters_dir.mkdir()
    (characters_dir / "chloe.yaml").write_text(CHLOE_YAML, encoding="utf-8")

    if lorebook is not None:
        lorebook_dir = scenario_path / "lorebook"
        lorebook_dir.mkdir()
        for filename, content in lorebook.items():
            (lorebook_dir / filename).write_text(content, encoding="utf-8")

    if commands is not None:
        (scenario_path / "commands.yaml").write_text(commands, encoding="utf-8")

    return scenario_path


def _config(flags=None):
    return Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": {"narrator": {"provider": "local", "model": "m"}},
            "flags": flags or {},
        }
    )


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("OOC_SESSIONS_DB", str(tmp_path / "sessions.db"))
    yield


@pytest.fixture(autouse=True)
def _isolated_global_commands(tmp_path, monkeypatch):
    monkeypatch.setenv("OOC_COMMANDS_FILE", str(tmp_path / "global-commands.yaml"))
    yield


@pytest.fixture
def scenarios_root(tmp_path, monkeypatch):
    root = tmp_path / "scenarios"
    root.mkdir()
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: root)
    return root


def _stream_events(response) -> list[dict]:
    events = []
    for line in "".join(response.iter_text()).splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[len("data:") :].strip()
        if payload == "[DONE]":
            continue
        events.append(json.loads(payload))
    return events


def _make_fake_stream(deltas, captured=None):
    async def fake_stream(self, messages, model):
        if captured is not None:
            captured.append(messages)
        for delta in deltas:
            yield delta

    return fake_stream


def _send(client, session_id, message):
    with client.stream(
        "POST", f"/api/sessions/{session_id}/turn", json={"message": message}
    ) as response:
        assert response.status_code == 200
        return _stream_events(response)


def test_lore_matched_keyword_adds_active_lore_section_between_world_and_characters(
    scenarios_root, monkeypatch
):
    _write_scenario(scenarios_root, lorebook={"caderno.yaml": CADERNO_YAML})
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    captured: list = []
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["voce olha o caderno."], captured=captured)
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    _send(client, session["id"], "eu pego o caderno")

    system = captured[0][0].content
    assert "## LORE ATIVA" in system
    assert "### O caderno de capa preta" in system
    assert "brochurão de capa preta" in system
    world_pos = system.index("## MUNDO")
    lore_pos = system.index("## LORE ATIVA")
    characters_pos = system.index("## PERSONAGENS EM CENA")
    assert world_pos < lore_pos < characters_pos


def test_lore_scope_always_enters_without_keyword(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, lorebook={"regras.yaml": REGRAS_ALWAYS_YAML})
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    captured: list = []
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["voce anda pelo patio."], captured=captured)
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    _send(client, session["id"], "eu ando por ai")

    system = captured[0][0].content
    assert "## LORE ATIVA" in system
    assert "### Regras da escola" in system


def test_lore_two_matches_ordered_by_priority_desc(scenarios_root, monkeypatch):
    _write_scenario(
        scenarios_root,
        lorebook={"caderno.yaml": CADERNO_YAML, "gremio.yaml": GREMIO_YAML},
    )
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    captured: list = []
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["voce anda."], captured=captured)
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    _send(client, session["id"], "eu falo do caderno na sala do gremio")

    system = captured[0][0].content
    caderno_pos = system.index("### O caderno de capa preta")
    gremio_pos = system.index("### A sala do grêmio")
    assert caderno_pos < gremio_pos


def test_lore_no_keyword_match_no_section(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, lorebook={"caderno.yaml": CADERNO_YAML})
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    captured: list = []
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["voce anda."], captured=captured)
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    _send(client, session["id"], "eu ando pelo patio")

    system = captured[0][0].content
    assert "## LORE ATIVA" not in system


def test_lore_keyword_matches_regardless_of_accent_and_case(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, lorebook={"caderno.yaml": CADERNO_YAML})
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    captured: list = []
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["voce anda."], captured=captured)
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    _send(client, session["id"], "onde esta o DIARIO da Chloe?")

    system = captured[0][0].content
    assert "## LORE ATIVA" in system
    assert "### O caderno de capa preta" in system


def test_lore_keyword_from_previous_turn_still_matches_next_turn(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, lorebook={"caderno.yaml": CADERNO_YAML})
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    captured: list = []
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["voce anda."], captured=captured)
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    _send(client, session["id"], "eu vi o caderno na mesa")
    _send(client, session["id"], "e agora, o que eu faco?")

    system_turn_two = captured[1][0].content
    assert "## LORE ATIVA" in system_turn_two
    assert "### O caderno de capa preta" in system_turn_two


def test_lore_keyword_three_turns_ago_no_longer_matches(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, lorebook={"caderno.yaml": CADERNO_YAML})
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    captured: list = []
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["voce anda."], captured=captured)
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    _send(client, session["id"], "eu vi o caderno na mesa")
    _send(client, session["id"], "beleza, seguimos")
    _send(client, session["id"], "certo, vamos la")
    _send(client, session["id"], "e agora?")

    system_turn_four = captured[3][0].content
    assert "## LORE ATIVA" not in system_turn_four


def test_lore_disabled_entry_never_matches(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, lorebook={"caderno.yaml": CADERNO_DISABLED_YAML})
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    captured: list = []
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["voce anda."], captured=captured)
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    _send(client, session["id"], "eu pego o caderno")

    system = captured[0][0].content
    assert "## LORE ATIVA" not in system


def test_lore_body_heading_neutralized_title_stays_level_three(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, lorebook={"caderno.yaml": CADERNO_HEADING_YAML})
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    captured: list = []
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["voce anda."], captured=captured)
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    _send(client, session["id"], "eu pego o caderno")

    system = captured[0][0].content
    assert "### O caderno de capa preta" in system
    assert "##### Subtitulo" in system
    assert "\n## Subtitulo" not in system


def test_lore_meta_command_receives_section_when_keyword_matches(scenarios_root, monkeypatch):
    _write_scenario(
        scenarios_root, lorebook={"caderno.yaml": CADERNO_YAML}, commands=COMMANDS_YAML
    )
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    captured: list = []
    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _make_fake_stream(["Chloe fofoca sobre o caderno."], captured=captured),
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    _send(client, session["id"], "!fofoca sobre o caderno")

    system = captured[0][0].content
    assert "## LORE ATIVA" in system
    assert "### O caderno de capa preta" in system


def test_lore_flag_off_skips_select_lore_and_no_section(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, lorebook={"caderno.yaml": CADERNO_YAML})
    monkeypatch.setattr(main, "load_config", lambda: _config({"lorebook": False}))
    monkeypatch.setattr(turn, "load_config", lambda: _config({"lorebook": False}))
    calls: list = []
    monkeypatch.setattr(turn, "select_lore", lambda scenario, scan_text: calls.append(scan_text) or [])
    captured: list = []
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["voce anda."], captured=captured)
    )
    emitted: list = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    _send(client, session["id"], "eu pego o caderno")

    assert calls == []
    system = captured[0][0].content
    assert "## LORE ATIVA" not in system
    assert all(event != "lore_injected" for event, _ in emitted)


def test_lore_scenario_without_lorebook_no_section_no_telemetry(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, lorebook=None)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    captured: list = []
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["voce anda."], captured=captured)
    )
    emitted: list = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    _send(client, session["id"], "eu pego o caderno")

    system = captured[0][0].content
    assert "## LORE ATIVA" not in system
    assert all(event != "lore_injected" for event, _ in emitted)


def test_lore_injected_emits_ids_and_tokens_on_match(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, lorebook={"caderno.yaml": CADERNO_YAML})
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["voce anda."]))
    emitted: list = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    _send(client, session["id"], "eu pego o caderno")

    lore_events = [props for event, props in emitted if event == "lore_injected"]
    assert len(lore_events) == 1
    assert lore_events[0]["ids"] == ["caderno"]
    assert lore_events[0]["tokens"] > 0


def test_lore_injected_emits_empty_ids_when_no_match(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, lorebook={"caderno.yaml": CADERNO_YAML})
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["voce anda."]))
    emitted: list = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    _send(client, session["id"], "eu ando pelo patio")

    lore_events = [props for event, props in emitted if event == "lore_injected"]
    assert len(lore_events) == 1
    assert lore_events[0]["ids"] == []
