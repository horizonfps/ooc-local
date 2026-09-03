---
id: TCK-076
title: Aceitar JSON schema nas GenerationOptions e emitir response_format no provider
status: in_review
points: 2
blockedBy: []
files:
  - backend/app/llm/base.py
  - backend/app/llm/openai_compat.py
  - backend/app/config.py
  - backend/tests/test_structured_output.py
migration: false
ui: false
risk: low
---

## Problema

Os três módulos do utility mandam o formato de resposta por instrução de texto no
system prompt (`judge.py:26-31`, `director.py:20-24`, `minds.py:26-33`) e
esperam o modelo obedecer. Ele não obedece: o verde da Fase 3 registrou director
devolvendo prosa, juiz ecoando o exemplo do prompt e minds em três formatos
distintos de JSON. Por isso os três têm parser tolerante
(`parse_judgement:135-156`, `parse_scene:101-122`, `parse_minds:120-133` com
`_loads_object_per_line` e `_list_to_map`) e o engine clampa tudo.

Nada disso resolve o caso em que o modelo simplesmente não emite JSON. O único
jeito de eliminar a classe inteira de defeito é o servidor restringir a
amostragem ao schema. `OpenAICompatProvider.build_payload`
(`backend/app/llm/openai_compat.py:16-26`) hoje só sabe mandar `model`,
`messages`, `stream`, `max_tokens` e `temperature`; não existe caminho para
`response_format`.

Este ticket é só o **contrato do provider**. Ele não muda nenhum comportamento
observável sozinho: sem ninguém preencher o campo novo e sem ninguém ligar a
opção na config, o payload sai byte a byte igual ao de hoje.

## Escopo

Dentro:
- `backend/app/llm/base.py`: campo `json_schema: dict | None = None` e
  `schema_name: str = "response"` em `GenerationOptions`.
- `backend/app/llm/openai_compat.py`: `build_payload` acrescenta
  `response_format` quando **e só quando** as duas condições valem: a config do
  provider declara `structured_output: "json_schema"` e `options.json_schema`
  não é `None`.
- `backend/app/config.py`: `ProviderConfig` ganha
  `structured_output: Literal["json_schema", "none"] = "none"`.
- `backend/tests/test_structured_output.py` novo, com os cenários abaixo.

Fora (explícito):
- `backend/app/judge.py`, `director.py`, `minds.py`: quem declara os schemas por
  tarefa e passa `json_schema` nas options é o TCK-077. Este ticket não importa
  nenhum dos três nem cria schema de tarefa nenhum.
- `backend/app/compact.py`: a saída do compact é prosa. `COMPACT_OPTIONS`
  (`compact.py:19`) não ganha schema, nem agora nem depois.
- GBNF / `grammar`. O plano cita GBNF como alternativa; esta fase implementa só
  `response_format`, que é o caminho openai-compatible e o que o llama-server do
  TCK-085 vai servir.
- Retry, fallback ou detecção automática de suporte do servidor. Se o servidor
  recusar o payload, o call falha como qualquer outro erro de provider e o
  chamador já trata (`JudgeError`/`DirectorError`/`MindsError`). Escolher entre
  `json_schema` e `none` é decisão de quem escreve o `config.yaml`.
- `DEFAULT_CONFIG` (`config.py:10-20`) **não** muda. O default de fábrica aponta
  para o KoboldCpp em `127.0.0.1:5001`, que não aceita `response_format`; ligar
  isso por padrão quebraria a instalação atual do usuário.

## Comportamento esperado

Do ponto de vista do chamador do provider: `GenerationOptions` passa a carregar
um JSON schema opcional. Se o provider configurado declara saber restringir
amostragem por schema, o payload da chamada leva o `response_format` no formato
OpenAI e o servidor devolve JSON válido por construção. Se o provider não
declara, o schema é silenciosamente ignorado e o comportamento é o de hoje — a
mesma `GenerationOptions` funciona nos dois servidores sem `if` no chamador.

Do ponto de vista do usuário: nada muda até ele escrever `structured_output`
no `~/.ooc-local/config.yaml`.

## Detalhes técnicos

### `backend/app/llm/base.py`

```python
class GenerationOptions(BaseModel):
    max_tokens: int | None = None
    temperature: float | None = None
    timeout_s: float = 120.0
    json_schema: dict | None = None
    schema_name: str = "response"
```

`json_schema` é `dict` cru, não um `type[BaseModel]`: `base.py` não pode importar
os modelos de tarefa (viraria import circular com `judge.py`, que já importa
`llm.base`), e quem chama passa `Model.model_json_schema()`. `schema_name` vira o
campo `name` exigido pelo formato OpenAI; default genérico porque o nome só
importa para o log do servidor.

Pydantic com `dict` sem parametrizar é aceito e não valida o conteúdo. É o que se
quer: o schema é opaco para o provider.

### `backend/app/config.py`

```python
class ProviderConfig(BaseModel):
    base_url: str
    api_key_env: str = "OOC_LOCAL_API_KEY"
    structured_output: Literal["json_schema", "none"] = "none"
```

`Literal` já é importável (`from typing import Literal`; hoje `config.py` não o
importa — acrescente o import). Default `"none"` porque o servidor atual do
projeto é o KoboldCpp em `:5001`, que não implementa `response_format`; o
llama-server que o TCK-085 sobe implementa, e o trecho de config que aquele
ticket imprime já sai com `structured_output: json_schema`.

### `backend/app/llm/openai_compat.py`

Em `build_payload`, depois do bloco de `temperature` (`openai_compat.py:24-25`):

```python
if self.structured_output == "json_schema" and self.options.json_schema is not None:
    payload["response_format"] = {
        "type": "json_schema",
        "json_schema": {
            "name": self.options.schema_name,
            "schema": self.options.json_schema,
            "strict": True,
        },
    }
```

`__init__` (`openai_compat.py:11-14`) guarda `self.structured_output =
provider.structured_output`, no mesmo padrão de `self.base_url` e `self.api_key`:
o provider já copia o que precisa do `ProviderConfig` em vez de guardar o objeto.

Formato: é a forma aninhada da OpenAI, que o llama-server aceita no
`/v1/chat/completions` junto com a forma achatada própria dele. Fonte:
[llama.cpp server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).
Armadilha conhecida, registrada para quem for depurar em runtime (não afeta este
ticket, que não fala com servidor real): builds de llama.cpp do começo de 2025
respondiam "either json_schema or grammar can be specified, but not both" nesse
endpoint ([issue #11847](https://github.com/ggml-org/llama.cpp/issues/11847),
[issue #11988](https://github.com/ggml-org/llama.cpp/issues/11988)); o remédio é
subir o build.

`strict: True` fixo. Schema parcialmente respeitado não serve para nada aqui: o
ponto do ticket é que formato inválido deixe de existir.

## Contrato público

```python
# backend/app/llm/base.py
class GenerationOptions(BaseModel):
    max_tokens: int | None = None
    temperature: float | None = None
    timeout_s: float = 120.0
    json_schema: dict | None = None      # Model.model_json_schema(), ou None
    schema_name: str = "response"        # vira json_schema.name no payload

# backend/app/config.py
class ProviderConfig(BaseModel):
    base_url: str
    api_key_env: str = "OOC_LOCAL_API_KEY"
    structured_output: Literal["json_schema", "none"] = "none"

# backend/app/llm/openai_compat.py
# build_payload acrescenta, e SÓ quando structured_output == "json_schema"
# e options.json_schema is not None:
#   payload["response_format"] = {"type": "json_schema",
#     "json_schema": {"name": <schema_name>, "schema": <json_schema>, "strict": True}}
```

**Interface freeze.** Consumidores já enfileirados no grafo: TCK-077 (schemas
por tarefa no juiz, director e minds), TCK-081 (`app.dataset label`, que roda os
prompts no papel `teacher` com o schema da tarefa) e TCK-085 (`app.models serve`,
que imprime `structured_output: json_schema` no trecho de config do
llama-server). Três consumidores nomeados; nenhum deles pode inventar o nome do
campo por conta própria.

## Acceptance criteria

- [ ] `GenerationOptions()` sem argumentos tem `json_schema is None` e
      `schema_name == "response"`, e o payload gerado não tem `response_format`.
- [ ] Provider com `structured_output: "none"` (default) e options **com**
      schema: payload sem `response_format`.
- [ ] Provider com `structured_output: "json_schema"` e options **sem** schema:
      payload sem `response_format`.
- [ ] Provider com `structured_output: "json_schema"` e options com schema:
      payload traz exatamente
      `{"type": "json_schema", "json_schema": {"name": ..., "schema": ..., "strict": True}}`,
      e `max_tokens`/`temperature`/`stream` continuam nas chaves de sempre.
- [ ] `ProviderConfig` recusa `structured_output: "gbnf"` com `ValidationError`.
- [ ] Config carregada de YAML sem a chave `structured_output` continua válida e
      resolve para `"none"`.
- [ ] `load_config` num caminho inexistente continua escrevendo `DEFAULT_CONFIG`
      byte a byte igual (`test_config.py:7-12` intacto).
- [ ] `npm run check` verde sem editar nenhum teste existente.

## Cenários de teste

Suíte existente que muda de preparação: **nenhuma**. Verificado por Grep em
`backend/tests/`:

- `backend/tests/test_compact.py:206-258` é onde vivem hoje os testes de
  `build_payload` e `GenerationOptions`
  (`test_build_payload_without_options_omits_max_tokens_and_temperature:210`,
  `test_generation_options_defaults_have_no_max_tokens_or_temperature:233`,
  `test_generation_options_zero_temperature_is_kept_in_payload:245`). Todos
  afirmam ausência de `max_tokens`/`temperature` ou valor de chave específica;
  nenhum compara o payload inteiro por igualdade, e nenhum menciona
  `response_format`. Como os dois defaults novos (`json_schema=None`,
  `structured_output="none"`) mantêm o payload idêntico, os testes seguem verdes
  sem edição. Por isso `test_compact.py` **não** entra em `files`.
- `backend/tests/test_config.py:7-24` valida `DEFAULT_CONFIG` byte a byte e o
  erro de papel com provider desconhecido. Campo opcional novo com default não
  toca nem um nem outro.
- `backend/tests/test_judge.py:537-552`, `test_director.py:372-386` e
  `test_minds.py:450-465` espionam `OpenAICompatProvider.__init__` e comparam a
  `options` recebida por **identidade** (`is JUDGE_OPTIONS`). Este ticket não
  altera nenhuma dessas constantes; o TCK-077 altera o conteúdo delas, e a
  comparação por identidade continua valendo lá também.

Cenários novos, todos em `backend/tests/test_structured_output.py`, montando
`ProviderConfig` direto (sem YAML) e chamando `build_payload` — nenhum toca a
rede:
- Feliz: `structured_output="json_schema"` + `json_schema={"type": "object", ...}`
  + `schema_name="judgement"` → `response_format` completo e correto, com
  `strict is True`.
- Feliz: as três chaves antigas (`model`, `messages`, `stream`) seguem no payload
  junto com `response_format`.
- Borda: `structured_output` default → sem `response_format`, mesmo com schema.
- Borda: `structured_output="json_schema"` e `json_schema=None` → sem
  `response_format`.
- Borda: `GenerationOptions` construída com `max_tokens`/`temperature` **e**
  schema → as três chaves convivem.
- Falha: `ProviderConfig(base_url=..., structured_output="gbnf")` levanta
  `ValidationError`.
- Falha: YAML de config com `structured_output: json_schema` em um provider e
  ausente em outro carrega e resolve `"json_schema"` e `"none"`
  respectivamente (usa `load_config(tmp_path / "config.yaml")`, no molde de
  `test_config.py:14-24`).

## Rollout e kill switch

Não há flag: o kill switch é a própria config. `structured_output: none` (o
default, e o valor que toda instalação existente tem por omissão) desliga a
feature inteira sem deploy e sem reiniciar mais do que o processo da API.

`risk: low` porque o caminho novo só existe para provider que optou por ele, e
todo consumidor mantém o parser tolerante como rede secundária.

## Observabilidade

Eventos: N/A. Este ticket não emite nada — o provider não emite telemetria hoje
(`openai_compat.py` não importa `observability`) e não é aqui que isso muda. Quem
registra `structured: bool` na telemetria dos três subsistemas é o TCK-077.

Métrica de sucesso: nenhuma própria. A métrica que este contrato serve é a do
TCK-077 (taxa de `*_rejected` por formato caindo a zero com o llama-server).

## i18n

N/A. Nenhuma string de usuário; `schema_name` é identificador técnico em inglês
e nunca aparece na UI.
