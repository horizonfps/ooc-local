---
id: TCK-069
title: Rodar juiz de HUD e minds depois do narrador e emitir as sugestões do turno
status: in_review
points: 5
blockedBy: [TCK-060, TCK-061, TCK-062, TCK-063]
files:
  - backend/app/turn.py
  - backend/app/prompt.py
  - backend/app/sessions.py
  - backend/app/tags.py
  - backend/tests/test_turn_hud_judge.py
  - backend/tests/test_turn_suggestions.py
  - backend/tests/test_turn_director.py
  - backend/tests/test_compact.py
  - backend/tests/test_prompt.py
migration: false
ui: false
risk: high
---

## Problema

Três módulos ficam prontos e desconectados depois da wave 2:

- `backend/app/judge.py` (TCK-062) sabe propor e clampar mudança de stat, e nada
  o chama. Sem ele, o HUD só se move quando o narrador lembra de emitir
  `[STAT:...]`, o que ele esquece o tempo todo.
- `backend/app/minds.py` (TCK-063) sabe ler a mente dos NPCs em cena, e nada o
  chama. `SessionDetail.minds` (congelado no TCK-060) responde `{}` para sempre,
  e o `InfoTracker` do TCK-067 fica com o placeholder permanente.
- As sugestões continuam congeladas no start: `SessionDetail.suggestions` nasce
  `[]` no TCK-060 e o narrador não tem instrução para propor as próximas.

Este ticket é a fiação: os dois calls ao utility depois do narrador e antes da
persistência, as sugestões saindo do texto do turno, e tudo isso no **mesmo**
`append_events` que já grava o turno.

É o ticket de maior risco da fase: o turno passa a ter **dois** calls extras ao
provider local depois de o jogador já ter visto o texto. Por isso nasce com dois
kill switches independentes e com todo o bloco embrulhado em `try/except`.

## Escopo

Dentro:
- `backend/app/turn.py`: `TurnContext.minds` semeado de `read_minds`; call do
  juiz sob o flag `hud_judge` e call do minds sob o flag `minds`, ambos depois
  do stream do narrador e antes do `append_events`; eventos `stat` (source
  `judge`) e `minds` na mesma lista de eventos do turno; `stats` e `minds` no
  payload `hud` do SSE; sugestões coletadas das tags `SUGGEST`, gravadas no
  `narrator_turn` e emitidas como evento SSE próprio; telemetria.
- `backend/app/tags.py`: `SUGGEST` no `_validate`.
- `backend/app/prompt.py`: linha `Estado atual:` na ficha do personagem em cena;
  instrução de sugestão no `format_body`; `MASTER_PROMPT_VERSION` 9 → 10.
- `backend/app/sessions.py`: `read_minds`; `SessionDetail.minds` e
  `SessionDetail.suggestions` preenchidos; `TurnView.suggestions` preenchido em
  `_build_turns`.
- `backend/tests/test_turn_hud_judge.py` e `backend/tests/test_turn_suggestions.py`
  novos, no molde de `backend/tests/test_turn_director.py`.
- Adaptação de preparação em `test_turn_director.py`, `test_compact.py` e do pino
  de versão em `test_prompt.py`.

Fora (explícito):
- `backend/app/judge.py` e `backend/app/minds.py`: vêm prontos dos TCK-062/063 e
  **não são editados aqui**. Se a assinatura deles não bater com a seção
  "Interface consumida" abaixo, o defeito volta para o ticket do módulo; não
  contorne com adaptador local.
- `backend/app/hud.py` e `backend/app/cast.py`: `stat_event` (TCK-061) e
  `minds_event`/`MIND_EVENT_KIND` (TCK-060) já existem e são reusados como
  estão. `apply_stat` **não** é usado no caminho do juiz: quem clampa lá é o
  `apply_judgement` do TCK-062, que devolve o HUD pronto.
- `backend/app/main.py`: a rota (`main.py:157-167`) só serializa o que o gerador
  produz; o evento SSE `suggestions` chega ao cliente sem tocar nela.
- Comandos, modos de input e lorebook: TCK-072 e TCK-075.
- Criar stat dinâmico **fora** do parecer do juiz. `[STAT:...]` continua só
  mexendo em id que já existe (regra do TCK-061).
- Qualquer arquivo de frontend. O `InfoTracker`, as barras e os chips são
  TCK-067/071, contra o contrato congelado no TCK-060.

## Comportamento esperado

Ao fim de cada turno, sem que o jogador espere por isso no texto: o motor pergunta
ao utility se a ação mudou algum atributo e o que cada NPC em cena está achando
agora. O que volta é validado, clampado e escrito junto com o turno. Na tela, as
barras já se movem e o bloco INFO já mostra a atitude nova quando o HUD chega.

O narrador termina cada turno com três sugestões de ação; elas somem do texto
narrado (o parser já as remove) e chegam como lista própria, para virarem chips.

Se o utility falhar, devolver lixo, ou estiver desligado por flag: o turno é
idêntico ao de hoje. Nenhum turno é bloqueado, recusado ou perdido por causa do
juiz, do minds ou de uma sugestão malformada.

## Detalhes técnicos

### Interface consumida (TCK-062 e TCK-063)

Copiada dos contratos publicados por aqueles tickets. Se algo aqui divergir do
que for mergeado, o defeito e deles, nao deste ticket.

```python
# backend/app/judge.py (TCK-062)
JUDGE_MAX_DELTA: int          # 10
MAX_DYNAMIC_STATS: int        # 6
JUDGE_RAW_LOG_CHARS: int      # 200
class JudgeError(Exception): ...

class StatChange(BaseModel):
    id: str
    delta: int                        # mudanca efetiva; value == anterior + delta
    value: int
    source: Literal["tag", "judge"]

class StatRejection(BaseModel):
    id: str                           # "stats" / "new" para recusa de secao inteira
    reason: str

async def judge_turn(scenario, hud, message, narrator_text, touched_ids, config
) -> tuple[dict | None, str | None, str]      # (judgement, reason, raw)

def apply_judgement(scenario, hud, judgement: dict, touched_ids: list[str]
) -> tuple[HudState, list[StatChange], list[StatRejection]]
```

```python
# backend/app/minds.py (TCK-063)
MINDS_RAW_LOG_CHARS: int      # 200
class MindsError(Exception): ...
class MindRejection(BaseModel):
    id: str
    reason: str

async def think_minds(scenario, cast_ids, previous, message, narrator_text, config
) -> tuple[dict | None, str | None, str]      # (proposed, reason, raw)

def merge_minds(previous: dict[str, MindView], proposed: dict, cast_ids: list[str]
) -> tuple[dict[str, MindView], list[MindRejection]]   # mapa COMPLETO, nunca delta
```

A divisao e a mesma do director (`director.py`): a corotina fala com o provider e
faz o parse tolerante; a funcao pura decide. Este ticket chama as duas em
sequencia — `judge_turn` -> `apply_judgement`, `think_minds` -> `merge_minds` —
porque so ele tem o HUD do turno e o elenco em cena. `judge_turn`/`think_minds`
levantam `JudgeError`/`MindsError` quando o papel `utility` falta na config ou o
provider explode, exatamente como `DirectorError` (`director.py:133-144`), e
devolvem o `raw` **inteiro**: quem corta em `*_RAW_LOG_CHARS` na telemetria e o
chamador.

### Onde entram no `run_turn`

Depois do laço de tags do TCK-061 (que produz `new_hud`, `resolved_tags` e
`stat_events`) e **antes** de montar a lista `events` (`turn.py:317`). Nunca
antes do stream: o jogador já viu o texto, e nenhuma latência do utility pode
atrasar o primeiro delta.

```python
touched_ids = [payload["id"] for _kind, payload in stat_events]
```

**Juiz** (`if config.flag("hud_judge")`), num `try/except JudgeError` mais
`except Exception` defensivo, no molde do bloco do director
(`turn.py:228-287`):

```python
judgement, reason, raw = await judge_turn(
    ctx.scenario, new_hud, message, clean_text, touched_ids, config
)
if judgement is not None:
    new_hud, changes, rejections = apply_judgement(
        ctx.scenario, new_hud, judgement, touched_ids
    )
    stat_events += [stat_event(c.id, c.delta, c.value, c.source) for c in changes]
```

`apply_judgement` devolve o **HUD ja atualizado**, inclusive com os stats
dinamicos criados. Este ticket nao reaplica nada com `apply_stat`: haveria dois
lugares clampando o mesmo valor, e o segundo poderia divergir do primeiro. Cada
`StatChange` vira um evento `stat` com o `source` que o proprio modelo carrega
(sempre `"judge"` neste caminho; `apply_judgement` ja descartou o que foi tocado
por tag, via `touched_ids`).

**Minds** (`if config.flag("minds")`), mesmo embrulho:

```python
proposed, reason, raw = await think_minds(
    ctx.scenario, ctx.cast_ids, ctx.minds, message, clean_text, config
)
if proposed is not None:
    entries, rejections = merge_minds(ctx.minds, proposed, ctx.cast_ids)
    if entries != ctx.minds:
        pending_minds_event = minds_event(entries)
        ctx = ctx.model_copy(update={"minds": entries})
```

`merge_minds` devolve o mapa completo (anterior + aceitos), entao a comparacao
com `ctx.minds` e o que decide se ha evento a gravar. `ctx.minds` e atualizado
para que o SSE mande o mapa novo e o proximo turno nao releia o banco a toa.

Os dois blocos rodam mesmo quando o outro falha: são `try` separados, não um
`try` com dois calls dentro.

### `TurnContext.minds`

`TurnContext` (`turn.py:43-48`) ganha `minds: dict[str, MindView] = {}`,
preenchido em `load_turn_context` (`turn.py:51-66`) com
`read_minds(session_id)`. É o mesmo padrão de `cast_ids`/`read_cast_ids`
(`turn.py:60-65`), e evita passar `minds` como parâmetro por `_maybe_compact`
até `build_context` — `build_context` já recebe `ctx` (`turn.py:93`) e lê de lá.

### Sugestões

`tags.py:19-28`, `_validate` ganha:

```python
if kind == "SUGGEST":
    text = ":".join(args).strip()
    return bool(text) and len(text) <= SUGGEST_MAX_CHARS
```

`SUGGEST_MAX_CHARS = 120`, constante de módulo em `tags.py`. O `":".join` é
necessário porque o parser já quebrou os args por `:` (`tags.py:37`) e uma
sugestão pode conter dois-pontos. Esta é a **única** mudança em `tags.py`: a
linha que só contém a tag já sai do texto limpo pelo parser atual
(`tags.py:57-58`), e os 34 testes de `test_tags.py` não mencionam `SUGGEST`.

No `run_turn`, depois de `resolved_tags`:

```python
suggestions = [":".join(t.args).strip() for t in resolved_tags if t.kind == "SUGGEST" and t.valid][:3]
```

- vai em `("narrator_turn", {"text": clean_text, "suggestions": suggestions})`
  — a chave é gravada mesmo vazia, para o leitor distinguir "turno novo sem
  sugestão" de "evento antigo";
- vira `yield {"suggestions": suggestions}` **antes** do `yield {"hud": ...}`,
  e **só quando a lista não é vazia**. Emitir sempre acrescentaria um evento a
  todo turno de toda suíte existente sem que ninguém o consuma; a ausência já
  significa "mantenha os chips atuais" no contrato do TCK-060.

### SSE

O `yield` final (`turn.py:328-329`, já reescrito pelo TCK-061) ganha a chave
`minds`, sempre presente em turno bem-sucedido:

```python
"minds": {char_id: view.model_dump() for char_id, view in ctx.minds.items()},
```

Mandar sempre (mesmo com a flag desligada, aí é o mapa persistido) é a mesma
decisão do `cast` no TCK-055 e do `stats` no TCK-061.

### `backend/app/sessions.py`

```python
def read_minds(session_id: str) -> dict[str, MindView]
```
Último evento `MIND_EVENT_KIND` (`read_events(session_id, kinds=(MIND_EVENT_KIND,))`),
`payload["entries"]` validado item a item com `MindView.model_validate`. Payload
sem a chave, que não é dict, ou com entrada malformada → `{}`. Defesa idêntica à
de `read_cast_ids` (`sessions.py:459-470`): evento corrompido não pode derrubar
`GET /api/sessions/{id}`.

`get_session` (`sessions.py:282-311`) passa a preencher:
- `minds=read_minds(session_id)`;
- `suggestions`: do último evento `narrator_turn`, `payload.get("suggestions")`
  quando é lista de strings não vazia; **sem nenhum** `narrator_turn` na sessão,
  `start.suggestions`; com `narrator_turn` mas sem a chave (evento antigo), `[]`.
  A comparação é por existência de turno narrado, não por lista vazia, senão uma
  sessão de 40 turnos voltaria a sugerir as falas de abertura.

`create_session` (`sessions.py:163-225`) passa `suggestions=start.suggestions`
(sessão nova nunca tem turno) e `minds={}`.

`_build_turns` (`sessions.py:473-481`) preenche
`suggestions=event.payload.get("suggestions", [])` no `TurnView` de
`narrator_turn`. Uma linha, e o campo congelado no TCK-060 deixa de ser morto.

### `backend/app/prompt.py`

`_format_character` (`prompt.py:184-202`) ganha um terceiro parâmetro
`mind: MindView | None = None` e, quando ele existe e `attitude` não é vazio,
acrescenta `f"{template['current_state_label']}: {mind.attitude}"` como **última**
linha da ficha — depois de segredo, porque é a informação mais volátil e a mais
recente. `build_master_prompt` (`prompt.py:261-267`) ganha
`minds: dict[str, MindView] | None = None` no fim da assinatura (compatível com
todos os 21 call sites de `test_prompt.py`, que passam no máximo `compact=`), e
resolve o id de cada personagem com `_character_id` (`prompt.py:228-232`), que já
existe.

`format_body` dos dois locales ganha a instrução de sugestão: terminar o turno
com exatamente três linhas `[SUGGEST:...]`, cada uma uma ação curta em segunda
pessoa, no máximo 120 caracteres, uma por linha, nada depois delas.
`MASTER_PROMPT_VERSION` sobe para **10**.

### Ressalva de porte

A estimativa com os cenários listados é ~480 linhas, acima do alvo de ~400.
Corte nesta ordem, se o diff passar disso:
1. Funda os dois cenários de falha de provider (juiz e minds) num só, com os
   dois flags ligados e o fake explodindo para ambos.
2. Funda os dois cenários de "flag desligado" num teste parametrizado.
Não corte o cenário de narrador que falha depois de um juiz bem-sucedido: é o que
prova que não fica evento `stat` órfão, e é o defeito mais caro desta fatia.

## Contrato público

```python
# backend/app/sessions.py
def read_minds(session_id: str) -> dict[str, MindView]   # {} quando nunca houve ou payload corrompido
```

```python
# backend/app/tags.py
SUGGEST_MAX_CHARS: int   # 120; SUGGEST valido = ":".join(args) nao vazio e <= 120 chars
```

```python
# backend/app/turn.py
# TurnContext ganha minds: dict[str, MindView] = {}
# SSE: {"suggestions": [...]} emitido antes de {"hud": ...}, so quando nao vazio
# SSE: o payload "hud" ganha "minds": {id: {attitude, emoji, event}} (mapa completo)
```

Nenhum ticket consome estas assinaturas: TCK-067 e TCK-071 consomem o contrato
congelado no TCK-060 (`MindView`, `SessionDetail.minds/suggestions`,
`TurnHudPayload.minds`, evento SSE `suggestions`), não o código deste ticket.

## Acceptance criteria

- [ ] Com `hud_judge` ligado e o utility devolvendo `{"stats": {"reputacao": -5}}`,
      o SSE traz `hud.stats` com o valor 5 pontos abaixo, o banco tem um evento
      `stat` com `source: "judge"`, e `judge_applied` é emitido.
- [ ] Id já alterado por tag no mesmo turno não é tocado pelo juiz: um turno com
      `[STAT:reputacao:+3]` e um parecer `{"reputacao": -5}` termina em `+3`, com
      um único evento `stat` (`source: "tag"`), e `judge_applied` traz
      `rejected` com `{"id": "reputacao", "reason": "touched_by_tag"}`.
- [ ] Com `allow_dynamic_stats: true`, um parecer com
      `new: [{"id":"vida","name":"Vida","value":110,"max":110}]` cria o stat, o
      SSE devolve `hud.stats` com ele no fim da lista, e o evento `stat` sai com
      `source: "judge"` e o `value` inicial clampado.
- [ ] Com `minds` ligado e o utility devolvendo
      `{"chloe": {"attitude": "desconfiada", "emoji": "🤨", "event": "te viu"}}`,
      o SSE traz `hud.minds` com a entrada, o banco tem um evento `minds` com o
      mapa completo, e `GET /api/sessions/{id}` devolve o mesmo em `minds`.
- [ ] Parecer de minds idêntico ao mapa anterior não grava evento `minds` novo.
- [ ] O turno seguinte traz `Estado atual: desconfiada` na ficha da Chloe no
      system prompt; personagem sem mente registrada não ganha a linha.
- [ ] Narrador terminando com três `[SUGGEST:...]` produz o evento SSE
      `{"suggestions": [...]}` antes do `hud`, com as três na ordem, e o texto
      narrado sai sem as linhas de tag.
- [ ] Quatro `[SUGGEST:...]` produzem três; uma vazia e uma com 121 chars são
      descartadas e o evento `tag` correspondente sai `valid: false`.
- [ ] `GET /api/sessions/{id}` de sessão sem turno devolve `start.suggestions`;
      depois de um turno com sugestões, devolve as do último `narrator_turn`;
      depois de um turno sem sugestões, devolve `[]`.
- [ ] Falha do provider do utility (exceção, papel `utility` ausente, JSON
      inválido) em qualquer um dos dois: turno chega ao fim normalmente, com
      `judge_failed`/`minds_failed` ou `judge_rejected`/`minds_rejected`
      emitidos, e o outro subsistema roda igual.
- [ ] Turno cujo narrador falha depois de um juiz bem-sucedido não grava evento
      nenhum (`read_events(...) == []`) — nem `stat`, nem `minds`.
- [ ] Com `flags: {hud_judge: false, minds: false}`, nenhum call ao utility
      acontece por conta deste ticket, `hud.minds` traz o mapa persistido e
      `hud.stats` continua vindo do TCK-061.
- [ ] `MASTER_PROMPT_VERSION == 10`.
- [ ] `npm run check` verde, com as asserções de `test_turn.py`,
      `test_turn_director.py` e `test_compact.py` inalteradas.

## Cenários de teste

Suíte existente que muda **de preparação** (asserções preservadas):

- `backend/tests/test_turn_director.py` — **quebra sem adaptação**. O `_config`
  de lá (`:93-103`) declara o papel `utility` com o modelo `utility-model`, e
  todos os fakes roteiam qualquer chamada a esse modelo para
  `'{"scene": [...]}'`. Com `hud_judge` e `minds` ligados por padrão, o juiz e o
  minds passariam a fazer duas chamadas extras por turno ao mesmo fake, e
  `test_director_flag_disabled_never_calls_utility:300` — que afirma
  `utility_calls == []` (`:320`) com `director: False` — falharia.
  **Estratégia escolhida (uma só):** o helper `_config` desliga os dois por
  padrão, mantendo o override, exatamente como o TCK-055 fez com o director:
  ```python
  "flags": {"hud_judge": False, "minds": False, **(flags or {})},
  ```
  Uma linha, num helper de preparação. Os 10 testes do arquivo mantêm corpo e
  asserções; `test_director_flag_disabled_never_calls_utility` continua passando
  `flags={"director": False}` e o override se aplica por cima. É a escolha certa
  porque esses testes aferem o **director**: contar chamadas ao utility ali
  significa contar chamadas do director, e o juiz seria ruído de outro
  subsistema.
- `backend/tests/test_compact.py` — mesma quebra e mesmo remédio. O `_config`
  de lá (`:61-71`) já desliga o director; passa a desligar os três:
  ```python
  "flags": {"director": False, "hud_judge": False, "minds": False, **(flags or {})},
  ```
  Pontos que seriam atingidos: `assert utility_calls == []` (`:619`, `:781`),
  `len(utility_calls) == 1` (`:942`, `:977`, `:985`), `len(utility_calls) == 2`
  (`:992`), e `_split_stream({"narrator-model": [...]})` (`:517`), cujo
  dicionário não tem a chave `utility-model` e levantaria `KeyError` dentro do
  fake. Nenhum corpo de teste muda.
- `backend/tests/test_prompt.py` — o pino de versão (renomeado para
  `test_master_prompt_version_is_nine` pelo TCK-061) passa a `10` e é renomeado
  para `test_master_prompt_version_is_ten`. **Única edição
  de asserção autorizada**, pelo mesmo motivo do TCK-061: o teste afere que
  alguém lembrou de subir o número, não comportamento. Os testes de ficha de
  personagem (`:186-195`) não passam `minds`, então a linha `Estado atual` não
  aparece e as asserções seguem verdes.
- `backend/tests/test_turn.py` — verificado, **não** entra em `files`. O
  `_config()` de lá (`:56-62`) **não** tem papel `utility`, então juiz e minds
  caem em `JudgeError`/`MindsError("no utility role")` sem tocar a rede, emitem
  `*_failed` e o turno segue. `test_turn_route_missing_narrator_role_emits_turn_failed_and_done:419`
  monta um `Config` inline só com `utility` e sem `stream_chat` fake, mas
  `config.models["narrator"]` levanta `KeyError` em `turn.py:224`, **antes** de
  qualquer call do juiz — nenhuma chamada de rede real acontece. Nenhum teste do
  arquivo emite `[SUGGEST:...]`, e o evento SSE novo não é emitido com lista
  vazia, então a sequência de eventos de `test_turn_happy_path...:103` não muda.
- `backend/tests/test_sessions.py` — verificado, **não** entra em `files`:
  `test_create_session_happy_path:149` e `test_post_sessions_route_happy_path:409`
  aferem campo a campo, e nenhum cenário de lá tem `suggestions` no start.

Cenários novos (`backend/tests/test_turn_hud_judge.py`, no padrão de
`test_turn_director.py`: `TestClient`, cenário em `tmp_path` com `stats.yaml`,
config com `narrator` e `utility` em modelos distintos, `stream_chat`
monkeypatchado roteando por `model`):
- Feliz: parecer `{"stats": {"reputacao": -5}}` → HUD, evento `stat` com
  `source: "judge"`, `judge_applied` com `changes` e `duration_ms`.
- Feliz: parecer de minds com uma entrada → `hud.minds` no SSE, evento `minds`
  com o mapa completo, `GET /api/sessions/{id}` com `minds` preenchido,
  `minds_applied`.
- Feliz: o turno seguinte traz `Estado atual: ...` na ficha da Chloe.
- Feliz: `allow_dynamic_stats: true` e `new: [...]` cria o stat dinâmico, que sai
  depois dos declarados em `hud.stats`.
- Borda: tag tem precedência — `[STAT:reputacao:+3]` mais parecer `{-5}` termina
  em `+3`, com um evento `stat` só, e `judge_rejected` com o motivo.
- Borda: parecer de minds igual ao anterior → nenhum evento `minds` novo.
- Borda: `hud_judge: false` e `minds: false` → o fake do utility nunca é chamado,
  e o turno grava e streama normalmente.
- Borda: `allow_dynamic_stats` ausente (default `False`) e parecer com `new` →
  nenhum stat criado, e `judge_applied` com `rejected` contendo
  `{"id": "new", "reason": "dynamic_disabled"}`.
- Falha: provider do utility levanta `RuntimeError` → `judge_failed` e
  `minds_failed`, turno com HUD e persistência normais.
- Falha: utility devolve prosa sem JSON → `judge_rejected` com
  `reason == "invalid_json"` e o `raw` cortado em `JUDGE_RAW_LOG_CHARS` pelo
  próprio `turn.py`.
- Falha: narrador explode depois de um juiz bem-sucedido → `read_events(...) == []`,
  nenhum evento `stat` nem `minds` órfão.
- Borda: evento `minds` gravado com payload `{"entries": "lixo"}` →
  `read_minds` devolve `{}` e `GET /api/sessions/{id}` responde 200.

Cenários novos (`backend/tests/test_turn_suggestions.py`):
- Feliz: três `[SUGGEST:...]` → evento SSE `{"suggestions": [...]}` antes do
  `hud`, na ordem, texto narrado limpo, `narrator_turn.payload["suggestions"]`
  com as três, e `GET /api/sessions/{id}` devolvendo as mesmas.
- Feliz: sessão sem turno devolve `start.suggestions`.
- Borda: quatro sugestões → só as três primeiras.
- Borda: sugestão vazia (`[SUGGEST:]`) e de 121 chars → descartadas, evento `tag`
  com `valid: false`, e o evento SSE traz só as válidas.
- Borda: sugestão com dois-pontos no meio chega inteira
  (`[SUGGEST:Perguntar: onde está o caderno?]`).
- Borda: turno sem nenhuma `SUGGEST` → nenhum evento SSE `suggestions`,
  `narrator_turn.payload["suggestions"] == []`, e
  `GET /api/sessions/{id}` devolve `[]` (não volta para as do start).
- Borda: `TurnView.suggestions` do turno narrado vem preenchido em
  `SessionDetail.turns`; turno gravado antes deste ticket (sem a chave) vem `[]`.
- Borda: o `format_body` menciona `[SUGGEST:` nos dois locales.

## Rollout e kill switch

Dois flags de runtime independentes, no padrão do projeto (`Config.flag`,
`backend/app/config.py:43`): ausente = ligado. Desligar sem deploy e sem
reiniciar é acrescentar em `~/.ooc-local/config.yaml`:

```yaml
flags:
  hud_judge: false
  minds: false
```

São **dois** flags e não um porque as falhas são independentes: um juiz que
alucina delta é um problema de balanceamento, e um minds que devolve lixo é um
problema de prompt; desligar os dois juntos para investigar um só custaria uma
feature à toa.

Desligado o `hud_judge`: nenhum call ao utility pelo juiz, o HUD só se move por
tag (comportamento do TCK-061), e `hud.stats` continua no SSE. Desligado o
`minds`: nenhum call, `hud.minds` e `SessionDetail.minds` devolvem o último mapa
persistido, e a ficha do prompt volta a não ter `Estado atual`. Eventos `stat` e
`minds` já gravados continuam valendo como estado — desligar congela, não
rebobina.

As sugestões **não** têm flag: são só uma tag a mais no texto e uma lista a mais
no payload, sem call extra, sem latência e sem caminho de falha próprio. Um
narrador que pare de emitir `SUGGEST` produz lista vazia, que é um estado
previsto.

`risk: high` porque o turno passa a ter dois calls extras ao provider entre o fim
do stream e a persistência. Mitigações: os dois flags, os `timeout_s=45.0` de
`JUDGE_OPTIONS`/`MINDS_OPTIONS`, os `try/except` separados que devolvem o turno
ao caminho antigo em toda falha, e o fato de os dois rodarem **depois** do último
delta — o jogador já leu o turno antes de qualquer um deles começar.

## Observabilidade

Eventos (via `emit` de `backend/app/observability.py`, no molde do director):
- `judge_applied`: `session_id`, `turn`, `changes` (lista de
  `{id, delta, value}` a partir de `StatChange`), `rejected` (lista de
  `{id, reason}` a partir de `StatRejection`), `duration_ms`, `model`. Emitido
  mesmo com `changes` vazio: parecer que não mudou nada é informação.
- `judge_rejected`: `session_id`, `turn`, `reason` (`invalid_json`, único motivo
  de recusa total devolvido por `judge_turn`), `raw` (cortado em
  `JUDGE_RAW_LOG_CHARS` **aqui**, porque o módulo devolve inteiro),
  `duration_ms`.
- `judge_failed`: `session_id`, `turn`, `error`, `duration_ms`.
- `minds_applied`: `session_id`, `turn`, `ids` (chaves do mapa novo), `changed`
  (ids cujo valor mudou), `rejected` (lista de `{id, reason}` a partir de
  `MindRejection`), `duration_ms`, `model`.
- `minds_rejected`: `session_id`, `turn`, `reason` (`invalid_json`), `raw`
  (cortado em `MINDS_RAW_LOG_CHARS` aqui), `duration_ms`.
- `minds_failed`: `session_id`, `turn`, `error`, `duration_ms`.
- `game_turn` (`turn.py:200-215`) ganha `suggestions`, com o número de sugestões
  válidas do turno, e `None` quando o turno falhou antes de ter contexto — mesma
  defesa de `cast` (`turn.py:214`).
- A propriedade `stats` de `game_turn` (TCK-061) passa a contar também os eventos
  `stat` do juiz; nenhum contador novo para isso.

Métrica de sucesso: em 20 turnos jogados no `exemplo-escola`, a razão
`judge_applied / (applied + rejected + failed)` e a de `minds_applied` ficam
acima de 0,8, pelo menos um `judge_applied` traz um `changes` não vazio, e
`game_turn.suggestions == 3` em pelo menos 18 dos 20 — os três subsistemas
entregam de verdade sem nenhum turno falhar por causa deles.

## i18n

Chaves novas de template no `backend/app/prompt.py`, nos dois locales já
existentes:

| chave | pt-br | en |
| --- | --- | --- |
| `current_state_label` | `Estado atual` | `Current state` |

Mais a instrução de sugestão acrescentada ao `format_body` de `pt-br`
(`prompt.py:95-113`) e de `en` (`prompt.py:161-179`). Nenhuma string de UI: os
chips são do TCK-071. `attitude`, `emoji` e `event` vêm do utility, já no locale
do cenário, e nunca passam por `t()`.
