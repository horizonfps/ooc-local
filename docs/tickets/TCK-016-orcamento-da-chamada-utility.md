---
id: TCK-016
title: Dar orçamento próprio à chamada de compactação (max_tokens, temperatura, timeout)
status: in_review
points: 3
blockedBy: [TCK-024]
files:
  - backend/app/llm/base.py
  - backend/app/llm/openai_compat.py
  - backend/app/compact.py
  - backend/tests/test_compact.py
migration: false
ui: false
risk: low
---

## Problema

A compactação roda **antes** do primeiro byte do turno (`_maybe_compact` é
aguardada em `backend/app/turn.py:114`, antes do `stream_chat` do narrador) e
usa o mesmo cliente HTTP do narrador: `OpenAICompatProvider.stream_chat` cria
`httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))`
(`backend/app/llm/openai_compat.py:22`). Consequência prática: se o modelo
utility travar, o jogador fica **dois minutos** olhando uma tela sem nenhum
byte, sem indicação de nada, e só então o turno começa. O orçamento de tempo de
um stream de narração longa não é o de uma chamada de resumo de ~400 tokens;
hoje é o mesmo.

Junto disso, `compact_block` (`backend/app/compact.py:68`) chama
`provider.complete(prompt_messages, role.model)` sem `max_tokens` e sem
`temperature`. O prompt do utility pede "no máximo 400 tokens"
(`backend/app/compact.py:18-19`), mas nada no payload impõe isso: um modelo
verborrágico devolve 2.000 tokens de resumo, que entram no system prompt de
**todos** os turnos seguintes e comem o orçamento que a compactação existia para
liberar — e, com o TCK-024 no lugar, transformam o corte de overflow em caminho
comum em vez de exceção. Sem temperatura baixa o resumo ainda varia entre
execuções, o que o TCK-007 pedia explicitamente ("Temperatura baixa") e nunca
foi implementado.

Lacuna de cobertura correlata: o template `en` de
`backend/app/compact.py:26` (`_PROMPT_TEMPLATES["en"]`) nunca é exercitado —
todo cenário de teste em `backend/tests/test_compact.py` usa `locale: pt-br`
(`backend/tests/test_compact.py:19`).

## Escopo

Dentro:
- `GenerationOptions` em `backend/app/llm/base.py`: `max_tokens`,
  `temperature`, `timeout_s`.
- `OpenAICompatProvider` aceita `GenerationOptions` no construtor e as aplica no
  payload e no timeout do cliente; `build_payload` extraído para virar
  superfície testável.
- `COMPACT_MAX_TOKENS` e `COMPACT_OPTIONS` em `backend/app/compact.py`;
  `compact_block` constrói o provider do utility com elas.
- Testes de payload, de timeout e do template `en`.

Fora (explícito):
- Mudar a assinatura de `stream_chat`/`complete`. Os fakes das suítes
  existentes são `async def fake_stream(self, messages, model)`
  (`backend/tests/test_chat.py`, `backend/tests/test_turn.py:91`,
  `backend/tests/test_compact.py:100`); acrescentar parâmetro na assinatura
  quebraria todos eles sem ganho. As opções viajam no **construtor** do
  provider, não na chamada.
- Mudar o orçamento do narrador: `stream_chat` sem opções continua com
  `Timeout(120.0, connect=10.0)`.
- Escolher a **reserva** que o `select_window` aplica: `COMPACT_RESERVE_TOKENS`
  é definida no TCK-024 e este ticket só a respeita como teto ao escolher
  `COMPACT_MAX_TOKENS`.
- Tirar a compactação de antes do stream (fila em background, evento SSE de
  progresso): fora da Fase 1; o TCK-007 decidiu por síncrono deliberadamente, e
  o que este ticket faz é **limitar** o custo dessa decisão.
- Retry da chamada do utility: falha continua sendo degradação de um turno.

### Testes existentes que este ticket invalida

Grep em `backend/tests/`: **nenhum**.

- A única construção direta de provider em teste é
  `backend/tests/test_compact.py:198`:
  `provider = OpenAICompatProvider(_config().providers["local"])`, dentro de
  `test_complete_joins_stream_chat_deltas` (`:192`). Com `options` opcional e
  default `None`, essa chamada continua válida sem adaptação, e o comportamento
  aferido (concatenar os deltas) é idêntico.
- Nenhum teste inspeciona o payload HTTP nem o timeout: a suíte inteira
  monkeypatcha `stream_chat`, que passa a ignorar as opções exatamente como
  hoje.
- `backend/tests/test_chat.py` monkeypatcha `stream_chat` do mesmo jeito e não é
  tocado.

Todos os cenários abaixo são novos.

## Comportamento esperado

Do ponto de vista do jogador: se o utility travar, o turno começa a streamar em
até ~25 s em vez de ~120 s, com a janela truncada e o resumo antigo — a mesma
degradação que o TCK-007 já definiu, só que rápida.

Do ponto de vista do chamador:
- A requisição de compactação sai com `max_tokens` e `temperature` no corpo.
- O resumo devolvido não passa do teto negociado com o servidor.
- O prompt do utility sai em inglês quando o cenário tem `locale: en`.

## Detalhes técnicos

- `GenerationOptions` é um `BaseModel` pydantic (padrão do repo: todo modelo em
  `backend/app/` é pydantic), com `max_tokens: int | None = None`,
  `temperature: float | None = None`, `timeout_s: float = 120.0`.
- `OpenAICompatProvider.__init__(self, provider: ProviderConfig, options:
  GenerationOptions | None = None)`, guardando
  `self.options = options or GenerationOptions()`. `options=None` preserva o
  comportamento atual byte a byte.
- `build_payload(messages, model) -> dict` monta `{"model", "messages",
  "stream": True}` e acrescenta `max_tokens`/`temperature` **só quando não são
  `None`** — servidor OpenAI-compat local recusa `null` em alguns builds, e
  omitir é o comportamento de hoje.
- O timeout vira `httpx.Timeout(self.options.timeout_s, connect=10.0)`.
- **Número escolhido**: `COMPACT_MAX_TOKENS = 400`, igual a
  `COMPACT_TARGET_TOKENS` (`backend/app/compact.py:11`), que já é o número
  escrito nos dois prompts de compactação. O teto duro coincidir com o alvo
  pedido em texto é o que mantém prompt e payload dizendo a mesma coisa.
  A coerência com o TCK-024 é por folga, não por igualdade:
  `COMPACT_RESERVE_TOKENS = 700` reserva ~1,75x este teto, porque
  `estimate_tokens` conta `ceil(len/4)` sobre **caracteres** e um resumo de 400
  tokens reais em português acentuado estima acima de 400. Com 400 de teto e 700
  de reserva, `compact_overflow` continua sendo exceção.
- `COMPACT_OPTIONS = GenerationOptions(max_tokens=COMPACT_MAX_TOKENS,
  temperature=0.2, timeout_s=25.0)` em `backend/app/compact.py`, usada na
  construção do provider em `compact_block` (`backend/app/compact.py:71`).
- Armadilha: `complete()` (`backend/app/llm/base.py:17`) consome `stream_chat`;
  não há nada a mudar lá. Quem carrega a opção é a instância do provider.
- Armadilha: um timeout do httpx levanta `httpx.TimeoutException`, que
  `compact_block` já converte em `CompactError` pelo `except Exception`
  (`backend/app/compact.py:76`). Não acrescente tratamento novo — só confirme
  com teste.

## Contrato público

```python
# backend/app/llm/base.py
class GenerationOptions(BaseModel):
    max_tokens: int | None = None
    temperature: float | None = None
    timeout_s: float = 120.0
```

```python
# backend/app/llm/openai_compat.py
class OpenAICompatProvider(LLMProvider):
    options: GenerationOptions
    def __init__(self, provider: ProviderConfig, options: GenerationOptions | None = None): ...
    def build_payload(self, messages: list[ChatMessage], model: str) -> dict: ...
```

```python
# backend/app/compact.py
COMPACT_MAX_TOKENS = 400
COMPACT_OPTIONS: GenerationOptions   # max_tokens=400, temperature=0.2, timeout_s=25.0
```

## Acceptance criteria

- [ ] `OpenAICompatProvider(cfg).build_payload(...)` não contém as chaves
      `max_tokens` nem `temperature`, e contém `stream: True`.
- [ ] `OpenAICompatProvider(cfg, COMPACT_OPTIONS).build_payload(...)` contém
      `max_tokens == 400` e `temperature == 0.2`.
- [ ] `COMPACT_MAX_TOKENS < COMPACT_RESERVE_TOKENS` (constante do TCK-024).
- [ ] O provider construído dentro de `compact_block` tem
      `provider.options == COMPACT_OPTIONS`, aferido por monkeypatch de
      `stream_chat` que captura `self` e inspeciona `self.options`.
- [ ] `OpenAICompatProvider(cfg, COMPACT_OPTIONS).options.timeout_s == 25.0` e
      `OpenAICompatProvider(cfg).options.timeout_s == 120.0`.
- [ ] O timeout chega ao httpx: com `httpx.AsyncClient` monkeypatchado por um
      duplo que grava o kwarg `timeout` recebido, uma chamada feita com
      `COMPACT_OPTIONS` registra `timeout.read == 25.0` e uma feita sem opções
      registra `timeout.read == 120.0`.
- [ ] `httpx.TimeoutException` na chamada do utility vira `CompactError` e o
      turno completa mesmo assim.
- [ ] Cenário com `locale: en` produz prompt de compactação com o texto do
      template inglês e sem nenhuma palavra do template pt-br.
- [ ] `npm run check` verde.

## Cenários de teste

- Feliz: `build_payload` com e sem opções, aferindo presença/ausência das chaves
  e o `stream: True` em ambos.
- Feliz: `compact_block` com `stream_chat` monkeypatchado capturando `self` → o
  provider recebido carrega `COMPACT_OPTIONS`.
- Feliz: `httpx.AsyncClient` monkeypatchado por um duplo que grava o `timeout`
  recebido e devolve um contexto assíncrono mínimo (o `stream_chat` real é
  exercido, sem rede) → 25.0 para o utility e 120.0 para o provider sem opções.
- Feliz (`en`): cenário de teste com `locale: en` e histórico que dispara
  compactação, capturando as mensagens enviadas ao utility → contém
  `PREVIOUS SUMMARY` e `TURNS LEAVING THE WINDOW`, e não contém
  `RESUMO ANTERIOR`.
- Borda: `GenerationOptions()` puro → `timeout_s` 120.0, `max_tokens` e
  `temperature` `None`, nenhuma chave extra no payload.
- Borda: `GenerationOptions(temperature=0.0)` → a chave `temperature` **aparece**
  com valor `0.0` (o teste que impede um `if options.temperature:` no lugar de
  `is not None`).
- Falha: `stream_chat` levantando `httpx.TimeoutException("utility travou")` →
  `CompactError`, `compact_run` com `error` preenchido, turno segue com a janela
  truncada e sem resumo novo.

## Rollout e kill switch

N/A como flag nova. O kill switch aplicável continua sendo **`compact`**
(default `true`) em `~/.ooc-local/config.yaml`, lido em
`backend/app/turn.py:68`: desligado, nenhuma chamada de utility acontece e
nenhum destes parâmetros é exercido. Reverter só os parâmetros sem deploy não é
possível nem necessário — são constantes de código, com risco baixo e cobertas
por teste. Rollback é `git revert` do PR.

## Observabilidade

Eventos: `compact_run` — evento **já existente** desde o TCK-007
(`backend/app/turn.py:95`), estendido pelo TCK-015. Este ticket não acrescenta
campo: o texto de `error` passa a distinguir timeout de outras falhas, porque
vem do `str(exc)` da exceção do httpx.
Métrica de sucesso: `compact_run.duration_ms` com p95 abaixo de 25.000 e
`out_tokens` sempre abaixo de `COMPACT_RESERVE_TOKENS` nas sessões longas.

## i18n

N/A para a UI. O ticket não cria chave de prompt nova: usa os templates `pt-br`
e `en` que já existem em `backend/app/compact.py:15`, e passa a exercitar o `en`
em teste.
