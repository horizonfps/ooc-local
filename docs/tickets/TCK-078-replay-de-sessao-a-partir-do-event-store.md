---
id: TCK-078
title: Reconstruir turno a turno o estado de uma sessão a partir do event store
status: ready
points: 5
blockedBy: []
files:
  - backend/app/replay.py
  - backend/tests/test_replay.py
migration: false
ui: false
risk: low
---

## Problema

A sub-fase 4.2 quer transformar sessões jogadas em dataset de treino, e um
exemplo de treino é o par (prompt exato daquela chamada, resposta que o engine
aceitou). O prompt exato não está guardado em lugar nenhum: o event store
(`backend/app/sessions.py:34-43`) grava o que **aconteceu**, não o que foi
**perguntado**, e a linha `sessions` (`sessions.py:22-33`) guarda só o HUD final
da sessão inteira.

Para remontar a pergunta de cada turno é preciso rejogar o estado:

- HUD daquele turno: `hud_from_start` (`hud.py:111`) mais `advance`
  (`hud.py:120`), `apply_location` (`hud.py:128`) e os eventos `stat`
  (`hud.py:197`) na ordem. E são **dois** HUDs por turno, não um: o director
  roda com o HUD do fim do turno anterior (`turn.py:355` passa `ctx.row.hud`) e o
  juiz roda com o HUD já avançado e já mexido pelas tags (`turn.py:479` passa
  `new_hud`).
- Elenco em cena antes e depois do director: eventos `cast`
  (`cast.py:65`), com a semente `seed_cast_ids` (`cast.py:27`) quando a sessão
  nunca teve um.
- Mentes anteriores: último evento `minds` **antes** do turno (`turn.py:537`
  passa `ctx.minds`, lido no início do turno).
- Janela de histórico e resumo ativo: eventos `player_turn`/`narrator_turn` mais
  o último evento `compact` (`sessions.py:467-487`).

Sem um lugar único que faça isso, cada um dos exportadores (TCK-079 e TCK-080)
reimplementaria a mesma máquina de estado, e as duas cópias divergiriam no
primeiro caso de borda — que aqui é o normal, porque sessões antigas foram
gravadas por versões anteriores do engine.

## Escopo

Dentro:
- `backend/app/replay.py` novo: `TurnSnapshot`, `SessionReplay`,
  `replay_session(session_id)`.
- `backend/tests/test_replay.py` novo.

Fora (explícito):
- **Montar mensagem de prompt.** `replay.py` não importa `judge.py`,
  `director.py`, `minds.py`, `prompt.py` nem `turn.py`, e não chama nenhum
  `build_*_messages`. Ele devolve os **argumentos** que aqueles builders
  recebem; quem os chama é o exportador (TCK-079/TCK-080). Isso é o que mantém
  este módulo pequeno e o que evita import circular com `turn.py`.
- **Texto cru do narrador com as tags nas posições originais.** O event store
  guarda `narrator_turn.text` já limpo (`turn.py:462`) e as tags como eventos
  `tag` separados, com `raw` mas sem posição (`turn.py:465`); a informação foi
  perdida na gravação e não é reconstruível. Passar a persistir o cru daqui pra
  frente é do **TCK-080**, que é o único consumidor (alvo de treino do
  narrator), e é lá que `TurnSnapshot` ganha o campo.
- Escrever, migrar ou apagar qualquer coisa. `replay_session` é somente leitura.
- Turnos meta (`meta_player_turn`/`meta_narrator_turn`, `turn.py:329-330`). São
  turnos de comando, ficam fora da memória narrativa por decisão da Fase 3 e não
  viram exemplo de treino. Ver "Detalhes técnicos" para o efeito deles no estado.
- CLI. `replay.py` não tem `__main__`; quem tem é `app.dataset` (TCK-079).
- Qualquer arquivo de `frontend/`.

## Comportamento esperado

Do ponto de vista do chamador: dado um `session_id` de uma sessão cujo cenário
ainda carrega, `replay_session` devolve o cenário, o start e uma lista de
snapshots — um por turno jogado, na ordem — em que cada snapshot tem tudo que os
builders do turno receberam naquele momento. Sessão sem turno nenhum devolve
lista vazia. Sessão cujo cenário sumiu do disco levanta `ScenarioNotFound`, o
mesmo erro que `load_turn_context` já levanta (`turn.py:73-74`).

Snapshot que o motor não conseguiu reconstruir com fidelidade vem marcado
(`exact=False`) em vez de vir errado em silêncio.

## Detalhes técnicos

### Superfície

```python
class TurnSnapshot(BaseModel):
    seq: int                                # seq do evento narrator_turn
    turn: int                               # hud.turn depois do advance
    message: str                            # texto CRU do jogador (player_turn.text)
    mode: str | None                        # player_turn.mode, None em evento antigo
    narrator_text: str                      # narrator_turn.text (limpo)
    suggestions: list[str]
    hud_start: HudState                     # fim do turno anterior; input do director
    hud_after_tags: HudState                # advance + LOC + STAT de tag; input do juiz
    hud_end: HudState                       # depois dos stats do juiz
    touched_ids: list[str]
    cast_before: list[str]                  # input do director
    cast_after: list[str]                   # input do minds e do prompt-mestre
    minds_before: dict[str, MindView]
    history_before: list[Event]             # player_turn/narrator_turn com seq menor
    compact: str | None
    compact_seq: int | None
    exact: bool


class SessionReplay(BaseModel):
    session_id: str
    scenario: LoadedScenario
    start: StartConfig
    locale: str
    turns: list[TurnSnapshot]


def replay_session(session_id: str) -> SessionReplay: ...
```

### Algoritmo

1. `row = get_session_row(session_id)` (`sessions.py:274`); carrega cenário e
   start com o mesmo `try/except (ScenarioError, KeyError)` de
   `load_turn_context` (`turn.py:70-74`), levantando `ScenarioNotFound`.
2. `events = read_events(session_id)` — **sem** filtro de `kinds`, porque a
   ordem relativa entre `compact`, `player_turn`, `stat`, `cast` e `minds` é o
   que carrega a informação.
3. Estado inicial: `hud = ensure_stats(hud_from_start(start), scenario.stats)`
   com `stats` semeado pelos defaults. `create_session` (`sessions.py:184-185`)
   faz isso com `hud.model_copy(update={"stats": {stat.id: stat.default ...}})`
   e não com `ensure_stats`; o resultado é o mesmo e aqui se usa `ensure_stats`
   (`hud.py`) porque é a função que já existe para esse fim; `cast = seed_cast_ids(scenario, start)` filtrado
   para ids ainda presentes (mesmo filtro de `turn.py:80`); `minds = {}`;
   `compact = None`; `compact_seq = None`; `exact = True`.
4. Varre os eventos em ordem, agrupando por turno. Um turno começa num
   `player_turn` e termina imediatamente antes do próximo `player_turn` ou
   `meta_player_turn`, ou no fim da lista.
5. Antes de entrar no grupo, o estado corrente é o `hud_start`/`cast_before`/
   `minds_before` daquele turno, e `history_before` é a lista de
   `player_turn`/`narrator_turn` com `seq` menor que o do `player_turn` do grupo.
6. Dentro do grupo, na ordem em que `turn.py:460-469` grava:
   - `narrator_turn` → `narrator_text`, `suggestions` (`payload.get("suggestions", [])`), `seq`;
   - eventos `tag` → `touched_ids` é a lista de `payload["args"][0]` dos que têm
     `kind == "STAT"` e `valid is True`, na ordem (**é assim que `turn.py:451`
     calcula**, a partir das tags, não dos eventos `stat`: uma tag válida cujo
     clamp não moveu nada não gera evento `stat` mas ocupa o id);
   - `hud_after_tags = advance(hud_start)`, depois `apply_location` para cada
     `tag` com `kind == "LOC"` e `valid is True`, depois os eventos `stat` com
     `payload["source"] == "tag"`;
   - `hud_end` = `hud_after_tags` mais os eventos `stat` com `source != "tag"`;
   - evento `cast` no grupo → `cast_after`; ausente → `cast_after = cast_before`;
   - evento `minds` no grupo → vira o `minds_before` do **próximo** turno.
7. Aplicar um evento `stat` é **escrever o `value` gravado**, não rechamar
   `apply_stat`: o evento carrega o valor final já clampado
   (`hud.py:197-198`), e reexecutar a aritmética contra um `stats.yaml` que o
   autor pode ter editado desde então produziria um número diferente do que o
   jogador viu.
8. Evento `compact` → atualiza `compact` (`payload["text"]`) e `compact_seq`
   (`payload["to_seq"]`). Ele é gravado **antes** do `player_turn` do turno que o
   gerou (`set_compact` em `turn.py:181` roda dentro de `_maybe_compact`, antes
   do stream; o `append_events` do turno só vem em `turn.py:469`), então varrer
   em ordem já entrega o resumo certo para o turno corrente.
9. Turnos meta: `meta_player_turn`/`meta_narrator_turn` fecham o grupo anterior e
   **não** abrem snapshot. Eles não alteram HUD, elenco nem mentes
   (`turn.py:288-344` grava só os dois eventos e sai), e não entram em
   `history_before` — `history_events` (`turn.py:91`) filtra por
   `("player_turn", "narrator_turn")`, e a janela do narrador tem que bater com
   a do engine.

### `exact`

`False` a partir do turno em que a reconstrução deixa de ser fiel, e daí em
diante até o fim da sessão (estado corrompido não se recupera). Um caso conhecido
e concreto: um evento `stat` com `source == "judge"` para um id que não está em
`scenario.stats` nem em `hud.dynamic_stats` é a criação de um stat dinâmico
(`turn.py:504` a partir de `apply_judgement:279-281`), e o evento só carrega
`id`, `delta`, `value` e `source` — `name`, `min` e `max` do `DynamicStat`
(`hud.py:34-38`) nunca foram persistidos. O replay registra o id com
`DynamicStat(name=id, value=value, min=0, max=value)` para não perder a linha do
HUD, e marca `exact=False`, porque o `_stat_lines` do juiz (`judge.py:95-99`)
imprime `name`, `min` e `max` no prompt e sairia diferente do original.

Outros gatilhos de `exact=False`: `narrator_turn` sem `player_turn` antes
(evento órfão), `player_turn` sem `narrator_turn` no grupo (turno que falhou
depois de gravar — não deveria existir, porque `turn.py:460-469` grava os dois na
mesma transação, mas um banco editado à mão pode ter), e payload sem a chave
`text`.

Nada disso levanta exceção. Um evento corrompido não pode derrubar o replay
inteiro; é a mesma defesa que `read_cast_ids` (`sessions.py:490-501`) e
`read_minds` (`sessions.py:504-520`) já aplicam.

### Desempenho

Uma passada única sobre `read_events(session_id)` (índice
`events_session_seq`, `sessions.py:43`). `history_before` é uma **fatia** da
lista acumulada, não uma consulta por turno: sessão de 200 turnos faz 1 query,
não 200.

### Ressalva de porte

Estimativa: ~200 linhas de `replay.py` e ~250 de teste, ~450 no total.
Exceção registrada pelo coordenador do HRZ Workflow (03/09/2026): o porte de
~450 é aceito; este módulo é a base de TCK-079 e TCK-080 e quebrá-lo em dois
deixaria um deles sem consumidor. Os dois cortes abaixo **não** são
condicionais, são a forma obrigatória da suíte:
1. Os cenários de `exact=False` de evento órfão e de payload sem `text` são um
   único teste parametrizado.
2. Os dois cenários de `compact` (com e sem resumo ativo) são um só teste, com
   duas asserções.
Nenhum outro corte é permitido: o cenário dos dois HUDs por turno e o de
precedência de tag são o núcleo do módulo.

## Contrato público

```python
# backend/app/replay.py
class TurnSnapshot(BaseModel):
    seq: int
    turn: int
    message: str
    mode: str | None
    narrator_text: str
    suggestions: list[str]
    hud_start: HudState          # input do director (turn.py:355)
    hud_after_tags: HudState     # input do juiz (turn.py:479)
    hud_end: HudState
    touched_ids: list[str]       # input do juiz (turn.py:451)
    cast_before: list[str]       # input do director (turn.py:355)
    cast_after: list[str]        # input do minds (turn.py:537)
    minds_before: dict[str, MindView]   # input do minds (turn.py:537)
    history_before: list[Event]  # player_turn/narrator_turn anteriores, em ordem
    compact: str | None
    compact_seq: int | None
    exact: bool

class SessionReplay(BaseModel):
    session_id: str
    scenario: LoadedScenario
    start: StartConfig
    locale: str
    turns: list[TurnSnapshot]

def replay_session(session_id: str) -> SessionReplay
    # levanta app.sessions.SessionNotFound / ScenarioNotFound
```

Consumidores já enfileirados: TCK-079 (exporta `judge.jsonl`, `director.jsonl` e
`minds.jsonl` chamando os builders com estes campos) e TCK-080 (exporta
`narrator.jsonl` e acrescenta `narrator_raw` ao `TurnSnapshot`).

## Acceptance criteria

- [ ] Sessão com 3 turnos gravados devolve 3 snapshots, na ordem, com
      `turn == 1, 2, 3`.
- [ ] `hud_start` do turno N é igual a `hud_end` do turno N-1, e o `hud_start`
      do turno 1 é igual ao HUD do `create_session`.
- [ ] Turno com `[LOC:...]` e `[STAT:reputacao:+3]`: `hud_after_tags` tem o
      `location` novo, `turn` incrementado, `time` avançado em `TURN_MINUTES` e
      `reputacao` com o valor do evento `stat` de `source: "tag"`;
      `touched_ids == ["reputacao"]`.
- [ ] Turno em que o juiz mexeu num stat: `hud_after_tags` **não** tem a mudança
      do juiz e `hud_end` tem.
- [ ] Tag `STAT` válida cujo clamp não moveu nada (sem evento `stat`
      correspondente) mesmo assim aparece em `touched_ids`.
- [ ] Turno com evento `cast`: `cast_before` é o elenco anterior e `cast_after`
      é o do evento; turno sem evento `cast`: os dois são iguais.
- [ ] `minds_before` do turno N é o mapa do último evento `minds` gravado até o
      turno N-1; no turno 1 é `{}`.
- [ ] `history_before` do turno 3 tem exatamente os 4 eventos
      `player_turn`/`narrator_turn` dos turnos 1 e 2, em ordem, e nenhum evento
      `tag`, `stat`, `cast`, `minds` ou meta.
- [ ] Sessão com evento `compact`: os turnos anteriores a ele têm
      `compact is None`, e os posteriores (inclusive o turno em que ele foi
      gravado) têm o texto e o `to_seq` dele.
- [ ] Turno meta no meio da sessão não vira snapshot e não aparece em
      `history_before` de nenhum turno seguinte.
- [ ] Sessão sem turno nenhum devolve `turns == []` e não levanta.
- [ ] Sessão cujo cenário foi apagado levanta `ScenarioNotFound`;
      `session_id` inexistente levanta `SessionNotFound`.
- [ ] Evento `stat` com `source: "judge"` para id desconhecido: o snapshot dele e
      todos os seguintes vêm com `exact is False`, e o replay não levanta.
- [ ] `player_turn` com payload sem `mode` (evento antigo) devolve `mode is None`.
- [ ] `npm run check` verde sem editar nenhum teste existente.

## Cenários de teste

Suíte existente que muda de preparação: **nenhuma**. Este ticket só acrescenta um
módulo e um arquivo de teste; nenhum símbolo existente muda de assinatura ou de
comportamento. Verificado por Grep: não há nenhuma ocorrência de `replay` em
`backend/app/` nem em `backend/tests/`.

Preparação de `backend/tests/test_replay.py`: isolamento por
`monkeypatch.setenv("OOC_SESSIONS_DB", str(tmp_path / "sessions.db"))` — é assim
que a suíte isola o banco (`test_sessions.py:69-72`, `test_turn.py:78`), **não**
por monkeypatch de `app.sessions.db_path`, que lê a env var em tempo de chamada
(`sessions.py:121-125`). Cenário escrito em `tmp_path` com
`monkeypatch.setattr("app.scenario.scenarios_dir", lambda: root)`
(`test_sessions.py:74-79`). Sessões criadas com `create_session` e eventos
inseridos com `append_events` diretamente — **sem** subir turno de verdade: o
objetivo é fixar o contrato de leitura do event store, e montar os eventos à mão
é o único jeito de testar payload de versão antiga.

- Feliz: 3 turnos completos (player/narrator/tag/stat/cast/minds) → snapshots com
  todos os campos.
- Feliz: os dois HUDs por turno, com tag `LOC` e tag `STAT`.
- Feliz: `hud_start[N] == hud_end[N-1]` numa sessão de 3 turnos.
- Feliz: `compact` gravado no meio da sessão aparece do turno dele em diante.
- Borda: turno sem evento `cast` e sem evento `minds`.
- Borda: sessão cujo start declara `characters` explícito → `cast_before` do
  turno 1 é `seed_cast_ids`, não o elenco inteiro.
- Borda: turno meta entre dois turnos normais.
- Borda: `player_turn` sem `mode`, `narrator_turn` sem `suggestions`.
- Borda: sessão com 0 turnos.
- Falha: stat dinâmico criado pelo juiz → `exact is False` daquele turno em
  diante, com o id presente em `hud_end.dynamic_stats`.
- Falha: `narrator_turn` órfão (sem `player_turn` antes) → não vira snapshot,
  não levanta, e marca `exact=False`.
- Falha: cenário apagado → `ScenarioNotFound`; sessão inexistente →
  `SessionNotFound`.

## Rollout e kill switch

N/A. Módulo somente-leitura sem ponto de entrada: nenhuma rota, nenhum
`__main__`, nenhuma chamada a partir de `turn.py` ou `main.py`. Não há o que
desligar porque nada em produção o executa até o TCK-079 existir.

## Observabilidade

Eventos: N/A neste ticket. `replay_session` não emite telemetria — ele roda em
lote, fora do servidor, e quem conta sessões, turnos e descartes é o exportador
(`dataset_export` no TCK-079, com `sessions`, `turns` e `skipped`).

Métrica de sucesso: numa base real de sessões (`~/.ooc-local/sessions.db`), a
razão de snapshots com `exact is True` sobre o total fica acima de 0,95. Abaixo
disso, o event store perdeu informação demais e o dataset precisa de mais campos
persistidos antes de valer treino.

## i18n

N/A. `SessionReplay.locale` é o `scenario.meta.locale` repassado, para o
exportador agrupar por língua; nenhuma string nova.
