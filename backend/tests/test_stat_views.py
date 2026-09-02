import pytest
from fastapi.testclient import TestClient

from app import main
from app.cast import MindView, minds_event
from app.hud import DynamicStat, HudState, stat_views
from app.scenario import StatDef, StatLevel

WORLD_MD = "# Mundo\n\nUma escola.\n"

SCENARIO_YAML = """\
name: Exemplo Escola
tagline: uma tagline
locale: pt-br
"""

DEFAULT_START = """\
name: Começo
prologue: prologo
opening_scene: cena
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

STATS_TWO = """\
- id: reputacao
  name: Reputação
  min: 0
  max: 100
  default: 50
  levels:
    - from: 0
      text: desconhecido
    - from: 40
      text: conhecido
    - from: 80
      text: famoso
- id: energia
  name: Energia
  min: 0
  max: 10
  default: 5
"""


def _write_scenario(root, scenario_id, *, stats=None):
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

    if stats is not None:
        (scenario_path / "stats.yaml").write_text(stats, encoding="utf-8")

    return scenario_path


@pytest.fixture
def scenarios_root(tmp_path, monkeypatch):
    root = tmp_path / "scenarios"
    root.mkdir()
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: root)
    return root


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("OOC_SESSIONS_DB", str(tmp_path / "sessions.db"))
    yield


def _make_scenario(scenarios_root):
    from app.scenario import load_scenario

    _write_scenario(scenarios_root, "exemplo-escola", stats=STATS_TWO)
    return load_scenario("exemplo-escola")


def test_stat_views_uses_hud_value_or_default_in_scenario_order(scenarios_root):
    scenario = _make_scenario(scenarios_root)
    hud = HudState(location="patio", time="08:00", weather="clear", stats={"reputacao": 55})

    views = stat_views(scenario, hud)

    assert [v.id for v in views] == ["reputacao", "energia"]
    assert views[0].value == 55
    assert views[1].value == 5


def test_stat_views_level_is_last_from_lte_value(scenarios_root):
    scenario = _make_scenario(scenarios_root)

    hud_low = HudState(location="patio", time="08:00", weather="clear", stats={"reputacao": 60})
    assert stat_views(scenario, hud_low)[0].level == "conhecido"

    hud_high = HudState(location="patio", time="08:00", weather="clear", stats={"reputacao": 90})
    assert stat_views(scenario, hud_high)[0].level == "famoso"


def test_stat_views_value_below_first_from_is_none(scenarios_root):
    scenario = _make_scenario(scenarios_root)
    hud = HudState(location="patio", time="08:00", weather="clear", stats={"reputacao": -5})

    views = stat_views(scenario, hud)

    assert views[0].level is None


def test_stat_views_stat_without_levels_is_none(scenarios_root):
    scenario = _make_scenario(scenarios_root)
    hud = HudState(location="patio", time="08:00", weather="clear", stats={"energia": 7})

    views = stat_views(scenario, hud)

    assert views[1].level is None


def test_stat_views_ignores_hud_stat_id_no_longer_in_scenario(scenarios_root):
    scenario = _make_scenario(scenarios_root)
    hud = HudState(
        location="patio",
        time="08:00",
        weather="clear",
        stats={"reputacao": 10, "extinto": 999},
    )

    views = stat_views(scenario, hud)

    assert [v.id for v in views] == ["reputacao", "energia"]


def test_stat_views_dynamic_stats_come_after_declared_with_none_fields(scenarios_root):
    scenario = _make_scenario(scenarios_root)
    hud = HudState(
        location="patio",
        time="08:00",
        weather="clear",
        dynamic_stats={"sanidade": DynamicStat(name="Sanidade", value=3, max=10)},
    )

    views = stat_views(scenario, hud)

    assert [v.id for v in views] == ["reputacao", "energia", "sanidade"]
    dynamic_view = views[-1]
    assert dynamic_view.icon is None
    assert dynamic_view.color is None
    assert dynamic_view.level is None
    assert dynamic_view.value == 3


def test_mind_view_and_minds_event_contract():
    entries = {"chloe": MindView(attitude="curiosa", emoji="🙂", event="conheceu o jogador")}

    kind, payload = minds_event(entries)

    assert kind == "minds"
    assert payload == {
        "entries": {"chloe": {"attitude": "curiosa", "emoji": "🙂", "event": "conheceu o jogador"}}
    }


def test_session_detail_defaults_for_minds_commands_suggestions_and_turn_view(client, scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")

    response = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"})

    body = response.json()
    assert body["minds"] == {}
    assert body["commands"] == []
    assert body["suggestions"] == []


def test_post_sessions_route_returns_stats_with_defaults_and_saves_hud(client, scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola", stats=STATS_TWO)

    response = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"})

    assert response.status_code == 201
    body = response.json()
    assert {(s["id"], s["value"]) for s in body["stats"]} == {("reputacao", 50), ("energia", 5)}
    assert body["hud"]["stats"] == {"reputacao": 50, "energia": 5}

    get_response = client.get(f"/api/sessions/{body['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["stats"] == body["stats"]


def test_get_session_route_with_legacy_hud_missing_stats_key_responds_with_defaults(
    client, scenarios_root
):
    from app import sessions as sessions_module

    _write_scenario(scenarios_root, "exemplo-escola", stats=STATS_TWO)
    detail = sessions_module.create_session("exemplo-escola")

    conn = sessions_module._connect()
    try:
        conn.execute(
            "UPDATE sessions SET hud = ? WHERE id = ?",
            ('{"turn": 0, "location": "patio", "time": "08:00", "weather": "clear"}', detail.id),
        )
        conn.commit()
    finally:
        conn.close()

    response = client.get(f"/api/sessions/{detail.id}")

    assert response.status_code == 200
    body = response.json()
    assert {(s["id"], s["value"]) for s in body["stats"]} == {("reputacao", 50), ("energia", 5)}


def test_turn_route_accepts_valid_mode_and_rejects_invalid_mode(client, scenarios_root, monkeypatch):
    from app import main as main_module
    from app import turn as turn_module
    from app.config import Config
    from app.llm.openai_compat import OpenAICompatProvider

    def _config():
        return Config.model_validate(
            {
                "providers": {"local": {"base_url": "http://x/v1"}},
                "models": {"narrator": {"provider": "local", "model": "m"}},
            }
        )

    async def fake_stream(self, messages, model):
        yield "ok"

    _write_scenario(scenarios_root, "exemplo-escola")
    monkeypatch.setattr(main_module, "load_config", _config)
    monkeypatch.setattr(turn_module, "load_config", _config)
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    create = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"})
    session_id = create.json()["id"]

    good_response = client.post(
        f"/api/sessions/{session_id}/turn", json={"message": "oi", "mode": "say"}
    )
    assert good_response.status_code == 200

    bad_response = client.post(
        f"/api/sessions/{session_id}/turn", json={"message": "oi", "mode": "gritar"}
    )
    assert bad_response.status_code == 422
