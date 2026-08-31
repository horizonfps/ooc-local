import asyncio
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import compact, main, sessions, turn
from app.compact import CompactError, estimate_tokens, fits
from app.config import Config
from app.llm.base import ChatMessage
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


def _write_scenario(root, scenario_id="exemplo-escola"):
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

    return scenario_path


def _config(flags=None):
    return Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": {
                "narrator": {"provider": "local", "model": "narrator-model"},
                "utility": {"provider": "local", "model": "utility-model"},
            },
            "flags": flags or {},
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


def _split_stream(deltas_by_model):
    async def fake_stream(self, messages, model):
        for delta in deltas_by_model[model]:
            yield delta

    return fake_stream


# ---------------------------------------------------------------------------
# estimate_tokens / fits
# ---------------------------------------------------------------------------


def test_estimate_tokens_empty_is_zero():
    assert estimate_tokens("") == 0


def test_estimate_tokens_matches_ceil_len_over_four():
    text = "café com pão açúcar" * 10
    assert estimate_tokens(text) == -(-len(text) // 4)


def test_fits_true_under_budget():
    messages = [ChatMessage(role="system", content="curto")]
    assert fits(messages) is True


def test_fits_false_over_budget():
    messages = [ChatMessage(role="system", content="x" * (compact.INPUT_BUDGET_TOKENS * 4 + 100))]
    assert fits(messages) is False


# ---------------------------------------------------------------------------
# compact_block
# ---------------------------------------------------------------------------


def test_compact_block_sends_previous_and_outgoing_to_utility(monkeypatch):
    captured = []

    async def fake_stream(self, messages, model):
        captured.append((messages, model))
        yield "resumo novo"

    monkeypatch.setattr(compact, "load_config", lambda: _config())
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    outgoing = [
        ChatMessage(role="user", content="jogador foi ate a sala"),
        ChatMessage(role="assistant", content="narrador descreveu a sala"),
    ]

    result = compact.compact_block("resumo antigo", outgoing, "pt-br")

    text = asyncio.run(result)

    assert text == "resumo novo"
    messages, model = captured[0]
    assert model == "utility-model"
    prompt_text = "\n".join(m.content for m in messages)
    assert "resumo antigo" in prompt_text
    assert "jogador foi ate a sala" in prompt_text
    assert "narrador descreveu a sala" in prompt_text


def test_compact_block_raises_compact_error_on_provider_failure(monkeypatch):
    async def fake_stream(self, messages, model):
        raise RuntimeError("provider exploded")
        yield  # pragma: no cover

    monkeypatch.setattr(compact, "load_config", lambda: _config())
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with pytest.raises(CompactError):
        asyncio.run(compact.compact_block(None, [], "pt-br"))


def test_compact_block_raises_compact_error_on_empty_result(monkeypatch):
    async def fake_stream(self, messages, model):
        yield "   "

    monkeypatch.setattr(compact, "load_config", lambda: _config())
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with pytest.raises(CompactError):
        asyncio.run(compact.compact_block(None, [], "pt-br"))


# ---------------------------------------------------------------------------
# LLMProvider.complete()
# ---------------------------------------------------------------------------


def test_complete_joins_stream_chat_deltas(monkeypatch):
    async def fake_stream(self, messages, model):
        for delta in ["ola", " ", "mundo"]:
            yield delta

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)
    provider = OpenAICompatProvider(_config().providers["local"])

    text = asyncio.run(provider.complete([ChatMessage(role="user", content="oi")], "m"))
    assert text == "ola mundo"


# ---------------------------------------------------------------------------
# run_turn integration
# ---------------------------------------------------------------------------


def test_short_history_skips_compact_and_matches_tck006(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(compact, "load_config", lambda: _config())
    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _split_stream({"narrator-model": ["voce anda ate a Chloe."]}),
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "vou ate a Chloe"}
    ) as response:
        events = _stream_events(response)

    assert events[-1]["hud"]["turn"] == 1
    assert sessions.get_compact(session["id"]) is None
    compact_events = [e for e in sessions.read_events(session["id"]) if e.kind == "compact"]
    assert compact_events == []


def test_budget_overflow_triggers_compact_and_context_gets_resumo(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(compact, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    long_pairs = []
    for i in range(18):
        long_pairs.append(("player_turn", {"text": f"jogador {i} " + "lorem " * 500}))
        long_pairs.append(("narrator_turn", {"text": f"narrador {i} " + "ipsum " * 500}))
    sessions.append_events(session["id"], long_pairs)

    captured_narrator = []

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            yield "Resumo: promessa feita, conflito aberto com Chloe."
        else:
            captured_narrator.append(messages)
            yield "voce continua andando."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "proximo turno"}
    ) as response:
        events = _stream_events(response)

    assert events[-1]["hud"]["turn"] == 1
    assert sessions.get_compact(session["id"]) == "Resumo: promessa feita, conflito aberto com Chloe."

    compact_events = [e for e in sessions.read_events(session["id"]) if e.kind == "compact"]
    assert len(compact_events) == 1
    assert compact_events[0].payload["text"] == "Resumo: promessa feita, conflito aberto com Chloe."

    narrator_messages = captured_narrator[0]
    system_content = narrator_messages[0].content
    assert "RESUMO DA CAMPANHA" in system_content
    assert "Resumo: promessa feita" in system_content

    all_content_tokens = sum(estimate_tokens(m.content) for m in narrator_messages)
    assert all_content_tokens <= compact.INPUT_BUDGET_TOKENS


def test_second_turn_reuses_compact_without_calling_utility_again(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(compact, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    # Session already carries a compact from a previous compaction, and the
    # window that remains after it is short enough to fit the budget again.
    sessions.set_compact(
        session["id"],
        "Resumo do bloco antigo.",
        {"replaced_turns": 3, "from_index": 0, "to_index": 3},
    )
    sessions.append_events(
        session["id"],
        [("player_turn", {"text": "turno curto anterior"}), ("narrator_turn", {"text": "resposta curta"})],
    )

    utility_calls = []

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            utility_calls.append(messages)
            yield "novo resumo, nao deveria ser chamado"
        else:
            yield "voce continua andando."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "proximo turno curto"}
    ) as response:
        _stream_events(response)

    assert utility_calls == []
    assert sessions.get_compact(session["id"]) == "Resumo do bloco antigo."


def test_second_compaction_replaces_previous_compact(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(compact, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    def _push_long_pairs():
        pairs = []
        for i in range(18):
            pairs.append(("player_turn", {"text": f"jogador {i} " + "lorem " * 500}))
            pairs.append(("narrator_turn", {"text": f"narrador {i} " + "ipsum " * 500}))
        sessions.append_events(session["id"], pairs)

    _push_long_pairs()

    utility_prompts = []
    responses = iter(["Primeiro resumo.", "Segundo resumo substitui o primeiro."])

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            utility_prompts.append(messages)
            yield next(responses)
        else:
            yield "voce continua andando."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "turno 1"}
    ) as response:
        _stream_events(response)

    assert sessions.get_compact(session["id"]) == "Primeiro resumo."

    _push_long_pairs()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "turno 2"}
    ) as response:
        _stream_events(response)

    assert len(utility_prompts) == 2
    second_prompt_text = "\n".join(m.content for m in utility_prompts[1])
    assert "Primeiro resumo." in second_prompt_text
    assert sessions.get_compact(session["id"]) == "Segundo resumo substitui o primeiro."


def test_utility_failure_falls_back_to_truncated_window(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(compact, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    long_pairs = []
    for i in range(18):
        long_pairs.append(("player_turn", {"text": f"jogador {i} " + "lorem " * 500}))
        long_pairs.append(("narrator_turn", {"text": f"narrador {i} " + "ipsum " * 500}))
    sessions.append_events(session["id"], long_pairs)

    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            raise RuntimeError("utility offline")
            yield  # pragma: no cover
        yield "voce continua andando mesmo assim."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "proximo turno"}
    ) as response:
        events = _stream_events(response)

    assert events[-1]["hud"]["turn"] == 1
    assert sessions.get_compact(session["id"]) is None
    compact_events = [e for e in sessions.read_events(session["id"]) if e.kind == "compact"]
    assert compact_events == []

    compact_run = next(props for name, props in emitted if name == "compact_run")
    assert compact_run["error"] is not None


def test_flag_compact_false_behaves_like_tck006(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    disabled_config = _config(flags={"compact": False})
    monkeypatch.setattr(main, "load_config", lambda: disabled_config)
    monkeypatch.setattr(turn, "load_config", lambda: disabled_config)
    monkeypatch.setattr(compact, "load_config", lambda: disabled_config)
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    long_pairs = []
    for i in range(18):
        long_pairs.append(("player_turn", {"text": f"jogador {i} " + "lorem " * 500}))
        long_pairs.append(("narrator_turn", {"text": f"narrador {i} " + "ipsum " * 500}))
    sessions.append_events(session["id"], long_pairs)

    utility_calls = []

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            utility_calls.append(messages)
            yield "nao deveria ser chamado"
        else:
            yield "voce continua andando."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "proximo turno"}
    ) as response:
        _stream_events(response)

    assert utility_calls == []
    assert sessions.get_compact(session["id"]) is None


# ---------------------------------------------------------------------------
# migration
# ---------------------------------------------------------------------------


def test_init_db_migrates_old_schema_without_compact_column(tmp_path, monkeypatch):
    db_path = tmp_path / "old.db"
    monkeypatch.setenv("OOC_SESSIONS_DB", str(db_path))

    old_conn = sqlite3.connect(db_path)
    old_conn.executescript(
        """
        CREATE TABLE sessions (
          id            TEXT PRIMARY KEY,
          scenario_id   TEXT NOT NULL,
          scenario_name TEXT NOT NULL,
          start_id      TEXT NOT NULL,
          created_at    TEXT NOT NULL,
          updated_at    TEXT NOT NULL,
          hud           TEXT NOT NULL
        );
        CREATE TABLE events (
          id         INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id TEXT NOT NULL REFERENCES sessions(id),
          seq        INTEGER NOT NULL,
          kind       TEXT NOT NULL,
          payload    TEXT NOT NULL,
          created_at TEXT NOT NULL,
          UNIQUE(session_id, seq)
        );
        """
    )
    old_conn.execute(
        "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("s1", "exemplo-escola", "Exemplo", "default", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", "{}"),
    )
    old_conn.commit()
    old_conn.close()

    sessions.init_db()
    sessions.init_db()

    assert sessions.get_compact("s1") is None

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT scenario_id FROM sessions WHERE id = 's1'").fetchone()
    conn.close()
    assert row[0] == "exemplo-escola"
