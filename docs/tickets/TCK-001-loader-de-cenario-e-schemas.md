---
id: TCK-001
title: Ler pasta de cenário com schemas pydantic e expor GET /api/scenarios
status: done
points: 5
blockedBy: []
files:
  - backend/app/scenario.py
  - backend/app/hud.py
  - backend/app/main.py
  - backend/tests/test_scenario.py
migration: false
ui: false
risk: low
---

## Problema

Hoje o backend só tem a rota de fumaça `/api/chat` com prompt fixo
(`backend/app/main.py:13`). Não existe nenhuma noção de cenário: nem schema, nem
leitura de pasta, nem catálogo. Todo o resto da Fase 1 (prompt-mestre, sessão,
HUD, UI) depende de um contrato estável para "o que é um cenário em disco". Sem
ele cada ticket inventa o seu formato de YAML e a Fase 2 (builder) reescreve
tudo.

Este ticket é o **interface freeze** do formato de cenário e do formato do HUD.
Consumidores já enfileirados: TCK-002 (cenário exemplo), TCK-003 (prompt-mestre),
TCK-005 (sessões), TCK-006 (turno), TCK-011 (HUD na UI).

## Escopo

Dentro:
- `backend/app/scenario.py`: modelos pydantic `ScenarioMeta`, `StartConfig`,
  `Character`, `LoadedScenario` + `list_scenarios()` e `load_scenario(id)`.
- `backend/app/hud.py`: modelo `HudState`, vocabulário fechado de clima e
  `hud_from_start(start)`.
- Rota `GET /api/scenarios` em `backend/app/main.py`.
- Raiz de cenários resolvida por `scenarios_dir()`: `OOC_SCENARIOS_DIR` do
  ambiente se definida, senão `<raiz do repo>/scenarios` (a pasta
  `backend/app/scenario.py` fica em `backend/app/`, logo a raiz é
  `Path(__file__).resolve().parents[2]`).
- Testes em `backend/tests/test_scenario.py` montando pastas de cenário em
  `tmp_path` (não dependem de `scenarios/exemplo-escola`, que é o TCK-002).

Fora (explícito):
- `stats.yaml`, `lorebook.yaml`, `commands.yaml`, `endings.yaml`, `media/` —
  existem no layout da spec (`dev/scenario-builder-spec.md` §1) mas são das
  Fases 3–5. O loader os ignora e **não** os declara no schema.
- Escrever cenário em disco (é o builder da Fase 2). Loader é somente leitura.
- Criar `scenarios/exemplo-escola/` (é o TCK-002).
- Setup wizard / `{{variáveis}}` (Fase 7).

## Comportamento esperado

Do ponto de vista do chamador da API:

`GET /api/scenarios` devolve 200 com a lista de cenários válidos encontrados na
raiz de cenários, ordenada por `name` (comparação por `str.casefold()`). Pasta
com YAML inválido não derruba a rota: é omitida da lista e logada.

Do ponto de vista do chamador Python: `load_scenario("exemplo-escola")` devolve
um `LoadedScenario` com meta, texto do `world.md`, dicionário de starts (chave =
nome do arquivo sem extensão) e dicionário de personagens (chave = nome do
arquivo sem extensão). Qualquer problema de formato levanta `ScenarioError` com
o caminho do arquivo culpado e o motivo.

Layout lido (subconjunto de `dev/scenario-builder-spec.md` §1):

```
scenarios/<id>/
  scenario.yaml
  world.md
  starts/default.yaml
  characters/<char-id>.yaml
```

## Detalhes técnicos

- Pydantic v2 já é dependência (`backend/pyproject.toml`), assim como `pyyaml`.
  Seguir o estilo de `backend/app/config.py`: `BaseModel` + `model_validate` +
  `yaml.safe_load`.
- Todos os modelos usam `model_config = ConfigDict(extra="forbid")`. Campo
  desconhecido é erro, não é ignorado silenciosamente: o arquivo é o contrato e
  typo de autor precisa aparecer. Campos das fases seguintes entram no schema
  quando a fase chegar.
- `id` do cenário é o nome da pasta; `id` do personagem e do start é o nome do
  arquivo sem extensão. Nunca vem de dentro do YAML (evita divergência).
- Erros de leitura: `class ScenarioError(Exception)` com `path` e `reason`.
  `list_scenarios()` captura `ScenarioError`, chama
  `emit("scenario_invalid", path=str(path), error=reason)` (de
  `app.observability`; `emit` faz `json.dumps` das props, então `Path` cru
  levantaria `TypeError`) e segue para a próxima pasta. `load_scenario()` propaga.
- `list_scenarios()` devolve `[]` quando `scenarios_dir()` não existe, sem log
  de erro — a raiz só passa a existir com o TCK-002, uma wave depois.
- `world.md` ausente ou vazio é erro. Pasta sem `starts/` ou sem nenhum
  personagem é erro. Pasta que não tem `scenario.yaml` não é cenário: é ignorada
  sem log de erro (permite `.gitkeep`, `README`, etc.).
- Encoding sempre `utf-8` explícito (o repo roda no Windows, onde o default é
  cp1252 e quebraria acento).
- A rota entra em `main.py` junto das existentes (`/api/health`, `/api/chat`),
  sem router novo — mantém o estilo atual do arquivo.

Testes existentes que este ticket invalida: **nenhum**.
`backend/tests/test_chat.py`, `test_config.py` e `test_flags.py` exercitam
`/api/chat`, `load_config` e as flags; nenhum toca cenário. Nenhum
comportamento existente muda — o ticket só adiciona.

## Contrato público

```python
# backend/app/scenario.py
class CharacterMind(BaseModel):      # extra="forbid"
    feeling: str
    goal: str
    opinion_of_player: str | None = None
    secret_plan: str | None = None

class Character(BaseModel):          # extra="forbid"
    name: str
    role: str
    appearance: str
    personality: str
    voice: str
    mind: CharacterMind
    sprite: str | None = None

class HudDefaults(BaseModel):        # extra="forbid"
    location: str
    time: str = "08:00"              # HH:MM 24h, valida ^([01]\d|2[0-3]):[0-5]\d$
    weather: str = "clear"           # precisa estar em app.hud.WEATHER_CODES

class StartConfig(BaseModel):        # extra="forbid"
    id: str                          # preenchido pelo loader (stem do arquivo)
    name: str
    prologue: str
    opening_scene: str
    play_guide: str | None = None
    suggestions: list[str] = []
    hud: HudDefaults
    characters: list[str] | None = None   # ids; None = todos

class ScenarioMeta(BaseModel):       # extra="forbid"
    name: str
    tagline: str | None = None
    description: str | None = None
    locale: Literal["en", "pt-br"] = "pt-br"
    tags: list[str] = []
    default_start: str = "default"

class LoadedScenario(BaseModel):
    id: str
    meta: ScenarioMeta
    world: str
    starts: dict[str, StartConfig]
    characters: dict[str, Character]
    def start(self, start_id: str | None = None) -> StartConfig: ...

class ScenarioError(Exception):
    path: Path
    reason: str

def scenarios_dir() -> Path: ...
def list_scenarios() -> list[LoadedScenario]: ...
def load_scenario(scenario_id: str) -> LoadedScenario: ...   # ScenarioError se inválido/ausente
```

```python
# backend/app/hud.py
WEATHER_CODES = ("clear", "cloudy", "rain", "storm", "snow", "fog", "night")

class HudState(BaseModel):
    turn: int = 0
    location: str
    time: str        # HH:MM 24h, hora do mundo do jogo, já formatada
    weather: str     # um de WEATHER_CODES

def hud_from_start(start: StartConfig) -> HudState: ...   # turn=0 + defaults do start
```

Rota:

```
GET /api/scenarios -> 200
[{ "id": "exemplo-escola", "name": "...", "tagline": "..."|null, "locale": "pt-br" }]
```

Ordenação por `name` casefold. Lista vazia quando não há cenário válido (200,
`[]`, nunca 404).

## Acceptance criteria

- [ ] `load_scenario` devolve `LoadedScenario` completo para uma pasta válida em
      `tmp_path`, com ids derivados dos nomes de arquivo/pasta.
- [ ] Campo desconhecido em qualquer um dos quatro arquivos levanta
      `ScenarioError` citando o caminho do arquivo.
- [ ] `hud` do start com `weather` fora de `WEATHER_CODES` ou `time` fora de
      `HH:MM` levanta `ScenarioError`.
- [ ] `list_scenarios()` ignora pasta sem `scenario.yaml` e omite (com
      `emit("scenario_invalid", ...)`) pasta com YAML inválido, devolvendo as
      demais.
- [ ] `GET /api/scenarios` responde 200 com a lista ordenada por nome; com raiz
      vazia responde `[]`.
- [ ] Raiz de cenários inexistente → `GET /api/scenarios` responde 200 `[]`,
      sem `scenario_invalid` no log.
- [ ] `hud_from_start` devolve `turn=0` e os defaults do start.
- [ ] `npm run check` verde.

## Cenários de teste

- Feliz: pasta com `scenario.yaml` + `world.md` + `starts/default.yaml` +
  `characters/chloe.yaml` → `LoadedScenario` com `id` da pasta,
  `starts["default"].id == "default"`, `characters["chloe"].mind.feeling`
  preenchido; `GET /api/scenarios` lista esse cenário.
- Feliz: dois starts (`default.yaml`, `rota-vilao.yaml`) → ambos no dicionário;
  `scenario.start()` devolve o de `default_start`.
- Borda: `start.characters = None` → todos os personagens da pasta entram em
  cena; lista explícita com id inexistente levanta `ScenarioError`.
- Borda: pasta `scenarios/README.md` (arquivo, não pasta) e pasta sem
  `scenario.yaml` → ignoradas sem erro.
- Borda: acento em `world.md` lido em utf-8 sem mojibake.
- Falha: `characters/chloe.yaml` com chave `personalidade` (typo) →
  `ScenarioError` com o caminho do arquivo no texto.
- Falha: `world.md` ausente → `ScenarioError`; `load_scenario("nao-existe")` →
  `ScenarioError`.
- Falha: uma pasta inválida entre duas válidas → `GET /api/scenarios` devolve
  200 com as duas válidas.

## Rollout e kill switch

N/A — rota nova de leitura, sem efeito colateral e sem consumidor em produção
antes do TCK-009. Reverter é remover o arquivo e a rota.

## Observabilidade

Eventos: `scenario_invalid` (`path`, `error`) via `app.observability.emit`,
emitido só por `list_scenarios()`.
Métrica de sucesso: `GET /api/scenarios` devolve o cenário exemplo do TCK-002
sem nenhum `scenario_invalid` no log.

## i18n

N/A — a rota devolve dados do cenário (que carrega seu próprio `locale`); não há
string de UI neste ticket. Mensagem de `ScenarioError` é log/erro técnico, em
inglês, como o resto do código.
