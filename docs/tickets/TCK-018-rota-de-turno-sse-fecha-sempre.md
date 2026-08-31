---
id: TCK-018
title: Fechar o SSE do turno em todo caminho de erro e corrigir a precedência da rota
status: ready
points: 5
blockedBy: [TCK-015, TCK-024]
files:
  - backend/app/main.py
  - backend/app/turn.py
  - backend/tests/test_turn.py
migration: false
ui: false
risk: high
---

## Problema

`run_turn` (`backend/app/turn.py:107`) faz três coisas **antes** do bloco `try`
que protege o stream: `load_config()`, `config.models["narrator"]` /
`config.providers[role.provider]`, e `get_session_row` + `load_scenario` +
`_maybe_compact`. Qualquer exceção aí — papel `narrator` ausente da config
(`KeyError`), provider inexistente, sessão apagada em corrida entre a validação
da rota e o início do stream (`SessionNotFound`), cenário removido do disco
(`ScenarioError`) — escapa do gerador **depois** que a
`StreamingResponse` já respondeu 200 e já abriu o corpo. O `event_stream` de
`backend/app/main.py:138` não tem `try`, então a exceção mata o gerador antes do
`yield "data: [DONE]"`. O cliente recebe um corpo truncado sem evento `error` e
sem `[DONE]`: `streamTurn` em `frontend/src/api.ts:82` sai do laço pelo `done`
do reader sem nunca chamar `onError`, e `GameScreen` fica com
`pending.status === 'streaming'` para sempre — textarea desabilitada, botão
`aria-busy`, jogador travado, sem nem o botão de retry. **Todo** caminho de erro
depois do 200 tem que emitir `error` e `[DONE]`.

No mesmo arquivo, quatro problemas menores:

- **Precedência invertida**: `turn_route` (`backend/app/main.py:120-121`)
  rejeita a mensagem vazia com 422 (`:126`) **antes** de checar a existência da
  sessão (`:130`). `POST
  /api/sessions/nao-existe/turn {"message": "  "}` responde 422 "message must
  not be empty", escondendo que a sessão não existe. Recurso inexistente é 404,
  e a validação de corpo vem depois.
- **Leituras redundantes**: por turno, a sessão é lida 3x (`get_session` na
  rota, `get_session_row` em `run_turn`, `get_session_row` de novo dentro de
  `build_context`) e o cenário é carregado 2x (`load_scenario` em `run_turn` e
  em `build_context`) — `build_context` é chamada 1 ou 2 vezes, então na verdade
  são até 4 leituras e 3 loads. São arquivos YAML lidos do disco e parseados a
  cada turno, para produzir sempre o mesmo objeto.
- **Flag lida duas vezes**: `load_config()` na rota (`main.py:122`) e de novo em
  `run_turn` (`turn.py:108`), e o `chat` kill switch é avaliado só na rota.
- **Vazamento de mensagem técnica**: `error = str(exc)` (`turn.py:132`,
  `turn.py:153`) vai direto para o SSE e o frontend exibe em `<details>`. Um
  `httpx.ConnectError` ou um traceback de sqlite viram texto de jogo.

Lacuna de cobertura do TCK-006: **nenhum teste inspeciona o conteúdo do system
prompt** que chega ao narrador. `backend/tests/test_turn.py:156` captura
`messages` mas só afere os turnos de histórico; se o mundo, os personagens em
cena ou o HUD sumissem do prompt, a suíte inteira continuaria verde.

## Escopo

Dentro:
- `TurnContext` em `backend/app/turn.py`: carrega sessão + cenário + start +
  personagens **uma vez**, e é criado na rota e repassado a `run_turn`, a
  `_maybe_compact` e a `build_context`.
- `load_turn_context` assume a conversão `ScenarioError`/start ausente →
  `ScenarioNotFound` que hoje mora em `get_session`
  (`backend/app/sessions.py:232-236`).
- `run_turn` com todo o corpo dentro de tratamento de erro, e `event_stream` em
  `backend/app/main.py` garantindo `error` + `[DONE]` em qualquer exceção.
- Precedência da rota: 503 (flag) → 404 (sessão/cenário) → 422 (mensagem vazia).
- Config lida uma vez por turno na rota e repassada.
- Mensagem de erro do SSE sanitizada; detalhe técnico só no log.
- Cenários de teste novos, incluindo a inspeção do system prompt.

Fora (explícito):
- Mudar o formato do SSE (nomes de campo `delta`/`hud`/`error`, `data: [DONE]`):
  o frontend do TCK-014 depende deles e não há ticket de frontend nesta leva
  consumindo formato novo.
- Reavaliar a flag `chat` **no meio** de um stream já iniciado: um turno em voo
  termina. Desligar a flag impede o **próximo** turno, e isso é o kill switch
  suficiente.
- Cache de cenário entre requisições (dicionário de módulo, TTL, invalidação por
  mtime): reduzir de 3 loads para 1 já resolve a redundância deste ticket; cache
  global tem invalidação a decidir e não cabe aqui.
- Traduzir a mensagem de erro do turno para o idioma do jogador: o campo `error`
  do SSE vira um **código** estável, e a UI já tem `game.turn.error` /
  `game.turn.errorBody` para o texto. Mapear código → texto na UI é fora de
  escopo desta leva.
- `POST /api/chat` (rota smoke da Fase 0, `backend/app/main.py:85`): fica como
  está.
- `get_session` (`backend/app/sessions.py:230`) e a rota
  `GET /api/sessions/{id}`: continuam exatamente como estão. A conversão de
  erro é **replicada** em `load_turn_context`, não movida.
- A regra de seleção de janela e o disparo do compact: chegam prontos do
  TCK-024; aqui `_maybe_compact` só passa a receber e repassar o `TurnContext`.

### Testes existentes que este ticket invalida

Grep em `backend/tests/test_turn.py`:

- `test_turn_route_empty_message_is_422` (linha 317) usa uma sessão que
  **existe**, então continua 422 depois da inversão de precedência. Sem
  adaptação. O caso novo (sessão inexistente + mensagem vazia → 404) é cenário
  novo deste ticket.
- `test_turn_route_session_not_found_is_404` (292) e
  `test_turn_route_scenario_deleted_is_404` (302): continuam válidos; a rota
  passa a detectar os dois casos via `TurnContext`, mas os `detail` das
  `HTTPException` (`"session not found"`, `"scenario not found"`) **não mudam** e
  as asserções continuam literais.
- `test_turn_route_flag_disabled_is_503` (272): continua válido. Note que o
  `Config` desse teste só declara o papel `narrator`; a rota continua não
  precisando de mais nada antes do 503.
- `test_turn_provider_error_mid_stream_does_not_persist` (222) afere
  `any("error" in e for e in events)` — não afere o **texto** do erro. Continua
  válido sem adaptação depois da sanitização.
- `test_turn_append_events_failure_preserves_hud` (247): idem, afere presença de
  `error`, não o texto.
- `test_turn_that_is_only_a_tag_is_treated_as_failure` (185): o turno cujo texto
  limpo fica vazio vira `error = "empty turn"` (`backend/app/turn.py:139`).
  Esse é o **único** `error` que continua sendo texto próprio e não vira
  `TURN_ERROR_CODE`: ele não é exceção, é resultado de negócio, e o teste afere
  só a presença de `"error"` no evento e a ausência de persistência. Continua
  válido sem adaptação — e a implementação não pode substituí-lo por
  `turn_failed`, senão o log perde a distinção entre "modelo devolveu só tag" e
  "algo explodiu".
- `test_turn_window_truncated_at_18_pairs` (203) chama
  `turn.build_context(session_id, "nova mensagem")` sem contexto. **Adaptação de
  preparação**: nenhuma — `ctx` é keyword opcional e `build_context` continua
  capaz de carregar sozinha quando não recebe. Se a implementação tornar `ctx`
  obrigatório, o teste quebra: não torne.
- `backend/tests/test_compact.py` passa por `run_turn` em vários cenários mas
  não afere texto de erro; este ticket **não** edita esse arquivo, para não
  colidir com o TCK-016 na mesma wave.

## Comportamento esperado

Do ponto de vista do jogador:

- Qualquer falha depois do envio produz o bloco de erro com botão "tentar de
  novo" e a mensagem dele preservada — nunca uma tela presa em "Narrando…".
- Enviar um turno para uma sessão que não existe mais responde 404, mesmo se a
  caixa estiver vazia.
- O `<details>` de detalhe técnico mostra um código curto e estável, não um
  traceback nem uma URL interna.

Do ponto de vista do chamador da API:

| Situação | Resposta |
|---|---|
| flag `chat` desligada | 503 `{"detail": "chat disabled by flag"}` |
| sessão inexistente | 404 `{"detail": "session not found"}` |
| cenário da sessão removido | 404 `{"detail": "scenario not found"}` |
| mensagem vazia, sessão existe | 422 `{"detail": "message must not be empty"}` |
| **exceção** depois do 200 (qualquer uma) | `data: {"error": "turn_failed"}` seguido de `data: [DONE]` |
| turno cujo texto limpo fica vazio | `data: {"error": "empty turn"}` seguido de `data: [DONE]` (inalterado) |

## Detalhes técnicos

- `TurnContext` é um `BaseModel` pydantic com `row: SessionRow`, `scenario:
  LoadedScenario`, `start: StartConfig`, `characters: list[Character]` — todos
  já são modelos pydantic em `backend/app/sessions.py` e
  `backend/app/scenario.py`, então o modelo composto valida sem código extra.
- `load_turn_context(session_id) -> TurnContext` é o **único** ponto que lê a
  sessão e carrega o cenário. Reusa `_characters_in_scene`
  (`backend/app/turn.py:27`).
- **Onde a conversão de erro passa a viver.** Hoje quem transforma
  `ScenarioError` (cenário sumiu do disco) e `KeyError` (start id que não existe
  mais) em `ScenarioNotFound` é `get_session`
  (`backend/app/sessions.py:232-236`), e é dessa conversão que
  `backend/tests/test_turn.py:302` (`test_turn_route_scenario_deleted_is_404`)
  depende. Tirando `get_session` do caminho do turno, a conversão passa a viver
  em `load_turn_context`, com o mesmo `try/except (ScenarioError, KeyError):
  raise ScenarioNotFound(row.scenario_id) from None`. `get_session` **continua
  intacta** — ela ainda serve `GET /api/sessions/{id}`
  (`backend/app/main.py:76`) e não é tocada por este ticket.
- A rota chama `load_turn_context` para decidir 404 (em vez de `get_session`,
  que ainda por cima lê todos os eventos só para descartá-los) e repassa o
  `TurnContext` e o `Config` para `run_turn`.
- `run_turn(session_id, message, *, ctx: TurnContext | None = None, config:
  Config | None = None)`: quando não recebe, carrega — mantém a função chamável
  isolada em teste.
- `_maybe_compact` (`backend/app/turn.py:65`) entra no escopo: ela hoje recebe
  `(session_id, message, config, locale)` e chama `build_context` uma ou duas
  vezes (`:69`, `:91`), cada chamada com um `get_session_row` + um
  `load_scenario` embutidos. Passa a receber o `TurnContext` e a repassá-lo a
  `build_context`. Sem isso o critério de "1 `load_scenario` + 1
  `get_session_row` por turno" é inatingível, porque o caminho de compactação
  fica de fora da economia.
- `build_context(session_id, message, compact=None, compact_seq=None, *,
  history: list[Event] | None = None, ctx: TurnContext | None = None)`: a
  assinatura publicada pelo TCK-015 (incluindo o keyword-only `history`)
  continua válida; `ctx` é mais um keyword opcional ao lado dele.
- Sanitização: constante `TURN_ERROR_CODE = "turn_failed"` em
  `backend/app/turn.py`. Todo `error` vindo de exceção passa a ser essa
  constante; o `str(exc)` vai para `emit(..., error=<texto real>)`. Nada de
  `repr`, nada de traceback. O `"empty turn"`
  (`backend/app/turn.py:139`) não vem de exceção e permanece como está.
- `event_stream` em `main.py`:

  ```python
  async def event_stream():
      failed = False
      try:
          async for event in run_turn(session_id, req.message, ctx=ctx, config=config):
              yield f"data: {json.dumps(event)}\n\n"
      except Exception as exc:
          failed = True
          emit("turn_stream_failed", session_id=session_id, error=str(exc))
      if failed:
          yield f"data: {json.dumps({'error': TURN_ERROR_CODE})}\n\n"
      yield "data: [DONE]\n\n"
  ```

  **Armadilha**: não coloque o `yield` do `[DONE]` dentro de um `finally`. Se o
  cliente desconectar, o gerador recebe `GeneratorExit` e um `yield` no
  `finally` levanta `RuntimeError: async generator ignored GeneratorExit`, o que
  polui o log a cada aba fechada. O padrão acima só emite no fluxo normal.
- O `run_turn` continua um gerador assíncrono: mesmo com o `try` externo em
  `main.py`, envolva também o preâmbulo de `run_turn` (`load_config`,
  `models["narrator"]`, `providers[...]`, `_maybe_compact`) para que ele possa
  emitir `game_turn` com `error` antes de propagar. Sem isso a telemetria do
  turno some justamente nas falhas.

## Contrato público

```python
# backend/app/turn.py
TURN_ERROR_CODE = "turn_failed"

class TurnContext(BaseModel):
    row: SessionRow
    scenario: LoadedScenario
    start: StartConfig
    characters: list[Character]

def load_turn_context(session_id: str) -> TurnContext: ...
    # levanta SessionNotFound ou ScenarioNotFound; nunca deixa ScenarioError
    # nem KeyError escaparem

async def _maybe_compact(
    session_id: str,
    message: str,
    config: Config,
    locale: str,
    ctx: TurnContext,
) -> tuple[list[ChatMessage], str | None]: ...   # privada, listada para fixar o repasse do ctx

async def run_turn(
    session_id: str,
    message: str,
    *,
    ctx: TurnContext | None = None,
    config: Config | None = None,
) -> AsyncIterator[dict]: ...
```

Rota `POST /api/sessions/{session_id}/turn`: corpo e formato do SSE inalterados;
só a ordem dos códigos de status e o conteúdo do campo `error` mudam, conforme a
tabela em "Comportamento esperado".

## Acceptance criteria

- [ ] Com o papel `narrator` ausente da config, o POST responde 200 e o corpo
      SSE contém exatamente um evento `error` seguido de `data: [DONE]`.
- [ ] Com a sessão apagada entre a validação e o stream, o corpo SSE também
      termina em `error` + `[DONE]`.
- [ ] Cada um destes cinco caminhos termina o corpo SSE com `data: [DONE]`,
      aferido um a um: (a) turno completo; (b) exceção no preâmbulo de
      `run_turn` (papel `narrator` ausente); (c) exceção do provider no meio do
      stream; (d) exceção em `append_events` depois do stream; (e) sessão
      apagada entre o `TurnContext` e o primeiro delta.
- [ ] `POST /api/sessions/nao-existe/turn` com `{"message": "   "}` responde 404
      com `{"detail": "session not found"}`.
- [ ] Um turno completo faz **uma** chamada a `load_scenario` e **uma** a
      `get_session_row`.
- [ ] `load_config` é chamada uma vez por turno no caminho da rota (chamadas
      internas de `compact_block` não contam).
- [ ] Todo `error` do SSE originado de **exceção** é `"turn_failed"`, nunca
      `str(exc)`; o texto real da exceção aparece em `emit`. O único outro valor
      possível continua sendo `"empty turn"`, que não vem de exceção.
- [ ] O system prompt entregue ao narrador contém o texto do `world.md`, o nome
      de cada personagem em cena e a linha de HUD com o turno corrente.
- [ ] `npm run check` verde.

## Cenários de teste

- Feliz: turno normal → deltas, `hud`, `[DONE]`, e um contador de chamadas
  (monkeypatch em `app.turn.load_scenario` e `app.turn.get_session_row`)
  registrando exatamente 1 cada.
- Feliz (system prompt): fake provider captura `messages`; afere
  `"Uma escola"` (texto do `world.md` do fixture), `"Chloe"`,
  `"## ESTADO DO JOGO"` e `"Turno: 0"` em `messages[0].content`.
- Borda: `Config` sem o papel `narrator` → 200 + `error` + `[DONE]`, e
  `turn_stream_failed` emitido.
- Borda: sessão removida do banco depois do `TurnContext` (apagar a linha via
  `sqlite3` dentro do fake `stream_chat`) → `error` + `[DONE]`, HUD não avança.
- Borda: mensagem vazia numa sessão que existe → continua 422.
- Falha: provider levanta no meio do stream → evento `error` com
  `"turn_failed"`, nada persistido, `game_turn` emitido com o texto real da
  exceção.
- Falha: `append_events` levanta → `error` no SSE, HUD preservado, e o texto
  técnico não aparece no corpo da resposta.

## Rollout e kill switch

Flag **`chat`** em `~/.ooc-local/config.yaml`, default `true`, avaliada uma vez
por turno em `turn_route` (`backend/app/main.py:123`). Desligar sem deploy:
editar o YAML; o próximo POST responde 503 e a UI mostra
`error.chatDisabled.*`. É o kill switch certo porque este ticket altera o
caminho quente do turno inteiro: com a flag desligada nenhuma linha do código
novo executa, e a Fase 1 volta ao estado de "sem jogar".

Rollback de código é `git revert` do PR; não há migração nem estado persistido
novo.

## Observabilidade

Eventos:
- `turn_stream_failed` (novo) — `session_id`, `error` (texto real da exceção).
- `game_turn` — inalterado, mas agora garantido também nas falhas de preâmbulo.
- `turn_rejected` — inalterado (`session_id`, `reason`), agora com `reason`
  refletindo a precedência nova.

Métrica de sucesso: zero streams sem `[DONE]` num turno jogado com o servidor
LLM desligado, e nenhum `turn_rejected` com `reason="message must not be empty"`
para sessão inexistente.

## i18n

N/A. O campo `error` do SSE passa a ser um código (`turn_failed`), não texto de
usuário; a UI já traduz o bloco de erro do turno com `game.turn.error` e
`game.turn.errorBody`, que existem em `en` e `pt-br` em
`frontend/src/strings.ts`. Nenhuma chave nova.
