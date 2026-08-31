---
id: TCK-024
title: Disparar o compact por contagem de turnos, com histerese e corte auditável
status: in_review
points: 3
blockedBy: [TCK-015]
files:
  - backend/app/compact.py
  - backend/app/turn.py
  - backend/tests/test_compact.py
migration: false
ui: false
risk: high
---

## Problema

O TCK-007 lista como cenário feliz nº 1 "30 turnos curtos → dispara por contagem
de janela". Isso nunca foi implementado. O código só olha `fits()`
(`backend/app/turn.py:71`), que é orçamento em tokens: com turnos curtos, 18
pares cabem folgadamente nos 23.200 tokens de entrada, então nada dispara.
`build_context` corta em `events[-(WINDOW_TURNS * 2):]` (`:45`) e **joga o resto
fora em silêncio**. A partir do turno ~19 o narrador esquece promessa feita e
conflito aberto — a dor original do TCK-007, intacta depois do TCK-015 (que
resolveu a recompactação, não o disparo).

No mesmo caminho, o segundo corte — o do rebuild pós-compactação
(`backend/app/turn.py:92-93`, e o mesmo ponto depois do TCK-015) — descarta os
pares extras sem registrar nada: quando o resumo devolvido pelo utility é grande
demais, o contexto é cortado de novo e os turnos cortados somem sem aparecer em
log nenhum e sem entrar em resumo nenhum.

## Escopo

Dentro:
- `select_window` em `backend/app/compact.py`: função pura que substitui
  `_shrink_to_fit` e decide o corte por **contagem** e por **orçamento** numa
  única passada, com histerese. Mantém a **forma de retorno** que o TCK-015
  publicou para `_shrink_to_fit` — um inteiro, contando as mensagens que saem do
  início do histórico — para ser substituição direta.
- Restaurar o corte por contagem no caminho do compact, agora como **gatilho de
  compactação** em vez de descarte: é o que fecha o estado intermediário que o
  TCK-015 declarou.
- `COMPACT_KEEP_TURNS` e `COMPACT_RESERVE_TOKENS` em
  `backend/app/compact.py`.
- `_maybe_compact` (`backend/app/turn.py:65`) passando a usar `select_window`.
- Evento `compact_overflow` para o corte extra pós-compactação.
- Testes em `backend/tests/test_compact.py`.

Fora (explícito):
- Coluna `compact_seq`, migração, `history_events`, `events_to_messages`,
  `build_context(..., history=...)`, `get_compact`/`set_compact`: são do
  TCK-015 e chegam prontos. Este ticket **consome** esse contrato — em
  particular, o candidato já chega montado sobre a lista **completa** de
  eventos não cobertos, que é o que torna o gatilho por contagem alcançável.
- Mudar o comportamento de `build_context` **sem** `history`: ele continua
  truncando em `WINDOW_TURNS` pares, e é isso que mantém
  `backend/tests/test_turn.py:203` verde (ver inventário).
- `max_tokens`/temperatura/timeout da chamada do utility: TCK-016.
- Mudar `WINDOW_TURNS` (18) ou o orçamento (`CONTEXT_BUDGET_TOKENS`,
  `OUTPUT_RESERVE_TOKENS`): os três números continuam como estão.
- Compact em camadas, memória por categoria: Fase 7.
- Estender `compact_seq` para cobrir os pares descartados no corte de overflow:
  eles **não** foram resumidos, então continuam descobertos e entram no resumo
  da próxima compactação. Cobri-los seria perder conteúdo em silêncio, que é o
  defeito que este ticket fecha.

### Testes existentes que este ticket invalida

Grep em `backend/tests/`, sobre o estado do repositório **depois** do TCK-015:

- `test_short_history_skips_compact_and_matches_tck006`
  (`backend/tests/test_compact.py:209`): a sessão tem 0 pares de histórico, bem
  abaixo do gatilho de contagem. Continua válido sem adaptação.
- `test_budget_overflow_triggers_compact_and_context_gets_resumo` (`:233`),
  `test_second_compaction_replaces_previous_compact` (`:319`),
  `test_utility_failure_falls_back_to_truncated_window` (`:368`),
  `test_flag_compact_false_behaves_like_tck006` (`:407`): todos preparam 18
  pares e disparam por orçamento. Com o gatilho de contagem em "mais de 18
  pares", 18 pares **não** disparam por contagem, e o disparo continua sendo o
  de orçamento. As asserções sobre quantidade de chamadas ao utility e sobre o
  resumo vigente continuam verbatim. Sem adaptação.
  A única diferença observável é o **tamanho** do bloco resumido: `select_window`
  com histerese move mais pares que `_shrink_to_fit` movia. Nenhum desses testes
  afere `turns_summarized` nem o número de mensagens em `outgoing` — grep por
  `turns_summarized` em `backend/tests/` não devolve nada.
- `test_second_turn_reuses_compact_without_calling_utility_again` (`:279`):
  prepara um resumo e um par curto. Continua válido.
- `backend/tests/test_turn.py::test_turn_window_truncated_at_18_pairs` (`:203`)
  monta 25 pares e chama `turn.build_context(session_id, "nova mensagem")` sem o
  parâmetro `history`, aferindo 36 mensagens e `"jogador 7"` na primeira.
  **Continua válido sem adaptação**, por dois motivos que precisam ficar ditos:
  `select_window` vive em `backend/app/compact.py` e é chamada por
  `_maybe_compact`, nunca por `build_context`; e o corte por contagem que este
  ticket introduz é o do **caminho do compact**, sobre a lista completa passada
  em `history`, enquanto o caminho sem `history` continua com o truncamento do
  TCK-006 intacto. Este teste é a fronteira entre os dois modos: se ele quebrar,
  `select_window` vazou para dentro de `build_context`.
- `test_fits_true_under_budget` (`:121`) e `test_fits_false_over_budget`
  (`:126`): `fits` não muda de assinatura nem de regra. Válidos.
- `test_shrink_to_fit_always_returns_an_even_count`
  (`backend/tests/test_compact.py:247`) chama `turn._shrink_to_fit` direto e
  afere `n == 4` (contagem sempre par). O teste nasceu no TCK-015, depois desta
  spec. Adaptação: reescrever contra `select_window`, preservando a asserção de
  paridade; o valor esperado de `n` é recalculado pelas regras de
  `select_window` sobre a mesma preparação (a invariante "sempre par" vale
  igualmente, e este ticket já tem AC próprio para ela).

## Comportamento esperado

Do ponto de vista do jogador: a partir do turno 20 de uma sessão de turnos
curtos, o narrador continua lembrando de promessa feita no turno 3 — hoje ele
esquece.

Do ponto de vista do chamador:

- Quando os pares não cobertos pelo resumo passam de **18**, a compactação
  dispara e resume até sobrarem **9** pares na janela.
- Essa histerese é o que impede a compactação a cada turno: depois de disparar,
  são precisos 10 turnos novos para voltar ao gatilho. Numa sessão de 40 turnos
  curtos, isso são 3 compactações; sem histerese (compactar só o excedente),
  seriam 21.
- O disparo por orçamento continua existindo e é avaliado na mesma passada: se
  os 9 pares que sobrariam ainda não couberem, mais pares saem.
- A janela nunca fica vazia: o par mais recente sempre permanece.
- Se, depois de gravar o resumo novo, o contexto ainda não couber, pares extras
  são cortados **e** o evento `compact_overflow` é emitido com quantos foram.

## Detalhes técnicos

- Constantes novas em `backend/app/compact.py`:
  - `COMPACT_KEEP_TURNS = 9` — quantos pares ficam na janela depois de uma
    compactação. Metade de `WINDOW_TURNS`, que é o gatilho.
  - `COMPACT_RESERVE_TOKENS = 700` — espaço reservado para o resumo novo ao
    decidir o corte. Tem que ser maior que o teto de geração do resumo
    (`COMPACT_MAX_TOKENS = 400`, definido no TCK-016), porque `estimate_tokens`
    conta `ceil(len/4)` sobre caracteres e o português acentuado rende mais
    caracteres por token real. 700 é ~1,75x o teto: folga suficiente para o
    corte de overflow ser exceção, não regra.
- `WINDOW_TURNS` continua em `backend/app/turn.py:24` e é passado como argumento
  para `select_window`, para `compact.py` não importar de `turn.py` (hoje a
  dependência é só na direção `turn.py → compact.py`; manter assim evita ciclo).
- **A janela candidata já chega inteira.** O TCK-015 fez `_maybe_compact` montar
  o contexto com `build_context(..., history=full)`, onde `full` é a lista
  completa de `history_events(session_id, compact_seq)` — sem truncar. É essa
  decisão que torna o gatilho por contagem alcançável: se o candidato viesse
  truncado em `WINDOW_TURNS` pares, `len(history) // 2 > window_turns` seria
  falso por construção e nada dispararia. `select_window` **não** carrega
  eventos nem vai ao banco; ela recebe a janela inteira e devolve onde cortar.
- Assinatura, **cinco parâmetros**, devolvendo um **índice**:

  ```python
  def select_window(
      system: ChatMessage,
      history: list[ChatMessage],   # janela COMPLETA não coberta, ordem cronológica
      tail: ChatMessage,            # mensagem nova do jogador
      window_turns: int,            # gatilho: WINDOW_TURNS
      keep_turns: int,              # alvo: COMPACT_KEEP_TURNS
  ) -> int:
      """Quantas mensagens saem do INÍCIO de history. Sempre par.
      0 significa 'não compactar'. O chamador fatia:
      outgoing = history[:n]; kept = history[n:]"""
  ```

  Devolver o índice, e não as duas listas, é o que permite ao chamador endereçar
  o evento correspondente em `full` — reconstruir por posição a partir de listas
  diferentes é o defeito que o TCK-015 fechou e que este ticket não pode
  reabrir. O resumo anterior **já está dentro de `system`** (`build_context` o
  interpola na seção `RESUMO DA CAMPANHA`), por isso não é parâmetro.
- Regra, em prosa implementável, com `n` começando em `0`:
  1. **Contagem**: se `len(history) // 2 > window_turns`, avance `n` até que
     `(len(history) - n) // 2 == keep_turns`.
  2. **Orçamento**: enquanto sobrar mais de um par depois de `n` e o contexto
     candidato não couber, avance `n` em 2. O contexto candidato é
     `[system, *history[n:], tail, placeholder]`, onde `placeholder` é um
     `ChatMessage(role="system", content="x" * (COMPACT_RESERVE_TOKENS * 4))` —
     uma mensagem de preenchimento cujo único papel é fazer `fits()` reservar o
     espaço do resumo que ainda vai nascer. O `placeholder` nunca é enviado ao
     modelo; só entra na conta.
  3. Devolve `n`.
- `_maybe_compact` troca a chamada de `_shrink_to_fit` por
  `select_window(messages[0], messages[1:-1], messages[-1], WINDOW_TURNS,
  COMPACT_KEEP_TURNS)` e **não muda mais nada** no fluxo que o TCK-015 deixou:
  `outgoing = messages[1:1 + n]`, `from_seq = full[0].seq`,
  `covered_seq = full[n - 1].seq`, `compact_block`, `set_compact`, remontagem com
  `history=full[n:]`. A forma de retorno idêntica é o que faz a troca ser de uma
  linha.
- Corte de overflow: depois do rebuild, se `fits(messages)` ainda for falso,
  corte pares do início da janela até caber e emita
  `compact_overflow(session_id, dropped_turns, compact_tokens)`. `compact_seq`
  **não** avança para esses pares (ver "Fora de escopo").
- `_shrink_to_fit` (`backend/app/turn.py:55`) é removida. Deixar as duas
  convivendo é como o descarte silencioso apareceu.
  **Armadilha**: `select_window` move sempre **pares**, nunca mensagens soltas;
  mover uma mensagem só desalinha os papéis `user`/`assistant` no resto da
  janela.

## Contrato público

```python
# backend/app/compact.py
COMPACT_KEEP_TURNS = 9
COMPACT_RESERVE_TOKENS = 700

def select_window(
    system: ChatMessage,
    history: list[ChatMessage],
    tail: ChatMessage,
    window_turns: int,
    keep_turns: int,
) -> int: ...
```

Substitui o `_shrink_to_fit(system, history, tail) -> int` que o TCK-015
publicou, com a mesma semântica de retorno e dois parâmetros a mais.

`COMPACT_RESERVE_TOKENS` é o teto que o TCK-016 referencia ao escolher
`COMPACT_MAX_TOKENS`.

## Acceptance criteria

- [ ] `select_window` com 19 pares curtos, `window_turns=18`, `keep_turns=9`
      devolve `20` (10 pares saem, 9 ficam).
- [ ] `select_window` com exatamente 18 pares curtos devolve `0`.
- [ ] `select_window` com 1 par que sozinho estoura o orçamento devolve `0`
      (nunca esvazia a janela).
- [ ] `select_window` devolve sempre um número par.
- [ ] Com 25 pares não cobertos, `compact_seq` gravado é o `seq` do evento na
      posição `n - 1` de `history_events`, e o primeiro turno do contexto do
      narrador é o primeiro evento devolvido por
      `history_events(session_id, compact_seq)` (`full[n]`) — não
      `compact_seq + 1`, que num turno com tag endereça um evento `tag`.
- [ ] Numa sessão de 40 turnos curtos que nunca estoura o orçamento, o log tem
      no máximo **4** eventos `compact_run` (hoje seriam ~21).
- [ ] Depois de uma compactação por contagem, os 9 turnos seguintes não disparam
      compactação nenhuma.
- [ ] Quando o resumo devolvido estoura a reserva e pares extras precisam sair,
      `compact_overflow` é emitido com `dropped_turns > 0` e o turno completa.
- [ ] `_shrink_to_fit` não existe mais em `backend/app/turn.py`.
- [ ] Flag `compact: false` → nenhuma chamada ao utility e nenhum
      `compact_overflow`.
- [ ] `npm run check` verde.

## Cenários de teste

- Feliz (pura, contagem): `select_window` com 19, 20 e 27 pares curtos → `20`,
  `22` e `36` (sempre sobram 9 pares).
- Feliz (pura, orçamento): 12 pares longos, abaixo do gatilho de contagem, que
  não cabem → retorno maior que `0` mesmo sem estourar a contagem.
- Feliz (pura, reserva): conjunto de pares que **caberia** sem reserva e **não**
  cabe com a reserva de 700 tokens → retorno maior que `0`. Este é o teste que
  prova que a reserva está sendo aplicada.
- Feliz (integração, contagem): sessão com 19 pares curtos → o turno seguinte
  chama o utility uma vez, e o prompt do utility contém o texto do par mais
  antigo.
- **Feliz (integração, fronteira com janela grande)**: sessão com **25 pares
  curtos** não cobertos → dispara por contagem, e as asserções são as mesmas do
  cenário de fronteira do TCK-015: `compact_seq` é o `seq` do último evento
  citado no prompt do utility; o primeiro turno do prompt do narrador é o
  primeiro evento devolvido por `history_events(session_id, compact_seq)`
  (`full[n]`); nenhum texto aparece nos dois prompts. Com 25
  pares e `keep_turns=9`, saem 16 pares (32 mensagens) — bem além dos 18 pares
  da janela antiga, que é justamente onde uma janela truncada faria o
  `compact_seq` cair no evento errado.
- Feliz (histerese): logo depois do cenário de 19 pares, 9 turnos curtos
  seguidos → nenhuma chamada nova ao utility; o décimo dispara.
- Borda: exatamente `WINDOW_TURNS` pares → nenhuma compactação.
- Borda: `history` vazio → retorno `0`, sem exceção.
- Borda: `keep_turns` maior que os pares existentes → retorno `0`.
- Borda: resumo devolvido com ~4x a reserva → contexto cabe depois do corte
  extra, `compact_overflow` emitido com `dropped_turns` igual ao número de pares
  cortados, e `compact_seq` **não** cobre os pares cortados.
- Falha: utility levanta → nenhuma janela é cortada além do que `select_window`
  já decidiu, `compact_run` com `error`, turno completa.

## Rollout e kill switch

Flag **`compact`** em `~/.ooc-local/config.yaml`, default `true`, lida a cada
turno em `backend/app/turn.py:68` — o mesmo kill switch do TCK-007 e do
TCK-015, sem flag nova. Desligar: editar o YAML; o próximo turno volta ao corte
seco por janela do TCK-006, sem nenhuma chamada ao utility. É o kill switch
certo porque o risco deste ticket é qualitativo (resumo ruim contamina todos os
turnos seguintes) e a degradação sem ele é compreensível: o narrador esquece,
mas não alucina.

Rollback de código é `git revert` do PR; não há migração associada e o
`compact_seq` gravado continua válido.

## Observabilidade

Eventos:
- `compact_run` — já existente desde o TCK-007 (`backend/app/turn.py:95`) e
  estendido pelo TCK-015 com `from_seq`/`to_seq`/`covered_seq`. Este ticket não
  acrescenta campo, só muda a frequência com que ele é emitido.
- `compact_overflow` (**novo**) — `session_id`, `dropped_turns`,
  `compact_tokens`.
- `context_budget` — inalterado.

Métrica de sucesso: numa sessão de 40 turnos curtos, no máximo 4 `compact_run`
com `error: null`, nenhum `compact_overflow`, e
`context_budget.estimated_tokens` oscilando dentro de uma faixa em vez de
crescer monotonicamente.

## i18n

N/A. Nenhum texto de usuário; os prompts pt-br/en do utility
(`backend/app/compact.py:15`) não mudam neste ticket.
