---
id: TCK-080
title: Persistir o texto cru do narrador e exportar narrator.jsonl
status: ready
points: 3
blockedBy: [TCK-078, TCK-079]
files:
  - backend/app/turn.py
  - backend/app/replay.py
  - backend/app/dataset.py
  - backend/tests/test_turn.py
  - backend/tests/test_replay.py
  - backend/tests/test_dataset_export.py
migration: false
ui: false
risk: low
---

## Problema

O alvo de treino do narrator próprio (sub-fase 4.4) é o turno **com as tags nas
posições em que o modelo as emitiu**: `[SUGGEST:]`, `[STAT:]`, `[SPRITE:]`,
`[LOC:]` no meio da prosa. É exatamente essa informação que o engine joga fora
ao gravar.

`run_turn` acumula o texto do stream em `raw_text` (`turn.py:422`), separa tags e
prosa com `parse_tags` (`turn.py:425`), limpa eco de HUD com `strip_engine_echo`
(`turn.py:426`) e grava **só o limpo**:
`("narrator_turn", {"text": clean_text, "suggestions": suggestions})`
(`turn.py:462`). As tags viram eventos `tag` separados, com `raw` mas sem posição
(`turn.py:465`), e as linhas removidas por `strip_engine_echo` (`cleanup.py`)
somem de vez. Reconstruir o texto original a partir disso é impossível.

Sem o cru, `narrator.jsonl` não existe e a sub-fase 4.4 não tem dado.

## Escopo

Dentro:
- `backend/app/turn.py`: `raw` no payload do evento `narrator_turn`, sob o flag
  `narrator_raw`.
- `backend/app/replay.py`: `TurnSnapshot.narrator_raw: str | None`.
- `backend/app/dataset.py`: `"narrator"` em `TASKS` e a montagem da linha de
  `narrator.jsonl`.
- Cenários novos em `test_turn.py`, `test_replay.py` e `test_dataset_export.py`.

Fora (explícito):
- Reconstruir o cru de turnos **antigos**. Não dá, e não se tenta. Ausência de
  `raw` num evento gravado antes deste ticket nunca é erro: `replay` devolve
  `None` e o exportador pula a linha contando o descarte.
- `meta_narrator_turn` (`turn.py:330`). Turno de comando fica fora da memória
  narrativa e fora do dataset; o payload dele não ganha `raw`.
- Reexibir o cru na UI ou em `GET /api/sessions/{id}`. `_build_turns`
  (`sessions.py:539-547`) continua lendo só `text`; o jogador nunca vê a tag.
  Nenhum arquivo de `frontend/` é tocado.
- Alvo de treino do narrator já formatado com prefixo/chat template: TCK-083.
- `strip_engine_echo`, `parse_tags` e a lógica de sugestões: intactos. O cru é
  gravado **além** do limpo, nunca no lugar dele.

## Comportamento esperado

Do ponto de vista do jogador: nada muda. O texto exibido, as tags, o HUD e as
sugestões são idênticos; o evento gravado só tem uma chave a mais.

Do ponto de vista de quem exporta: `uv run python -m app.dataset export --out DIR`
passa a escrever também `narrator.jsonl`, com uma linha por turno cujo evento
tem `raw` — o prompt-mestre completo daquele turno como `messages`, e o texto cru
do narrador como `engine_label`.

## Detalhes técnicos

### `backend/app/turn.py`

Uma linha, em `turn.py:462`:

```python
narrator_payload = {"text": clean_text, "suggestions": suggestions}
if config.flag("narrator_raw"):
    narrator_payload["raw"] = raw_text
events = [
    ("player_turn", {"text": message, "mode": mode} if mode else {"text": message}),
    ("narrator_turn", narrator_payload),
]
```

`raw_text` é o texto do stream **antes** de `parse_tags` e de
`strip_engine_echo`, que é o alvo de treino desejado: o modelo tem que aprender a
emitir a tag, não a prosa depois de o engine tirá-la.

Custo: dobra o tamanho do texto narrado por turno no banco. Um turno é ~500
tokens (orçamento de contexto do plano), ou ~2 KB; 1.000 turnos são ~2 MB a
mais num SQLite local. É barato, e por isso o flag existe mais como interruptor
de privacidade/espaço do que como proteção contra defeito.

`Config.flag` (`config.py:43-45`) devolve `True` por omissão, então a chave
passa a ser gravada sem ninguém mexer em config nenhuma. Desligar é acrescentar
`flags: {narrator_raw: false}` no `~/.ooc-local/config.yaml`.

### `backend/app/replay.py`

`TurnSnapshot` ganha `narrator_raw: str | None = None`, preenchido com
`event.payload.get("raw")` do `narrator_turn` do grupo. Ausência **não** marca
`exact=False`: não é corrupção, é evento de antes deste ticket, e os outros
campos do snapshot continuam fiéis. Marcar `exact=False` faria o exportador do
TCK-079 pular as linhas de juiz/director/minds de todas as sessões antigas, que
são justamente as que já existem.

### `backend/app/dataset.py`

`TASKS` passa a `("judge", "director", "minds", "narrator")` e o exportador
escreve um quarto arquivo. A linha usa o mesmo envelope do TCK-079, com
`engine_label` **string** (o texto cru) em vez de objeto — é a única tarefa cujo
alvo é texto, e o campo é JSON livre no contrato.

`messages` é o prompt do turno, montado com os campos do snapshot na mesma ordem
de `build_context` (`turn.py:120-145`):

```python
characters = [scenario.characters[cid] for cid in snap.cast_after
              if cid in scenario.characters]
lore_window = events_to_messages(snap.history_before[-(LORE_SCAN_TURNS * 2):], locale)
lore = select_lore(scenario, build_scan_text(lore_window, snap.message))
system = build_master_prompt(scenario, start, snap.hud_start, characters,
                             snap.compact, snap.minds_before, lore=lore)
window = [e for e in snap.history_before
          if snap.compact_seq is None or e.seq > snap.compact_seq]
messages = [ChatMessage(role="system", content=system),
            *events_to_messages(window, locale),
            ChatMessage(role="user",
                        content=format_player_message(snap.message, snap.mode, locale))]
```

Por que cada peça é essa e não outra:
- `snap.hud_start` e `snap.minds_before`: `build_context` recebe `ctx.row.hud` e
  `ctx.minds`, lidos no início do turno (`turn.py:133`).
- `snap.cast_after`: `ctx.characters` já foi atualizado pelo director antes do
  prompt do narrador (`turn.py:379-384`).
- `select_lore` recalculado: a seleção é determinística e pura
  (`lore.py:54`), a partir da janela de `LORE_SCAN_TURNS * 2` eventos e da
  mensagem crua (`turn.py:274-277`). Nada de lore é persistido, então recalcular
  é o único caminho.
- janela desde `compact_seq`: é o que `_maybe_compact` entrega no caminho sem
  compactação e no caminho com compactação bem-sucedida
  (`turn.py:156`, `turn.py:187-188`). `build_context` **não** trunca quando
  recebe `history` (`turn.py:139-140`), então não aplique `WINDOW_TURNS` aqui.

**Desvio conhecido, aceito e documentado:** o caminho de `compact_overflow`
(`turn.py:190-203`) descarta turnos extras da janela quando o prompt não coube, e
esse descarte não é gravado em evento nenhum — só na telemetria. Em turnos assim,
a janela reconstruída tem alguns pares a mais do que a real. É raro, o efeito é
um prompt levemente mais longo no exemplo de treino, e o remédio (persistir a
janela efetiva) custaria mais do que vale. Registrado aqui para não ser
redescoberto como defeito.

Turno com `narrator_raw is None` não vira linha em `narrator.jsonl`; conta em
`skipped_no_raw` no resumo. As linhas das outras três tarefas continuam saindo
normalmente para esse mesmo turno.

## Contrato público

```python
# evento de sessão
("narrator_turn", {"text": str, "suggestions": list[str], "raw": str})
# "raw" ausente em evento gravado antes deste ticket ou com flag narrator_raw: false

# backend/app/replay.py
class TurnSnapshot(BaseModel):
    ...
    narrator_raw: str | None = None

# backend/app/dataset.py
TASKS = ("judge", "director", "minds", "narrator")
# <out>/narrator.jsonl, mesmo envelope do TCK-079, com engine_label: str
```

Consumidor já enfileirado: TCK-083 (`app.training format --target narrator` lê
`narrator.jsonl` e converte para o formato de treino do SFT).

## Acceptance criteria

- [ ] Turno normal grava `narrator_turn.payload["raw"]` com o texto do stream
      **incluindo** as tags e as linhas de eco que o `strip_engine_echo` removeu.
- [ ] `narrator_turn.payload["text"]` continua sendo o texto limpo, idêntico ao
      de hoje, e `suggestions` continua igual.
- [ ] Com `flags: {narrator_raw: false}`, o payload sai sem a chave `raw` e o
      resto do turno é idêntico.
- [ ] Turno meta não ganha `raw` no `meta_narrator_turn`.
- [ ] `replay_session` devolve `narrator_raw` preenchido para turno novo e `None`
      para evento antigo sem a chave, com `exact is True` nos dois casos.
- [ ] `export` grava `narrator.jsonl` com uma linha por turno com `raw`, e
      `engine_label` igual ao cru.
- [ ] A linha de `narrator.jsonl` tem `messages[0].role == "system"` com o
      prompt-mestre, os pares de histórico no meio e a mensagem do jogador
      formatada por `format_player_message` no fim.
- [ ] Turno gravado com `mode: "say"` produz a última mensagem com o texto entre
      aspas e o rótulo de fala (`prompt.py:48-50`).
- [ ] Turno sem `raw` não vira linha em `narrator.jsonl`, conta em
      `skipped_no_raw`, e continua gerando linha em `judge.jsonl`,
      `director.jsonl` e `minds.jsonl`.
- [ ] Sessão com evento `compact`: a janela da linha do narrador só tem os
      eventos com `seq > compact_seq`, e o system prompt contém o texto do
      resumo.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente que muda de preparação: **nenhuma**. Verificado por Grep em
`backend/tests/` por `narrator_turn`:

- Ninguém compara o payload de `narrator_turn` por igualdade de dict. As
  asserções são sempre por chave: `narrator_event.payload["text"] == ...`
  (`test_turn.py:163-166`),
  `narrator_events[0].payload["suggestions"] == [...]`
  (`test_turn_suggestions.py:147`, `:243`). Chave nova não as afeta.
- As comparações por igualdade de dict que existem são de **outros** kinds:
  `tag_events[0].payload == {...}` (`test_turn.py:163`) e
  `cast_events[0].payload == {...}` (`test_turn_director.py:188`). Nenhum dos
  dois muda aqui.
- `test_turn_suggestions.py:262` insere à mão um `narrator_turn` legado
  (`{"text": "turno antigo sem chave"}`) e afere o fallback de `suggestions`.
  Esse teste continua verde e vira, de graça, a prova de que evento sem `raw`
  não quebra nada.
- Os arquivos `test_turn.py`, `test_replay.py` e `test_dataset_export.py` entram
  em `files` só por causa dos cenários **novos**.

Cenários novos:

`backend/tests/test_turn.py` (molde do arquivo: `TestClient`, `_make_fake_stream`,
`monkeypatch.setenv("OOC_SESSIONS_DB", ...)` em `:78`):
- Feliz: narrador emitindo `"# Turno 1\nLocal: patio\nVoce anda. [STAT:reputacao:+1]"`
  → `payload["raw"]` tem a linha de eco e a tag; `payload["text"]` tem só
  `"Voce anda."`.
- Borda: `flags: {narrator_raw: false}` → sem a chave `raw`.
- Borda: turno meta (comando) → `meta_narrator_turn` sem `raw`.

`backend/tests/test_replay.py`:
- Feliz: evento com `raw` → `snap.narrator_raw` preenchido.
- Borda: evento sem `raw` → `None` e `exact is True`.

`backend/tests/test_dataset_export.py`:
- Feliz: sessão de 2 turnos com `raw` → 2 linhas em `narrator.jsonl`,
  `engine_label` igual ao cru, `messages` conferido contra chamada direta de
  `build_master_prompt` + `events_to_messages` + `format_player_message`.
- Feliz: turno com `mode: "say"` → última mensagem formatada.
- Borda: sessão com `compact` → janela cortada em `compact_seq` e resumo no
  system.
- Borda: cenário com lorebook cuja keyword aparece na mensagem → a entrada de
  lore está no system prompt (prova de que `select_lore` foi recalculado).
- Borda: turno sem `raw` → pulado só em `narrator.jsonl`, contado em
  `skipped_no_raw`, presente nos outros três arquivos.

## Rollout e kill switch

Flag de runtime `narrator_raw`, no padrão do projeto (`Config.flag`,
`config.py:43-45`): ausente = ligado. Desligar sem deploy:

```yaml
flags:
  narrator_raw: false
```

Desligado, os turnos novos param de gravar o cru e o exportador simplesmente
produz menos linhas de narrator. Nada mais no turno depende da chave — nem o
replay, nem a UI, nem `GET /api/sessions/{id}`. Ligar de volta não recupera os
turnos que passaram; é uma gravação a partir do momento em que se liga.

`risk: low`: uma chave a mais num payload já existente, sob flag, sem call novo,
sem mudança de ordem e sem alteração de nada que o jogador veja.

## Observabilidade

Eventos: nenhum novo. `game_turn` (`turn.py:241-259`) já tem `chars=len(raw_text)`,
que é o tamanho do cru — não é preciso contador novo para saber quanto está sendo
gravado.

Resumo de stdout do `export` ganha `narrator=<n>` e `skipped_no_raw=<n>`.

Métrica de sucesso: depois de 20 turnos jogados com o flag ligado,
`narrator.jsonl` tem 20 linhas e `skipped_no_raw == 0`; e pelo menos 16 delas
têm `[SUGGEST:` no `engine_label` — se o cru não tiver as tags, foi gravado no
lugar errado do fluxo.

## i18n

N/A. Nenhuma string de usuário. O prompt exportado já nasce no locale do cenário
porque `build_master_prompt` escolhe o template por `scenario.meta.locale`
(`prompt.py:344`).
