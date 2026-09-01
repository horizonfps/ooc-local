---
id: TCK-050
title: Persistir o elenco em cena como estado da sessão e expor no contrato
status: done
points: 3
blockedBy: []
files:
  - backend/app/cast.py
  - backend/app/sessions.py
  - backend/tests/test_cast.py
  - backend/tests/test_sessions.py
  - frontend/src/api.ts
  - frontend/src/components/GamePanel.test.tsx
  - frontend/src/screens/GameScreen.test.tsx
  - frontend/src/components/builder/BuilderPreview.test.tsx
migration: false
ui: false
risk: medium
---

## Problema

Hoje quem está em cena é decidido uma vez, no disco: `_characters_in_scene`
(`backend/app/turn.py:47`) devolve `start.characters` ou o elenco inteiro do
cenário, e nada disso é estado da sessão. Não existe onde escrever "agora a
Chloe entrou em cena", nem como o frontend saberia disso.

Este é o ticket de **interface freeze** da fatia Director: TCK-053 (módulo do
director), TCK-055 (fiação no turno) e TCK-054 (UI da linha de elenco) consomem
o contrato definido aqui. Sem congelar tipo e semântica antes, cada um inventa
um formato de `cast` diferente.

Sozinho, este ticket já muda comportamento visível: `GET /api/sessions/{id}`
passa a devolver `cast`, semeado do start. É o mesmo elenco que o motor já usa
para narrar, agora dito em voz alta no contrato.

## Escopo

Dentro:
- `backend/app/cast.py` novo: módulo **puro** (importa só `app.scenario` e
  pydantic) com o tipo `CastMember`, o kind do evento, o cap de personagens em
  cena, a semente a partir do start, a resolução id → membro e a validação
  determinística de uma lista de ids proposta, que devolve o motivo da rejeição
  junto.
- `backend/app/sessions.py`: leitura do último elenco persistido no event store
  e campo `cast` em `SessionDetail`.
- `frontend/src/api.ts`: tipo `CastMember`, campo `cast` em `SessionDetail` e
  tipo próprio para o payload do evento `hud` do SSE de turno.
- Ajuste de preparação nos fixtures de sessão dos testes de frontend.

Fora (explícito):
- Chamar o utility / decidir elenco: TCK-053 e TCK-055. Este ticket não emite
  nenhum evento `cast`, só sabe ler e validar.
- Tocar em `backend/app/turn.py`. Enquanto o TCK-055 não entra,
  `_characters_in_scene` continua exatamente como está e o `cast` de
  `SessionDetail` coincide com ele por construção (mesma semente).
- Tocar em `backend/app/prompt.py` (roster é TCK-051) e em qualquer componente
  React (TCK-054).
- Coluna nova em `sessions` ou qualquer migration de schema: o elenco vive no
  event store, que não tem schema por kind.

## Comportamento esperado

Do ponto de vista do chamador da API: `GET /api/sessions/{id}` e
`POST /api/sessions` devolvem `cast: [{id, name}]`, na ordem em que os ids
aparecem. Sessão recém-criada com `characters: [chloe, ashlee, mika]` no start
devolve os três; start com `characters: null` devolve o elenco inteiro do
cenário; start com `characters: []` devolve `[]`.

Do ponto de vista dos tickets de backend que dependem deste: existe uma função
pura que recebe uma lista de ids proposta por um LLM e devolve `(ids saneados,
None)` ou `(None, motivo)` — sem exceção, sem I/O, sem log. O motivo é o que a
telemetria do TCK-055 publica, sem precisar de um segundo juiz.

## Detalhes técnicos

### Por que dois arquivos e não um

`sessions.py` é quem fala com o SQLite (`read_events`, `append_events`). Se
`cast.py` importasse `sessions.py` para ler eventos e `sessions.py` importasse
`cast.py` para o tipo `CastMember`, o import viraria ciclo. Corte: `cast.py` é
puro (regras e constantes) e **não importa `sessions.py`**; `sessions.py` é I/O
e importa `cast.py`. Toda constante desta feature (`CAST_EVENT_KIND`,
`MAX_CAST_IN_SCENE`) tem domicílio único em `cast.py`.

### `backend/app/cast.py`

```python
CAST_EVENT_KIND = "cast"
MAX_CAST_IN_SCENE = 6

class CastMember(BaseModel):
    id: str
    name: str

def seed_cast_ids(scenario: LoadedScenario, start: StartConfig) -> list[str]
def resolve_cast(scenario: LoadedScenario, ids: list[str]) -> list[CastMember]
def validate_cast_ids(scenario: LoadedScenario, ids: object) -> tuple[list[str] | None, str | None]
def cast_event(ids: list[str], source: str) -> tuple[str, dict]
```

- `seed_cast_ids`: `start.characters is None` → `list(scenario.characters)`
  (ordem de `_load_characters`, que é `sorted` por nome de arquivo); caso
  contrário `list(start.characters)`, inclusive `[]`. Espelha
  `_characters_in_scene` de `turn.py:47`, que continua sendo o que roda no turno
  até o TCK-055.
- `resolve_cast`: ignora id desconhecido em silêncio (a sessão pode ter sido
  gravada com um personagem que o autor apagou depois); `name` vem de
  `scenario.characters[id].name`.
- `validate_cast_ids` é o juiz determinístico do engine e recebe `object`,
  porque a entrada vem de JSON de LLM. Devolve `(None, reason)` com:
  - `"not_a_list"` — não é `list`, ou algum item não é `str`;
  - `"unknown_ids"` — algum id não existe em `scenario.characters`;
  - `"over_cap"` — o total após dedupe passa de `MAX_CAST_IN_SCENE`.

  Ordem de verificação: forma → ids → cap (o primeiro motivo encontrado vence).
  Caso válido devolve `(ids_deduplicados_em_ordem, None)`. `[]` é **válido**
  (cena sem NPC é estado legítimo desde a semântica de start vazio). Rejeitar por
  estouro de cap em vez de truncar mantém a regra "o utility propõe, o engine
  decide" auditável: o elenco anterior fica de pé e a telemetria registra o
  motivo. `invalid_json` **não** é motivo desta função: quem lê JSON é o parser
  do TCK-053.
- `cast_event(ids, source)` devolve `(CAST_EVENT_KIND, {"ids": ids, "source":
  source})`, no formato `NewEvent` que `append_events` já consome. Só o TCK-055
  chama.

### `backend/app/sessions.py`

- `read_cast_ids(session_id) -> list[str] | None`: `read_events(session_id,
  kinds=(CAST_EVENT_KIND,))`, devolve `payload["ids"]` do último (maior `seq`) ou
  `None` se nunca houve nenhum. Payload sem a chave `ids`, ou com `ids` que não é
  lista de strings, é tratado como ausência (`None`) — evento corrompido não pode
  derrubar `GET /api/sessions/{id}`.
- `SessionDetail` ganha `cast: list[CastMember]`. Preenchido em `get_session` e
  em `create_session`:
  ```python
  ids = read_cast_ids(session_id)
  if ids is None:
      ids = seed_cast_ids(scenario, start)
  cast = resolve_cast(scenario, ids)
  ```
  Comparação explícita com `None`: `read_cast_ids(...) or seed_...` trataria `[]`
  como falsy e ressuscitaria a semente numa cena legitimamente vazia. Em
  `create_session` a sessão é nova, então a semente sempre vale.
- Nenhuma outra função muda. `history_events` e `_build_turns` já filtram por
  `kinds=("player_turn", "narrator_turn")`, então evento `cast` no meio da
  sequência **não** entra na janela do narrador nem na lista de turnos da API.

### `frontend/src/api.ts`

```ts
export type CastMember = { id: string; name: string }
export type TurnHudPayload = HudState & { cast?: CastMember[] }
// SessionDetail ganha: cast: CastMember[]
// TurnEvent.hud e TurnHandlers.onHud passam a usar TurnHudPayload
```

`HudState` **não** ganha campo nenhum. Ele é o mesmo tipo usado em
`SessionDetail.hud`, e `cast` ali seria mentira: no nível da sessão o elenco vive
em `SessionDetail.cast`, não dentro do HUD. O `cast` só existe no payload do
evento `hud` do SSE (`TurnEvent`, `api.ts:231`), e por isso ganha tipo próprio.
`cast` em `SessionDetail` é obrigatório (o backend sempre manda); em
`TurnHudPayload` é opcional — quem implementa a emissão é o TCK-055, e a ausência
significa "elenco inalterado", nunca "elenco vazio".

## Contrato público

```python
# backend/app/cast.py
CAST_EVENT_KIND: str
MAX_CAST_IN_SCENE: int
class CastMember(BaseModel): id: str; name: str
def seed_cast_ids(scenario: LoadedScenario, start: StartConfig) -> list[str]
def resolve_cast(scenario: LoadedScenario, ids: list[str]) -> list[CastMember]
def validate_cast_ids(scenario: LoadedScenario, ids: object) -> tuple[list[str] | None, str | None]
    # reasons: "not_a_list" | "unknown_ids" | "over_cap"
def cast_event(ids: list[str], source: str) -> tuple[str, dict]

# backend/app/sessions.py
def read_cast_ids(session_id: str) -> list[str] | None
# SessionDetail ganha cast: list[CastMember]
```

```ts
// frontend/src/api.ts
export type CastMember = { id: string; name: string }
export type TurnHudPayload = HudState & { cast?: CastMember[] }
// SessionDetail ganha cast: CastMember[]
```

Consumido por TCK-053, TCK-055 e TCK-054. **Congelado**: mudança aqui depois do
merge vira ticket de foundation, mergeado antes dos três.

## Acceptance criteria

- [ ] `POST /api/sessions` e `GET /api/sessions/{id}` devolvem `cast` com
      `[{id, name}]` na ordem de `start.characters`.
- [ ] Start com `characters: null` devolve o elenco inteiro do cenário; start com
      `characters: []` devolve `[]`.
- [ ] Havendo evento `cast` gravado na sessão, o último vence sobre a semente.
- [ ] Evento `cast` com payload sem a chave `ids` (ou com `ids` que não é lista
      de strings) não derruba `GET /api/sessions/{id}`: responde 200 com o elenco
      semeado do start.
- [ ] `validate_cast_ids` devolve `(None, "not_a_list")` para não-lista e para
      item não-string, `(None, "unknown_ids")` para id inexistente e
      `(None, "over_cap")` acima de `MAX_CAST_IN_SCENE`.
- [ ] `validate_cast_ids` devolve `(lista_deduplicada, None)` no caso válido, e
      `([], None)` para `[]`.
- [ ] `resolve_cast` ignora id que não existe mais no cenário.
- [ ] Evento `cast` gravado na sessão não aparece em `SessionDetail.turns` nem na
      janela de contexto do narrador.
- [ ] `HudState` continua sem o campo `cast`; o `cast` do SSE mora em
      `TurnHudPayload`.
- [ ] `npm run check` verde (pytest + `tsc -b` + vitest).

## Cenários de teste

Suíte existente que muda **de preparação** (asserções preservadas):
- `frontend/src/components/GamePanel.test.tsx:16`,
  `frontend/src/screens/GameScreen.test.tsx:40` e
  `frontend/src/components/builder/BuilderPreview.test.tsx:72`: a fábrica de
  `SessionDetail` de cada um ganha `cast: []`, porque o tipo passou a exigir o
  campo. Mesmo movimento que o TCK-042 fez ao introduzir `assets`. Nenhuma
  asserção desses testes muda.
- `backend/tests/test_sessions.py`: os testes que comparam campo a campo
  (`test_append_events_updates_hud_and_updated_at:233`, `:533`) continuam
  válidos; onde algum comparar o modelo inteiro, a preparação ganha o `cast`
  esperado, sem mexer no que o teste afere.

Cenários novos (`backend/tests/test_cast.py`):
- Feliz: `seed_cast_ids` com `characters: [chloe, mika]` devolve exatamente isso;
  `resolve_cast` devolve os nomes na mesma ordem.
- Feliz: sessão sem evento `cast` responde a API com a semente; depois de
  `append_events(id, [cast_event(["chloe"], "director")])`, responde `["chloe"]`.
- Borda: dois eventos `cast` na sessão → vale o último.
- Borda: `characters: null` → elenco inteiro; `characters: []` → `[]` e a API
  devolve `cast: []` (e não a semente).
- Borda: `validate_cast_ids` com `["chloe", "chloe"]` devolve
  `(["chloe"], None)`; com 7 ids válidos devolve `(None, "over_cap")`; com
  `["chloe", 3]`, `"chloe"`, `None` e `{"scene": []}` devolve
  `(None, "not_a_list")`; com `["fantasma"]` devolve `(None, "unknown_ids")`.
- Borda: `validate_cast_ids(scenario, [])` devolve `([], None)`.
- Borda: `resolve_cast(scenario, ["fantasma", "chloe"])` devolve só a Chloe.
- Falha: evento `cast` com payload `{"source": "director"}` (sem `ids`) →
  `read_cast_ids` devolve `None` e `GET /api/sessions/{id}` responde 200 com a
  semente.

## Rollout e kill switch

N/A — `risk: medium` por tocar no formato de resposta de duas rotas em uso, mas
sem flag própria: o campo é aditivo e o comportamento de turno é idêntico ao de
hoje. O kill switch da feature (`director`) é definido no TCK-055, que é quem
muda o fluxo do turno.

## Observabilidade

Eventos: nenhum novo. Os eventos `cast` no event store são estado, não
telemetria; a telemetria (`director_applied` e irmãos) é do TCK-055 e usa como
`reason` exatamente as strings devolvidas por `validate_cast_ids`.
Métrica de sucesso: `GET /api/sessions/{id}` de uma sessão antiga (criada antes
deste ticket, sem nenhum evento `cast`) responde 200 com o elenco semeado do
start — nenhuma sessão existente quebra.

## i18n

N/A — `CastMember.name` vem do YAML do cenário, que já nasce no locale do
cenário. Nenhuma string de UI é criada aqui.
