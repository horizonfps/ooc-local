---
id: TCK-007
title: Resumir o bloco que sai da janela com o modelo utility (compact v0)
status: done
points: 3
blockedBy: [TCK-006]
files:
  - backend/app/compact.py
  - backend/app/turn.py
  - backend/app/sessions.py
  - backend/app/llm/base.py
  - backend/tests/test_compact.py
migration: true
ui: false
risk: high
---

## Problema

O TCK-006 corta a janela em 18 turnos e joga o resto fora. Com teto útil de 24K
(plano, "Orçamento de contexto"), o corte seco significa que a partir do turno
19 o narrador esquece tudo: promessa feita, conflito aberto, mudança de relação.
O plano é explícito: "com teto de 24K, compact é requisito do loop mínimo, não
memória esperta". Sem ele a sessão longa do critério de verde degrada em
contradição narrativa.

## Escopo

Dentro:
- `backend/app/compact.py`: estimador de tokens, orçamento, decisão de quando
  compactar e a chamada ao modelo `utility` que resume o bloco que sai da
  janela.
- Integração em `backend/app/turn.py` **dentro de `run_turn`**, que já é async:
  antes de montar o contexto do turno, `run_turn` lê o compact vigente, verifica
  o orçamento, `await`-a a compactação quando precisar e passa o texto
  resultante para `build_context(session_id, message, compact=...)`.
  `build_context` **continua síncrona, com a assinatura congelada pelo TCK-006**
  — este ticket não altera contrato já publicado.
- Persistência do compact como evento `kind="compact"` no event store e coluna
  `compact` na tabela `sessions` (projeção do compact vigente, para não varrer
  eventos a cada turno) — `ALTER TABLE` idempotente em `init_db()`.
- Método `complete()` no `LLMProvider` (chamada não-streamada, usada pelo
  utility), implementado como método **concreto** em `backend/app/llm/base.py`
  em cima de `stream_chat`.
- Flag de kill switch e telemetria.
- `backend/tests/test_compact.py`.

Fora (explícito):
- Tornar `build_context` async ou mudar sua assinatura: contrato congelado do
  TCK-006, e não há razão para quebrá-lo — a única chamada de rede do compact
  cabe em `run_turn`, que já é assíncrona.
- Tocar em `backend/app/llm/openai_compat.py`: `complete()` é concreto na base e
  o provider existente o herda sem edição.
- Compact **em camadas** (blocos antigos se fundindo num resumo de campanha
  saturado em 2K) — o plano manda isso para a Fase 7. Aqui há **um** compact por
  sessão, reescrito.
- Memórias por categoria, NPC minds persistentes, User Note — Fase 7.
- Tokenizer real (tiktoken ou similar): dependência nova sem ganho na Fase 1.
- Mexer no formato do SSE ou nas rotas: o compact é invisível para a API.

## Comportamento esperado

Do ponto de vista do jogador: nada muda na tela. Do ponto de vista do narrador:
a partir do momento em que o histórico não cabe mais no orçamento, o contexto do
turno passa a levar um bloco `RESUMO DA CAMPANHA` (seção que o TCK-003 já
prevê), e o custo de contexto do turno 100 é igual ao do turno 20.

Regra de disparo, executada em `run_turn` antes de o stream começar:
1. monta o contexto candidato com `build_context(session_id, message,
   compact=<compact vigente>)`;
2. se `fits(messages)` for falso, remove os turnos mais antigos da janela até
   caber, remontando o contexto;
3. os turnos removidos formam o "bloco que sai": o modelo `utility` resume
   (compact anterior + bloco que sai) em até ~400 tokens, e esse texto vira o
   compact novo, gravado antes de o turno começar a streamar;
4. se a chamada do utility falhar, o turno **continua** com a janela truncada e
   o compact antigo — degradação, não erro para o jogador.

## Detalhes técnicos

- `estimate_tokens(text) = ceil(len(text) / 4)`. Aproximação declarada no
  código, calibrada para pt-br/en em modelos SentencePiece; erra para mais em
  texto acentuado, que é o lado seguro do erro. Nenhuma dependência nova.
- `fits(messages)` é a **única** definição da regra de disparo, e é o que
  `run_turn` chama:
  `fits(m) = sum(estimate_tokens(x.content) for x in m) <= CONTEXT_BUDGET_TOKENS
  - OUTPUT_RESERVE_TOKENS`, ou seja, 23.200 tokens de entrada. Nenhum outro
  ponto do código recalcula esse limiar, e nenhuma constante de orçamento é lida
  fora de `compact.py`.
- Prompt do utility (pt-br e en, escolhidos pelo `locale` do cenário): pede
  resumo em terceira pessoa, foco em **promessas, conflitos abertos e mudanças
  de relação**, sem inventar fato, sem diálogo literal, no idioma do cenário, em
  no máximo ~400 tokens. Temperatura baixa.
- Modelo: `config.models["utility"]` — a config por papéis já existe
  (`backend/app/config.py:18`), e o plano prevê trocar o utility de modelo sem
  código.
- `LLMProvider.complete(messages, model) -> str` entra em
  `backend/app/llm/base.py` como método concreto que consome `stream_chat` e
  junta os deltas. Não é abstrato: `OpenAICompatProvider` e implementações
  futuras herdam de graça, e nenhum teste que monkeypatcha `stream_chat` quebra.
- Coluna nova: `ALTER TABLE sessions ADD COLUMN compact TEXT` protegido por
  checagem em `PRAGMA table_info(sessions)`. O event store continua append-only:
  cada compactação grava um evento `compact` com `{text, replaced_turns,
  from_index, to_index}`, e a coluna é só projeção do último.
- O compact é reconstituível: apagar a coluna e reprocessar os eventos `compact`
  devolve o mesmo estado. Isso é o que autoriza tratar a coluna como cache.
- A compactação roda antes do turno, de forma síncrona do ponto de vista do
  jogador (uma chamada de LLM a mais no turno em que dispara, tipicamente a cada
  ~18 turnos). Fila em background é Fase 7; síncrono é honesto sobre a latência e
  não introduz concorrência sobre o event store.

Testes existentes que este ticket invalida: **nenhum**, e a compatibilidade é
deliberada. `backend/tests/test_chat.py:7` e o fake provider do TCK-006
monkeypatcham `stream_chat`; como `complete()` é implementado **em cima** de
`stream_chat`, esses fakes continuam funcionando sem adaptação. Os testes do
TCK-006 sobre janela de 18 turnos continuam válidos: o corte por contagem
permanece, o orçamento só entra como segundo limite.

## Contrato público

```python
# backend/app/compact.py
CONTEXT_BUDGET_TOKENS = 24_000
OUTPUT_RESERVE_TOKENS = 800
COMPACT_TARGET_TOKENS = 400

def estimate_tokens(text: str) -> int: ...
def fits(messages: list[ChatMessage]) -> bool: ...   # <= BUDGET - RESERVE
async def compact_block(
    previous: str | None, outgoing: list[ChatMessage], locale: str
) -> str: ...          # levanta CompactError quando o utility falha
class CompactError(Exception): ...
```

```python
# backend/app/llm/base.py
class LLMProvider(ABC):
    async def complete(self, messages: list[ChatMessage], model: str) -> str: ...
```

```python
# backend/app/sessions.py  (acrescentado)
def get_compact(session_id: str) -> str | None: ...
def set_compact(session_id: str, text: str, payload: dict) -> None: ...  # evento + projeção
```

`build_context` mantém a assinatura do TCK-006, inclusive o parâmetro
`compact: str | None = None`, que este ticket passa a preencher.

## Acceptance criteria

- [ ] Com histórico curto, `fits()` é verdadeiro, nenhuma chamada ao utility
      acontece e o contexto sai igual ao do TCK-006.
- [ ] Estourando o orçamento, os turnos mais antigos saem da janela e o contexto
      passa a conter a seção `RESUMO DA CAMPANHA` com o texto do compact.
- [ ] `build_context` continua síncrona e com a mesma assinatura; a compactação
      é aguardada em `run_turn`.
- [ ] O compact é gravado como evento `compact` **e** na coluna projetada; um
      turno seguinte reusa o compact sem chamar o utility de novo.
- [ ] Segunda compactação recebe o compact anterior como entrada e o substitui.
- [ ] Falha do utility → turno acontece normalmente com janela truncada, sem
      compact novo, e evento de telemetria com `error`.
- [ ] Flag `compact: false` → comportamento idêntico ao do TCK-006 (janela
      truncada, sem chamada de utility).
- [ ] `init_db()` sobre banco criado pelo TCK-005 adiciona a coluna sem perder
      dados e roda duas vezes sem erro.
- [ ] `complete()` devolve a concatenação dos deltas de `stream_chat`, aferido
      com o mesmo estilo de fake provider de `backend/tests/test_chat.py`.
- [ ] `npm run check` verde.

## Cenários de teste

- Feliz: 30 turnos curtos → dispara por contagem de janela; o bloco que sai é
  resumido e aparece no contexto do turno 31.
- Feliz: turnos longos que estouram 23.200 tokens antes dos 18 → dispara por
  orçamento (`fits()` falso).
- Borda: `estimate_tokens("")` é 0; texto acentuado não subestima.
- Borda: banco antigo sem a coluna `compact` → migração idempotente aplicada em
  `init_db()`.
- Borda: compact anterior + bloco novo → o prompt do utility contém os dois, e o
  resultado substitui (não concatena) o anterior.
- Falha: `complete()` levanta → `CompactError` capturada em `run_turn`, turno
  segue, `compact_run` com `error` preenchido, banco sem evento `compact` novo.
- Falha: utility devolve string vazia → tratada como falha (compact antigo
  preservado), nunca grava compact vazio.

## Rollout e kill switch

Flag: **`compact`** em `~/.ooc-local/config.yaml`, default `true`, lida por
`config.flag("compact")` a cada turno. Desligar sem deploy: editar o YAML; o
próximo turno já ignora o compact e volta ao corte por janela do TCK-006 (o
compact gravado fica no banco, intacto, e volta a ser usado quando a flag
religar). É o kill switch certo porque o risco aqui é qualitativo — um resumo
ruim contamina todos os turnos seguintes — e a degradação sem ele é
compreensível: o narrador esquece, mas não alucina.

## Observabilidade

Eventos: `compact_run` (`session_id`, `turns_summarized`, `in_tokens`,
`out_tokens`, `duration_ms`, `error`); `context_budget` (`session_id`,
`estimated_tokens`, `window_turns`) emitido a cada turno.
Métrica de sucesso: `estimated_tokens` estável (não crescente) entre o turno 20
e o turno 100 da mesma sessão, com `error: null` em `compact_run`.

## i18n

N/A para a UI. O prompt do utility existe em `pt-br` e `en`, escolhido pelo
`locale` do cenário, no mesmo padrão do TCK-003 — o resumo tem que sair no
idioma da narração.
