---
id: TCK-006
title: Jogar um turno por SSE com prompt-mestre, tags e HUD do engine
status: ready
points: 5
blockedBy: [TCK-003, TCK-004, TCK-005]
files:
  - backend/app/turn.py
  - backend/app/hud.py
  - backend/app/main.py
  - backend/tests/test_turn.py
migration: false
ui: false
risk: high
---

## Problema

Os pedaços do turno existem separados — prompt-mestre (TCK-003), parser de tags
(TCK-004), event store (TCK-005) — e nada os conecta. A única rota que fala com
o LLM é `/api/chat` (`backend/app/main.py:28`), que manda um prompt fixo e não
persiste, não conhece sessão e não tem HUD. Sem este ticket não existe game
loop: a UI de jogo (TCK-012) não tem o que consumir.

## Escopo

Dentro:
- `backend/app/turn.py`: montagem do contexto do turno (system = prompt-mestre +
  janela recente de turnos) e orquestração do turno.
- Rota `POST /api/sessions/{session_id}/turn` em `backend/app/main.py`, SSE no
  mesmo formato da Fase 0 mais o evento `hud` antes do `[DONE]`.
- Avanço determinístico do HUD em `backend/app/hud.py`: `advance(hud)` incrementa
  `turn` e adianta `time` em `TURN_MINUTES` (2 minutos, como o OOC —
  `dev/ooc-teardown.md:128`), com virada de dia; `location` e `weather`
  permanecem os do start (mudá-los é Fase 3).
- Persistência atômica do turno (jogador + narrador + tags) via `append_events`.
- Kill switch e telemetria.
- `backend/tests/test_turn.py`, com o provider monkeypatchado (como
  `backend/tests/test_chat.py:7` já faz com `fake_stream`).

Fora (explícito):
- Compact / orçamento de 24K — TCK-007. Aqui a janela é fixa: os últimos 18
  turnos (36 eventos), o resto é descartado do contexto sem resumo.
- Aplicar efeito de tag (stat, sprite, background) — Fases 2–5. As tags são
  gravadas como eventos `tag` e logadas.
- Cancelar, regenerar ou editar turno — a UI da Fase 1 não tem (spec, tema 02);
  rewind é Fase 7.
- Sugestões de ação e bloco INFO — Fase 3.
- Mexer em `/api/chat`: a rota de fumaça **continua existindo e intocada**.

## Comportamento esperado

`POST /api/sessions/{id}/turn {"message": "vou até a Chloe"}` responde
`text/event-stream` com:

```
data: {"delta": "..."}      (N vezes, texto ainda cru de tags)
data: {"hud": {"turn": 1, "location": "...", "time": "07:52", "weather": "clear"}}
data: [DONE]
```

Em caso de erro no meio do stream:

```
data: {"delta": "..."}      (o que já saiu)
data: {"error": "mensagem técnica"}
data: [DONE]
```

Regras que a UI depende:
- O evento `hud` só é emitido quando o turno **terminou e foi gravado**. Turno
  com erro não emite `hud` — a UI mantém o último estado conhecido e mostra
  `hud.stale`.
- Turno com erro **não grava nada**: nem o turno do jogador, nem texto parcial.
  A mensagem do jogador vive no cliente e o retry da UI é um `POST` novo com a
  mesma mensagem. Isso é o que torna o retry seguro e sem duplicata.
- Antes do stream: 503 se a flag `chat` estiver desligada, 404 se a sessão não
  existir, 404 `{"detail": "scenario not found"}` se a sessão existir mas o
  cenário tiver sido apagado do disco (mesmo comportamento do
  `GET /api/sessions/{id}` do TCK-005), 422 se `message` for vazia ou só
  espaços. Erros pré-stream são HTTP de verdade, não evento SSE — a UI decide
  entre `error.chatDisabled.*`, `game.notFound.*` e erro genérico pelo status.

## Detalhes técnicos

- `deltas` saem crus (é o texto do modelo); a limpeza de tags acontece no
  fechamento do turno, sobre o texto acumulado, e o texto **limpo** é o que vai
  para o event store. A UI aplica um filtro de defesa durante o streaming
  (TCK-010) — combinação deliberada: o engine é a fonte da verdade, a UI evita o
  flash visual.
- Payloads gravados via `append_events`, seguindo o schema por `kind` do
  contrato do TCK-005: `player_turn` recebe `{"text": <mensagem crua do
  jogador>}`, `narrator_turn` recebe `{"text": <texto já limpo de tags>}`, e
  cada tag vira um evento `tag` com
  `{"kind": str, "args": list[str], "raw": str, "valid": bool}` saído do parser
  do TCK-004.
- `build_context(..., compact: str | None = None)`: o parâmetro existe desde já
  e é interpolado no prompt-mestre quando presente; quem o produz é o TCK-007.
  Neste ticket ele nunca é passado.
- Contexto = `[system: build_master_prompt(...)]` + janela de turnos como
  mensagens alternadas `user`/`assistant` (texto limpo já persistido) + a
  mensagem nova do jogador como `user`. Prólogo e `opening_scene` já entram pelo
  prompt-mestre; não repetir no histórico.
- Personagens em cena = os ids de `start.characters` (ou todos, quando `None`),
  resolvidos pelo `LoadedScenario`.
- Provider e modelo: `config.models["narrator"]` +
  `OpenAICompatProvider(config.providers[role.provider])`, exatamente como
  `main.py:33-34` faz hoje. Nada de novo cliente HTTP.
- Streaming com `StreamingResponse(..., media_type="text/event-stream")`,
  `json.dumps` por evento, no formato já usado em `main.py:47`.
- Concorrência: dois `POST` simultâneos na mesma sessão são um bug de cliente
  (a UI desabilita o input), mas o servidor não corrompe: a gravação usa
  `MAX(seq)+1` na transação e a `UNIQUE(session_id, seq)` do TCK-005 faz o
  segundo falhar em vez de intercalar. Falha de gravação vira evento
  `{"error": ...}` no stream.
- Turno vazio do modelo (stream terminou sem nenhum delta, ou texto limpo vazio
  após remover tags) é tratado como falha: emite `error`, não grava.
- `TURN_MINUTES = 2` e a virada de 23:59 → 00:01 ficam em `app/hud.py`, com
  teste próprio: relógio é do mundo do jogo, nunca do sistema.

Testes existentes que este ticket invalida: **nenhum**. `test_chat.py` e
`test_flags.py` continuam valendo porque `/api/chat` não muda; a flag `chat` é
**reusada** (não renomeada), então `test_flags.py::test_chat_disabled_by_flag`
segue aferindo o mesmo. O teste novo de 503 para a rota de turno é cenário novo,
não adaptação.

## Contrato público

```
POST /api/sessions/{session_id}/turn
  body: {"message": str}
  200  text/event-stream:
       data: {"delta": str}      *
       data: {"hud": HudState}   ? (só em turno bem-sucedido, antes do DONE)
       data: {"error": str}      ? (falha no meio do stream)
       data: [DONE]              (sempre o último)
  404  {"detail": "session not found"} | {"detail": "scenario not found"}
  422  {"detail": "message must not be empty"}
  503  {"detail": "chat disabled by flag"}
```

```python
# backend/app/turn.py  (consumido pelo TCK-007)
WINDOW_TURNS = 18
def build_context(session_id: str, message: str, compact: str | None = None) -> list[ChatMessage]: ...
async def run_turn(session_id: str, message: str) -> AsyncIterator[dict]: ...
```

```python
# backend/app/hud.py  (acrescentado)
TURN_MINUTES = 2
def advance(hud: HudState) -> HudState: ...
```

## Acceptance criteria

- [ ] Turno bem-sucedido emite deltas, depois `hud`, depois `[DONE]`, nessa
      ordem.
- [ ] Após o turno, `GET /api/sessions/{id}` traz um par de turnos com o texto
      do narrador **sem tags** e `hud.turn` incrementado.
- [ ] As tags do turno viram eventos `kind="tag"` no event store.
- [ ] Turno que falha no meio não deixa nenhum evento novo no banco e não altera
      `hud`.
- [ ] `message` vazia ou só espaços → 422 sem chamar o provider.
- [ ] Flag `chat: false` → 503 sem chamar o provider.
- [ ] Sessão inexistente → 404 sem chamar o provider.
- [ ] Sessão existente com cenário apagado do disco → 404
      `{"detail": "scenario not found"}` sem chamar o provider.
- [ ] O `system` enviado ao provider contém o mundo, os personagens em cena e o
      HUD atual (asserção sobre as mensagens capturadas no fake provider).
- [ ] Com 25 turnos gravados, a janela enviada tem no máximo 18 pares.
- [ ] `advance` incrementa turno e hora; 23:59 vira 00:01 sem estourar.
- [ ] `npm run check` verde.

## Cenários de teste

- Feliz: sessão nova + `message` → SSE com deltas, `hud.turn == 1`, dois eventos
  de turno e as tags gravadas.
- Feliz: segundo turno → contexto enviado ao provider inclui o par anterior em
  `user`/`assistant`.
- Borda: modelo devolve texto que é só uma tag → turno tratado como falha, nada
  gravado.
- Borda: 25 turnos no banco → janela truncada em 18, sem erro.
- Borda: texto com `[STAT:reputacao:+1]` no meio de frase → texto gravado sem a
  tag e sem espaço duplo.
- Falha: provider levanta no meio do stream → evento `error`, `[DONE]`, banco
  inalterado (asserção explícita de contagem de eventos antes/depois).
- Falha: `append_events` levanta → evento `error` no stream e HUD antigo
  preservado.
- Falha: flag desligada / sessão inexistente / mensagem vazia → 503 / 404 / 422.

## Rollout e kill switch

Flag: **`chat`**, a mesma de `~/.ooc-local/config.yaml` já lida por
`Config.flag()` (`backend/app/config.py:43`), default `true`. Reusada de
propósito: é o kill switch de "qualquer chamada de LLM" e a UI já tem a mensagem
correspondente (`error.chatDisabled.*`). Desligar não exige deploy — editar o
YAML e a próxima requisição já responde 503, porque `load_config()` é chamada
por requisição. Com a flag off, listar e abrir sessão continuam funcionando
(só não se joga turno novo).

## Observabilidade

Eventos:
- `game_turn` (`session_id`, `turn`, `model`, `prompt_version`, `duration_ms`,
  `chars`, `tags`, `invalid_tags`, `error`) — emitido sempre ao fim do stream,
  com ou sem erro, no mesmo padrão do `chat_turn` existente
  (`backend/app/main.py:52`).
- `turn_rejected` (`session_id`, `reason`) para 422/404/503.
Métrica de sucesso: 5 turnos seguidos no cenário exemplo com `error: null` em
todos os `game_turn` e `duration_ms` mediano abaixo de 30s no modelo local.

## i18n

N/A no backend. O texto narrado sai no idioma do cenário (via prompt-mestre do
TCK-003); `detail` de erro é técnico em inglês e a UI traduz por status,
com as chaves já criadas no TCK-008.
