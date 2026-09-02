---
id: TCK-061
title: Aplicar a tag STAT no HUD e levar status com nível ao prompt do narrador
status: done
points: 4
blockedBy: [TCK-060]
files:
  - backend/app/hud.py
  - backend/app/turn.py
  - backend/app/prompt.py
  - backend/tests/test_stats_engine.py
  - backend/tests/test_turn.py
  - backend/tests/test_prompt.py
migration: false
ui: false
risk: low
---

## Problema

O TCK-060 declarou o schema (`StatDef`), o estado (`HudState.stats`) e a
projeção (`StatView`), mas nada os move. A tag `[STAT:id:±N]` é reconhecida pelo
parser desde sempre (`backend/app/tags.py:20-21`) e o turno grava um evento `tag`
com ela (`turn.py:321-322`) — e o valor nunca muda. Um narrador que emite
`[STAT:reputacao:+5]` hoje produz um evento morto no banco.

O narrador também não tem como narrar coerente: o prompt tem `## ESTADO DO JOGO`
com turno/local/hora/clima (`prompt.py:288-295`) e nada sobre o jogador. Sem
saber que a reputação está em 15/100 e que isso significa "ninguém te leva a
sério", ele escreve NPCs simpáticos num personagem odiado pela escola.

Este ticket fecha o laço: a tag muda o HUD, a mudança vira evento, o SSE devolve
o valor novo e o prompt do turno seguinte diz onde o jogador está.

## Escopo

Dentro:
- `backend/app/hud.py`: `STAT_EVENT_KIND`, `stat_event()`, `ensure_stats()`,
  `stat_ids()` e `apply_stat()` — todas puras, no molde de `apply_location`
  (`hud.py:68-79`).
- `backend/app/turn.py`: `ensure_stats` na carga do contexto; aplicação das tags
  STAT no HUD do turno; rebaixamento de `valid` da tag com id desconhecido;
  eventos `stat` no **mesmo** `append_events` do turno; `stats` no payload `hud`
  do SSE; propriedade `stats` no `game_turn`.
- `backend/app/prompt.py`: seção `## STATUS DO JOGADOR` / `## PLAYER STATUS`
  depois de `## ESTADO DO JOGO`; linha sobre `[STAT:id:±N]` no `format_body`;
  `MASTER_PROMPT_VERSION` 8 → 9.
- `backend/tests/test_stats_engine.py`: unitários das funções puras e
  integração pela rota, no molde de `backend/tests/test_turn.py`.
- Adaptação de preparação em `backend/tests/test_turn.py` e do pino de versão em
  `backend/tests/test_prompt.py`.

Fora (explícito):
- `backend/app/tags.py`. O parser já valida `STAT` com 2 args e inteiro com sinal
  (`tags.py:20-21`) e os 4 testes de `test_tags.py:4-61,177-195` fixam esse
  comportamento. Quem sabe se o **id existe** é o engine, que tem o cenário; o
  parser não tem e não vai ter. **Este ticket não edita `tags.py`.**
- `backend/app/sessions.py`. `SessionDetail.stats` já é preenchido por
  `stat_views` no TCK-060; `create_session` já semeia `hud.stats`. Nada a fazer.
- Stat dinâmico (`hud.dynamic_stats`) sendo **criado**: quem cria é o juiz
  (TCK-062/069). Aqui `dynamic_stats` só é **lido** — um id que já exista lá é
  alvo válido de tag, e é isso.
- Juiz, INFO, sugestões, lorebook, comandos: TCK-069/072/075.
- Qualquer arquivo de frontend. As barras são o TCK-067, contra o contrato
  congelado no TCK-060.

## Comportamento esperado

Num cenário com `stats.yaml`, o narrador que emite `[STAT:reputacao:-5]` faz a
barra de reputação cair 5 pontos no fim do turno; o HUD do SSE já vem com o valor
novo e o turno seguinte nasce com o número certo no prompt. Chegando ao fundo da
faixa, o valor para em `min` e o narrador continua narrando normalmente — clamp
não é erro.

Tag com id que o cenário não declara não muda nada, aparece no histórico de tags
como inválida e não vira evento `stat`. Cenário sem `stats.yaml` se comporta
exatamente como hoje: nenhuma seção de status no prompt, nenhum evento `stat`,
`hud.stats` vazio no SSE.

Turno que falha (provider explode, texto vazio) não grava mudança de stat
nenhuma, do mesmo jeito que hoje não grava turno.

## Detalhes técnicos

### `backend/app/hud.py`

```python
STAT_EVENT_KIND = "stat"

def stat_ids(hud: HudState, stats: list["StatDef"]) -> set[str]
def ensure_stats(hud: HudState, stats: list["StatDef"]) -> HudState
def apply_stat(hud: HudState, stats: list["StatDef"], stat_id: str, delta: int) -> tuple[HudState, tuple[int, int] | None]
def stat_event(stat_id: str, delta: int, value: int, source: str) -> tuple[str, dict]
```

`hud.py` continua sem importar `app.scenario` em runtime (`scenario.py:10` importa
de volta): `StatDef` entra por `TYPE_CHECKING` e anotação em string, como
`StartConfig` já faz em `hud.py:8-9,51`.

- `stat_ids`: união dos `stat.id` declarados com as chaves de
  `hud.dynamic_stats`. É a fonte única de "esse id existe?".
- `ensure_stats`: devolve o HUD com toda chave declarada e ausente preenchida com
  `stat.default`; **não** remove chave de stat que o autor apagou do cenário
  (o valor pode voltar a fazer sentido se o autor desfizer a edição, e
  `stat_views` já ignora id desconhecido). Sem nada a preencher, devolve o mesmo
  objeto — `model_copy` só quando muda, igual a `apply_location` (`hud.py:77-79`).
- `apply_stat`: id fora de `stat_ids` → `(hud, None)`. Faixa vem do `StatDef`
  declarado ou do `DynamicStat`. Valor novo = `min(max(atual + delta, lo), hi)`;
  igual ao atual → `(hud, None)` (clamp que não moveu não é mudança). Caso
  contrário devolve o HUD novo e `(delta_efetivo, valor_novo)`, com
  `delta_efetivo = valor_novo - atual` (é o que o freeze do TCK-060 congela como
  `delta` do evento `stat`: o efetivo, nunca o pedido). Stat dinâmico atualiza
  `dynamic_stats[id].value`, não `hud.stats`.
- `stat_event`: `(STAT_EVENT_KIND, {"id": ..., "delta": ..., "value": ...,
  "source": ...})`, no formato `NewEvent` que `append_events` consome — molde
  exato de `cast_event` (`cast.py:54-55`).

### `backend/app/turn.py`

**Onde `ensure_stats` roda.** Em `load_turn_context` (`turn.py:51-66`), no
`SessionRow` que vai para o `TurnContext`:

```python
row = row.model_copy(update={"hud": ensure_stats(row.hud, scenario.stats)})
```

É o único ponto certo: `_maybe_compact` (`turn.py:289-291`) monta o system prompt
a partir de `ctx.row.hud` **antes** de `hud = ctx.row.hud` (`turn.py:292`), então
preencher depois deixaria o primeiro prompt de uma sessão antiga sem os valores.
E `load_turn_context` também é chamado pela rota (`main.py:146`), então o `ctx`
que chega em `run_turn` já vem completo pelos dois caminhos. Nada é persistido
aqui: `SessionRow` é objeto em memória, e o HUD só vai ao banco no
`append_events` do fim do turno (`turn.py:325`).

**Aplicação das tags.** Depois de `new_hud = advance(hud)` e do laço de LOC
(`turn.py:312-316`), no mesmo laço ou num segundo laço sobre `tags`, na ordem de
aparição:

```python
known = stat_ids(new_hud, ctx.scenario.stats)
resolved_tags: list[Tag] = []
stat_events: list[tuple[str, dict]] = []
for tag in tags:
    if tag.kind == "STAT" and tag.valid and tag.args[0] not in known:
        tag = tag.model_copy(update={"valid": False})
    elif tag.kind == "STAT" and tag.valid:
        new_hud, change = apply_stat(new_hud, ctx.scenario.stats, tag.args[0], int(tag.args[1]))
        if change is not None:
            delta, value = change
            stat_events.append(stat_event(tag.args[0], delta, value, "tag"))
    resolved_tags.append(tag)
tags = resolved_tags
```

Reatribuir `tags` é deliberado: a closure `emit_game_turn` (`turn.py:200-215`)
conta `invalid_tags` sobre essa mesma lista, e o evento `tag` (`turn.py:321-322`)
é escrito a partir dela. Sem a reatribuição, a tag apareceria `valid: True` no
banco e o contador diria que estava tudo certo.

Duas tags do mesmo id no mesmo turno aplicam em sequência e geram **dois**
eventos `stat`, cada um com seu `delta` e o `value` resultante daquele passo. O
`int(tag.args[1])` é seguro: `_validate` já garantiu `^[+-]?[0-9]+$`
(`tags.py:21`) e a validade foi checada antes.

**Persistência.** `stat_events` entra na lista `events` do `append_events` que já
existe (`turn.py:317-325`), depois dos eventos `tag` e antes do
`pending_cast_event`. Turno que falha antes do `append_events` não grava nada — é
o que `test_turn_provider_error_mid_stream_does_not_persist:268` e
`test_turn_that_is_only_a_tag_is_treated_as_failure:231` afirmam com
`read_events(...) == []`, e continua verdade porque o `return` de turno vazio
(`turn.py:308-310`) acontece antes.

**SSE.** `turn.py:328-329` passa a ser:

```python
yield {
    "hud": {
        **new_hud.model_dump(exclude={"stats", "dynamic_stats"}),
        "cast": cast,
        "stats": [view.model_dump() for view in stat_views(ctx.scenario, new_hud)],
    }
}
```

O `exclude` é obrigatório, não cosmético: sem ele o `stats` cru de `HudState`
(mapa `id -> int`) e a lista de `StatView` disputam a mesma chave. `stats` vai em
**todo** turno bem-sucedido, inclusive em cenário sem stats (aí é `[]`) — mesma
decisão do `cast` no TCK-055, pelo mesmo motivo: ausência significa "inalterado"
no contrato do TCK-060, e mandar sempre poupa a UI de adivinhar.

### `backend/app/prompt.py`

Chaves novas nos dois locales de `_TEMPLATES` (`prompt.py:47-181`):
`status_header` (`"## STATUS DO JOGADOR"` / `"## PLAYER STATUS"`) e
`status_level_label` (`"Nível atual"` / `"Current level"`).

```python
def _status(scenario: LoadedScenario, hud: HudState, template: dict[str, str]) -> str | None
```

Usa `stat_views(scenario, hud)` — a mesma função que alimenta a UI, para prompt e
tela nunca divergirem. `[]` devolve `None` e a seção não aparece. Uma linha por
stat:

`Reputação: 55/100 — Quanto a escola te respeita. Nível atual: Você é um aluno comum.`

`description` e `Nível atual` entram só quando existem; sem os dois a linha é
`Reputação: 55/100`. O texto do level e a descrição passam por
`" ".join(valor.split())` antes de entrar, para que um YAML com bloco de várias
linhas não quebre a linha do prompt (mesma defesa que `_roster` já faz em
`prompt.py:219-220`).

A seção entra logo depois da de HUD (`prompt.py:295`) e antes de
`## CENA DE ABERTURA`. `build_master_prompt` **não** muda de assinatura:
`scenario.stats` e `hud.stats` já chegam nos parâmetros que ela recebe hoje.

`format_body` dos dois locales: a linha que hoje diz
`"Você pode emitir as tags inline [STAT:nome:±N], ..."` (`prompt.py:101`) passa a
dizer `[STAT:id:±N]`, e ganha uma frase dizendo que os únicos ids válidos são os
listados em `## STATUS DO JOGADOR`, e que sem essa seção a tag não deve ser
emitida. `MASTER_PROMPT_VERSION` sobe para **9**.

## Contrato público

```python
# backend/app/hud.py
STAT_EVENT_KIND: str  # "stat"
def stat_ids(hud: HudState, stats: list["StatDef"]) -> set[str]
def ensure_stats(hud: HudState, stats: list["StatDef"]) -> HudState
def apply_stat(hud: HudState, stats: list["StatDef"], stat_id: str, delta: int) -> tuple[HudState, tuple[int, int] | None]
    # (hud novo, (delta efetivo, valor novo)) quando mudou; (hud, None) quando id desconhecido ou clamp nao moveu
def stat_event(stat_id: str, delta: int, value: int, source: str) -> tuple[str, dict]
    # source: "tag" | "judge"
```

Consumido pelo **TCK-069**, que reusa `apply_stat` e `stat_event(..., "judge")`
para aplicar o parecer do juiz no mesmo turno. O payload do evento `stat` e o
formato de `hud.stats` no SSE já estão congelados no TCK-060; esta seção só
publica as assinaturas.

## Acceptance criteria

- [ ] Cenário com `reputacao` (0..100, default 40) e narrador emitindo
      `[STAT:reputacao:+5]`: o SSE devolve `hud.stats` com `value == 45`, o banco
      tem um evento `stat` `{"id": "reputacao", "delta": 5, "value": 45,
      "source": "tag"}`, e `GET /api/sessions/{id}` devolve 45.
- [ ] O turno seguinte nasce com `Reputação: 45/100` no system prompt.
- [ ] `[STAT:reputacao:-100]` com valor em 40 grava `value == 0` (clamp em `min`)
      e um evento `stat` com `delta: -40` (o efetivo, não o pedido); um segundo
      `[STAT:reputacao:-5]`
      logo depois **não** grava evento nenhum (o clamp não moveu).
- [ ] `[STAT:fantasma:+1]` não muda HUD, não grava evento `stat`, e o evento
      `tag` correspondente tem `valid: false`.
- [ ] Duas tags do mesmo id no mesmo turno geram dois eventos `stat`, na ordem,
      com o `value` acumulado.
- [ ] Cenário sem `stats.yaml`: nenhuma seção `## STATUS DO JOGADOR` no prompt,
      `hud.stats == []` no SSE, nenhum evento `stat`, e `[STAT:x:+1]` sai como
      `valid: false`.
- [ ] A linha de status traz descrição e `Nível atual` quando existem, e só
      `Nome: valor/max` quando não existem; o level ativo é o último `from` menor
      ou igual ao valor.
- [ ] Sessão criada antes deste ticket (HUD sem a chave `stats`) joga um turno,
      e o `append_events` grava o HUD já com todos os defaults preenchidos.
- [ ] Turno que falha no meio do stream depois de uma tag STAT válida não grava
      evento `stat` nenhum (`read_events(...) == []`).
- [ ] `MASTER_PROMPT_VERSION == 9` e `game_turn` traz a propriedade `stats`.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente que muda **de preparação** (asserções preservadas):

- `backend/tests/test_turn.py` — **é o arquivo que quebra sem adaptação**.
  `test_turn_records_tags_as_events:130` manda `[STAT:reputacao:+1]` num cenário
  que não tem `stats.yaml` e afirma
  `tag_events[0].payload == {..., "valid": True}` (`:152`). Com este ticket o id
  é desconhecido e a tag vira inválida.
  **Estratégia escolhida (uma só):** `_write_scenario` (`test_turn.py:39-53`)
  ganha um parâmetro `stats: str | None = None` que escreve `stats.yaml` quando
  recebido, e **só** `test_turn_records_tags_as_events` passa um `STATS_YAML` de
  módulo com `reputacao` (0..100, default 40). Preparação de duas linhas; o corpo
  do teste e as duas asserções ficam idênticos. Os outros 28 testes do arquivo
  continuam sem `stats.yaml` — que é justamente o cenário "sem stats" que
  precisamos ver verde.
  Verificados e **não** afetados: `test_turn_strips_hud_echo_and_keeps_tag_events:156`
  afere `len(tag_events) == 1`, não a validade; `test_turn_that_is_only_a_tag_is_treated_as_failure:231`
  afere `read_events(...) == []` e o turno segue falhando por texto vazio antes
  de qualquer persistência; `test_turn_happy_path_emits_deltas_hud_then_done:103`
  afere `events[-1]["hud"]["turn"] == 1`, e o payload só ganha uma chave;
  `test_turn_system_prompt_contains_world_characters_and_hud:396` afere inclusão
  (`"## ESTADO DO JOGO" in system_prompt`), nunca a lista fechada de seções.
- `backend/tests/test_prompt.py` — `test_master_prompt_version_is_eight:624` é um
  **pino de versão**, cujo propósito declarado é obrigar um bump consciente a
  cada mudança de prompt. Ele é renomeado para
  `test_master_prompt_version_is_nine` e a constante passa a 9. **Esta é a única
  edição de asserção autorizada no ticket**, e vale só para este teste, porque
  ele não afere comportamento: afere que alguém lembrou de subir o número. Todos
  os outros testes do arquivo aferem inclusão ou ordem relativa de seções
  (`:112-147`, `:486-499`) e ficam intactos, porque os cenários de `_load`
  (`:100-105`) não têm `stats.yaml` e a seção nova não aparece neles.
- `backend/tests/test_compact.py` — verificado, **não** entra em `files`: o
  `_write_scenario` de lá não tem `stats.yaml`, o `_config` já desliga o director
  (`:69`) e nenhuma asserção toca em tag ou HUD além de `turn`/`location`.
- `backend/tests/test_turn_director.py` — verificado, **não** entra em `files`:
  afere `events[-1]["hud"]["cast"]`, e o payload só ganha a chave `stats`.

Cenários novos (`backend/tests/test_stats_engine.py`; a metade de rota segue o
padrão de `test_turn.py`: `TestClient`, cenário em `tmp_path`, `_config()` sem
papel `utility`, `stream_chat` monkeypatchado):

Unitários das funções puras:
- Feliz: `apply_stat` com `+5` sobre 40 devolve `(hud novo, (5, 45))` e não muta
  o original.
- Borda: `+100` sobre 40 num stat de max 100 devolve `(hud novo, (60, 100))`; um
  segundo `+5` devolve `(hud, None)`.
- Borda: `-100` sobre 40 num stat de min 0 devolve `(hud novo, (-40, 0))`.
- Borda: `apply_stat` com id desconhecido devolve `(hud, None)` e não cria chave.
- Borda: `apply_stat` sobre um id que só existe em `hud.dynamic_stats` clampa
  pela faixa do `DynamicStat` e escreve em `dynamic_stats`, não em `stats`.
- Borda: `ensure_stats` preenche só o que falta, preserva valor já gravado, e
  devolve o mesmo objeto quando não há nada a preencher.
- Borda: `ensure_stats` preserva chave de stat que sumiu do cenário.
- Borda: `stat_ids` une declarados e dinâmicos.
- Feliz: `stat_event("reputacao", -5, 35, "tag")` devolve
  `("stat", {"id": "reputacao", "delta": -5, "value": 35, "source": "tag"})`.

Prompt:
- Feliz: com dois stats, a seção `## STATUS DO JOGADOR` aparece depois de
  `## ESTADO DO JOGO` e antes de `## CENA DE ABERTURA`, com uma linha por stat na
  ordem do cenário.
- Feliz: a linha traz `— descrição` e `Nível atual: ...` quando existem; um stat
  sem descrição e sem levels sai como `Energia: 80/100`.
- Feliz: locale `en` usa `## PLAYER STATUS` e `Current level`.
- Borda: cenário sem stats não produz a seção.
- Borda: descrição escrita como bloco YAML de três linhas vira uma linha só no
  prompt.
- Borda: `format_body` menciona `[STAT:id:±N]` nos dois locales.

Rota (integração):
- Feliz: `[STAT:reputacao:+5]` → `hud.stats` no SSE com 45, um evento `stat`,
  `GET /api/sessions/{id}` com 45, e o prompt do turno 2 com `45/100`.
- Borda: `[STAT:fantasma:+1]` → evento `tag` com `valid: false`, nenhum evento
  `stat`, HUD intacto.
- Borda: duas tags do mesmo id no mesmo turno → dois eventos `stat` na ordem.
- Borda: cenário sem `stats.yaml` → `hud.stats == []` e nenhum evento `stat`.
- Borda: sessão gravada com HUD sem a chave `stats` (INSERT direto no SQLite, no
  molde de `test_sessions.py:101-148`) joga um turno e sai com todos os defaults
  no banco.
- Falha: provider explode no meio depois de uma tag STAT válida →
  `read_events(...) == []`.

## Rollout e kill switch

N/A — sem flag própria, e `risk: low` por mudar o fluxo de persistência do
turno. O desligamento efetivo é estrutural e já é o estado de todo cenário
existente: **cenário sem `stats.yaml` não tem stat nenhum**, e aí o
comportamento é byte a byte o de hoje, exceto pelo `hud.stats: []` aditivo no
SSE e pelo bump de `MASTER_PROMPT_VERSION`. Reverter um cenário que deu problema
é apagar (ou esvaziar) o `stats.yaml` dele, sem tocar em código nem em config.

Os eventos `stat` já gravados continuam valendo como histórico; o estado vivo
mora em `hud.stats`, e apagar o `stats.yaml` faz `stat_views` parar de projetar
aquele id sem apagar nada do banco.

## Observabilidade

Eventos (via `emit` de `backend/app/observability.py`):
- `game_turn` (`turn.py:200-215`) ganha a propriedade `stats`, com o número de
  eventos `stat` gravados no turno (0 quando não houve mudança), e `None` quando
  o turno falhou antes de ter contexto — mesma defesa que `cast` já usa em
  `turn.py:214`.
- `invalid_tags`, que já existe no `game_turn`, passa a contar também as tags
  STAT rebaixadas por id desconhecido. É o sinal de que o narrador está
  inventando id, e é medido sem evento novo.
- Nenhum evento de telemetria novo: os eventos `stat` da tabela `events` são
  estado, não telemetria.

Métrica de sucesso: em 20 turnos jogados no `exemplo-escola` depois do TCK-068,
`invalid_tags` fica em zero para tags STAT e pelo menos um evento `stat` é
gravado — o narrador usa os ids que recebeu e o valor se move de verdade.

## i18n

Duas chaves de template no `backend/app/prompt.py`, nos dois locales já
existentes:

| chave | pt-br | en |
| --- | --- | --- |
| `status_header` | `## STATUS DO JOGADOR` | `## PLAYER STATUS` |
| `status_level_label` | `Nível atual` | `Current level` |

Mais a frase sobre os ids válidos de `[STAT:id:±N]` acrescentada ao `format_body`
de `pt-br` (`prompt.py:95-113`) e de `en` (`prompt.py:161-179`). Nenhuma string
de UI. `StatDef.name`, `description` e o texto do level vêm do YAML do cenário,
já no locale do cenário, e não passam por tradução.
