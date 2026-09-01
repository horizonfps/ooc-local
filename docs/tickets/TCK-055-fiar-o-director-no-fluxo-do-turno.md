---
id: TCK-055
title: Rodar o director antes do narrador e persistir o elenco do turno
status: done
points: 5
blockedBy: [TCK-050, TCK-053]
files:
  - backend/app/turn.py
  - backend/tests/test_turn_director.py
  - backend/tests/test_turn.py
  - backend/tests/test_compact.py
migration: false
ui: false
risk: high
---

## Problema

O estado de elenco existe (TCK-050) e o módulo que propõe elenco existe
(TCK-053), mas o turno continua com `_characters_in_scene` (`backend/app/turn.py:47`),
que devolve `start.characters` ou o cenário inteiro do primeiro ao último turno.
Ficha completa de todo mundo no prompt, ninguém entra em cena depois do começo, e
o `cast` que o TCK-054 desenha nunca muda.

Este ticket é a fiação: o call do director antes do narrador, a decisão do
engine, a persistência e a telemetria.

## Escopo

Dentro:
- `backend/app/turn.py`: `TurnContext` semeado do elenco persistido; call do
  director sob o flag `director` antes do narrador; validação com
  `validate_cast_ids`; evento `cast` gravado no **mesmo** `append_events` do
  turno; `cast` no payload `hud` do SSE; telemetria `director_applied` /
  `director_rejected` / `director_failed`.
- `backend/tests/test_turn_director.py`: testes de integração pela rota
  (`TestClient`), no estilo de `backend/tests/test_turn.py`.
- Adaptação de preparação em `backend/tests/test_compact.py` e, se necessário, em
  `backend/tests/test_turn.py`.

Fora (explícito):
- `backend/app/director.py` e `backend/app/cast.py`: vêm prontos e não são
  editados aqui.
- `backend/app/prompt.py`: o roster é do TCK-051. Aqui muda **qual** lista de
  personagens chega em `build_master_prompt`, não a função.
- Qualquer arquivo de frontend. O `cast` no payload `hud` é consumido pelo
  TCK-054 contra o contrato congelado no TCK-050.
- Mexer em `compact`: o director roda antes e não entra na janela nem no resumo.
- Deixar o narrador puxar personagem para a cena por tag.

## Comportamento esperado

A cada turno, antes do narrador escrever, o motor pergunta ao utility quem está
em cena. Valendo a proposta, esse é o elenco do turno: as fichas completas no
prompt são só dessas pessoas e o SSE devolve o elenco novo junto do HUD.

Proposta inválida ou falha do provider: o elenco anterior continua valendo, o
narrador roda normalmente, o jogador não vê nada de diferente. Nenhum turno é
bloqueado, recusado ou perdido por causa do director.

Com o flag `director` desligado: comportamento de hoje, nenhum call extra,
nenhuma latência extra.

## Detalhes técnicos

### `load_turn_context`

`ids = read_cast_ids(session_id)`; se `None`, `seed_cast_ids(scenario, start)`.
`characters = [scenario.characters[i] for i in ids if i in scenario.characters]`.
`_characters_in_scene` sai; a semente passa a morar em `cast.py`. `TurnContext`
ganha `cast_ids: list[str]`, para não ter de reverter nome → id depois.

### Onde o director entra

Em `run_turn`, depois de resolver `config`/`ctx` e **antes** de `_maybe_compact`
(`turn.py:222`), que é quem monta o system prompt via `build_context`. Só se
`config.flag("director")`.

Janela:
`events_to_messages(history_events(session_id, None)[-(DIRECTOR_WINDOW_TURNS * 2):])`.

```python
ids, reason, raw = await decide_scene(ctx.scenario, ctx.row.hud, ctx.cast_ids, message, window, config)
```

`ids is not None` e diferente de `ctx.cast_ids` →
`ctx = ctx.model_copy(update={"cast_ids": ids, "characters": [...]})` e o evento
fica pendente. `TurnContext` é `BaseModel`, então `model_copy` é o idiomático.

### Persistência

**Não** grave o elenco na hora. Guarde `cast_event(new_ids, "director")` numa
variável e acrescente-o à lista `events` do `append_events` que já existe
(`turn.py:250-256`), só quando o elenco mudou. Turno que falha não grava turno
nenhum hoje e não pode passar a gravar elenco órfão: os testes
`test_turn_provider_error_mid_stream_does_not_persist:290` e
`test_turn_that_is_only_a_tag_is_treated_as_failure:246` afirmam
`read_events(...) == []` depois da falha.

### SSE

O `yield {"hud": ...}` (`turn.py:259`) passa a mandar
`{**new_hud.model_dump(), "cast": [m.model_dump() for m in resolve_cast(ctx.scenario, ctx.cast_ids)]}`.
O `cast` vai em **todo** turno bem-sucedido, inclusive com o flag desligado (aí é
o elenco estático): o contrato do TCK-050 diz que ausência significa
"inalterado", e mandar sempre poupa a UI de adivinhar. A rota
(`backend/app/main.py:141-142`) não muda — ela só serializa o que o gerador
produz.

### Falha nunca bloqueia

Todo o bloco do director vive num `try/except DirectorError` (mais
`except Exception` defensivo, porque provider local devolve coisa criativa) que
só emite telemetria e segue com `ctx` intacto.

### `emit_game_turn`

A closure de `turn.py:197` roda também no `except` do topo, quando `ctx` pode ser
`None` (falha em `load_config`/`load_turn_context`). A propriedade nova é
`cast=len(ctx.cast_ids) if ctx is not None else None` — `len(ctx.cast_ids)` cru
transformaria uma falha de carregamento em `AttributeError` dentro do próprio
tratamento de erro.

### Preview do builder

Nada de especial: `BuilderPreview` cria sessão efêmera e usa a mesma rota
`POST /api/sessions/{id}/turn`, então o director roda igual. O evento `cast` mora
na mesma tabela `events` e some com a sessão em `delete_session` /
`purge_ephemeral_sessions`. Coberto por teste.

## Contrato público

```python
# backend/app/turn.py
# TurnContext ganha cast_ids: list[str]; _characters_in_scene deixa de existir.
# Payload SSE do evento hud ganha "cast": [{"id","name"}] (contrato do TCK-050).
```

Nenhum ticket consome esta seção: o TCK-054 consome o contrato congelado no
TCK-050, não estas assinaturas.

## Acceptance criteria

- [ ] Com o flag ligado e o utility devolvendo `{"scene": ["chloe"]}`, o system
      prompt do turno tem ficha completa só da Chloe e o SSE devolve
      `hud.cast == [{"id": "chloe", "name": "Chloe"}]`.
- [ ] O elenco decidido sobrevive ao turno seguinte (evento `cast` persistido e
      `GET /api/sessions/{id}` mostrando o mesmo).
- [ ] Elenco inalterado não grava evento `cast` novo.
- [ ] Proposta rejeitada (`invalid_json`, `unknown_ids`, `over_cap`,
      `not_a_list`): elenco anterior mantido, turno narrado normalmente,
      `director_rejected` emitido com o `reason` devolvido pelo TCK-053/TCK-050.
- [ ] Provider do utility levantando exceção ou papel `utility` ausente na
      config: turno normal, `director_failed` emitido, nenhum turno perdido.
- [ ] Turno que falha depois de um director bem-sucedido não grava evento `cast`.
- [ ] Com `flags: {director: false}`, nenhum call ao utility acontece e o elenco
      é o persistido (ou a semente do start).
- [ ] `{"scene": []}` é aceito: prompt com `Nenhum NPC em cena no momento.` e
      `hud.cast == []`.
- [ ] Falha antes de `ctx` existir ainda emite `game_turn`, com `cast=None` e sem
      exceção secundária.
- [ ] `npm run check:api` verde, com as asserções de `test_turn.py` e
      `test_compact.py` inalteradas.

## Cenários de teste

Suíte existente que muda de preparação (asserções preservadas):

- `backend/tests/test_compact.py` — **é o arquivo que quebra sem adaptação**: o
  `_config(flags=None)` de lá (`test_compact.py:61-70`) declara o papel `utility`
  com o modelo `utility-model` e o flag `director` nasce ligado, então o call do
  director entra como chamada extra ao mesmo fake de provider. Pontos atingidos:
  `assert utility_calls == []` (`:619`, `:781`), `len(utility_calls) == 1`
  (`:942`, `:977`, `:985`), `len(utility_calls) == 2` (`:992`), e
  `_split_stream({"narrator-model": [...]})` (`:517`), cujo dicionário não tem a
  chave `utility-model` e levantaria `KeyError` dentro do fake.
  **Estratégia escolhida (uma só):** o helper `_config` do arquivo passa a
  desligar o director por padrão, mantendo o override:
  ```python
  "flags": {"director": False, **(flags or {})},
  ```
  Uma linha, em um helper de preparação. Todo teste do arquivo continua com o
  mesmo corpo e as mesmas asserções, e `test_compact_disabled_by_flag` (`:752`),
  que passa `flags={"compact": False}`, segue funcionando porque o override é
  aplicado por cima. É a opção correta porque esses testes aferem compactação:
  contar chamadas ao utility ali significa contar chamadas de compactação, e o
  director seria ruído de outro subsistema. `captured_timeouts` (`:317-318`) é
  teste puro de provider, não passa por `run_turn`, e continua intocado — está
  listado aqui só para constar que foi verificado.
- `backend/tests/test_turn.py` — o `_config()` de lá (`:56`) **não** tem papel
  `utility`, então os testes que usam `_config()` caem no caminho
  `DirectorError("no utility role")`, narram igual e não chamam provider nenhum a
  mais; as asserções sobre `events[-1]["hud"]["turn"]`/`["location"]` seguem
  válidas porque o payload só ganha uma chave. Se algum teste precisar de elenco
  previsível, acrescente `flags={"director": False}` **na config daquele teste**
  — preparação, não asserção. Não reescreva o `_config()` global do arquivo.
  **Exceção obrigatória**: `test_turn_route_missing_narrator_role_emits_turn_failed_and_done`
  (`test_turn.py:421-424`) não usa `_config()` — monta um `Config` inline com só
  o papel `utility`, sem `stream_chat` monkeypatchado. Com o director ligado por
  padrão, esse teste passaria a fazer uma chamada de rede real a `http://x/v1`
  antes de falhar. Acrescente `"flags": {"director": False}` a esse `Config`
  inline — preparação de uma linha, as asserções não mudam.

Cenários novos (`backend/tests/test_turn_director.py`, no padrão de
`backend/tests/test_turn.py`: `TestClient`, cenário em `tmp_path`, config com os
papéis `narrator` e `utility` em modelos distintos, `stream_chat` monkeypatchado
roteando por `model` — o mesmo truque de `test_compact.py:550`):
- Feliz: cenário com 4 personagens, start com 2 em cena; utility devolve
  `{"scene": ["chloe", "renan"]}` → o prompt do narrador contém a ficha do Renan,
  `hud.cast` traz os dois, e `read_events` tem exatamente um evento `cast` com
  `{"ids": ["chloe", "renan"], "source": "director"}`.
- Feliz: dois turnos com a mesma proposta → um único evento `cast` no total.
- Feliz: o elenco decidido no turno 1 é o elenco de partida do turno 2 (o prompt
  do segundo turno já nasce com ele).
- Borda: `{"scene": []}` → `hud.cast == []` e o prompt tem
  `Nenhum NPC em cena no momento.`
- Borda: proposta rejeitada (um caso de `unknown_ids`) → elenco anterior mantido,
  nenhum evento `cast`, `director_rejected` com o `reason` e o `raw` cortado.
- Borda: flag `director: false` → o fake do utility nunca é chamado (contagem em
  zero) e o elenco é o do start.
- Falha: provider do utility levanta `RuntimeError` → `director_failed`, turno
  chega ao fim com HUD e persistência normais.
- Falha: narrador explode depois de um director bem-sucedido → `read_events`
  vazio, nenhum evento `cast` órfão.
- Falha: `load_turn_context` explodindo antes do director ainda emite `game_turn`
  com `cast=None`.
- Borda: sessão efêmera joga um turno com director e `DELETE /api/sessions/{id}`
  remove sessão e evento `cast` junto.

Ressalva de porte (gate: teto de 2 rodadas do spec-critic atingido): a estimativa
com os 10 cenários fica em ~430-470 linhas, acima do alvo de ~400. Se o diff
passar disso na implementação, funda os dois últimos cenários de falha num só
(narrador explodindo pós-director já cobre a ausência de evento órfão) em vez de
abrir PR gigante ou ticket novo.

## Rollout e kill switch

Flag de runtime **`director`**, no padrão do projeto (`Config.flag`,
`backend/app/config.py:43`): ausente = ligado. Desligar sem deploy e sem
reiniciar é acrescentar em `~/.ooc-local/config.yaml`:

```yaml
flags:
  director: false
```

Desligado: nenhum call ao utility, elenco em cena volta a ser o persistido (ou a
semente do start), e o payload `hud` segue mandando `cast` com esse elenco
estático. Eventos `cast` já gravados continuam valendo como estado — desligar o
flag congela o elenco, não o rebobina. `risk: high` porque o fluxo do turno passa
a ter um call extra antes do narrador; mitigações: o flag, o `timeout_s=45.0` do
`DIRECTOR_OPTIONS` e o `try/except` que devolve o turno ao caminho antigo em toda
falha.

## Observabilidade

Eventos (via `emit` de `backend/app/observability.py`):
- `director_applied`: `session_id`, `turn`, `before` (ids), `after` (ids),
  `added`, `removed`, `duration_ms`, `model`.
- `director_rejected`: `session_id`, `turn`, `reason` (`invalid_json` |
  `not_a_list` | `unknown_ids` | `over_cap`), `raw` (resposta cortada em
  `DIRECTOR_RAW_LOG_CHARS`), `kept` (ids mantidos), `duration_ms`.
- `director_failed`: `session_id`, `turn`, `error`, `duration_ms`.
- `game_turn` ganha a propriedade `cast` com o tamanho do elenco em cena, ou
  `None` quando o turno falhou antes de ter contexto.

Métrica de sucesso: em 20 turnos jogados no exemplo, a razão
`director_applied / (applied + rejected + failed)` fica acima de 0,8 e pelo menos
um `director_applied` traz um `added` — o elenco muda de verdade sem o turno
nunca falhar por causa do director.

## i18n

N/A — todo texto de prompt do director mora em `backend/app/director.py`
(TCK-053), nos dois locales. Este ticket não cria string de usuário nem de
prompt.
