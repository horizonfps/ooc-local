import asyncio
import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from app import compact, main, sessions, turn
from app.compact import COMPACT_OPTIONS, COMPACT_RESERVE_TOKENS, CompactError, estimate_tokens, fits
from app.config import Config
from app.llm.base import ChatMessage, GenerationOptions
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
# GenerationOptions / OpenAICompatProvider.build_payload / timeout budget
# ---------------------------------------------------------------------------


def test_build_payload_without_options_omits_max_tokens_and_temperature():
    provider = OpenAICompatProvider(_config().providers["local"])
    payload = provider.build_payload([ChatMessage(role="user", content="oi")], "m")

    assert "max_tokens" not in payload
    assert "temperature" not in payload
    assert payload["stream"] is True


def test_build_payload_with_compact_options_includes_max_tokens_and_temperature():
    provider = OpenAICompatProvider(_config().providers["local"], COMPACT_OPTIONS)
    payload = provider.build_payload([ChatMessage(role="user", content="oi")], "m")

    assert payload["max_tokens"] == 400
    assert payload["temperature"] == 0.2
    assert payload["stream"] is True


def test_compact_max_tokens_is_below_compact_reserve_tokens():
    assert COMPACT_OPTIONS.max_tokens < COMPACT_RESERVE_TOKENS


def test_generation_options_defaults_have_no_max_tokens_or_temperature():
    options = GenerationOptions()
    assert options.timeout_s == 120.0
    assert options.max_tokens is None
    assert options.temperature is None

    provider = OpenAICompatProvider(_config().providers["local"], options)
    payload = provider.build_payload([ChatMessage(role="user", content="oi")], "m")
    assert "max_tokens" not in payload
    assert "temperature" not in payload


def test_generation_options_zero_temperature_is_kept_in_payload():
    options = GenerationOptions(temperature=0.0)
    provider = OpenAICompatProvider(_config().providers["local"], options)
    payload = provider.build_payload([ChatMessage(role="user", content="oi")], "m")

    assert payload["temperature"] == 0.0


def test_provider_options_timeout_s_matches_construction():
    with_options = OpenAICompatProvider(_config().providers["local"], COMPACT_OPTIONS)
    without_options = OpenAICompatProvider(_config().providers["local"])

    assert with_options.options.timeout_s == 180.0
    assert without_options.options.timeout_s == 120.0


def test_compact_block_builds_provider_with_compact_options(monkeypatch):
    captured_self = []

    async def fake_stream(self, messages, model):
        captured_self.append(self)
        yield "resumo novo"

    monkeypatch.setattr(compact, "load_config", lambda: _config())
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    asyncio.run(compact.compact_block(None, [], "pt-br"))

    assert captured_self[0].options == COMPACT_OPTIONS


def test_timeout_reaches_httpx_client_from_provider_options(monkeypatch):
    captured_timeouts = []

    class _FakeResponse:
        def raise_for_status(self):
            pass

        async def aiter_lines(self):
            yield "data: [DONE]"

    class _FakeStreamCtx:
        async def __aenter__(self):
            return _FakeResponse()

        async def __aexit__(self, *args):
            return False

    class _FakeClient:
        def __init__(self, timeout=None):
            captured_timeouts.append(timeout)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def stream(self, *args, **kwargs):
            return _FakeStreamCtx()

    monkeypatch.setattr("app.llm.openai_compat.httpx.AsyncClient", _FakeClient)

    provider_with_options = OpenAICompatProvider(_config().providers["local"], COMPACT_OPTIONS)
    asyncio.run(
        provider_with_options.complete([ChatMessage(role="user", content="oi")], "m")
    )

    provider_without_options = OpenAICompatProvider(_config().providers["local"])
    asyncio.run(
        provider_without_options.complete([ChatMessage(role="user", content="oi")], "m")
    )

    assert captured_timeouts[0].read == 180.0
    assert captured_timeouts[1].read == 120.0


def test_compact_block_en_locale_uses_english_template(monkeypatch):
    captured = []

    async def fake_stream(self, messages, model):
        captured.append(messages)
        yield "summary"

    monkeypatch.setattr(compact, "load_config", lambda: _config())
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    outgoing = [
        ChatMessage(role="user", content="player walked to the room"),
        ChatMessage(role="assistant", content="narrator described the room"),
    ]

    asyncio.run(compact.compact_block("previous summary", outgoing, "en"))

    prompt_text = "\n".join(m.content for m in captured[0])
    assert "PREVIOUS SUMMARY" in prompt_text
    assert "TURNS LEAVING THE WINDOW" in prompt_text
    assert "RESUMO ANTERIOR" not in prompt_text
    assert "TURNOS QUE SAEM DA JANELA" not in prompt_text


def test_compact_block_raises_compact_error_on_timeout(monkeypatch):
    async def fake_stream(self, messages, model):
        raise httpx.TimeoutException("utility travou")
        yield  # pragma: no cover

    monkeypatch.setattr(compact, "load_config", lambda: _config())
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with pytest.raises(CompactError):
        asyncio.run(compact.compact_block(None, [], "pt-br"))


# ---------------------------------------------------------------------------
# history_events / events_to_messages / select_window
# ---------------------------------------------------------------------------


def test_history_events_filters_by_compact_seq(scenarios_root):
    _write_scenario(scenarios_root)
    session = sessions.create_session("exemplo-escola")

    pairs = []
    for i in range(3):
        pairs.append(("player_turn", {"text": f"jogador {i}"}))
        pairs.append(("narrator_turn", {"text": f"narrador {i}"}))
    sessions.append_events(session.id, pairs)

    assert len(turn.history_events(session.id, None)) == 6

    from_seq_4 = turn.history_events(session.id, 4)
    assert [e.seq for e in from_seq_4] == [5, 6]

    assert turn.history_events(session.id, 999) == []


def test_events_to_messages_is_order_preserving_and_one_to_one(scenarios_root):
    _write_scenario(scenarios_root)
    session = sessions.create_session("exemplo-escola")
    sessions.append_events(
        session.id,
        [
            ("player_turn", {"text": "primeira fala"}),
            ("narrator_turn", {"text": "primeira resposta"}),
            ("player_turn", {"text": "segunda fala"}),
        ],
    )

    events = turn.history_events(session.id, None)
    messages = turn.events_to_messages(events)

    assert len(messages) == len(events)
    assert [m.role for m in messages] == ["user", "assistant", "user"]
    assert [m.content for m in messages] == ["primeira fala", "primeira resposta", "segunda fala"]


def test_select_window_always_returns_an_even_count():
    huge = "x" * (compact.INPUT_BUDGET_TOKENS * 4)
    system = ChatMessage(role="system", content="s")
    tail = ChatMessage(role="user", content="t")
    history = [
        ChatMessage(role="user", content=huge),
        ChatMessage(role="assistant", content=huge),
        ChatMessage(role="user", content=huge),
        ChatMessage(role="assistant", content=huge),
    ]

    n = compact.select_window(system, history, tail, turn.WINDOW_TURNS, compact.COMPACT_KEEP_TURNS)

    assert n % 2 == 0
    assert n == 2


def _short_pairs(count):
    history = []
    for i in range(count):
        history.append(ChatMessage(role="user", content=f"jogador {i}"))
        history.append(ChatMessage(role="assistant", content=f"narrador {i}"))
    return history


def test_select_window_count_trigger_with_hysteresis():
    system = ChatMessage(role="system", content="s")
    tail = ChatMessage(role="user", content="t")

    for pairs, expected_n in [(19, 20), (20, 22), (27, 36)]:
        history = _short_pairs(pairs)
        n = compact.select_window(system, history, tail, 18, compact.COMPACT_KEEP_TURNS)
        assert n == expected_n
        assert (len(history) - n) // 2 == compact.COMPACT_KEEP_TURNS


def test_select_window_exactly_window_turns_does_not_compact():
    system = ChatMessage(role="system", content="s")
    tail = ChatMessage(role="user", content="t")
    history = _short_pairs(18)

    assert compact.select_window(system, history, tail, 18, compact.COMPACT_KEEP_TURNS) == 0


def test_select_window_budget_trigger_without_count_trigger():
    system = ChatMessage(role="system", content="s")
    tail = ChatMessage(role="user", content="t")
    huge = "x" * (compact.INPUT_BUDGET_TOKENS * 4)
    history = []
    for _ in range(12):
        history.append(ChatMessage(role="user", content=huge))
        history.append(ChatMessage(role="assistant", content=huge))

    n = compact.select_window(system, history, tail, 18, compact.COMPACT_KEEP_TURNS)

    assert n > 0


def test_select_window_reserve_forces_extra_drop():
    system = ChatMessage(role="system", content="s")
    tail = ChatMessage(role="user", content="t")
    budget = compact.INPUT_BUDGET_TOKENS
    near_budget_chars = (budget - 300) * 4
    history = [
        ChatMessage(role="user", content="x" * (near_budget_chars // 2)),
        ChatMessage(role="assistant", content="x" * (near_budget_chars // 2)),
        ChatMessage(role="user", content="curto"),
        ChatMessage(role="assistant", content="curto"),
    ]

    assert compact.fits([system, *history, tail]) is True

    n = compact.select_window(system, history, tail, 18, compact.COMPACT_KEEP_TURNS)

    assert n > 0


def test_select_window_never_empties_the_window():
    system = ChatMessage(role="system", content="s")
    tail = ChatMessage(role="user", content="t")
    huge = "x" * (compact.INPUT_BUDGET_TOKENS * 4)
    history = [
        ChatMessage(role="user", content=huge),
        ChatMessage(role="assistant", content=huge),
    ]

    assert compact.select_window(system, history, tail, 18, compact.COMPACT_KEEP_TURNS) == 0


def test_select_window_empty_history_returns_zero():
    system = ChatMessage(role="system", content="s")
    tail = ChatMessage(role="user", content="t")

    assert compact.select_window(system, [], tail, 18, compact.COMPACT_KEEP_TURNS) == 0


def test_select_window_keep_turns_larger_than_history_returns_zero():
    system = ChatMessage(role="system", content="s")
    tail = ChatMessage(role="user", content="t")
    history = _short_pairs(5)

    assert compact.select_window(system, history, tail, 18, keep_turns=9) == 0


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
    assert sessions.get_compact(session["id"])[0] is None
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
    resumo, covered_seq = sessions.get_compact(session["id"])
    assert resumo == "Resumo: promessa feita, conflito aberto com Chloe."

    compact_events = [e for e in sessions.read_events(session["id"]) if e.kind == "compact"]
    assert len(compact_events) == 1
    assert compact_events[0].payload["text"] == "Resumo: promessa feita, conflito aberto com Chloe."
    assert compact_events[0].payload["to_seq"] == covered_seq
    assert compact_events[0].payload["from_seq"] <= compact_events[0].payload["to_seq"]

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
        0,
        {"replaced_turns": 3, "from_seq": 0, "to_seq": 0},
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
    assert sessions.get_compact(session["id"])[0] == "Resumo do bloco antigo."


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

    assert sessions.get_compact(session["id"])[0] == "Primeiro resumo."

    _push_long_pairs()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "turno 2"}
    ) as response:
        _stream_events(response)

    assert len(utility_prompts) == 2
    second_prompt_text = "\n".join(m.content for m in utility_prompts[1])
    assert "Primeiro resumo." in second_prompt_text
    assert sessions.get_compact(session["id"])[0] == "Segundo resumo substitui o primeiro."


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
    assert sessions.get_compact(session["id"])[0] is None
    compact_events = [e for e in sessions.read_events(session["id"]) if e.kind == "compact"]
    assert compact_events == []

    compact_run = next(props for name, props in emitted if name == "compact_run")
    assert compact_run["error"] is not None


def test_utility_timeout_falls_back_to_truncated_window(scenarios_root, monkeypatch):
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
            raise httpx.TimeoutException("utility travou")
            yield  # pragma: no cover
        yield "voce continua andando mesmo assim."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "proximo turno"}
    ) as response:
        events = _stream_events(response)

    assert events[-1]["hud"]["turn"] == 1
    assert sessions.get_compact(session["id"])[0] is None
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
    assert sessions.get_compact(session["id"])[0] is None


def test_budget_overflow_with_more_than_window_turns_covers_full_history(scenarios_root, monkeypatch):
    """22 pairs not covered by any prior compact: this is the case that let the
    original defect through, because it exceeds WINDOW_TURNS (18)."""
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(compact, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    long_pairs = []
    for i in range(22):
        long_pairs.append(("player_turn", {"text": f"jogador {i} " + "lorem " * 500}))
        long_pairs.append(("narrator_turn", {"text": f"narrador {i} " + "ipsum " * 500}))
    sessions.append_events(session["id"], long_pairs)

    seq_to_text = {e.seq: e.payload["text"] for e in sessions.read_events(session["id"])}

    utility_prompts = []
    captured_narrator = []

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            utility_prompts.append(messages)
            yield "Resumo dos 22 pares."
        else:
            captured_narrator.append(messages)
            yield "voce continua andando."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "proximo turno"}
    ) as response:
        _stream_events(response)

    resumo, covered_seq = sessions.get_compact(session["id"])
    assert resumo == "Resumo dos 22 pares."

    compact_events = [e for e in sessions.read_events(session["id"]) if e.kind == "compact"]
    assert len(compact_events) == 1
    assert compact_events[0].payload["to_seq"] == covered_seq

    # The candidate window must have been built over the FULL 22 pairs, not a
    # window already truncated to the last 18: the first summarized turn is
    # the very first turn of the session.
    assert compact_events[0].payload["from_seq"] == min(seq_to_text)

    summarized_texts = [text for seq, text in seq_to_text.items() if seq <= covered_seq]
    remaining_texts = [text for seq, text in seq_to_text.items() if seq > covered_seq]
    assert summarized_texts
    assert remaining_texts

    utility_prompt_text = "\n".join(m.content for m in utility_prompts[0])
    narrator_prompt_text = "\n".join(m.content for m in captured_narrator[0])

    for text in summarized_texts:
        assert text in utility_prompt_text
        assert text not in narrator_prompt_text
    for text in remaining_texts:
        assert text in narrator_prompt_text
        assert text not in utility_prompt_text

    first_remaining_seq = min(seq for seq in seq_to_text if seq > covered_seq)
    assert captured_narrator[0][1].content == seq_to_text[first_remaining_seq]


def test_25_short_pairs_trigger_compact_by_count(scenarios_root, monkeypatch):
    """More than WINDOW_TURNS pairs, light enough to fit the budget on their
    own: the count trigger fires anyway (TCK-024), leaving keep_turns pairs
    in the window instead of silently keeping all of them uncovered."""
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(compact, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    pairs = []
    for i in range(25):
        pairs.append(("player_turn", {"text": f"jogador {i:02d}"}))
        pairs.append(("narrator_turn", {"text": f"narrador {i:02d}"}))
    sessions.append_events(session["id"], pairs)

    seq_to_text = {e.seq: e.payload["text"] for e in sessions.read_events(session["id"])}

    utility_prompts = []
    captured_narrator = []

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            utility_prompts.append(messages)
            yield "Resumo dos 25 pares curtos."
        else:
            captured_narrator.append(messages)
            yield "voce continua andando."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "proximo turno"}
    ) as response:
        _stream_events(response)

    resumo, covered_seq = sessions.get_compact(session["id"])
    assert resumo == "Resumo dos 25 pares curtos."

    # 25 pairs, keep_turns=9: 16 pairs (32 messages) leave the window.
    summarized_texts = [text for seq, text in seq_to_text.items() if seq <= covered_seq]
    remaining_texts = [text for seq, text in seq_to_text.items() if seq > covered_seq]
    assert len(summarized_texts) == 32
    assert len(remaining_texts) == 18

    utility_prompt_text = "\n".join(m.content for m in utility_prompts[0])
    narrator_prompt_text = "\n".join(m.content for m in captured_narrator[0])

    for text in summarized_texts:
        assert text in utility_prompt_text
        assert text not in narrator_prompt_text
    for text in remaining_texts:
        assert text in narrator_prompt_text
        assert text not in utility_prompt_text

    first_remaining_seq = min(seq for seq in seq_to_text if seq > covered_seq)
    assert captured_narrator[0][1].content == seq_to_text[first_remaining_seq]


def test_19_short_pairs_call_utility_once_and_include_oldest_pair(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(compact, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    pairs = []
    for i in range(19):
        pairs.append(("player_turn", {"text": f"jogador {i}"}))
        pairs.append(("narrator_turn", {"text": f"narrador {i}"}))
    sessions.append_events(session["id"], pairs)

    utility_calls = []

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            utility_calls.append(messages)
            yield "Resumo dos 19 pares."
        else:
            yield "voce continua andando."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "proximo turno"}
    ) as response:
        _stream_events(response)

    assert len(utility_calls) == 1
    prompt_text = "\n".join(m.content for m in utility_calls[0])
    assert "jogador 0" in prompt_text


def test_hysteresis_needs_ten_new_turns_after_a_count_triggered_compact(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(compact, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    pairs = []
    for i in range(19):
        pairs.append(("player_turn", {"text": f"jogador {i}"}))
        pairs.append(("narrator_turn", {"text": f"narrador {i}"}))
    sessions.append_events(session["id"], pairs)

    utility_calls = []

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            utility_calls.append(messages)
            yield "Resumo."
        else:
            yield "voce continua andando."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    # Turn 0: triggers the compaction from the 19 pre-stored pairs.
    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "turno 0"}
    ) as response:
        _stream_events(response)
    assert len(utility_calls) == 1

    # Turns 1..9: hysteresis holds, no new compaction.
    for i in range(1, 10):
        with client.stream(
            "POST", f"/api/sessions/{session['id']}/turn", json={"message": f"turno {i}"}
        ) as response:
            _stream_events(response)
        assert len(utility_calls) == 1

    # Turn 10: back over the threshold, compacts again.
    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "turno 10"}
    ) as response:
        _stream_events(response)
    assert len(utility_calls) == 2


def test_compact_overflow_emitted_when_new_summary_still_does_not_fit(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(compact, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    pairs = []
    for i in range(19):
        pairs.append(("player_turn", {"text": f"jogador {i}"}))
        pairs.append(("narrator_turn", {"text": f"narrador {i}"}))
    sessions.append_events(session["id"], pairs)

    huge_summary = "x" * (compact.INPUT_BUDGET_TOKENS * 4 * 2)

    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            yield huge_summary
        else:
            yield "voce continua andando mesmo assim."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "proximo turno"}
    ) as response:
        events = _stream_events(response)

    assert events[-1]["hud"]["turn"] == 1

    overflow = next(props for name, props in emitted if name == "compact_overflow")
    assert overflow["dropped_turns"] > 0
    assert overflow["compact_tokens"] > 0
    assert overflow["session_id"] == session["id"]
    assert sessions.get_compact(session["id"])[0] == huge_summary


def test_40_short_turns_compact_at_most_four_times(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(compact, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            yield "Resumo curto."
        else:
            yield "voce continua andando."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    for i in range(40):
        with client.stream(
            "POST", f"/api/sessions/{session['id']}/turn", json={"message": f"turno {i}"}
        ) as response:
            _stream_events(response)

    compact_runs = [props for name, props in emitted if name == "compact_run"]
    overflows = [props for name, props in emitted if name == "compact_overflow"]

    assert len(compact_runs) <= 4
    assert all(props["error"] is None for props in compact_runs)
    assert overflows == []


def test_compact_seq_beyond_all_events_yields_empty_history(scenarios_root):
    _write_scenario(scenarios_root)
    session = sessions.create_session("exemplo-escola")
    sessions.append_events(
        session.id,
        [("player_turn", {"text": "fala"}), ("narrator_turn", {"text": "resposta"})],
    )

    full = turn.history_events(session.id, 999)
    assert full == []

    messages = turn.build_context(session.id, "mensagem nova", compact_seq=999, history=full)
    assert len(messages) == 2
    assert messages[0].role == "system"
    assert messages[1].content == "mensagem nova"


def test_legacy_session_with_compact_text_and_null_compact_seq_includes_full_history(
    scenarios_root, monkeypatch
):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(compact, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    # A legacy row: compact text present but compact_seq is NULL, as if
    # written before this ticket's migration.
    conn = sqlite3.connect(sessions.db_path())
    conn.execute("UPDATE sessions SET compact = ? WHERE id = ?", ("Resumo legado.", session["id"]))
    conn.commit()
    conn.close()

    sessions.append_events(
        session["id"],
        [("player_turn", {"text": "fala legada"}), ("narrator_turn", {"text": "resposta legada"})],
    )

    captured_narrator = []

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            raise AssertionError("utility should not be called")
        captured_narrator.append(messages)
        yield "voce continua andando."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "proximo turno"}
    ) as response:
        _stream_events(response)

    narrator_messages = captured_narrator[0]
    assert "Resumo legado." in narrator_messages[0].content
    contents = [m.content for m in narrator_messages]
    assert "fala legada" in contents
    assert "resposta legada" in contents


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

    assert sessions.get_compact("s1") == (None, None)

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT scenario_id FROM sessions WHERE id = 's1'").fetchone()
    columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
    conn.close()
    assert row[0] == "exemplo-escola"
    assert {"compact", "compact_seq"} <= columns


def test_init_db_migrates_old_schema_with_compact_but_no_compact_seq(tmp_path, monkeypatch):
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
          hud           TEXT NOT NULL,
          compact       TEXT
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
        "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("s1", "exemplo-escola", "Exemplo", "default", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", "{}", None),
    )
    old_conn.commit()
    old_conn.close()

    sessions.init_db()

    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
    conn.close()
    assert columns == {
        "id",
        "scenario_id",
        "scenario_name",
        "start_id",
        "created_at",
        "updated_at",
        "hud",
        "compact",
        "compact_seq",
        "ephemeral",
    }
    assert sessions.get_compact("s1") == (None, None)
