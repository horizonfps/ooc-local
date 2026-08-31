---
id: TCK-015
title: Tirar da janela de contexto os turnos já cobertos pelo resumo
status: done
points: 5
blockedBy: []
files:
  - backend/app/sessions.py
  - backend/app/turn.py
  - backend/app/main.py
  - backend/tests/test_compact.py
migration: true
ui: false
risk: high
---

## Problema

O compact v0 (TCK-007, mergeado) resume o bloco que sai da janela, mas **o bloco
resumido continua na janela**. `build_context` (`backend/app/turn.py:33`) lê os
eventos com `read_events(session_id, kinds=("player_turn","narrator_turn"))` e
corta em `events[-(WINDOW_TURNS * 2):]`, sem nenhuma noção de "até onde o resumo
já cobre". Depois de uma compactação, o turno seguinte remonta exatamente a mesma
janela de 18 pares, `fits()` (`backend/app/turn.py:71`) volta a falhar,
`_shrink_to_fit` (`:55`) volta a produzir `outgoing` e `compact_block` é chamado
**de novo** — agora com o resumo anterior como entrada. Numa sessão de 100
turnos isso é ~18x o número de chamadas previsto pelo TCK-007, e o resumo vira
resumo-de-resumo-de-resumo: exatamente a degradação qualitativa que o kill
switch daquele ticket existia para conter.

Dois defeitos menores no mesmo caminho:

- **`from_index`/`to_index` não correspondem a nada.** O payload do evento
  `compact` grava `{"from_index": 0, "to_index": len(outgoing) // 2}`
  (`backend/app/turn.py:89`) — dois números derivados do tamanho do bloco, não
  de posições reais no event store. Isso quebra a promessa explícita do TCK-007
  ("o compact é reconstituível: apagar a coluna e reprocessar os eventos
  `compact` devolve o mesmo estado"): não há como saber quais eventos cada
  resumo cobriu.
- **Migração de schema no lugar errado.** `_migrate_compact_column`
  (`backend/app/sessions.py:119`) é chamada por `_connect()` (`:115`), ou seja,
  um `PRAGMA table_info(sessions)` roda a cada abertura de conexão — em toda
  leitura de sessão, em todo turno, em toda listagem. `init_db()` (`:126`)
  existe e é exercitada em teste (`backend/tests/test_sessions.py:81-82`,
  `backend/tests/test_compact.py:481-482`), mas **nenhum caminho de produção a
  chama**: `backend/app/main.py` não a importa.

## Escopo

Dentro:
- Coluna `compact_seq INTEGER` em `sessions`: o maior `seq` de evento coberto
  pelo compact vigente. Entra no `SCHEMA_SQL` (banco novo) e como `ALTER TABLE`
  idempotente para banco antigo.
- `_migrate_compact_column` renomeada para `_migrate_session_columns`,
  cobrindo `compact` e `compact_seq`, chamada **apenas** por `init_db()`;
  `init_db()` passa a ser chamada na importação de `backend/app/main.py`.
- `get_compact` devolvendo `(texto, compact_seq)`; `set_compact` recebendo
  `covered_seq`.
- `history_events(session_id, compact_seq)` em `backend/app/turn.py`,
  devolvendo **todos** os eventos de turno com `seq > compact_seq`, sem truncar.
- `events_to_messages(events)` em `backend/app/turn.py`: mapeamento 1:1 e
  ordenado de `Event` para `ChatMessage`, extraído do laço que hoje está
  embutido em `build_context` (`backend/app/turn.py:48-50`).
- `build_context` com o parâmetro `compact_seq` e com o parâmetro keyword-only
  `history`: quando recebe uma lista de eventos, usa **exatamente** aquela
  lista, sem truncar; quando não recebe, carrega e trunca em `WINDOW_TURNS`
  pares, como hoje.
- `_maybe_compact` montando o contexto candidato sobre a lista **completa** de
  `history_events`, e gravando o `compact_seq` correto e o payload do evento com
  `from_seq`/`to_seq` reais.
- `_shrink_to_fit` passa a devolver a **contagem** de mensagens que saem do
  início da janela, em vez de uma lista reconstruída.
- Testes em `backend/tests/test_compact.py`, com as adaptações inventariadas
  abaixo. `backend/tests/test_turn.py` **não** entra em `files`: o inventário
  abaixo mostra que ele continua verde sem uma linha de edição.

Fora (explícito):
- **Disparo por contagem de turnos e a histerese que o acompanha**: é o
  TCK-024, que consome o contrato deste ticket. Aqui o corte continua sendo só
  por orçamento (`fits()` falso). O defeito "com turnos curtos o narrador
  esquece a partir do turno 19" **continua aberto** até o TCK-024 — declarado,
  não esquecido.
- **Estado intermediário aceito e declarado**: com a flag `compact` ligada e
  mais de `WINDOW_TURNS` pares não cobertos, o contexto deste ticket passa a
  carregar **mais** pares que hoje, porque no caminho do compact o corte por
  contagem sai e só o corte por orçamento fica. O crescimento é limitado por
  `fits()` — nunca passa dos 23.200 tokens de entrada — e é narrativamente
  melhor que o corte seco de hoje, que descarta em silêncio. O TCK-024 fecha
  esse intervalo transformando a contagem em gatilho de compactação. Com a flag
  desligada, `build_context` segue o caminho legado e trunca em 18 pares
  exatamente como hoje.
- Orçamento da chamada do utility (`max_tokens`, temperatura, timeout curto):
  TCK-016.
- Unificar `set_compact` no caminho de append do event store: TCK-017.
- Compact em camadas, memória por categoria, NPC minds: Fase 7, como o TCK-007
  já declarou.
- Tokenizer real: `estimate_tokens` continua `ceil(len/4)`.
- Reprocessar eventos `compact` antigos para preencher `compact_seq` de sessões
  já existentes: sessão legada fica com `compact_seq` nulo e é tratada como
  "o resumo não cobre nada", que é o comportamento de hoje. Declarado.
- Formato do SSE, rotas e o texto dos prompts de compactação.

### Testes existentes que este ticket invalida

Grep em `backend/tests/`:

**Mudança de tipo de `get_compact` (`str | None` → `tuple[str | None, int |
None]`).** Oito asserções em `backend/tests/test_compact.py` chamam a função:
linhas **228, 264, 316, 353, 365, 399, 439** e **484**. Regra de adaptação,
mecânica e idêntica nas oito: o valor comparado passa a ser
`sessions.get_compact(...)[0]`. O que cada asserção afere — qual texto de resumo
está vigente, ou que não há resumo — não muda. Onde o ticket quiser aferir o
`compact_seq`, isso é asserção **nova**, listada em "Cenários de teste", não
adaptação.

Testes nomeados, um a um:

- `test_short_history_skips_compact_and_matches_tck006` (`:209`) — adaptação de
  preparação: `get_compact(...)` → `get_compact(...)[0]` na linha 228. Continua
  aferindo que nenhum compact foi criado.
- `test_budget_overflow_triggers_compact_and_context_gets_resumo` (`:233`) —
  mesma adaptação na linha 264. As demais asserções (evento `compact` único,
  `RESUMO DA CAMPANHA` no system prompt, orçamento respeitado) continuam
  verbatim. Ganha asserções novas sobre `compact_seq` e sobre
  `from_seq`/`to_seq`, que são cenário novo deste ticket.
- `test_second_turn_reuses_compact_without_calling_utility_again` (`:279`) —
  duas adaptações de preparação: a chamada
  `sessions.set_compact(session["id"], "Resumo do bloco antigo.",
  {"replaced_turns": 3, "from_index": 0, "to_index": 3})` (`:289`) passa a usar
  a assinatura nova, com `covered_seq` igual ao último `seq` gravado até ali; e
  a asserção da linha 316 passa a indexar `[0]`. O que o teste afere — utility
  não chamado, resumo preservado — não muda.
- `test_second_compaction_replaces_previous_compact` (`:319`) — adaptação nas
  linhas 353 e 365. O corpo do teste (dois lotes de 18 pares longos, duas
  compactações, o primeiro resumo aparecendo no prompt da segunda) continua
  válido: os dois lotes estouram o orçamento independentemente do filtro por
  `compact_seq`.
- `test_utility_failure_falls_back_to_truncated_window` (`:368`) — adaptação na
  linha 399. Ganha a asserção nova de que `compact_seq` continua nulo.
- `test_flag_compact_false_behaves_like_tck006` (`:407`) — adaptação na linha
  439. Com a flag desligada, `get_compact` nem é chamada pelo código de
  produção (`backend/app/turn.py:68`), então o comportamento aferido não muda.
- `test_init_db_migrates_old_schema_without_compact_column` (`:447`) —
  adaptação na linha 484. O schema legado do fixture continua igual e as
  asserções de preservação de dados continuam verbatim; a asserção de que
  `compact_seq` foi criada é cenário novo.
- `backend/tests/test_turn.py::test_turn_window_truncated_at_18_pairs` (`:203`)
  monta 25 pares e chama `turn.build_context(session_id, "nova mensagem")` com
  dois argumentos, aferindo 36 mensagens e `"jogador 7"` na primeira.
  **Continua válido sem adaptação**: sem `history`, `build_context` carrega e
  trunca em `WINDOW_TURNS` pares, que é o caminho de hoje. É este teste que fixa
  a fronteira entre os dois modos da função — se ele quebrar, o truncamento foi
  removido do caminho errado; corrija a implementação, não o teste.
- Os cenários de integração de `backend/tests/test_compact.py` passam a
  exercitar o caminho `history=<lista completa>`, sem que nenhum deles precise
  de adaptação: `test_budget_overflow_...` (`:233`) prepara exatamente 18 pares,
  onde lista completa e lista truncada coincidem;
  `test_second_compaction_replaces_previous_compact` (`:319`) chega a mais de 18
  pares não cobertos no segundo turno, e o que ele afere (duas chamadas ao
  utility, o primeiro resumo dentro do segundo prompt, o resumo final vigente)
  vale nos dois modos. Nenhum deles afere `compact_seq` — daí o cenário novo de
  ">18 pares" listado adiante.
- `backend/tests/test_sessions.py::test_init_db_is_idempotent` (`:80`) continua
  válido: `init_db()` continua idempotente, agora com duas colunas.
- Nenhum teste de frontend toca este fluxo: o compact é invisível na API.

## Comportamento esperado

Do ponto de vista do jogador, nada muda na tela.

Do ponto de vista do chamador:

- Depois de uma compactação, os turnos cobertos pelo resumo **nunca** voltam ao
  contexto. O turno seguinte, com histórico curto, cabe no orçamento e não
  chama o utility.
- Uma sessão que estoura o orçamento compacta, e só volta a compactar quando os
  turnos **novos** estourarem o orçamento de novo.
- O evento `compact` registra o intervalo de `seq` que cobriu, e a coluna
  `compact_seq` é a projeção do último desses intervalos. O intervalo é exato:
  o último turno que entrou no resumo é o de `seq == to_seq`, e o primeiro turno
  que fica na janela é o primeiro evento devolvido por
  `history_events(session_id, to_seq)` — não `to_seq + 1`: os `seq` são
  contíguos sobre todos os tipos de evento, e um turno com tag grava eventos
  `tag` entre o `narrator_turn` e o `player_turn` seguinte.
- Com a flag ligada, o contexto do turno deixa de ser truncado por contagem e
  passa a ser limitado só pelo orçamento; com a flag desligada, o corte em 18
  pares do TCK-006 continua valendo. O corte por contagem volta, como gatilho de
  compactação, no TCK-024.
- Falha do utility continua sendo degradação: turno acontece com a janela
  truncada, sem resumo novo e sem avanço de `compact_seq`.
- Flag `compact: false` mantém o comportamento do TCK-006.

## Detalhes técnicos

- `history_events(session_id: str, compact_seq: int | None) -> list[Event]` em
  `backend/app/turn.py`: chama `read_events(session_id, kinds=("player_turn",
  "narrator_turn"))` e devolve `[e for e in events if compact_seq is None or
  e.seq > compact_seq]`, **sem truncar**. `Event` já expõe `seq`
  (`backend/app/sessions.py:93`) e `read_events` já ordena por `seq` (`:259`),
  então não há query nova.
- `events_to_messages(events: list[Event]) -> list[ChatMessage]` faz o
  mapeamento que hoje está inline em `build_context`
  (`backend/app/turn.py:48-50`): `player_turn` vira `user`, `narrator_turn` vira
  `assistant`, uma mensagem por evento, na ordem recebida. É **1:1 e
  order-preserving**, e é essa propriedade que torna índice de mensagem
  equivalente a índice de evento.
- **De onde sai a janela candidata.** Este é o ponto que precisa ficar sem
  ambiguidade, porque é onde o `covered_seq` pode nascer errado:
  - `build_context(session_id, message, compact, compact_seq)` **sem** o
    parâmetro `history` carrega `history_events(...)` e trunca em
    `events[-(WINDOW_TURNS * 2):]`, exatamente como hoje. É o caminho de quem
    quer só montar contexto — e o caminho de `backend/tests/test_turn.py:203`.
  - `build_context(..., history=<lista de Event>)` usa a lista recebida como
    veio, **sem truncar**. É o caminho de `_maybe_compact`.
  - `_maybe_compact` chama `history_events` **uma única vez**, guarda o
    resultado em `full`, e passa `history=full` para as duas montagens de
    contexto que faz (a candidata e a remontagem pós-compactação).
  Sem isso, o candidato viria já truncado em 18 pares e o índice devolvido pelo
  corte não teria como endereçar os eventos anteriores ao truncamento — que é
  exatamente o defeito que este ticket precisa não ter.
- **Cálculo do `covered_seq`, contra a lista sobre a qual o corte foi feito.**
  `_shrink_to_fit` deixa de devolver uma lista de `ChatMessage` reconstruída e
  passa a devolver um **inteiro**: quantas mensagens saem do **início** do
  histórico. Assinatura nova:
  `_shrink_to_fit(system, history, tail) -> int` (sempre par, `0` significa
  "nada sai"). O chamador fatia:

  ```python
  # inside _maybe_compact, only when config.flag("compact") is true;
  # with the flag off the legacy path of build_context runs unchanged
  full = history_events(session_id, current_seq)          # lista de Event
  messages = build_context(session_id, message, compact=current_compact,
                           compact_seq=current_seq, history=full)
  n = _shrink_to_fit(messages[0], messages[1:-1], messages[-1])
  if n == 0:
      return messages, None
  outgoing = messages[1:1 + n]                            # ChatMessage, para o utility
  from_seq = full[0].seq
  covered_seq = full[n - 1].seq                           # to_seq
  ```

  `messages[1:-1] == events_to_messages(full)` por construção, então o índice
  `n - 1` endereça o evento certo qualquer que seja o tamanho de `full`.
  **Armadilha**: nunca recalcule `full` depois do corte, e nunca derive
  `covered_seq` de uma lista diferente daquela que gerou `messages` — foi
  assumir "as duas listas são a mesma" sem garantir que produziu o defeito de
  cobrir evento nunca resumido.
- Falha do utility com `_shrink_to_fit` devolvendo `int`: o antigo
  `messages = trimmed` vira `messages = [messages[0], *messages[1 + n:]]` — o
  turno segue com a janela cortada, sem resumo novo e sem avanço de
  `compact_seq`. Sem esse corte, no estado intermediário deste ticket uma
  sessão longa com o utility fora do ar mandaria ao narrador um prompt acima de
  `CONTEXT_BUDGET_TOKENS`.
- As assinaturas novas de `backend/app/turn.py` anotam `Event`: acrescente
  `Event` ao import de `app.sessions` (hoje ele traz `ScenarioNotFound,
  append_events, get_compact, get_session_row, read_events, set_compact`).
- Remontagem pós-compactação: `build_context(..., compact=new_compact,
  compact_seq=covered_seq, history=full[n:])` — a mesma lista, já fatiada, sem
  ir ao banco de novo.
- Schema: `SCHEMA_SQL` (`backend/app/sessions.py:18`) ganha `compact TEXT` e
  `compact_seq INTEGER` no `CREATE TABLE sessions`, de modo que banco novo nasce
  completo. `_migrate_session_columns(conn)` (renomeada a partir de
  `_migrate_compact_column`, `:119`) faz `PRAGMA table_info(sessions)` uma vez e
  acrescenta as colunas que faltarem. `_connect()` fica só com os PRAGMAs e o
  `executescript(SCHEMA_SQL)`.
- `backend/app/main.py` chama `init_db()` no nível do módulo, logo após
  `setup_logging()` (`backend/app/main.py:28`). **Não** use `lifespan` nem
  `@app.on_event("startup")`: os testes instanciam `TestClient(main.app)` sem
  context manager (`backend/tests/test_turn.py:107` e vizinhos) e nesse modo o
  lifespan não roda — a migração ficaria sem cobertura e o servidor real teria
  comportamento diferente do testado.
- `set_compact(session_id, text, covered_seq, payload)` grava
  `compact`, `compact_seq` e `updated_at` na projeção, e o evento com
  `{"text", "replaced_turns", "from_seq", "to_seq"}`.

## Contrato público

```python
# backend/app/sessions.py
def get_compact(session_id: str) -> tuple[str | None, int | None]: ...
def set_compact(session_id: str, text: str, covered_seq: int, payload: dict) -> None: ...
def init_db() -> None: ...   # único lugar que migra schema
```

```python
# backend/app/turn.py
def history_events(session_id: str, compact_seq: int | None) -> list[Event]:
    """Todos os eventos de turno com seq > compact_seq, em ordem. Não trunca."""

def events_to_messages(events: list[Event]) -> list[ChatMessage]:
    """Mapeamento 1:1 e ordenado: player_turn -> user, narrator_turn -> assistant."""

def build_context(
    session_id: str,
    message: str,
    compact: str | None = None,
    compact_seq: int | None = None,
    *,
    history: list[Event] | None = None,
) -> list[ChatMessage]:
    """history=None: carrega e trunca em WINDOW_TURNS pares (comportamento do
    TCK-006). history=<lista>: usa a lista como veio, sem truncar."""
```

`history` é **keyword-only** de propósito: tickets posteriores acrescentam
outros parâmetros keyword-only a esta função (o TCK-018 acrescenta `ctx`), e
manter todos fora da posição impede que a ordem dos argumentos vire contrato
implícito.

Payload do evento `compact`: `{"text", "replaced_turns", "from_seq", "to_seq"}`.
As chaves `from_index`/`to_index` deixam de existir — grep em `backend/` e
`frontend/` confirma que nenhum consumidor as lê.

Contrato interno de corte, que o TCK-024 substitui mantendo a **mesma forma**:

```python
# backend/app/turn.py  (privada)
def _shrink_to_fit(
    system: ChatMessage,
    history: list[ChatMessage],
    tail: ChatMessage,
) -> int:
    """Quantas mensagens saem do INÍCIO de history para o resto caber no
    orçamento. Sempre par. 0 significa 'não compactar'."""
```

Coluna nova em `sessions`: `compact_seq INTEGER` (nula quando não há resumo).

**Consumido pelo TCK-024** (`history_events`, `events_to_messages`,
`build_context` com `history`, `set_compact`, `get_compact`, e a forma de
retorno de `_shrink_to_fit`, que vira a de `select_window`) e pelo TCK-016
(nada além da existência de `_maybe_compact`).

## Acceptance criteria

- [ ] Depois de uma compactação disparada por orçamento, o turno seguinte com
      histórico curto não chama o utility, e nenhum evento com `seq <=
      compact_seq` aparece no contexto.
- [ ] `compact_seq` gravado é igual ao `seq` do último evento resumido,
      **inclusive quando há mais de `WINDOW_TURNS` pares não cobertos**.
- [ ] O evento `compact` tem `from_seq` e `to_seq` iguais ao `seq` real do
      primeiro e do último evento resumidos, e `to_seq == compact_seq`.
- [ ] Fronteira exata: o último turno citado no prompt do utility é o evento de
      `seq == compact_seq`, e o primeiro turno de histórico no contexto do
      narrador é o primeiro evento devolvido por
      `history_events(session_id, compact_seq)` (isto é, `full[n]`).
- [ ] `_shrink_to_fit` devolve sempre um número **par** (aferido com histórico
      ímpar de mensagens forçado em teste da função, se exposta, ou pelos
      cenários de integração cujo corte cai sempre em fronteira de par).
- [ ] `history_events(session_id, None)` devolve **todos** os eventos de turno,
      sem truncar em 18 pares; com um `compact_seq` informado, devolve só os
      posteriores.
- [ ] `build_context` sem `history` continua truncando em `WINDOW_TURNS` pares;
      com `history`, devolve uma mensagem por evento da lista recebida.
- [ ] `len(events_to_messages(evs)) == len(evs)` e a ordem é preservada.
- [ ] `PRAGMA table_info` não é executado em `_connect()`.
- [ ] `init_db()` é chamada na importação de `app.main`.
- [ ] Banco criado pelo TCK-005 (sem `compact` nem `compact_seq`) migra em
      `init_db()`; duas execuções seguidas não dão erro e nenhuma linha é
      perdida.
- [ ] Banco que já tem `compact` mas não `compact_seq` ganha só a coluna que
      falta.
- [ ] Flag `compact: false` → nenhuma chamada ao utility, `compact_seq`
      permanece nulo.
- [ ] `npm run check` verde.

## Cenários de teste

- Feliz: 18 pares longos (fixture `lorem * 500` já existente em
  `backend/tests/test_compact.py:243`) → compacta por orçamento; `get_compact`
  devolve `(texto, seq)` com `seq` igual ao do último evento resumido.
- Feliz (não-recompactação): logo depois do cenário acima, um turno curto →
  utility **não** é chamado, `get_compact` devolve o mesmo par, e o system
  prompt continua com `RESUMO DA CAMPANHA`.
- Feliz (`history_events`): sessão com 6 eventos de turno; `compact_seq=4`
  devolve 2 eventos, `compact_seq=None` devolve 6, `compact_seq=999` devolve 0.
- **Feliz (janela maior que `WINDOW_TURNS`, o caso que deixou o defeito passar
  verde)**: sessão com **22 pares** não cobertos, cada um pesado o bastante para
  que só uma parte precise sair por orçamento. Asserções:
  1. `compact_seq` é o `seq` do **último** evento cujo texto aparece no prompt
     do utility;
  2. o **primeiro** turno de histórico no prompt do narrador é o primeiro
     evento devolvido por `history_events(session_id, compact_seq)`
     (`full[n]`) — não use `compact_seq + 1`, que num turno com tag endereça
     um evento `tag`;
  3. nenhum texto que apareceu no prompt do utility aparece no prompt do
     narrador, e vice-versa;
  4. `from_seq` do evento `compact` é o `seq` do primeiro evento não coberto
     antes da compactação.
  Uma fórmula de `covered_seq` calculada contra uma lista truncada em 18 pares
  reprova em (1) e (2) — é para isso que este cenário existe.
- Feliz (25 pares curtos, sem estourar orçamento): nenhuma compactação acontece
  neste ticket (o gatilho por contagem é do TCK-024), e o contexto carrega os 25
  pares — comprovando que o corte por contagem saiu do caminho do compact e que
  nada é descartado em silêncio.
- Borda: `compact_seq` maior que todos os `seq` → contexto com system +
  mensagem nova apenas, nenhuma compactação, nenhum erro.
- Borda: banco legado com `compact` e sem `compact_seq` → migração acrescenta
  uma coluna só; `get_compact` devolve `(None, None)`.
- Borda: sessão legada com resumo gravado e `compact_seq` nulo → tratada como
  "resumo não cobre nada": o contexto inclui todo o histórico e o comportamento
  é o de hoje, sem exceção.
- Falha: utility levanta → `compact_run` com `error` preenchido, nenhum evento
  `compact` novo, `compact_seq` inalterado, turno completa.
- Falha: utility devolve string vazia → mesma degradação, `compact_seq`
  inalterado.

## Rollout e kill switch

Flag **`compact`** em `~/.ooc-local/config.yaml`, default `true`, lida por
`config.flag("compact")` a cada turno (`backend/app/turn.py:68`) — o mesmo kill
switch do TCK-007, sem flag nova. Desligar: editar o YAML; o próximo turno volta
ao corte por janela do TCK-006, e o resumo e o `compact_seq` gravados ficam
intactos no banco, voltando a valer quando a flag religar.

A migração é aditiva (uma coluna nula) e não é revertida pelo kill switch:
desligar a flag é seguro com o schema novo no lugar.

## Observabilidade

Eventos:
- `compact_run` — evento **já existente** desde o TCK-007
  (`backend/app/turn.py:95`), com `session_id`, `turns_summarized`,
  `in_tokens`, `out_tokens`, `duration_ms`, `error`. Este ticket acrescenta
  `from_seq`, `to_seq` e `covered_seq`.
- `context_budget` — inalterado (`backend/app/turn.py:117`).

Métrica de sucesso: numa sessão que já compactou uma vez,
`context_budget.estimated_tokens` para de crescer e nenhum `compact_run` novo
aparece enquanto os turnos seguintes couberem no orçamento.

## i18n

N/A. Nenhum texto de usuário; os prompts pt-br/en do utility
(`backend/app/compact.py:15`) não mudam neste ticket.
