---
id: TCK-060
title: Congelar o contrato da Fase 3 — stats, lorebook, comandos e campos novos da sessão
status: ready
points: 5
blockedBy: []
files:
  - backend/app/scenario.py
  - backend/app/hud.py
  - backend/app/cast.py
  - backend/app/sessions.py
  - backend/app/builder_doc.py
  - backend/app/main.py
  - backend/tests/test_scenario_stats.py
  - backend/tests/test_scenario_lore_commands.py
  - backend/tests/test_stat_views.py
  - backend/tests/test_builder_doc.py
  - backend/tests/test_builder_doc_write.py
  - frontend/src/api.ts
  - frontend/src/screens/BuilderEditorScreen.tsx
  - frontend/src/builder/validate.test.ts
  - frontend/src/components/builder/BuilderPreview.test.tsx
  - frontend/src/components/builder/CharactersTab.test.tsx
  - frontend/src/components/builder/IdentityTab.test.tsx
  - frontend/src/components/builder/MediaTab.test.tsx
  - frontend/src/components/builder/StartsTab.test.tsx
  - frontend/src/components/builder/WorldTab.test.tsx
  - frontend/src/components/GamePanel.test.tsx
  - frontend/src/screens/GameScreen.test.tsx
migration: false
ui: false
risk: low
---

## Problema

A Fase 3 abre seis frentes que compartilham um único modelo de dados: stats com
level, lorebook por keyword, comandos de cenário, mente de NPC, sugestões e modos
de input. Hoje nada disso existe: `LoadedScenario` (`backend/app/scenario.py:127`)
tem só `meta`, `world`, `starts` e `characters`; `HudState`
(`backend/app/hud.py:34`) tem só `turn`, `location`, `time`, `weather`;
`SessionDetail` (`backend/app/sessions.py:83`) tem só `hud`, `assets` e `cast`;
`ScenarioDocument` (`backend/app/builder_doc.py:23`) serializa só `meta`, `world`,
`starts` e `characters`.

Sem congelar antes, cada um dos onze tickets seguintes inventa um formato próprio
de `stats.yaml`, de `StatView`, de `MindView` e de `CommandView` — e os quatro
tickets de UI, que rodam em wave paralela à do engine, teriam de adivinhar o que
o backend vai mandar.

Este é o **interface freeze** da fase. Consumidores já enfileirados no grafo:
TCK-061, TCK-062, TCK-063, TCK-064, TCK-065, TCK-066, TCK-067, TCK-069, TCK-070,
TCK-071, TCK-072, TCK-073, TCK-074, TCK-075.

Sozinho, este ticket já muda comportamento visível: um cenário com `stats.yaml`
passa a carregar sem erro, `GET /api/sessions/{id}` passa a devolver os stats com
os valores default, e o builder deixa de apagar `stats.yaml`/`lorebook/` ao
salvar (hoje `draftOf`, `BuilderEditorScreen.tsx:42-44`, copia só
meta/world/starts/characters; um save com os arquivos novos no disco os
destruiria).

## Escopo

Dentro:
- `backend/app/scenario.py`: modelos `StatLevel`, `StatDef`, `LoreEntry`,
  `CommandDef`, `CommandView`; `ScenarioMeta.allow_dynamic_stats`;
  `LoadedScenario.stats/lorebook/commands`; loaders dos três com validação
  cruzada em `load_scenario`.
- `backend/app/hud.py`: `DynamicStat`, `HudState.stats/dynamic_stats`,
  `StatView`, `stat_views()`.
- `backend/app/cast.py`: `MindView`, `MIND_EVENT_KIND`, `minds_event()`.
- `backend/app/sessions.py`: campos novos com default em `SessionDetail` e
  `TurnView`; `create_session` grava `hud.stats` com os defaults do cenário;
  `SessionDetail.stats` preenchido por `stat_views`.
- `backend/app/main.py`: `ChatRequest.mode`.
- `backend/app/builder_doc.py`: `ScenarioDocument.stats/lorebook/commands`;
  leitura, serialização, poda e `compute_revision` sobre os três arquivos novos.
- `frontend/src/api.ts`: tipos novos e campos novos nos tipos existentes.
- `frontend/src/screens/BuilderEditorScreen.tsx`: passthrough dos três campos em
  `draftOf` (o `documentOf`, `:211-219`, já espalha `...state.draft` e não muda).
- Adaptação de preparação nas nove fábricas de teste do frontend que constroem
  `BuilderDraft` ou `SessionDetail` tipados.

Fora (explícito):
- Qualquer uso dos campos novos no turno: aplicar tag STAT (TCK-061), chamar o
  juiz (TCK-062/069), injetar lore (TCK-064/075), resolver comando
  (TCK-065/072). Este ticket só declara e persiste o que já sabe declarar.
- `backend/app/prompt.py`. Nenhuma seção nova de prompt nasce aqui e
  `MASTER_PROMPT_VERSION` **não** sobe.
- `backend/app/turn.py`. O turno segue idêntico.
- `STAT_EVENT_KIND` / `stat_event()`: nascem em `backend/app/hud.py` no TCK-061,
  que é quem escreve o primeiro evento `stat`. `MIND_EVENT_KIND`/`minds_event()`
  vêm aqui porque `MindView` já entra no `SessionDetail` e deixar o kind solto
  faria TCK-063 e TCK-069 inventarem dois nomes.
- Abas novas do builder (TCK-066/070/073) e regras em
  `frontend/src/builder/validate.ts`. Aqui só o tipo trafega.
- `backend/app/builder.py`: `_write_skeleton` (`builder.py:137-171`) não ganha
  arquivo nenhum — cenário novo sem `stats.yaml` é cenário sem stats, e a
  semântica "ausente = vazio" cobre isso. `shutil.copytree` do duplicate
  (`builder.py:231`) já leva os arquivos novos junto.

## Comportamento esperado

Do ponto de vista do autor de cenário: pôr `stats.yaml`, `lorebook/*.yaml` e
`commands.yaml` na pasta do cenário passa a ser válido, e os arquivos sobrevivem
a um round-trip do builder (`GET` + `PUT` sem alteração não muda a revision).
Cenário sem esses arquivos continua carregando exatamente como hoje.

Do ponto de vista do chamador da API: `POST /api/sessions` e
`GET /api/sessions/{id}` devolvem `stats` com um item por stat declarado, na
ordem de `stats.yaml`, com o valor default; e devolvem `minds: {}`,
`commands: []`, `suggestions: []`. `POST /api/sessions/{id}/turn` aceita
`mode` no corpo e o ignora.

Do ponto de vista dos tickets que dependem deste: existe um lugar único onde o
tipo de cada coisa mora, e nenhum deles precisa decidir formato.

## Detalhes técnicos

### Onde cada tipo mora, e por quê

`backend/app/hud.py` **não pode importar `app.scenario` em runtime**:
`scenario.py:10` importa `validate_time`/`validate_weather` de `hud.py`. O
arquivo já resolve isso com `if TYPE_CHECKING: from app.scenario import
StartConfig` (`hud.py:8-9`) e anotação em string (`hud.py:51`). `stat_views`
segue o mesmo padrão. Por isso `StatDef` mora em `scenario.py` (é schema de
cenário) e `StatView`/`DynamicStat` em `hud.py` (são estado e projeção de
sessão).

`MindView` mora em `cast.py`, ao lado de `CastMember`: é uma leitura por membro
do elenco; `cast.py` importa só `app.scenario` (`cast.py:5`) e já é importado por
`sessions.py` (`sessions.py:13`) sem ciclo. `minds.py` (TCK-063) importará daqui.

`CommandView` mora em `scenario.py`, colado em `CommandDef`: é a projeção do
mesmo dado no locale escolhido. `commands.py` (TCK-065) importa `scenario.py`
para `LoadedScenario` de qualquer jeito; se `CommandView` morasse em
`sessions.py`, `commands.py` teria de importar `sessions.py` e `sessions.py`
teria de importar `commands.py` para montar `SessionDetail.commands` (TCK-072) —
ciclo.

### Validação: modelo primeiro, loader depois

Tudo que é verificável dentro de um item vira validador do próprio modelo
(`field_validator` para um campo, `model_validator(mode="after")` quando cruza
campos). Assim `builder_doc.read_document`/`write_document` herdam a mesma
validação de graça, sem duplicar regra (é o que já acontece com o
`field_validator` `Character._validate_emotions`, `scenario.py:56-71`).

No modelo:
- `StatDef`: `max > min`; `min <= default <= max`; `levels` com `from`
  estritamente crescente e todo `from` em `[min, max]`; `icon` com no máximo 4
  chars; `color` casando `^#[0-9a-fA-F]{6}$`; `id` casando `^[a-z0-9_-]+$`.
- `LoreEntry`: `keywords` não vazia quando `scope == "keyword"`.
- `CommandDef`: `name` casando `^[a-z0-9_-]+$`.

No loader (`load_scenario`), só o que é cruzado:
- ids de stat duplicados → `ScenarioError(stats_path, "duplicate stat id '<id>'")`;
- nomes de comando duplicados →
  `ScenarioError(commands_path, "duplicate command name '<name>'")`.
Duplicata de id de lorebook já cai na regra de stem duplicado que
`_load_characters` usa (`scenario.py:214-217`) — o loader de lorebook é o mesmo
laço, com `^[a-z0-9-]+$` no stem.

### `from` e palavra reservada

`StatLevel` tem um campo chamado `from` no YAML, que nao pode ser nome de
atributo em Python. O campo se chama `from_` com
`Field(validation_alias="from", serialization_alias="from")` e
`model_config = ConfigDict(extra="forbid", populate_by_name=True)`. FastAPI
serializa `response_model` por alias (e o que ja faz `SessionSummary.scenarioId`,
`sessions.py:76`), entao `GET /api/builder/scenarios/{id}` devolve `from` e o
tipo TS `StatLevel` casa. Nos serializadores YAML de `builder_doc.py` a chave e
escrita a mao como `"from"`, sem depender do alias.

### Ausente = vazio, nunca erro

`stats.yaml`, `commands.yaml` e `lorebook/` ausentes devolvem `[]`/`{}`. Arquivo
presente e ilegível (YAML quebrado, item que não é mapping, campo desconhecido)
**é** `ScenarioError`, como todo o resto do loader. Arquivo presente com conteúdo
`null` (documento YAML vazio) conta como vazio, não como erro: um autor que apaga
o conteúdo mas deixa o arquivo não deve derrubar `list_scenarios`.

### `create_session` e sessão antiga

`create_session` (`sessions.py:163-225`) monta o HUD com `hud_from_start`
(`hud.py:51`) e grava `hud.model_dump_json()` (`sessions.py:193`). Passa a
semear os defaults antes de gravar:

```python
hud = hud_from_start(start)
hud = hud.model_copy(update={"stats": {stat.id: stat.default for stat in scenario.stats}})
```

Sessão criada antes deste ticket não tem a chave: `HudState.stats` tem default
`{}` e `HudState.model_validate_json` (`sessions.py:278`) aceita o JSON antigo.
`stat_views` cobre o buraco lendo `stat.default` quando o id não está em
`hud.stats`, então `GET /api/sessions/{id}` de uma sessão velha já responde certo
sem escrever nada. O preenchimento persistido de sessão antiga (`ensure_stats`) é
do TCK-061.

### `SessionDetail.hud` passa a carregar mapa cru — de propósito

`SessionDetail.hud` é `HudState`, então a resposta JSON passa a incluir
`hud.stats` (mapa `id -> int`) e `hud.dynamic_stats`. Isso é estado do engine, é
verdadeiro, e é aditivo. O tipo TS `HudState` (`api.ts:25`) **não** ganha os dois
campos: o que a UI consome é `SessionDetail.stats`, que é `StatView[]`. Quem
emitir o payload SSE `hud` (TCK-061 em diante) usa
`hud.model_dump(exclude={"stats", "dynamic_stats"})` antes de acrescentar a chave
`stats` com os `StatView` — sem o `exclude`, o mapa cru e a lista de views
disputariam a mesma chave `stats` no dicionário.

### `builder_doc.py`

- `read_document` (`:104-117`) ganha três leituras. `lorebook` reusa `_load_dir`
  (`:74-101`) com `inject_id=False`, igual a `characters` (`:109`). `stats` e
  `commands` são arquivo-lista único: um helper `_load_list(scenario_dir,
  filename, model)` que devolve `[]` se o arquivo não existe, levanta
  `ScenarioError` se o conteúdo não é lista, e valida item a item com
  `scenario_module._summarize` no erro, como `_load_dir` já faz (`:99-100`).
- `compute_revision` (`:120-149`): a lista de arquivos ganha `stats.yaml`,
  `commands.yaml` (quando existem) e o glob de `lorebook/`. Sem isso, editar uma
  entrada de lore fora do builder não seria detectado como conflito.
- `write_document` (`:266-314`): `stats.yaml` e `commands.yaml` entram em
  `targets` **só quando a lista não é vazia**; lista vazia com arquivo no disco
  → o arquivo é removido e conta em `files_deleted`. `lorebook/<id>.yaml` entra
  em `targets` por entrada e `_prune_dir(scenario_dir / "lorebook",
  set(doc.lorebook))` (`:254-263`) remove o resto.
- Serializadores no molde de `_serialize_character` (`:222-244`): ordem canônica
  de chaves, opcional omitido quando `None`, `_dump_yaml` com
  `allow_unicode=True` e `sort_keys=False` (`:172-176`).
- `put_builder_document_route` reconstrói o doc campo a campo (`:357-363`);
  os três campos novos entram nessa construção, senão o PUT apaga tudo
  silenciosamente.
- `_validate_document` (`:152-169`) ganha três checagens, no mesmo molde das de
  start/character: id de entrada de lorebook fora de `_ID_RE` → erro
  `invalid lorebook id '<id>', expected [a-z0-9-]+`; dois stats com o mesmo `id`
  → `duplicate stat id '<id>'`; dois comandos com o mesmo `name` →
  `duplicate command name '<name>'`. Sem isso o `PUT` gravaria
  `lorebook/Caderno.yaml` ou um `stats.yaml` duplicado e o `load_scenario`
  seguinte derrubaria o cenário.

### Frontend

`draftOf` (`BuilderEditorScreen.tsx:42-44`) passa a copiar os três campos.
`BuilderDraft` é `Omit<ScenarioDocument, 'revision'>` (`:20`), então o tipo se
atualiza sozinho e o compilador aponta cada fábrica de teste que ficou
incompleta.

**Nove arquivos de teste do frontend quebram o `tsc -b`** por construírem os
tipos alargados. É preparação mecânica: cada fábrica ganha `stats: []`,
`lorebook: {}`, `commands: []` e `meta.allow_dynamic_stats: false`
(`BuilderDraft`), ou `stats: []`, `minds: {}`, `commands: []`, `suggestions: []`
(`SessionDetail`). Nenhuma asserção muda. É o mesmo movimento que o TCK-050 fez
ao introduzir `cast`.

O literal `DOCUMENT` de `BuilderEditorScreen.test.tsx:7` **não** é tipado (é
objeto solto passado a `jsonResponse(body: unknown)`), então não quebra o
compilador e **não** é tocado aqui: `draftOf` sobre ele produz `undefined` nos
três campos, `JSON.stringify` os omite no PUT e o backend aplica os defaults. As
duas asserções sobre o corpo do PUT (`:214` `toMatchObject({revision, force})` e
`:369` sobre `starts.default.suggestions`) continuam válidas. O arquivo
`BuilderEditorScreen.test.tsx` fica **fora** de `files` de propósito.

### Ressalva de porte

Exceção registrada pelo coordenador do HRZ Workflow (02/09/2026): este ticket
é o interface freeze da fase e o porte de ~620 linhas é aceito; o alvo de ~400
não se aplica a ele.

A estimativa é ~620 linhas com testes, acima do alvo de ~400. **Não** quebre em
dois freezes: quebrar o contrato em dois deixa metade dos consumidores sem uma
das metades. Corte assim, nesta ordem, se o diff passar de ~500:
1. Funda `backend/tests/test_scenario_stats.py` e
   `backend/tests/test_scenario_lore_commands.py` num arquivo só,
   `backend/tests/test_scenario_phase3.py`.
2. No round-trip do builder, teste os três arquivos num único cenário de
   `GET → PUT → GET` em vez de um cenário por arquivo.
3. Deixe os casos de borda de `StatDef` (icon > 4 chars, cor inválida) como um
   único `pytest.mark.parametrize` em vez de um teste por caso.
Não corte cenário de poda nem de revision: são o motivo de o ticket existir.

## Contrato público

```python
# backend/app/scenario.py
class StatLevel(BaseModel):          # extra="forbid"
    from_: int = Field(alias="from")  # serialization_alias/validation_alias "from"; populate_by_name
    text: str

class StatDef(BaseModel):            # extra="forbid"
    id: str                          # ^[a-z0-9_-]+$
    name: str
    icon: str | None = None          # <= 4 chars
    color: str | None = None         # ^#[0-9a-fA-F]{6}$
    min: int = 0
    max: int                         # > min
    default: int                     # min <= default <= max
    description: str | None = None
    levels: list[StatLevel] = []     # `from` estritamente crescente, cada um em [min, max]

class LoreEntry(BaseModel):          # extra="forbid"
    title: str
    keywords: list[str] = []         # >= 1 quando scope == "keyword"
    body: str
    scope: Literal["keyword", "always"] = "keyword"
    priority: int = 0
    enabled: bool = True

class CommandDef(BaseModel):         # extra="forbid"
    name: str                        # ^[a-z0-9_-]+$
    description: str
    prompt: str

class CommandView(BaseModel):
    name: str
    description: str
    scope: Literal["scenario", "global"]

# ScenarioMeta ganha: allow_dynamic_stats: bool = False
# LoadedScenario ganha:
#   stats: list[StatDef] = []
#   lorebook: dict[str, LoreEntry] = {}
#   commands: list[CommandDef] = []
```

```python
# backend/app/hud.py
class DynamicStat(BaseModel):
    name: str
    value: int
    min: int = 0
    max: int

class StatView(BaseModel):
    id: str
    name: str
    icon: str | None
    color: str | None
    value: int
    min: int
    max: int
    level: str | None      # texto do level ativo (ultimo `from` <= value), ou None

# HudState ganha:
#   stats: dict[str, int] = {}
#   dynamic_stats: dict[str, DynamicStat] = {}

def stat_views(scenario: "LoadedScenario", hud: HudState) -> list[StatView]
    # declarados na ordem de scenario.stats (hud.stats[id] ou stat.default),
    # seguidos dos de hud.dynamic_stats na ordem de insercao do dict.
```

```python
# backend/app/cast.py
MIND_EVENT_KIND = "minds"

class MindView(BaseModel):
    attitude: str
    emoji: str
    event: str

def minds_event(entries: dict[str, MindView]) -> tuple[str, dict]
    # (MIND_EVENT_KIND, {"entries": {id: {attitude, emoji, event}}}) — mapa completo
```

```python
# backend/app/sessions.py
# SessionDetail ganha:
#   stats: list[StatView] = []
#   minds: dict[str, MindView] = {}
#   commands: list[CommandView] = []
#   suggestions: list[str] = []
# TurnView ganha:
#   mode: Literal["do", "say", "story"] | None = None
#   meta: bool = False
#   suggestions: list[str] = []
#   command: str | None = None
```

```python
# backend/app/main.py
# ChatRequest ganha: mode: Literal["do", "say", "story"] | None = None
# Congelado aqui, entregue pelo TCK-072: POST /api/sessions/{id}/turn responde
# 422 com detail "unknown_command" quando message começa com '!' ou '/' e o
# nome não resolve; o TCK-074 consome este contrato, não o do TCK-072.
```

```python
# backend/app/builder_doc.py
# ScenarioDocument ganha:
#   stats: list[StatDef] = []
#   lorebook: dict[str, LoreEntry] = {}
#   commands: list[CommandDef] = []
```

Payload SSE, congelado aqui e **implementado nos tickets seguintes** (evento a
evento, na ordem em que `run_turn` os emite):

```jsonc
{"delta": "..."}                                  // ja existe
{"suggestions": ["...", "...", "..."]}            // TCK-069; substitui a lista inteira, nunca delta
{"hud": {
   "turn": 1, "location": "...", "time": "...", "weather": "...",
   "cast":  [{"id": "...", "name": "..."}],       // ja existe (TCK-050/055)
   "stats": [ /* StatView */ ],                   // TCK-061; ausente = inalterado
   "minds": { "chloe": {"attitude": "...", "emoji": "...", "event": "..."} }  // TCK-069; ausente = inalterado, presente = mapa completo
}}
{"error": "turn_failed"}                          // ja existe
```

Eventos novos do event store, congelados aqui:

| kind | payload | escrito por |
| --- | --- | --- |
| `stat` | `{id, delta, value, source}`, `source` em `tag \| judge`; `delta` é o **delta efetivo** depois do clamp (`value == valor anterior + delta`), nunca o pedido pela tag ou pelo juiz; mudança que clampa para o mesmo valor não gera evento | TCK-061 (tag), TCK-069 (judge) |
| `minds` | `{entries: {id: {attitude, emoji, event}}}` | TCK-069 |
| `meta_player_turn` | `{text, command}` | TCK-072 |
| `meta_narrator_turn` | `{text}` | TCK-072 |

`narrator_turn.payload` ganha `suggestions: list[str]` (TCK-069);
`player_turn.payload` ganha `mode: str` (TCK-072). Ambos ausentes nos eventos
antigos, e ausência **nunca** é erro: `history_events` (`turn.py:69-74`) e
`events_to_messages` (`turn.py:77-83`) leem só `payload["text"]` e continuam
lendo só isso.

```ts
// frontend/src/api.ts
export type StatLevel = { from: number; text: string }
export type StatDef = {
  id: string; name: string; icon: string | null; color: string | null
  min: number; max: number; default: number
  description: string | null; levels: StatLevel[]
}
export type LoreEntryDoc = {
  title: string; keywords: string[]; body: string
  scope: 'keyword' | 'always'; priority: number; enabled: boolean
}
export type CommandDoc = { name: string; description: string; prompt: string }

export type StatView = {
  id: string; name: string; icon: string | null; color: string | null
  value: number; min: number; max: number; level: string | null
}
export type MindView = { attitude: string; emoji: string; event: string }
export type CommandView = { name: string; description: string; scope: 'scenario' | 'global' }
export type InputMode = 'do' | 'say' | 'story'

// ScenarioMeta ganha:      allow_dynamic_stats: boolean
// ScenarioDocument ganha:  stats: StatDef[]; lorebook: Record<string, LoreEntryDoc>; commands: CommandDoc[]
// SessionDetail ganha:     stats: StatView[]; minds: Record<string, MindView>
//                          commands: CommandView[]; suggestions: string[]
// TurnView ganha:          mode?: InputMode | null; meta?: boolean
//                          suggestions?: string[]; command?: string | null
// TurnHudPayload ganha:    stats?: StatView[]; minds?: Record<string, MindView>
// TurnOptions ganha:       mode?: InputMode
```

`TurnHudPayload.stats` e `.minds` são **opcionais**: ausência significa
"inalterado", exatamente como `cast` (contrato do TCK-050). `SessionDetail.stats`
e `.minds` são obrigatórios — o backend sempre manda.

Os quatro campos novos de `TurnView` são **opcionais no TS** de propósito, embora
o backend sempre os mande: `GamePanel.tsx:278-279` e `GameScreen.test.tsx:157-159`,
`:611`, `:635` constroem literais `{ index, role, text }` para turnos otimistas,
e torná-los obrigatórios arrastaria `GamePanel.tsx` para este ticket. Consumidor
que precisar do valor lê com `?? null` / `?? false` / `?? []`. TCK-071 e TCK-074
preenchem só o que usam nos literais que criam.

`streamTurn` **não** muda neste ticket: `TurnOptions.mode` é declarado, e quem
passa a mandá-lo no body é o TCK-071.

**Congelado.** Mudança de qualquer coisa nesta seção depois do merge vira ticket
de foundation, mergeado em wave anterior à dos consumidores.

## Acceptance criteria

- [ ] Cenário com `stats.yaml` de dois stats carrega e
      `scenario.stats[0].id == "reputacao"`, na ordem do arquivo.
- [ ] Cenário sem `stats.yaml`, sem `lorebook/` e sem `commands.yaml` carrega com
      `stats == []`, `lorebook == {}`, `commands == []`.
- [ ] `stats.yaml` com dois stats de mesmo id levanta `ScenarioError` citando o
      caminho do arquivo; `commands.yaml` com dois `name` iguais também.
- [ ] `StatDef` com `default` fora de `[min, max]`, com `max <= min`, com
      `levels` fora de ordem, com `icon` de 5 chars ou com `color` sem `#` é
      recusado na carga.
- [ ] `LoreEntry` com `scope: keyword` e `keywords: []` é recusada;
      com `scope: always` e `keywords: []` é aceita.
- [ ] `stat_views` devolve um `StatView` por stat declarado, na ordem de
      `stats.yaml`, com `value` de `hud.stats` quando presente e `default` quando
      ausente, e `level` igual ao texto do último level cujo `from <= value`
      (`None` quando não há levels ou quando o valor é menor que o primeiro
      `from`); os dinâmicos vêm depois.
- [ ] `POST /api/sessions` num cenário com stats devolve `stats` com os defaults
      e grava `hud.stats` no banco; `GET /api/sessions/{id}` da mesma sessão
      devolve o mesmo.
- [ ] `GET /api/sessions/{id}` de sessão gravada **antes** deste ticket (HUD sem
      a chave `stats`) responde 200 com os defaults, sem escrever nada.
- [ ] `SessionDetail` traz `minds == {}`, `commands == []`, `suggestions == []`;
      `TurnView` traz `mode == None`, `meta is False`, `suggestions == []`,
      `command == None`.
- [ ] `POST /api/sessions/{id}/turn` com `{"message": "oi", "mode": "say"}`
      responde 200 e narra igual ao de hoje; com `"mode": "gritar"` responde 422.
- [ ] `PUT` com id de lorebook `Caderno`, com dois stats de id `reputacao`, ou com
      dois comandos de nome `fofoca` responde 422 citando o id/nome, sem escrever
      nada no disco.
- [ ] `GET → PUT` sem alteração num cenário com os três arquivos devolve a mesma
      revision e não toca nenhum arquivo no disco.
- [ ] `PUT` com `stats: []` num cenário que tem `stats.yaml` remove o arquivo;
      `PUT` sem uma entrada de lorebook remove `lorebook/<id>.yaml`.
- [ ] Editar `lorebook/caderno.yaml` fora do builder muda `compute_revision`, e
      um `PUT` com a revision antiga responde 409.
- [ ] `npm run check` verde (pytest + `tsc -b` + vitest), com todas as asserções
      dos testes existentes inalteradas.

## Cenários de teste

Suíte existente que muda **de preparação** (asserções preservadas):

- `frontend/src/components/GamePanel.test.tsx:16`,
  `frontend/src/screens/GameScreen.test.tsx:31` e
  `frontend/src/components/builder/BuilderPreview.test.tsx:67`: a fábrica
  `session()` de cada um ganha `stats: []`, `minds: {}`, `commands: []`,
  `suggestions: []`. Sem isso o `tsc -b` falha, porque as três anotam o retorno
  como `SessionDetail`. Os literais `TurnView` de `GameScreen.test.tsx:157-159`,
  `:611` e `:635` continuam válidos porque os campos novos são opcionais no TS.
- `frontend/src/builder/validate.test.ts:6`,
  `frontend/src/components/builder/BuilderPreview.test.tsx:32`,
  `CharactersTab.test.tsx:10`, `IdentityTab.test.tsx:10`,
  `MediaTab.test.tsx:9`, `StartsTab.test.tsx:10`, `WorldTab.test.tsx:10`: a
  fábrica de `BuilderDraft` de cada um ganha `stats: []`, `lorebook: {}`,
  `commands: []`, e `meta` ganha `allow_dynamic_stats: false`. Mesma razão.
  (`BuilderPreview.test.tsx` aparece nas duas listas: tem as duas fábricas.)
- `backend/tests/test_builder_doc.py:96-108`: os campos novos entram na resposta.
  As asserções são pontuais (`body["meta"]["name"]`, `len(body["starts"])`,
  `len(body["characters"])`, `"revision" in body`), nenhuma compara o corpo
  inteiro, então **nenhuma muda**; o arquivo está em `files` porque os cenários
  novos de loader/round-trip são escritos nele.
- `backend/tests/test_builder_doc_write.py`: o `doc` de cada teste vem de um
  `GET` real (`:93`, `:112`), então já chega com os três campos e o `PUT`
  devolve. `test_get_put_get_roundtrip_without_changes_keeps_revision:272` é o
  guarda-costas disso e não muda de corpo.
- `backend/tests/test_sessions.py`: `test_create_session_happy_path:149` e
  `test_post_sessions_route_happy_path:409` aferem campo a campo
  (`detail.turns`, `detail.prologue`, `detail.hud.turn`), nunca o modelo inteiro
  — seguem verdes sem edição. O arquivo fica **fora** de `files`.
- Nenhum teste de backend existente exercita `stats.yaml`, `lorebook/` ou
  `commands.yaml`: eles não existiam. Cobertura nova é toda deste ticket.

Cenários novos:

`backend/tests/test_scenario_stats.py` (padrão de `test_scenario.py`:
`_write_scenario` em `tmp_path` + `monkeypatch` de `app.scenario.scenarios_dir`):
- Feliz: `stats.yaml` com `reputacao` (3 levels) e `energia` carrega na ordem do
  arquivo, com `description` e `levels` preenchidos.
- Feliz: `allow_dynamic_stats: true` em `scenario.yaml` chega em
  `scenario.meta.allow_dynamic_stats`; ausente vira `False`.
- Borda: `stats.yaml` ausente → `[]`; `stats.yaml` com conteúdo vazio → `[]`.
- Falha: id duplicado; `max <= min`; `default` fora da faixa; `levels` com `from`
  não crescente; `from` fora de `[min, max]`; `icon` de 5 chars; `color`
  `"f5c542"` (sem `#`); `id` `"Reputação"`; campo desconhecido no item.
- Falha: `stats.yaml` que é um mapping em vez de lista → `ScenarioError` citando
  o caminho.

`backend/tests/test_scenario_lore_commands.py`:
- Feliz: duas entradas em `lorebook/` viram `dict` com o stem como chave, com
  defaults `scope="keyword"`, `priority=0`, `enabled=True`.
- Feliz: `commands.yaml` com `!fofoca` carrega `name/description/prompt`.
- Borda: pasta `lorebook/` ausente → `{}`; vazia → `{}`; `commands.yaml` ausente
  → `[]`.
- Borda: `scope: always` com `keywords: []` é aceito.
- Falha: `scope: keyword` sem keyword; stem `Caderno.yaml` (maiúscula) recusado;
  mesmo stem em `.yaml` e `.yml`; dois comandos com o mesmo `name`; `name` com
  espaço.
- Falha: `list_scenarios` com um cenário de `stats.yaml` quebrado emite
  `scenario_invalid` e devolve os outros (regra de `scenario.py:285-296`).

`backend/tests/test_stat_views.py`:
- Feliz: dois stats declarados e `hud.stats = {"reputacao": 55}` → `energia` sai
  com o default, `reputacao` com 55, na ordem do cenário.
- Feliz: level ativo é o último `from <= value`; `value` abaixo do primeiro
  `from` → `level is None`; stat sem `levels` → `level is None`.
- Borda: `hud.stats` com id que não existe mais no cenário é ignorado.
- Borda: `hud.dynamic_stats` sai depois dos declarados, com `icon`/`color`/
  `level` em `None`.
- Borda: `MindView` e `minds_event(...)` devolvem
  `("minds", {"entries": {...}})` — teste curto de contrato, para o TCK-069 não
  ter de descobrir o formato.
- Feliz (rota, com `TestClient` e cenário em `tmp_path`): `POST /api/sessions`
  devolve `stats` com defaults e o `hud` do banco tem a chave `stats`; um `GET`
  depois devolve igual.
- Borda (rota): sessão criada com `hud` sem `stats` (gravado direto no SQLite,
  como `test_sessions.py` já faz em `:101-148`) responde 200 com os defaults.
- Borda (rota): `POST .../turn` com `mode: "say"` responde 200; com
  `mode: "gritar"` responde 422.

`backend/tests/test_builder_doc.py` (cenários acrescentados):
- Feliz: `GET` de um cenário com os três arquivos devolve `stats` como lista na
  ordem do arquivo, `lorebook` como objeto por stem, `commands` como lista.
- Borda: cenário sem os três devolve `[]`/`{}`/`[]`.
- Borda: editar `lorebook/caderno.yaml` no disco muda `compute_revision`; editar
  `stats.yaml` também.

`backend/tests/test_builder_doc_write.py` (cenários acrescentados):
- Feliz: `GET → PUT` sem alteração mantém revision e mtime (molde de `:201`).
- Feliz: `PUT` acrescentando um stat escreve `stats.yaml` na ordem canônica de
  chaves, com acento preservado (molde de `:110`).
- Borda: `PUT` com `stats: []` num cenário que tinha `stats.yaml` apaga o arquivo
  e conta em `files_deleted`; idem `commands: []`.
- Borda: `PUT` sem uma das entradas de lorebook apaga só o `.yaml` dela (molde de
  `test_put_removes_start_missing_from_payload_and_adds_new_one:240`).
- Borda: entrada de lorebook salva como `.yml` e `.yaml` deixa só o `.yaml`
  (molde de `:310`).
- Falha: `PUT` com revision antiga depois de uma edição em `lorebook/` responde
  409 e não escreve nada.

## Rollout e kill switch

N/A — sem flag própria. `risk: low` porque três rotas em uso mudam de forma de
resposta (`POST /api/sessions`, `GET /api/sessions/{id}`,
`GET /api/builder/scenarios/{id}`) e o `PUT` do builder passa a escrever e podar
arquivos novos, mas todas as mudanças são aditivas e nenhum comportamento de
turno muda. Os kill switches da fase (`hud_judge`, `minds`, `lorebook`) nascem
nos tickets que ligam cada subsistema ao turno.

Mitigação do único risco destrutivo — a poda: `_prune_dir` só apaga dentro de
`lorebook/`, e só ids ausentes do payload; e o `PUT` só chega lá depois da
checagem de revision (`builder_doc.py:269-277`), que é o que impede um cliente
com estado velho de apagar entradas que ele nunca viu.

## Observabilidade

Eventos (via `emit` de `backend/app/observability.py`):
- `builder_doc_read` (`builder_doc.py:333-339`) ganha as propriedades `stats`
  (int), `lore` (int) e `commands` (int), ao lado de `starts` e `characters`.
- `builder_doc_saved` (`:306-313`) não ganha propriedade: `files_written` e
  `files_deleted` já contam os arquivos novos.
- Nenhum evento novo. Os eventos `stat`/`minds` da tabela `events` são estado, e
  a telemetria deles é dos TCK-061/069.

Métrica de sucesso: `GET /api/sessions/{id}` de uma sessão criada antes do merge
responde 200 com os stats no default, e um `GET → PUT → GET` do
`scenarios/exemplo-escola` (que ganha os três arquivos no TCK-068) devolve a
mesma revision — nenhuma sessão e nenhum cenário existente quebra.

## i18n

N/A — nenhuma string de usuário nasce aqui. `StatDef.name`, `StatDef.description`,
o texto dos levels, `LoreEntry.title/body` e `CommandDef.description/prompt` vêm
do YAML do cenário, já no locale do cenário, e nunca passam por `t()`. As chaves
de UI das abas novas são dos TCK-066/070/073 e as do jogo são dos TCK-067/071/074.
