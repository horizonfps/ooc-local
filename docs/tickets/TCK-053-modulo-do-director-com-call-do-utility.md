---
id: TCK-053
title: Criar o módulo do director com o call do utility e o parser da proposta
status: done
points: 3
blockedBy: [TCK-050]
files:
  - backend/app/director.py
  - backend/tests/test_director.py
migration: false
ui: false
risk: medium
---

## Problema

O elenco em cena já é estado de sessão e já tem juiz determinístico (TCK-050),
mas ninguém propõe elenco novo. Falta a peça que fala com o LLM: montar um
prompt curto para o papel `utility` com o elenco do cenário, quem está em cena, o
HUD, a janela recente e a ação do jogador, e transformar a resposta — texto livre
de modelo local, muitas vezes embrulhado em cerca de código — numa lista de ids
ou num motivo de rejeição.

Este ticket entrega só essa peça, isolada e testável sem servidor. A fiação no
fluxo do turno é o TCK-055, que depende deste.

## Escopo

Dentro:
- `backend/app/director.py` novo: `DIRECTOR_OPTIONS`, constantes da janela,
  `_PROMPT_TEMPLATES` nos dois locales, montagem do corpo do prompt,
  `DirectorError`, o call ao papel `utility` e o parser tolerante que devolve
  `(ids, None)` ou `(None, reason)`.
- `backend/tests/test_director.py`: testes **de unidade**, sem `TestClient` e sem
  banco — provider monkeypatchado e chamadas diretas às funções do módulo.

Fora (explícito):
- `backend/app/turn.py`, telemetria `director_*`, flag `director`, persistência
  do evento `cast` e `cast` no payload do SSE: tudo TCK-055.
- Reimplementar o juiz. `validate_cast_ids` vem de `backend/app/cast.py`
  (TCK-050) e é chamado daqui; este módulo só acrescenta o motivo
  `invalid_json`, que é do parsing e não da regra de elenco.
- Ler ou escrever qualquer coisa no event store. `director.py` não importa
  `app.sessions` — é módulo de I/O de rede e nada mais.
- `backend/app/prompt.py`: o prompt do narrador não é assunto deste ticket.

## Comportamento esperado

Do ponto de vista do chamador (o TCK-055): passa cenário, HUD, ids em cena,
mensagem do jogador, janela recente e config; recebe de volta ou a lista de ids
válida e saneada, ou `None` com um motivo publicável em telemetria. Falha de
provider, timeout e papel `utility` ausente na config viram `DirectorError`, que
o chamador trata; nada aqui levanta exceção crua nem escreve log.

## Detalhes técnicos

Espelhe `backend/app/compact.py`, que já é o precedente de call do papel
`utility` no repo (opções próprias, templates por locale, exceção própria,
`provider.complete` sobre `stream_chat`).

```python
DIRECTOR_OPTIONS = GenerationOptions(max_tokens=120, temperature=0.1, timeout_s=45.0)
DIRECTOR_WINDOW_TURNS = 3
DIRECTOR_EXCERPT_CHARS = 300
DIRECTOR_RAW_LOG_CHARS = 200

class DirectorError(Exception): ...

def build_director_messages(
    scenario: LoadedScenario,
    hud: HudState,
    current_ids: list[str],
    message: str,
    window: list[ChatMessage],
) -> list[ChatMessage]

def parse_scene(scenario: LoadedScenario, raw: str) -> tuple[list[str] | None, str | None]

async def decide_scene(
    scenario: LoadedScenario,
    hud: HudState,
    current_ids: list[str],
    message: str,
    window: list[ChatMessage],
    config: Config,
) -> tuple[list[str] | None, str | None, str]
```

- Locale sai de `scenario.meta.locale`, como em `compact_block`
  (`compact.py:100`); locale desconhecido cai em `pt-br`, mesmo fallback do
  `_build_prompt` de lá.
- `config.models["utility"]` ausente → `DirectorError("no utility role")`, em vez
  de deixar `KeyError` escapar. Não é hipótese: a config de teste de
  `backend/tests/test_turn.py:56` declara só o papel `narrator`.
- Provider:
  `OpenAICompatProvider(config.providers[role.provider], DIRECTOR_OPTIONS)` e
  `await provider.complete(...)`. Qualquer exceção do provider vira
  `DirectorError`. O `timeout_s=45.0` é o que impede o default de 120s do
  `GenerationOptions` de virar dois minutos de espera antes do primeiro delta do
  narrador.
- Corpo do prompt (mensagem de usuário), nesta ordem:
  1. elenco completo compacto, uma linha por personagem:
     `id | name | role | tier N`, com o tier omitido quando `power_tier is None`;
  2. `EM CENA AGORA: chloe, mika`, ou o rótulo de vazio;
  3. HUD em uma linha (turno, local, hora);
  4. janela: até `DIRECTOR_WINDOW_TURNS` pares finais recebidos em `window`, cada
     conteúdo cortado em `DIRECTOR_EXCERPT_CHARS`;
  5. ação do jogador por último.
- Sistema: instrução curta, no locale do cenário, mandando responder **só** o
  objeto JSON `{"scene": ["id", ...]}` com ids da lista dada, no máximo
  `MAX_CAST_IN_SCENE` (importado de `app.cast`), mantendo quem continua presente
  e incluindo quem a ação do jogador acabou de trazer para perto. Sem prosa, sem
  nome — id.
- `parse_scene`: pegue do primeiro `{` até o último `}` (modelos locais grudam
  cerca de código, comentário ou prosa em volta), `json.loads`, e passe
  `data.get("scene")` para `validate_cast_ids`, devolvendo o resultado dele tal e
  qual. Ausência de `{`, `json.JSONDecodeError` ou raiz que não é objeto →
  `(None, "invalid_json")`. Nada de sanear ids aqui: o juiz é um só.
- `decide_scene` = `build_director_messages` + `complete` + `parse_scene`, e
  devolve a 3-tupla `(ids, reason, raw)` onde `raw` é a resposta crua do
  provider, sem corte (o corte em `DIRECTOR_RAW_LOG_CHARS` é do chamador, no
  TCK-055). Resposta vazia ou só espaço → `(None, "invalid_json", raw)`.
  `parse_scene` mantém a 2-tupla: quem chama já tem o `raw` na mão.
- Comentários em inglês e mínimos, como o resto do backend.

## Contrato público

```python
# backend/app/director.py
DIRECTOR_OPTIONS: GenerationOptions
DIRECTOR_WINDOW_TURNS: int
DIRECTOR_EXCERPT_CHARS: int
DIRECTOR_RAW_LOG_CHARS: int
class DirectorError(Exception): ...
def build_director_messages(scenario, hud, current_ids, message, window) -> list[ChatMessage]
def parse_scene(scenario, raw: str) -> tuple[list[str] | None, str | None]
async def decide_scene(scenario, hud, current_ids, message, window, config) -> tuple[list[str] | None, str | None, str]
    # reasons: "invalid_json" | os de validate_cast_ids (TCK-050)
    # terceiro elemento: resposta crua do provider, para o chamador logar
```

Consumido pelo TCK-055, que declara este ticket em `blockedBy`.

## Acceptance criteria

- [ ] `decide_scene` com o utility devolvendo `{"scene": ["chloe"]}` retorna
      `(["chloe"], None, raw)`, com `raw` igual à resposta crua do provider.
- [ ] Resposta embrulhada em cerca de código (```` ```json {...} ``` ````) ou com
      prosa antes e depois do objeto é aceita.
- [ ] Em `parse_scene`, resposta sem `{`, com JSON quebrado, com raiz que não é
      objeto, ou vazia retorna `(None, "invalid_json")`; em `decide_scene`, a
      mesma entrada retorna `(None, "invalid_json", raw)`.
- [ ] `{"scene": ["fantasma"]}` retorna `(None, "unknown_ids")` e
      `{"scene": [7 ids válidos]}` retorna `(None, "over_cap")` — motivos vindos
      de `validate_cast_ids`, sem lógica duplicada em `director.py`.
- [ ] `{"scene": []}` retorna `([], None)`.
- [ ] Config sem o papel `utility` levanta `DirectorError("no utility role")` sem
      tocar no provider.
- [ ] Exceção do provider vira `DirectorError`.
- [ ] O prompt montado contém id, nome e papel de **todos** os personagens do
      cenário, marca os que estão em cena, traz o HUD e termina com a ação do
      jogador; a janela entra cortada em `DIRECTOR_EXCERPT_CHARS` por mensagem e
      limitada a `DIRECTOR_WINDOW_TURNS` pares.
- [ ] Cenário `locale: en` produz prompt sem nenhuma palavra dos templates
      pt-br, e vice-versa.
- [ ] `DIRECTOR_OPTIONS.timeout_s == 45.0` e `max_tokens == 120`.
- [ ] `npm run check:api` verde.

## Cenários de teste

Suíte existente que muda de preparação: **nenhuma**. O módulo é novo e ninguém o
importa até o TCK-055; nenhum teste atual passa por ele. `backend/tests/test_turn.py`
e `backend/tests/test_compact.py` seguem intocados neste ticket.

Cenários novos (`backend/tests/test_director.py`, unidade: cenário escrito em
`tmp_path` com `monkeypatch.setattr("app.scenario.scenarios_dir", ...)` como em
`backend/tests/test_prompt.py:92`, `OpenAICompatProvider.stream_chat`
monkeypatchado, `asyncio.run` para as corrotinas — mesmo estilo dos testes de
unidade de `backend/tests/test_compact.py:270`):
- Feliz: `decide_scene` com resposta `{"scene": ["chloe", "renan"]}` devolve os
  dois ids na ordem e o `raw` idêntico à resposta do provider.
- Feliz: resposta com cerca de código e comentário em volta é aceita.
- Borda: `{"scene": []}` → `([], None)`.
- Borda: `"a Chloe e o Renan entram"` → `(None, "invalid_json")`; `""` →
  `(None, "invalid_json")`; `[{"scene": []}]` (raiz lista) →
  `(None, "invalid_json")`.
- Borda: `{"scene": ["fantasma"]}` → `(None, "unknown_ids")`; sete ids válidos →
  `(None, "over_cap")`; `{"scene": "chloe"}` → `(None, "not_a_list")`.
- Borda: `build_director_messages` com janela de 10 pares usa só os
  `DIRECTOR_WINDOW_TURNS` últimos, e uma mensagem de 5000 caracteres aparece
  cortada em `DIRECTOR_EXCERPT_CHARS`.
- Borda: personagem sem `power_tier` não gera a palavra `None` na linha do
  elenco.
- Borda: cenário `locale: en` → prompt sem `EM CENA AGORA`; cenário `pt-br` →
  prompt sem `IN SCENE NOW`.
- Falha: config sem papel `utility` levanta `DirectorError`; provider que levanta
  `RuntimeError` também.

## Rollout e kill switch

N/A — `risk: medium`. O módulo não é chamado por ninguém enquanto o TCK-055 não
entra, então mergear este ticket não muda comportamento de jogo nenhum. O kill
switch da feature (flag `director`) é definido no TCK-055, que é quem liga o
módulo ao turno.

## Observabilidade

Eventos: nenhum. `director.py` não emite telemetria — devolve o motivo e deixa o
chamador publicar, para que exista um único ponto de `emit` por turno. A
constante `DIRECTOR_RAW_LOG_CHARS` existe para o TCK-055 cortar o `raw` que
`decide_scene` devolve antes de logar.
Métrica de sucesso: nos testes de unidade, as 6 formas de resposta malformada que
modelos locais realmente produzem (cerca de código, prosa em volta, JSON
quebrado, raiz lista, resposta vazia, ids inventados) caem em motivo conhecido, e
nenhuma delas levanta exceção.

## i18n

O prompt do director nasce nos dois locales, em `_PROMPT_TEMPLATES` dentro de
`backend/app/director.py`, no mesmo formato de `backend/app/compact.py:21`
(`system` mais rótulos do corpo), escolhido por `scenario.meta.locale`:

| chave | pt-br | en |
|---|---|---|
| `system` | instrução de responder só `{"scene": [...]}` com ids da lista dada, no máximo N, mantendo quem segue presente | idem em inglês |
| `cast_label` | `ELENCO DO CENÁRIO` | `SCENARIO CAST` |
| `in_scene_label` | `EM CENA AGORA` | `IN SCENE NOW` |
| `none_label` | `ninguém` | `no one` |
| `hud_label` | `ESTADO` | `STATE` |
| `window_label` | `ÚLTIMOS TURNOS` | `RECENT TURNS` |
| `action_label` | `AÇÃO DO JOGADOR` | `PLAYER ACTION` |

Nenhuma chave de `frontend/src/strings.ts`.
