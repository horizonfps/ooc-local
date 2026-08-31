---
id: TCK-014
title: Enviar o turno pelo input e receber a narração em streaming
status: ready
points: 5
blockedBy: [TCK-006, TCK-012]
files:
  - frontend/src/api.ts
  - frontend/src/screens/GameScreen.tsx
  - frontend/src/screens/GameScreen.test.tsx
  - frontend/src/screens/game.css
migration: false
ui: true
risk: medium
---

## Problema

Depois do TCK-012 a tela de jogo abre a sessão, mostra prólogo, histórico e HUD —
e não deixa jogar: não há campo de texto e ninguém chama
`POST /api/sessions/:id/turn` (TCK-006). Este é o ticket que fecha o critério de
verde da Fase 1: jogar 5 turnos, fechar o app, reabrir e continuar do mesmo
ponto.

## Escopo

Dentro:
- `streamTurn()` em `frontend/src/api.ts`: `POST /api/sessions/:id/turn` com
  leitura de SSE, incluindo o evento `hud` e o `[DONE]`.
- Formulário de input no rodapé do `GameScreen`: `<textarea>` com auto-grow,
  `Enter` envia / `Shift+Enter` quebra linha, estado ocupado.
- Turno otimista do jogador + bloco do narrador recebendo o stream, via
  `<TurnText streaming />`.
- Atualização do HUD ao fim do turno e estado `stale` quando o turno falha.
- Estado de erro de turno com retry que reenvia a mesma mensagem.
- Autoscroll com `atBottom` e botão flutuante `game.scrollToLatest`.

Fora (explícito):
- Cancelar turno, regenerar, editar turno, rewind — nada disso aparece na tela na
  Fase 1 (rewind é Fase 7).
- Sugestões de ação clicáveis, sprites, backgrounds, stats — Fases 2 a 5.
- Mudar a leitura da sessão feita no TCK-012 (prólogo, histórico inicial, 404,
  500): só o que este escopo lista é tocado.
- Persistir rascunho do input entre recargas.

## Comportamento esperado

Adaptado do tema 02 da spec de UI.

### Dados

`POST /api/sessions/:id/turn { message }` → SSE: `data: {"delta": "..."}`,
`data: {"error": "..."}`, um `data: {"hud": {...}}` antes do `[DONE]` em turno
bem-sucedido, e `data: [DONE]` sempre por último. Erros pré-stream são HTTP:
404 (sessão), 422 (mensagem vazia), 503 (flag `chat` desligada).

### Input do jogador

- `<textarea>` de uma linha que cresce até 5, com `<label>` visualmente oculto
  (`game.input.label`) e `placeholder` `game.input.placeholder`; dica
  `game.input.hint` abaixo do campo.
- `Enter` envia; `Shift+Enter` quebra linha.
- Envio limpa o campo imediatamente e adiciona o turno do jogador ao histórico de
  forma otimista, seguido de um bloco de narrador vazio que recebe o stream.
- Enquanto o turno corre: textarea e botão desabilitados, botão com
  `aria-busy="true"` e rótulo `game.input.sending`.
- Mensagem vazia ou só espaços não envia e não dá erro — o botão fica
  desabilitado enquanto o campo estiver vazio.
- `Esc` no textarea não descarta o texto digitado.

### Streaming

- Antes do primeiro `delta`, o bloco do narrador mostra `game.turn.thinking` com
  `role="status"` e `aria-live="polite"`.
- O bloco em streaming tem `aria-live="off"` — anunciar caractere a caractere é
  inutilizável em leitor de tela. Ao terminar, o fim do turno é anunciado uma vez
  por região `aria-live="polite"` separada, com `game.turn.done` interpolado com
  o índice.
- O texto renderiza incrementalmente com `<TurnText streaming />`, tolerando
  marcação parcial.
- Ao receber `[DONE]`: o bloco perde o estado de streaming, o HUD é atualizado
  com o payload de `hud`, o input volta a ficar habilitado e **recebe o foco**.

### Autoscroll

Durante o streaming o autoscroll acompanha o texto **apenas se** o usuário já
estava no fim; se ele rolou para cima para reler, o autoscroll pausa e aparece um
botão flutuante `game.scrollToLatest` que retoma. Nunca arrastar o usuário de
volta à força. O botão é alcançável por teclado e tem rótulo textual. Com
`prefers-reduced-motion`, todo scroll é instantâneo.

### Estados

| Estado | Comportamento |
|---|---|
| **Ocioso** | Input habilitado; botão desabilitado enquanto o campo estiver vazio. |
| **Enviando** | Turno do jogador no histórico, bloco do narrador com `game.turn.thinking`, controles desabilitados, HUD com `busy` (valores do turno anterior). |
| **Erro no meio do turno** | O bloco em streaming vira bloco de erro com `game.turn.error` / `game.turn.errorBody` + causa em `<details>` e `common.retry` que reenvia **a mesma mensagem**. O turno do jogador continua visível; texto parcial recebido fica acima do erro, marcado com `game.turn.partial`. O HUD entra em `stale`. Nenhum turno parcial é gravado — o backend não grava (TCK-006). |
| **Erro pré-stream** | 503 → `error.chatDisabled.*`; falha de rede → `error.offline.*`; 404 → `game.notFound.title`/`game.notFound.body` com botão de volta para `#/` (`common.back`), sem `common.retry`; demais → `error.unexpected.*` via `describeError`. Tudo no mesmo bloco de erro do turno, com o texto digitado preservado no campo. |
| **Sucesso** | Turno completo no histórico + HUD atualizado + foco de volta no input. Sem toast. |

## Detalhes técnicos

- `streamTurn` implementa o parser de SSE do zero, com a mesma forma do parser
  da Fase 0 (removido pelo TCK-009): checar `response.ok` e `response.body`;
  `pipeThrough(new TextDecoderStream())`; acumular buffer, `split('\n\n')`,
  guardar o último pedaço; por evento, ignorar o que não começa com `data: `;
  `[DONE]` encerra; `parsed.error` vira `onError`; `parsed.delta` vira
  `onDelta`; `parsed.hud` vira `onHud`.
- Estado local acrescentado ao `GameScreen`: `draft` (texto do campo),
  `streamingText`, `lastMessage` (para o retry), `hudStale`, e o valor
  `'streaming'` no `phase` já existente.
- Guarda de envio duplo: o `POST` só sai quando `phase !== 'streaming'`. `Enter`
  repetido rápido dispara um único request — sem debounce por tempo.
- `atBottom` derivado de `scrollHeight - scrollTop - clientHeight < 32`,
  recalculado no evento de scroll do container. Sem `scrollIntoView`
  incondicional.
- Auto-grow do textarea por `rows` calculado a partir de `scrollHeight`, com teto
  de 5 linhas; sem biblioteca.
- O turno otimista recebe o `index` seguinte ao último do histórico; ao fim do
  turno o bloco do narrador assume o mesmo `index` (é o par do backend).
- Falha no meio do stream **não** remove o turno do jogador do histórico local: é
  o que permite o retry sem redigitar. Um `GET` posterior mostra que ele também
  não foi gravado no servidor — comportamento esperado, não divergência.

Testes existentes que este ticket invalida: **nenhum**. `GameScreen.test.tsx`
(TCK-012) é **estendido**, não reescrito: os cenários de leitura continuam
aferindo o que aferiam, e o que muda neles é apenas a preparação (a tela agora
renderiza um formulário no rodapé). No backend, nada muda.

## Contrato público

```ts
// frontend/src/api.ts  (acrescentado)
export type TurnHandlers = {
  onDelta: (delta: string) => void
  onHud: (hud: HudState) => void
  onError: (err: unknown) => void
}
export function streamTurn(sessionId: string, message: string, h: TurnHandlers): Promise<void>
```

`GameScreen` continua consumido apenas por `App.tsx` e não expõe contrato novo.

## Acceptance criteria

- [ ] Enviar mensagem → turno do jogador aparece na hora; bloco do narrador
      começa com `game.turn.thinking`.
- [ ] Deltas chegando → texto cresce no bloco; a região em streaming tem
      `aria-live="off"`.
- [ ] `[DONE]` → input reabilitado e **focado**, HUD refletindo o payload `hud`.
- [ ] `{"error": ...}` no meio → bloco de erro, texto parcial marcado com
      `game.turn.partial`, HUD em `stale`, e `common.retry` reenvia a mesma
      mensagem com sucesso.
- [ ] 503 → `error.chatDisabled.*`; `fetch` rejeitando → `error.offline.*`; a
      mensagem do jogador continua visível nos dois casos.
- [ ] Campo vazio ou só espaços → botão desabilitado, nenhum `POST`.
- [ ] `Shift+Enter` quebra linha; `Enter` envia; duplo `Enter` rápido dispara
      **um** `POST`.
- [ ] Textarea cresce até 5 linhas e para de crescer.
- [ ] Rolar para cima durante o streaming → autoscroll pausa e
      `game.scrollToLatest` aparece; clicar volta ao fim e retoma.
- [ ] `game.turn.done` é anunciado uma única vez por turno concluído.
- [ ] Nenhuma chave de i18n nova; nenhuma string literal na tela.
- [ ] `npm run check` verde.

## Verificação manual

Não aferível em jsdom (sem layout nem scroll real) nem por e2e (`e2e: null` no
`.claude/pipeline.json`):

- Viewport 360px: sem scroll horizontal; o formulário fica visível sem cobrir o
  último turno (`100dvh`).
- `prefers-reduced-motion: reduce`: scroll instantâneo, sem animação.
- **Critério de verde da fase**: jogar 5 turnos no cenário exemplo com o modelo
  local, fechar o app, reabrir e continuar do ponto onde parou.

## Cenários de teste

- Feliz: enviar mensagem, receber 3 deltas + `hud` + `[DONE]` → histórico com o
  par jogador/narrador e HUD atualizado.
- Feliz: dois turnos seguidos → índices corretos e input focado ao fim de cada.
- Borda: stream que termina sem evento `hud` → HUD em `stale` com os valores
  anteriores preservados.
- Borda: delta contendo tag inline (`[SPRITE:chloe:sad]`) → nada da tag aparece
  na tela (filtro de defesa do `TurnText`, TCK-010).
- Borda: mensagem só com espaços → botão desabilitado, nenhum `POST`.
- Borda: `Esc` no textarea → texto digitado permanece.
- Falha: `{"error": ...}` no meio do stream → bloco de erro com causa em
  `<details>`, texto parcial marcado, retry concluindo o turno.
- Falha: `POST` 503 → `error.chatDisabled.*` com a instrução de config, não erro
  genérico.
- Falha: `POST` 404 (sessão apagada durante a partida) →
  `game.notFound.title`/`game.notFound.body` com `common.back` para `#/`, sem
  `common.retry`, e o texto digitado permanece no campo.

## Rollout e kill switch

Sem flag de frontend. O kill switch efetivo é o do backend: `chat: false` em
`~/.ooc-local/config.yaml` faz a rota de turno responder 503 (TCK-006) e a tela
mostra `error.chatDisabled.*` com a instrução de religar — abrir e reler sessões
continua funcionando (é o TCK-012, que não depende da flag). Rollback do ticket é
reverter o PR: a tela volta ao modo leitura e nenhum dado é perdido, porque o
histórico mora no SQLite do backend.

## Observabilidade

Eventos: nenhum no frontend. Todo turno jogado por esta tela aparece no backend
como `game_turn` (`session_id`, `turn`, `duration_ms`, `chars`, `tags`, `error`)
— é lá que se mede se a tela está funcionando.
Métrica de sucesso: 5 turnos seguidos jogados pela UI, com `error: null` em todos
os `game_turn`, e a sessão continuada depois de fechar e reabrir o app.

## i18n

Nenhuma chave nova. Consome `game.input.label`, `game.input.placeholder`,
`game.input.send`, `game.input.sending`, `game.input.hint`, `game.turn.thinking`,
`game.turn.done`, `game.turn.partial`, `game.turn.error`, `game.turn.errorBody`,
`game.scrollToLatest`, `common.retry`, `common.details` e as famílias
`error.offline.*` / `error.chatDisabled.*` / `error.unexpected.*`, todas criadas
no TCK-008.
