---
id: TCK-019
title: Confinar o loader de cenário à raiz e validar HUD e default_start no load
status: ready
points: 3
blockedBy: []
files:
  - backend/app/scenario.py
  - backend/app/hud.py
  - backend/tests/test_scenario.py
migration: false
ui: false
risk: low
---

## Problema

`load_scenario` (`backend/app/scenario.py:181`) monta o caminho com
`scenarios_dir() / scenario_id` sem nenhuma checagem do `scenario_id`. O id vem
de HTTP: `CreateSessionRequest.scenario_id` (`backend/app/main.py:38`, corpo do
`POST /api/sessions`) chega direto em `create_session`
(`backend/app/sessions.py:137`). Um id como `../../../etc` sai da raiz de
cenários; com `pathlib`, `raiz / "../.."` resolve para fora sem erro. O alcance
é ler `scenario.yaml`, `world.md`, `starts/` e `characters/` de um diretório
arbitrário do disco do jogador e devolver o conteúdo no prompt ou no corpo de
erro. O motor é local, mas é um servidor HTTP escutando em `:8000`: um id
malicioso não precisa de atacante remoto, basta uma página aberta no navegador
fazendo `fetch` para `127.0.0.1`.

Dois defeitos de validação no mesmo módulo:

1. **`HudState` sem validadores.** `HudDefaults` (`backend/app/scenario.py:43`)
   valida `time` contra `TIME_PATTERN` (`:12`) e `weather` contra
   `WEATHER_CODES`, mas `HudState` (`backend/app/hud.py:15`) — que é o modelo
   **persistido** na coluna `hud`, devolvido pela API e consumido por `advance`
   (`backend/app/hud.py:31`) — aceita qualquer string. `advance` faz
   `hud.time.split(":")` e `int(...)`: um `time` inválido no banco derruba o
   turno com `ValueError` sem contexto nenhum.
2. **`default_start` inválido só falha em runtime.** `LoadedScenario.start()`
   (`backend/app/scenario.py:98`) levanta `ScenarioError` quando
   `meta.default_start` não existe — mas isso só acontece na hora de **criar
   sessão**, não no load. Um cenário com `default_start: rota-vilao` e sem
   `starts/rota-vilao.yaml` aparece na listagem `GET /api/scenarios` como se
   estivesse são, e só quebra quando o jogador clica.

## Escopo

Dentro:
- Confinamento de `scenario_id` à raiz de cenários em `load_scenario`.
- `validate_time` / `validate_weather` e `TIME_PATTERN` em
  `backend/app/hud.py`, aplicados em `HudState` e reusados por `HudDefaults`.
- Validação de `meta.default_start` dentro de `load_scenario`.
- Testes em `backend/tests/test_scenario.py`.

Fora (explícito):
- Robustez da **listagem**: glob de `*.yml`, stem duplicado, `list_scenarios`
  resiliente a exceção não-`ScenarioError`, e resumo de `ValidationError` em uma
  linha. Tudo isso é o **TCK-025**, que consome a `ScenarioError` deste ticket.
- Hermeticidade de `backend/tests/test_example_scenario.py`: TCK-025.
- Cache de cenário carregado entre requisições: a redundância de load do turno é
  do TCK-018.
- Validar semântica de conteúdo (tamanho de `world.md`, número de sugestões):
  gate do cenário exemplo, não do loader.
- Migrar ou normalizar valores de `hud` já gravados no banco: nenhum valor
  inválido pode existir hoje, porque toda escrita passa por `hud_from_start`
  (`backend/app/hud.py:22`) sobre um `HudDefaults` já validado, e `advance` só
  produz `HH:MM` válido. Sem migração.
- Mudar `WEATHER_CODES` ou acrescentar clima novo.

### Testes existentes que este ticket invalida

Grep em `backend/tests/`:

- `test_hud_invalid_time_raises` (`backend/tests/test_scenario.py:209`) e
  `test_hud_invalid_weather_raises` (`:221`) exercitam `HudDefaults` via
  `load_scenario`. Continuam válidos sem adaptação: os validadores mudam de
  arquivo, não de efeito nem de mensagem.
- `test_start_characters_unknown_id_raises` (`:109`) afere `"ghost" in
  exc.reason`, sobre um `reason` construído à mão
  (`backend/app/scenario.py:196`). Válido sem adaptação.
- `test_load_scenario_two_starts_and_default` (`:87`),
  `test_start_characters_none_means_all` (`:101`),
  `test_hud_from_start_defaults` (`:196`) e todos os demais fixtures de
  `test_scenario.py` escrevem `starts/default.yaml`, e nenhum `scenario.yaml`
  de fixture define `default_start` (`SCENARIO_YAML`, `:43`), então o default
  implícito `"default"` existe em todos. A validação nova passa em todos, sem
  adaptação.
- `backend/tests/test_example_scenario.py::test_example_scenario_start_returns_default_without_argument`
  (`:20`) prova que `scenarios/exemplo-escola/` tem `starts/default.yaml`: o
  único cenário real do repo passa na validação nova.
- **Quatro construções diretas de `HudState`** existem na suíte:
  `backend/tests/test_prompt.py:83` (`time="09:30"`, `weather="cloudy"`),
  `backend/tests/test_prompt.py:193` (`time="08:00"`, `weather="clear"`),
  `backend/tests/test_turn.py:331` (`time="07:50"`, `weather="clear"`) e
  `backend/tests/test_turn.py:340` (`time="23:59"`, `weather="clear"`). Todos os
  valores estão dentro de `TIME_PATTERN` e de `WEATHER_CODES`: os quatro
  continuam verdes com os validadores ligados, e **nenhum dos dois arquivos é
  editado por este ticket** — por isso não estão em `files`.
- `backend/tests/test_compact.py:447`
  (`test_init_db_migrates_old_schema_without_compact_column`) insere um `hud`
  literal `"{}"` no banco (`:476`), mas o teste só chama `get_compact`, que lê a
  coluna `compact` (`backend/app/sessions.py:307`) e nunca constrói `HudState`.
  Continua válido sem adaptação.

## Comportamento esperado

Do ponto de vista do chamador da API:

- `POST /api/sessions {"scenarioId": "../../etc"}` → 404 `{"detail": "scenario
  not found"}`, e nenhum arquivo fora de `scenarios/` é lido.
- Um cenário com `default_start` apontando para um start inexistente falha no
  `load_scenario`, e não na hora do clique.
- Uma sessão com `hud` inválido no banco falha com erro de validação nomeando o
  campo, em vez de `ValueError` no meio do `advance`.

## Detalhes técnicos

- Confinamento, nesta ordem (barato antes de caro):
  1. rejeita id vazio, id que começa com `.`, ou que contenha `/`, `\` ou `\0`;
  2. resolve `(scenarios_dir() / scenario_id).resolve()` e exige que
     `scenarios_dir().resolve()` esteja em `.parents` do resultado.
  Falha levanta `ScenarioError(scenario_path, "scenario id outside the
  scenarios root")`. `create_session` já converte `ScenarioError` em
  `ScenarioNotFound` → 404 (`backend/app/sessions.py:136-139`), então a rota não
  muda. **Não** use `os.path.commonpath` com strings: em Windows a comparação de
  drive letter e de caixa morde; `Path.resolve()` + `parents` é o padrão.
- `validate_time(value: str) -> str` e `validate_weather(value: str) -> str`
  vivem em `backend/app/hud.py` (onde `WEATHER_CODES` já está, `:10`) e são
  usadas por `field_validator` tanto em `HudState` quanto em `HudDefaults`.
  `TIME_PATTERN` muda de `backend/app/scenario.py:12` para
  `backend/app/hud.py`; grep confirma que ninguém fora de `scenario.py` a
  importa. Compile o regex uma vez no módulo: hoje `HudDefaults.validate_time`
  faz `import re` **dentro** do validador (`backend/app/scenario.py:53`), a cada
  campo validado.
  **Armadilha de import**: `backend/app/scenario.py` já importa de
  `backend/app/hud.py` (`:9`), e `hud.py` importa `StartConfig` só sob
  `TYPE_CHECKING` (`:7`). Mantenha assim — mover as funções para `hud.py`
  preserva a direção da dependência e não cria ciclo.
- `default_start`: depois de `_load_starts`, `if meta.default_start not in
  starts: raise ScenarioError(meta_path, f"default_start '{meta.default_start}'
  not found; known starts: {sorted(starts)}")`.

## Contrato público

```python
# backend/app/hud.py
TIME_PATTERN: str                       # movido de scenario.py
WEATHER_CODES: tuple[str, ...]          # inalterado

def validate_time(value: str) -> str: ...     # levanta ValueError
def validate_weather(value: str) -> str: ...  # levanta ValueError

class HudState(BaseModel):
    turn: int = 0
    location: str
    time: str        # validado contra TIME_PATTERN
    weather: str     # validado contra WEATHER_CODES
```

```python
# backend/app/scenario.py
def load_scenario(scenario_id: str) -> LoadedScenario: ...
# assinatura inalterada; passa a levantar ScenarioError para id fora da raiz
# e para default_start inexistente
```

**Consumido pelo TCK-025**, que estende `ScenarioError` e a resiliência de
`list_scenarios` em cima deste comportamento.

## Acceptance criteria

- [ ] `load_scenario("../..")`, `load_scenario("a/b")`, `load_scenario("")` e
      `load_scenario(".oculto")` levantam `ScenarioError` sem ler nenhum arquivo
      fora da raiz.
- [ ] `POST /api/sessions` com `scenarioId` de travessia responde 404.
- [ ] `HudState(location="x", time="99:99", weather="clear")` levanta
      `ValidationError`; `HudState(location="x", time="08:00",
      weather="chuvoso")` também.
- [ ] `HudState` aceita `"00:00"` e `"23:59"` e recusa `"24:00"` e `"8:00"`.
- [ ] Cenário com `default_start` inexistente levanta `ScenarioError` no
      `load_scenario`, com a lista de starts conhecidos no `reason`.
- [ ] `TIME_PATTERN` não é mais importado de `backend/app/scenario.py` e não há
      `import re` dentro de nenhum validador.
- [ ] `npm run check` verde.

## Cenários de teste

- Feliz: cenário válido continua carregando com os mesmos ids de start e de
  personagem (regressão do caminho normal).
- Borda: `scenario_id` com separador (`"a/b"`, `"a\\b"`), com `..`, começando
  com ponto, e vazio → `ScenarioError`, um caso por id.
- Borda: link simbólico dentro da raiz apontando para fora — se o SO permitir
  criar (`pytest.mark.skipif` quando não permitir), `resolve()` o denuncia e o
  load falha.
- Borda: `default_start: rota-vilao` com apenas `starts/default.yaml` →
  `ScenarioError` cujo `reason` cita `rota-vilao` e `default`.
- Borda: `default_start` explícito e **existente** → carrega normalmente e
  `scenario.start().id` é o declarado.
- Borda: `HudState` nos limites de horário (`00:00`, `23:59`, `24:00`, `8:00`) e
  com cada código de `WEATHER_CODES`.
- Falha: `hud_from_start` sobre um `HudDefaults` válido continua produzindo um
  `HudState` válido (prova de que os dois validadores concordam).

## Rollout e kill switch

N/A. Não há flag: o confinamento de path e a validação de cenário não podem ser
desligados sem reabrir exatamente o problema que o ticket fecha. A única
mudança que poderia reprovar conteúdo existente (`default_start`) foi verificada
contra o único cenário do repositório, `scenarios/exemplo-escola/`, que passa.
Rollback é `git revert` do PR.

## Observabilidade

Eventos: `scenario_invalid` (`backend/app/scenario.py:224`) — já existente, e
passa a ser emitido também para cenário com `default_start` quebrado, porque a
falha vira `ScenarioError` durante `list_scenarios`. Nenhum evento novo.
Métrica de sucesso: `GET /api/scenarios` continua listando
`exemplo-escola` e o log não ganha nenhuma linha `scenario_invalid` nova numa
instalação sã.

## i18n

N/A. As mensagens de `ScenarioError` são log e detalhe de API para o
desenvolvedor, não texto de jogador; a UI já traduz os erros de carregamento com
`sessions.new.scenariosError` e a família `error.*` em
`frontend/src/strings.ts`. Nenhuma chave nova.
