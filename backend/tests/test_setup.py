import pytest
from fastapi.testclient import TestClient

from app import main, sessions, setup as setup_lib, turn
from app.config import Config
from app.prompt import build_master_prompt
from app.scenario import ScenarioError, load_scenario
from app.setup import SetupAnswers, SetupInvalid, apply_setup, read_setup, resolve_answers

WORLD_MD = "# Mundo\n\n{{scenario}} recebe {{player}}. Ola, {{unknown}}! {{ nome\n"

SCENARIO_YAML = """\
name: Exemplo Escola
tagline: uma tagline
locale: pt-br
"""

START_WITH_SETUP = """\
name: Começo
prologue: "Bem-vindo(a), {{player}}, ao {{scenario}} via {{start}}."
opening_scene: cena de {{turma}}
conflict: conflito de {{player}}
mission: missao de {{turma}}
hud:
  location: patio
setup:
  - id: player
    question: Como voce se chama?
    type: text
    default: Alex
  - id: turma
    question: Em que turma voce entrou?
    type: choice
    options: ["3o A", "3o B"]
    default: "3o B"
"""

START_NO_SETUP = """\
name: Sem setup
prologue: prologo cru
opening_scene: cena crua
hud:
  location: patio
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

LOREBOOK_ENTRY = """\
title: Segredo
keywords: [segredo]
scope: always
body: "O segredo pertence a {{player}}."
"""


def _write_scenario(root, scenario_id="exemplo-escola", *, starts=None, lorebook=None):
    starts = {"default.yaml": START_WITH_SETUP} if starts is None else starts

    scenario_path = root / scenario_id
    scenario_path.mkdir(parents=True)
    (scenario_path / "scenario.yaml").write_text(SCENARIO_YAML, encoding="utf-8")
    (scenario_path / "world.md").write_text(WORLD_MD, encoding="utf-8")

    starts_dir = scenario_path / "starts"
    starts_dir.mkdir()
    for filename, content in starts.items():
        (starts_dir / filename).write_text(content, encoding="utf-8")

    characters_dir = scenario_path / "characters"
    characters_dir.mkdir()
    (characters_dir / "chloe.yaml").write_text(CHLOE_YAML, encoding="utf-8")

    if lorebook is not None:
        lorebook_dir = scenario_path / "lorebook"
        lorebook_dir.mkdir()
        for filename, content in lorebook.items():
            (lorebook_dir / filename).write_text(content, encoding="utf-8")

    return scenario_path


def _config():
    return Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": {"narrator": {"provider": "local", "model": "m"}},
        }
    )


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("OOC_SESSIONS_DB", str(tmp_path / "sessions.db"))
    yield


@pytest.fixture
def scenarios_root(tmp_path, monkeypatch):
    root = tmp_path / "scenarios"
    root.mkdir()
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: root)
    return root


@pytest.fixture
def client():
    return TestClient(main.app)


# -- happy paths ---------------------------------------------------------


def test_create_session_with_answers_records_one_event_and_interpolates(scenarios_root, client):
    _write_scenario(scenarios_root)

    created = client.post(
        "/api/sessions",
        json={"scenarioId": "exemplo-escola", "setup": {"player": "Iury", "turma": "3o A"}},
    ).json()

    assert created["prologue"] == "Bem-vindo(a), Iury, ao Exemplo Escola via Começo."

    events = sessions.read_events(created["id"], kinds=("setup",))
    assert len(events) == 1
    assert events[0].payload["answers"] == {"player": "Iury", "turma": "3o A"}

    fetched = client.get(f"/api/sessions/{created['id']}").json()
    assert fetched["prologue"] == created["prologue"]


def test_create_session_defaults_fill_missing_answers(scenarios_root, client):
    _write_scenario(scenarios_root)

    created = client.post(
        "/api/sessions", json={"scenarioId": "exemplo-escola", "setup": {}}
    ).json()

    assert "Alex" in created["prologue"]

    events = sessions.read_events(created["id"], kinds=("setup",))
    assert events[0].payload["answers"] == {"player": "Alex", "turma": "3o B"}

    ctx = turn.load_turn_context(created["id"])
    assert ctx.start.opening_scene == "cena de 3o B"


def test_builtin_variables_resolve_scenario_start_player(scenarios_root, client):
    _write_scenario(scenarios_root)

    created = client.post(
        "/api/sessions",
        json={"scenarioId": "exemplo-escola", "setup": {"player": "Iury", "turma": "3o A"}},
    ).json()

    assert "Exemplo Escola" in created["prologue"]
    assert "Começo" in created["prologue"]
    assert "Iury" in created["prologue"]


def test_lorebook_body_interpolated_in_turn_context(scenarios_root):
    _write_scenario(scenarios_root, lorebook={"segredo.yaml": LOREBOOK_ENTRY})

    created = sessions.create_session("exemplo-escola", setup={"player": "Iury", "turma": "3o A"})
    ctx = turn.load_turn_context(created.id)

    assert ctx.scenario.lorebook["segredo"].body == "O segredo pertence a Iury."


def test_built_master_prompt_carries_all_interpolated_fields_and_lorebook(scenarios_root):
    """The point of the whole ticket: the prompt actually sent to the LLM,
    not just ctx.scenario/ctx.start, must show the resolved variables."""
    _write_scenario(scenarios_root, lorebook={"segredo.yaml": LOREBOOK_ENTRY})

    created = sessions.create_session("exemplo-escola", setup={"player": "Iury", "turma": "3o A"})
    ctx = turn.load_turn_context(created.id)

    prompt_text = build_master_prompt(
        ctx.scenario,
        ctx.start,
        ctx.row.hud,
        ctx.characters,
        lore=[ctx.scenario.lorebook["segredo"]],
    )

    assert "cena de 3o A" in prompt_text
    assert "conflito de Iury" in prompt_text
    assert "missao de 3o A" in prompt_text
    assert "O segredo pertence a Iury." in prompt_text


# -- edge cases -----------------------------------------------------------


def test_unknown_key_ignored_variable_unknown_and_unclosed_literal(scenarios_root):
    _write_scenario(scenarios_root)

    created = sessions.create_session(
        "exemplo-escola",
        setup={"player": "Iury", "turma": "3o A", "not-a-question": "ignored"},
    )

    ctx = turn.load_turn_context(created.id)
    assert "{{unknown}}" not in ctx.scenario.world
    assert "Ola, !" in ctx.scenario.world
    assert "{{ nome" in ctx.scenario.world


def test_session_without_setup_event_resolves_only_builtins(scenarios_root):
    _write_scenario(scenarios_root, starts={"default.yaml": START_NO_SETUP})

    created = sessions.create_session("exemplo-escola")

    assert sessions.read_events(created.id, kinds=("setup",)) == []
    assert created.prologue == "prologo cru"

    fetched = sessions.get_session(created.id)
    assert fetched.prologue == "prologo cru"


def test_apply_setup_does_not_mutate_loaded_scenario(scenarios_root):
    _write_scenario(scenarios_root)

    scenario = load_scenario("exemplo-escola")
    start = scenario.starts["default"]
    answers = SetupAnswers(answers={"player": "Iury", "turma": "3o A"})

    apply_setup(scenario, start, answers)

    reloaded = load_scenario("exemplo-escola")
    assert reloaded.starts["default"].prologue == start.prologue
    assert "{{player}}" in reloaded.starts["default"].prologue


def test_player_falls_back_to_empty_string_without_a_player_question(scenarios_root):
    _write_scenario(scenarios_root, starts={"default.yaml": START_NO_SETUP})

    scenario = load_scenario("exemplo-escola")
    start = scenario.starts["default"].model_copy(
        update={"prologue": "Ola, {{player}}! Sou {{scenario}} via {{start}}."}
    )
    answers = SetupAnswers(answers={})

    new_scenario, new_start = apply_setup(scenario, start, answers)

    assert new_start.prologue == "Ola, ! Sou Exemplo Escola via Sem setup."


def test_rewind_to_zero_and_to_a_middle_turn_keeps_the_setup_event(scenarios_root):
    """Setup is session-creation data, not turn history: it must survive any rewind."""
    _write_scenario(scenarios_root)

    created = sessions.create_session(
        "exemplo-escola", setup={"player": "Iury", "turma": "3o A"}
    )
    sessions.append_events(
        created.id,
        [
            ("player_turn", {"text": "turno 1", "mode": "do"}),
            ("narrator_turn", {"text": "narra 1", "suggestions": []}),
        ],
    )

    rewound_zero = sessions.rewind_session(created.id, 0)
    assert rewound_zero.prologue == "Bem-vindo(a), Iury, ao Exemplo Escola via Começo."
    assert len(sessions.read_events(created.id, kinds=("setup",))) == 1

    sessions.append_events(
        created.id,
        [
            ("player_turn", {"text": "turno 2", "mode": "do"}),
            ("narrator_turn", {"text": "narra 2", "suggestions": []}),
        ],
    )
    rewound_mid = sessions.rewind_session(created.id, 1)
    assert rewound_mid.prologue == "Bem-vindo(a), Iury, ao Exemplo Escola via Começo."
    assert len(sessions.read_events(created.id, kinds=("setup",))) == 1


def test_observability_events_carry_attribution_keys(scenarios_root, monkeypatch):
    emitted_setup: list[tuple[str, dict]] = []
    emitted_sessions: list[tuple[str, dict]] = []
    monkeypatch.setattr(setup_lib, "emit", lambda event, **props: emitted_setup.append((event, props)))
    monkeypatch.setattr(sessions, "emit", lambda event, **props: emitted_sessions.append((event, props)))

    _write_scenario(scenarios_root)

    created = sessions.create_session(
        "exemplo-escola", setup={"player": "Iury", "turma": "3o A"}
    )

    session_setup = [props for name, props in emitted_sessions if name == "session_setup"]
    assert len(session_setup) == 1
    assert session_setup[0]["session_id"] == created.id

    setup_applied = [props for name, props in emitted_setup if name == "setup_applied"]
    assert len(setup_applied) == 1
    assert setup_applied[0]["session_id"] == created.id
    assert setup_applied[0]["substitutions"] > 0

    unknown = [props for name, props in emitted_setup if name == "setup_unknown_variable"]
    assert len(unknown) == 1
    assert unknown[0]["session_id"] == created.id
    assert unknown[0]["name"] == "unknown"

    emitted_setup.clear()
    response_client = TestClient(main.app)
    response = response_client.post(
        "/api/sessions",
        json={"scenarioId": "exemplo-escola", "setup": {"player": "Iury", "turma": "3o C"}},
    )
    assert response.status_code == 422
    rejected = [props for name, props in emitted_setup if name == "setup_rejected"]
    assert len(rejected) == 1
    assert rejected[0]["scenario_id"] == "exemplo-escola"


def test_get_scenarios_lists_starts_with_setup_and_default_flag(scenarios_root, client):
    _write_scenario(
        scenarios_root,
        starts={"default.yaml": START_WITH_SETUP, "other.yaml": START_NO_SETUP},
    )

    data = client.get("/api/scenarios").json()
    assert len(data) == 1
    item = data[0]
    assert item["id"] == "exemplo-escola"
    assert item["name"] == "Exemplo Escola"
    assert item["tagline"] == "uma tagline"
    assert item["locale"] == "pt-br"

    starts = {s["id"]: s for s in item["starts"]}
    assert starts["default"]["isDefault"] is True
    assert starts["other"]["isDefault"] is False
    assert [q["id"] for q in starts["default"]["setup"]] == ["player", "turma"]
    assert starts["other"]["setup"] == []


# -- failures ---------------------------------------------------------------


def test_missing_answer_without_default_is_422(scenarios_root, client):
    starts = {
        "default.yaml": (
            "name: Começo\n"
            "prologue: p\n"
            "opening_scene: c\n"
            "hud:\n  location: patio\n"
            "setup:\n"
            "  - id: player\n"
            "    question: Como voce se chama?\n"
            "    type: text\n"
        )
    }
    _write_scenario(scenarios_root, starts=starts)

    response = client.post("/api/sessions", json={"scenarioId": "exemplo-escola", "setup": {}})

    assert response.status_code == 422
    assert "player" in response.json()["detail"]
    assert sessions.list_sessions() == []


def test_invalid_choice_is_422(scenarios_root, client):
    _write_scenario(scenarios_root)

    response = client.post(
        "/api/sessions",
        json={"scenarioId": "exemplo-escola", "setup": {"player": "Iury", "turma": "3o C"}},
    )

    assert response.status_code == 422
    assert sessions.list_sessions() == []


def test_answer_too_long_is_422(scenarios_root, client):
    _write_scenario(scenarios_root)

    response = client.post(
        "/api/sessions",
        json={
            "scenarioId": "exemplo-escola",
            "setup": {"player": "x" * 201, "turma": "3o A"},
        },
    )

    assert response.status_code == 422
    assert sessions.list_sessions() == []


def test_scenario_with_reserved_setup_id_fails_to_load(scenarios_root):
    starts = {
        "default.yaml": (
            "name: Começo\n"
            "prologue: p\n"
            "opening_scene: c\n"
            "hud:\n  location: patio\n"
            "setup:\n"
            "  - id: scenario\n"
            "    question: reservado\n"
            "    type: text\n"
            "    default: x\n"
        )
    }
    _write_scenario(scenarios_root, starts=starts)

    with pytest.raises(ScenarioError):
        load_scenario("exemplo-escola")


def test_scenario_with_setup_id_start_fails_to_load(scenarios_root):
    starts = {
        "default.yaml": (
            "name: Começo\n"
            "prologue: p\n"
            "opening_scene: c\n"
            "hud:\n  location: patio\n"
            "setup:\n"
            "  - id: start\n"
            "    question: reservado\n"
            "    type: text\n"
            "    default: x\n"
        )
    }
    _write_scenario(scenarios_root, starts=starts)

    with pytest.raises(ScenarioError):
        load_scenario("exemplo-escola")


def test_answer_at_exactly_setup_answer_chars_is_accepted(scenarios_root, client):
    from app.scenario import SETUP_ANSWER_CHARS

    _write_scenario(scenarios_root)

    response = client.post(
        "/api/sessions",
        json={
            "scenarioId": "exemplo-escola",
            "setup": {"player": "x" * SETUP_ANSWER_CHARS, "turma": "3o A"},
        },
    )

    assert response.status_code == 201


def test_resolve_answers_unit_missing_invalid_choice_and_too_long():
    from app.scenario import HudDefaults, SetupQuestion, StartConfig

    start = StartConfig(
        id="default",
        name="Começo",
        prologue="p",
        opening_scene="c",
        hud=HudDefaults(location="patio"),
        setup=[
            SetupQuestion(id="player", question="q", type="text"),
            SetupQuestion(id="turma", question="q2", type="choice", options=["A", "B"]),
        ],
    )

    with pytest.raises(SetupInvalid) as exc:
        resolve_answers(start, {"turma": "C"})
    assert set(exc.value.errors) == {"player", "turma"}


# -- kill switch --------------------------------------------------------


def test_kill_switch_disables_interpolation_and_validation(scenarios_root, client, monkeypatch):
    _write_scenario(scenarios_root)

    off_config = Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": {"narrator": {"provider": "local", "model": "m"}},
            "flags": {"setup": False},
        }
    )
    monkeypatch.setattr("app.setup.load_config", lambda: off_config)
    monkeypatch.setattr("app.sessions.load_config", lambda: off_config)

    created = client.post("/api/sessions", json={"scenarioId": "exemplo-escola", "setup": {}}).json()

    assert created["prologue"] == "Bem-vindo(a), {{player}}, ao {{scenario}} via {{start}}."


def test_kill_switch_skips_validation_even_when_required_answer_is_missing(scenarios_root, client, monkeypatch):
    """A question without a default would 422 with the flag on; off, it must
    not, because sessions.create_session skips resolve_answers entirely."""
    starts = {
        "default.yaml": (
            "name: Começo\n"
            "prologue: p\n"
            "opening_scene: c\n"
            "hud:\n  location: patio\n"
            "setup:\n"
            "  - id: player\n"
            "    question: Como voce se chama?\n"
            "    type: text\n"
            "  - id: turma\n"
            "    question: Em que turma?\n"
            "    type: choice\n"
            "    options: [\"3o A\", \"3o B\"]\n"
        )
    }
    _write_scenario(scenarios_root, starts=starts)

    off_config = Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": {"narrator": {"provider": "local", "model": "m"}},
            "flags": {"setup": False},
        }
    )
    monkeypatch.setattr("app.setup.load_config", lambda: off_config)
    monkeypatch.setattr("app.sessions.load_config", lambda: off_config)

    response = client.post(
        "/api/sessions",
        json={"scenarioId": "exemplo-escola", "setup": {"turma": "totalmente invalida"}},
    )

    assert response.status_code == 201
    events = sessions.read_events(response.json()["id"], kinds=("setup",))
    assert events[0].payload["answers"] == {"turma": "totalmente invalida"}


def test_builtin_variables_are_not_overridable_by_a_raw_answer(scenarios_root):
    """Reachable only with the flag off, where sessions.create_session stores
    raw client answers without going through resolve_answers."""
    _write_scenario(scenarios_root, starts={"default.yaml": START_NO_SETUP})

    scenario = load_scenario("exemplo-escola")
    start = scenario.starts["default"].model_copy(
        update={"prologue": "Ola de {{start}} em {{scenario}}."}
    )
    answers = SetupAnswers(answers={"start": "hacked", "scenario": "hacked"})

    _, new_start = apply_setup(scenario, start, answers)

    assert new_start.prologue == "Ola de Sem setup em Exemplo Escola."
