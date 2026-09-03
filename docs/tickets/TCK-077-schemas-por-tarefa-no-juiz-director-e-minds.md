---
id: TCK-077
title: Declarar o schema de resposta do juiz, do director e do minds e registrar structured na telemetria
status: ready
points: 3
blockedBy: [TCK-076]
files:
  - backend/app/judge.py
  - backend/app/director.py
  - backend/app/minds.py
  - backend/app/turn.py
  - backend/tests/test_judge.py
  - backend/tests/test_director.py
  - backend/tests/test_minds.py
  - backend/tests/test_turn_hud_judge.py
  - backend/tests/test_turn_director.py
migration: false
ui: false
risk: low
---

## Problema

O TCK-076 abriu o caminho no provider (`GenerationOptions.json_schema` +
`ProviderConfig.structured_output`), e ninguém o usa. Enquanto os três módulos do
utility não declararem o schema da própria resposta, a saída estruturada é código
morto e o formato continua sendo pedido só por texto no system prompt
(`judge.py:26-31`, `director.py:20-24`, `minds.py:26-33`) — o pedido que o
verde da Fase 3 provou que o Cydonia ignora.

Falta também a telemetria que responde a pergunta da fase: "quanto a saída
estruturada reduziu a rejeição de formato?". Hoje `judge_applied`
(`turn.py:509-522`), `director_applied` (`turn.py:386-396`) e `minds_applied`
(`turn.py:568-579`) não dizem se a chamada foi restringida por schema, e
`judge_rejected`/`director_rejected`/`minds_rejected`/`*_failed` sequer registram
o modelo — o que impede comparar dois modelos no mesmo log, que é exatamente o
que o relatório do TCK-086 precisa fazer.

## Escopo

Dentro:
- `backend/app/judge.py`: modelos Pydantic `JudgementNewStat` e
  `JudgementResponse`; `JUDGE_OPTIONS` ganha `json_schema`/`schema_name`;
  constante irmã `JUDGE_OPTIONS_DYNAMIC` com o campo `new`; `judge_turn` escolhe
  entre as duas por `scenario.meta.allow_dynamic_stats`.
- `backend/app/director.py`: modelo `SceneResponse`; `DIRECTOR_OPTIONS` ganha o
  schema.
- `backend/app/minds.py`: modelos `MindEntry` e `MindsResponse`; `MINDS_OPTIONS`
  ganha o schema.
- `backend/app/turn.py`: helpers `_utility_model(config)` e
  `_utility_structured(config)`; propriedade `structured` nos seis eventos
  `*_applied`/`*_rejected` do utility; propriedade `model` nos seis
  `*_rejected`/`*_failed`, que hoje não a têm.
- Cenários novos nos arquivos de teste já existentes dos três módulos.

Fora (explícito):
- `backend/app/llm/base.py`, `openai_compat.py` e `config.py`: vêm prontos do
  TCK-076 e **não** são editados aqui. Se o campo não tiver o nome do contrato
  daquele ticket, o defeito volta para lá; não crie adaptador local.
- **Restringir os ids do cenário dentro do schema.** Tentador (`stats` só aceitar
  ids declarados, `scene` só ids do elenco) e fora de escopo: exigiria montar um
  schema por cenário a cada turno, quebraria em cenário sem stat nenhum
  (`enum: []` é schema inválido) e duplicaria uma validação que o engine já faz e
  que continua sendo a autoridade (`unknown_id` em `apply_judgement:196`,
  `unknown_ids` em `validate_cast_ids` (`cast.py:45-57`), `not_in_scene` em
  `merge_minds` (`minds.py:190`)). O schema garante **forma**, o engine garante **conteúdo**.
- Os parsers tolerantes. `parse_judgement`, `parse_scene` e `parse_minds`
  (inclusive `_loads_object_per_line` e `_list_to_map`) ficam **intactos**: viram
  rede secundária para provider com `structured_output: none`, que é o default e
  o que roda no KoboldCpp de hoje. Nenhuma linha deles é apagada nesta fase.
- `backend/app/compact.py`: saída em prosa, sem schema, hoje e sempre.
- Ligar `structured_output` em algum lugar. Nenhum arquivo de config muda; quem
  imprime o trecho com `structured_output: json_schema` é o TCK-085.
- Remover a instrução de formato dos system prompts. Ela continua servindo o
  provider sem schema, e o dataset do TCK-079 exporta o prompt como ele é.

## Comportamento esperado

Do ponto de vista do jogador: nada muda enquanto o provider do papel `utility`
estiver com `structured_output: none` (default). Apontando o papel para um
llama-server com `structured_output: json_schema`, as três chamadas do utility
passam a vir com JSON válido por construção, e os motivos de recusa
`invalid_json` desaparecem do log.

Do ponto de vista de quem lê a telemetria: todo evento `*_applied` e
`*_rejected` do utility passa a dizer se a chamada foi restringida (`structured`)
e com qual modelo (`model`), permitindo comparar Cydonia sem schema, Cydonia com
schema e modelo próprio no mesmo arquivo de log.

## Detalhes técnicos

### Schemas

`judge.py` já importa `BaseModel` (`judge.py:7`) e tem `StatChange`/`StatRejection`
como precedente de modelo local. Acrescente, perto deles:

```python
class JudgementNewStat(BaseModel):
    id: str
    name: str
    value: int
    max: int
    min: int = 0


class JudgementResponse(BaseModel):
    stats: dict[str, int] = {}


class JudgementDynamicResponse(JudgementResponse):
    new: list[JudgementNewStat] = []
```

```python
JUDGE_OPTIONS = GenerationOptions(
    max_tokens=200, temperature=0.1, timeout_s=45.0,
    json_schema=JudgementResponse.model_json_schema(), schema_name="judgement",
)
JUDGE_OPTIONS_DYNAMIC = GenerationOptions(
    max_tokens=200, temperature=0.1, timeout_s=45.0,
    json_schema=JudgementDynamicResponse.model_json_schema(), schema_name="judgement",
)
```

Em `judge_turn` (`judge.py:306`):

```python
options = JUDGE_OPTIONS_DYNAMIC if scenario.meta.allow_dynamic_stats else JUDGE_OPTIONS
provider = OpenAICompatProvider(config.providers[role.provider], options)
```

São **duas** constantes e não uma com `new` sempre presente porque o schema é o
convite: oferecer `new` a um cenário com `allow_dynamic_stats: false` faria o
modelo propor stat novo que `apply_judgement:219-221` recusa com
`dynamic_disabled` a cada turno — gasto de tokens e ruído de log. A ramificação
espelha a que já existe no prompt (`judge.py:112-114`).

`director.py` (não importa `BaseModel` hoje; acrescente o import):

```python
class SceneResponse(BaseModel):
    scene: list[str]

DIRECTOR_OPTIONS = GenerationOptions(
    max_tokens=120, temperature=0.1, timeout_s=45.0,
    json_schema=SceneResponse.model_json_schema(), schema_name="scene",
)
```

`minds.py` (já importa `BaseModel`, `minds.py:5`):

```python
class MindEntry(BaseModel):
    attitude: str
    emoji: str
    event: str


class MindsResponse(BaseModel):
    entries: dict[str, MindEntry] = {}
```

Atenção, armadilha: a resposta do minds **não** tem envelope — o formato aceito é
`{"<id>": {...}}` na raiz (`minds.py:26-33`, `merge_minds` em `minds.py:177`). Então o schema
passado nas options **não** é `MindsResponse.model_json_schema()` inteiro, e sim
o schema do mapa da raiz:

```python
MINDS_SCHEMA = {
    "type": "object",
    "additionalProperties": MindEntry.model_json_schema(),
}
MINDS_OPTIONS = GenerationOptions(
    max_tokens=300, temperature=0.2, timeout_s=45.0,
    json_schema=MINDS_SCHEMA, schema_name="minds",
)
```

`MindsResponse` existe só para dar nome ao formato num lugar só e ser reusada
pelo TCK-081 na rotulagem; se preferir, declare apenas `MindEntry` e
`MINDS_SCHEMA` e deixe `MindsResponse` de fora. O que **não** pode acontecer é o
schema exigir uma chave `entries` que o parser não espera.

`MindEntry.model_json_schema()` traz `$defs`/`title` quando há aninhamento; para
`MindEntry` (três `str`) não há aninhamento e o dict é auto-contido. Para
`JudgementDynamicResponse`, que referencia `JudgementNewStat`, o
`model_json_schema()` sai com `$defs` e `$ref` — formato legítimo de JSON Schema
e aceito pelo conversor do llama.cpp. Não achate à mão.

### Telemetria em `turn.py`

Dois helpers de módulo, acima de `run_turn`:

```python
def _utility_model(config: Config) -> str | None:
    role = config.models.get("utility")
    return role.model if role is not None else None


def _utility_structured(config: Config) -> bool:
    role = config.models.get("utility")
    if role is None:
        return False
    return config.providers[role.provider].structured_output == "json_schema"
```

Ambos toleram o papel ausente: os testes de `test_turn.py:67-73` rodam com uma
config **sem** papel `utility`, e os blocos de telemetria de falha rodam nesse
caminho (`JudgeError("no utility role")`). Um `config.models["utility"]` cru
dentro de um `except` levantaria `KeyError` e derrubaria o turno inteiro.

Trocas nos seis pontos de emissão:
- `director_applied` (`turn.py:386-396`): `model=config.models["utility"].model`
  vira `model=_utility_model(config)`; acrescenta
  `structured=_utility_structured(config)`.
- `director_rejected` (`turn.py:397-406`): acrescenta `model` e `structured`.
- `director_failed` (`turn.py:358-372`, dois blocos `except`): acrescenta `model`
  (sem `structured` — a chamada nem chegou a formatar resposta).
- `judge_applied` (`turn.py:509-522`) / `judge_rejected` (`turn.py:524-531`) /
  `judge_failed` (`turn.py:482-496`): idem.
- `minds_applied` (`turn.py:568-579`) / `minds_rejected` (`turn.py:580-588`) /
  `minds_failed` (`turn.py:539-554`): idem.

Nada mais de `turn.py` muda. Nenhum call novo, nenhuma ordem alterada, nenhum
evento novo de sessão.

### `additionalProperties` e `strict`

Achado do review do PR #76 (TCK-076): `Model.model_json_schema()` do Pydantic
**não** emite `additionalProperties: false` e deixa fora de `required` os campos
com default. Como o provider manda `strict: true` fixo, um servidor que valide
`strict` de verdade recusaria o schema. Decisão do coordenador (03/09/2026): os
modelos Pydantic de schema deste ticket usam `model_config =
ConfigDict(extra="forbid")`, que faz o Pydantic emitir
`additionalProperties: false`, e declaram todo campo sem default (o schema do
juiz e do director não têm campo opcional; o `MindEntry` tem os três
obrigatórios). O schema do minds tem `additionalProperties` igual ao schema de
`MindEntry` na raiz, e isso é intencional: é o único jeito de aceitar ids
dinâmicos como chave. Acceptance criteria adicional: cada schema gerado tem
`additionalProperties` igual a `false` em todo objeto de campos fixos, e
`required` igual à lista completa dos campos.

### Ressalva de porte

Estimativa: ~120 linhas de código (três modelos Pydantic de schema com
`model_json_schema()`, um bloco de options por módulo e a propriedade
`structured` em seis `emit`) e ~220 linhas de teste, total ~340, abaixo do alvo
de ~400. Decisão do coordenador (03/09/2026): telemetria fica neste ticket, e
não em um separado, porque `structured` é uma propriedade booleana em `emit`
já existentes e um ticket só para ela não teria consumidor próprio. Se o diff
passar de ~400, o corte é um só e já está decidido: os cenários "schema de cada
tarefa é JSON Schema válido e `strict`-compatível" viram um único
`pytest.mark.parametrize` sobre as três tarefas. Não corte os cenários de
`structured` nos `*_applied`/`*_rejected`: são a métrica da sub-fase 4.1.

## Contrato público

```python
# backend/app/judge.py
class JudgementNewStat(BaseModel): id: str; name: str; value: int; max: int; min: int = 0
class JudgementResponse(BaseModel): stats: dict[str, int] = {}
class JudgementDynamicResponse(JudgementResponse): new: list[JudgementNewStat] = []
JUDGE_OPTIONS: GenerationOptions          # schema sem "new"
JUDGE_OPTIONS_DYNAMIC: GenerationOptions  # schema com "new"

# backend/app/director.py
class SceneResponse(BaseModel): scene: list[str]
DIRECTOR_OPTIONS: GenerationOptions       # schema de SceneResponse

# backend/app/minds.py
class MindEntry(BaseModel): attitude: str; emoji: str; event: str
MINDS_SCHEMA: dict                        # objeto de raiz, additionalProperties = MindEntry
MINDS_OPTIONS: GenerationOptions          # schema = MINDS_SCHEMA
```

```
# telemetria (backend/app/turn.py)
judge_applied | judge_rejected | director_applied | director_rejected
  | minds_applied | minds_rejected   -> ganham `model: str | None` e `structured: bool`
judge_failed | director_failed | minds_failed -> ganham `model: str | None`
```

Consumidores nomeados: TCK-081 (`app.dataset label` reusa
`JUDGE_OPTIONS`/`DIRECTOR_OPTIONS`/`MINDS_OPTIONS` e os schemas para rodar o
professor com a mesma restrição) e TCK-086 (`app.telemetry report`, que agrupa
por `model` e separa as linhas por `structured`).

## Acceptance criteria

- [ ] `JUDGE_OPTIONS.json_schema["properties"]` tem `stats` e **não** tem `new`;
      `JUDGE_OPTIONS_DYNAMIC.json_schema` tem os dois.
- [ ] `judge_turn` com cenário `allow_dynamic_stats: false` constrói o provider
      com `JUDGE_OPTIONS`; com `true`, com `JUDGE_OPTIONS_DYNAMIC` (espionando
      `OpenAICompatProvider.__init__`, no molde de `test_judge.py:537-552`).
- [ ] `DIRECTOR_OPTIONS.json_schema` descreve `{"scene": [str]}` e
      `MINDS_OPTIONS.json_schema` é um objeto de raiz cujo
      `additionalProperties` tem as três chaves `attitude`, `emoji`, `event`.
- [ ] `MINDS_OPTIONS.json_schema` **não** tem a chave `entries` no topo.
- [ ] Com provider `structured_output: "json_schema"`, o payload da chamada do
      juiz traz `response_format.json_schema.name == "judgement"` (afere-se pelo
      `build_payload` do provider construído, sem rede).
- [ ] Com provider `structured_output: "none"`, o payload das três chamadas é
      idêntico ao de hoje.
- [ ] Turno completo com provider `structured_output: "json_schema"`:
      `judge_applied`, `director_applied` e `minds_applied` saem com
      `structured is True` e `model` preenchido.
- [ ] Turno completo com o default: os mesmos eventos saem com
      `structured is False`.
- [ ] `judge_rejected`, `director_rejected` e `minds_rejected` trazem `model` e
      `structured`; `*_failed` traz `model`.
- [ ] Turno com config **sem** papel `utility` (caso de `test_turn.py`) emite
      `judge_failed`/`minds_failed` com `model is None` e chega ao fim sem
      exceção.
- [ ] Os três parsers tolerantes continuam aceitando exatamente o que aceitavam:
      `npm run check` verde com **zero** asserção alterada em `test_judge.py`,
      `test_director.py` e `test_minds.py`.

## Cenários de teste

Suíte existente que muda de preparação: **nenhuma**. Verificado por Grep,
arquivo a arquivo:

- `backend/tests/test_judge.py:544-552`
  (`test_judge_turn_builds_provider_with_judge_options`) compara por
  **identidade**: `assert captured["options"] is JUDGE_OPTIONS`. O helper
  `_load` (`test_judge.py:96`) tem `allow_dynamic_stats=False` por default e esse
  teste o chama sem argumento, então a ramificação nova continua entregando
  `JUDGE_OPTIONS` e a asserção segue verde sem edição.
- `backend/tests/test_judge.py:594-597`
  (`test_judge_options_tokens_temperature_timeout`) afere só `max_tokens`,
  `temperature` e `timeout_s` — campos intocados.
- `backend/tests/test_director.py:357-359` e `:385`, e
  `backend/tests/test_minds.py:463` e `:507-509`: mesma forma, mesmas conclusões.
- `backend/tests/test_compact.py:206-258`: os testes de `build_payload` usam
  `COMPACT_OPTIONS` e providers sem `structured_output`; nada deste ticket os
  toca.
- Nenhum teste do repositório compara um payload de `emit` por igualdade de dict:
  todos indexam chave a chave (`test_turn_hud_judge.py:158-161`,
  `test_turn_director.py:173-180`). Propriedade nova em `emit` não quebra
  ninguém. Os dois arquivos entram em `files` só por causa dos **cenários novos**
  abaixo, não por adaptação.

Cenários novos:

`backend/tests/test_judge.py`:
- Feliz: cenário com `allow_dynamic_stats=True` → provider construído com
  `JUDGE_OPTIONS_DYNAMIC`.
- Borda: forma do schema das duas constantes (presença/ausência de `new`,
  `stats` como objeto de inteiros).
- Borda: provider com `structured_output="json_schema"` → `build_payload` do
  provider capturado traz `response_format` com `name == "judgement"`; com
  `"none"`, não traz.

`backend/tests/test_director.py` e `backend/tests/test_minds.py`:
- Borda: forma do schema (`scene` como lista de string; mapa de raiz com as três
  chaves e sem `entries`).
- Falha: com o schema declarado, uma resposta em prosa ainda é recusada pelo
  parser tolerante com `invalid_json` — prova de que a rede secundária continua
  no lugar quando o servidor não honra o schema.

`backend/tests/test_turn_hud_judge.py` (padrão do arquivo: `TestClient`, cenário
em `tmp_path`, `_route_by_model`, `emit` monkeypatchado):
- Feliz: provider do papel `utility` com `structured_output: "json_schema"` →
  `judge_applied` e `minds_applied` com `structured is True` e `model` correto.
- Borda: default `"none"` → os mesmos eventos com `structured is False`.
- Falha: utility devolvendo prosa → `judge_rejected` com `structured` e `model`
  preenchidos.
- Falha: config sem papel `utility` → `judge_failed`/`minds_failed` com
  `model is None`, turno completo, sem exceção.

`backend/tests/test_turn_director.py`:
- Feliz: `director_applied` com `structured` e `model`.
- Falha: `director_rejected` e `director_failed` com `model` preenchido.

## Rollout e kill switch

Sem flag nova. O interruptor é a config do provider do papel `utility`
(`structured_output: none | json_schema`, TCK-076): voltar para `none` devolve o
comportamento exato de hoje sem deploy. Os flags `hud_judge`, `director` e
`minds` (`Config.flag`, `config.py:43-45`) continuam desligando cada subsistema
inteiro, como no TCK-069.

`risk: low`: o caminho novo só existe para provider que optou por ele, os
parsers tolerantes seguem intactos e a telemetria só ganha propriedades.

## Observabilidade

Eventos (todos já existentes, via `emit` de `backend/app/observability.py`):
- `judge_applied`, `judge_rejected`, `director_applied`, `director_rejected`,
  `minds_applied`, `minds_rejected`: ganham `structured: bool` (a chamada saiu
  com `response_format`) e `model: str | None` onde ainda não havia.
- `judge_failed`, `director_failed`, `minds_failed`: ganham `model: str | None`.

Métrica de sucesso: numa sessão de 10 turnos contra um llama-server com
`structured_output: json_schema`, a soma de `judge_rejected + director_rejected +
minds_rejected` com `structured: true` é **zero**, contra a linha de base do
mesmo cenário com `structured: false`. É a mesma comparação que o relatório do
TCK-086 imprime.

## i18n

N/A. Nenhuma string de usuário. Os system prompts dos três módulos, que são
bilíngues, não são editados por este ticket.
