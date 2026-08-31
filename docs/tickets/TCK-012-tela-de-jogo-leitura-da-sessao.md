---
id: TCK-012
title: Abrir a sessão na tela de jogo com prólogo, histórico e HUD
status: done
points: 3
blockedBy: [TCK-008, TCK-009, TCK-010, TCK-011, TCK-013]
files:
  - frontend/src/screens/GameScreen.tsx
  - frontend/src/screens/GameScreen.test.tsx
  - frontend/src/screens/game.css
  - frontend/src/App.tsx
migration: false
ui: true
risk: low
---

## Problema

Depois do TCK-009 a lista de sessões existe, mas o hash `#/session/:id` cai de
volta na lista: não há tela de jogo. As peças de leitura estão prontas e soltas —
`fetchSession` (TCK-009), `TurnText` (TCK-010), `Hud` (TCK-011), estados de erro
(TCK-013) — e nada as monta. Sem esta tela não dá para conferir a metade
"reabro e continuo" do critério de verde da fase.

## Escopo

Dentro:
- `frontend/src/screens/GameScreen.tsx` + `game.css`: barra de topo, HUD,
  histórico rolável (prólogo + turnos já gravados). **Somente leitura.**
- Registro da rota `game` em `frontend/src/App.tsx` (uma linha no switch de rota
  do TCK-009).
- `document.title` por `game.documentTitle`, restaurado ao sair da tela.
- Estados: carregando, vazio (só prólogo), 404 e erro genérico.
- `GameScreen.test.tsx` com `fetch` mockado.

Fora (explícito):
- Input, envio de turno, streaming SSE, erro de turno e autoscroll — **TCK-014**.
  Nesta tela não existe campo de texto: o histórico é de leitura e o input entra
  no ticket seguinte.
- `streamTurn` em `api.ts`: nasce no TCK-014, junto do seu único consumidor.
- Cancelar/regenerar/editar turno, rewind — Fase 1 não tem (rewind é Fase 7).
- Sprites, backgrounds, sugestões clicáveis, painel de stats/INFO — Fases 2 a 5.
- Apagar ou renomear sessão.
- Reimplementar parsing de texto ou HUD: vêm prontos do TCK-010 e TCK-011.

## Comportamento esperado

Adaptado do tema 02 da spec de UI.

### Dados

`GET /api/sessions/:id` → `{ id, scenarioId, scenarioName, prologue, playGuide,
turns[], hud }`; `turns[]` já vem com o texto **limpo** de tags (limpeza é do
engine, TCK-006).

### Layout (de cima para baixo)

1. Barra de topo: botão `game.back` (volta para `#/`) + nome do cenário.
2. HUD (`Hud`, TCK-011), fixo abaixo da barra, alimentado pelo `hud` do `GET`.
3. Histórico rolável: prólogo → turnos em ordem cronológica.
4. Rodapé reservado para o formulário do TCK-014 (área vazia, altura já
   reservada, para a tela não mudar de layout quando o input chegar).

Reusa a estrutura da `.chat` da Fase 0 (coluna flex, histórico com `flex: 1` e
`overflow-y: auto`).

### Prólogo

Primeiro bloco do histórico, sempre presente, com marcação visual distinta dos
turnos e o rótulo `game.prologue.label`. Renderizado pelo `TurnText`. Não é
apagável nem regenerável na Fase 1.

### Histórico de turnos

- Turno do jogador: alinhado à direita, fundo `#2b3a55`, **sem itálico** (é ação
  digitada, não narração).
- Turno do narrador: alinhado à esquerda, largura total, via `TurnText`.
- Sem avatar, sem timestamp — Fase 1 é texto puro.
- Ao abrir a sessão, o histórico começa **no fim** (última mensagem visível), sem
  animação.

### Estados

| Estado | Comportamento |
|---|---|
| **Carregando** | Skeleton: HUD com `hud={null}` e 2 blocos de texto cinza no histórico; `Loading` com `game.loading` para leitor de tela. |
| **Vazio** | Sessão recém-criada = prólogo sem turnos. Não é erro: abaixo do prólogo aparece `game.empty.hint`. |
| **Erro (404)** | `ErrorState` com `game.notFound.title`/`game.notFound.body` e um botão que volta para a lista (`common.back`). **Sem** `common.retry` — 404 não melhora com nova tentativa. |
| **Erro (outro)** | `ErrorState` de `describeError` com `common.retry` refazendo o `GET`. |
| **Sucesso** | Prólogo + turnos + HUD do estado atual. |

### Acessibilidade

`<h1>` = nome do cenário da sessão; ao entrar na tela o foco vai para ele
(`tabIndex={-1}` + `focus()`). Histórico é `<ol>` de turnos, com o papel de cada
turno em rótulo textual (`game.turn.playerLabel` / `game.turn.narratorLabel`),
não só por cor e alinhamento. O botão voltar é alcançável por teclado.

### Responsividade (360px)

Barra de topo com botão voltar e nome do cenário truncando em uma linha (`title`
com o nome completo); `100dvh` na coluna; turnos com largura total.

## Detalhes técnicos

- Estado local: `session` (do `GET`), `phase` (`loading` | `ready` | `error`),
  `error`. Nada disso sobe para `App.tsx` — a rota é a fonte da verdade.
- O `GET` é disparado por `useEffect` sobre o `id` da rota; trocar de sessão pela
  URL refaz a busca.
- 404 é distinguido pelo `status` do `ApiError` (TCK-009); os demais erros passam
  por `describeError` (TCK-013).
- Scroll inicial no fim: `scrollTop = scrollHeight` aplicado uma vez, sem
  `behavior: 'smooth'` (a spec pede sem animação ao abrir).
- `document.title` em `useEffect` com cleanup restaurando o valor anterior.
- O tipo `HudState` (de `api.ts`, TCK-009) é assinável a `HudView` (de
  `Hud.tsx`, TCK-011, que tem `location`/`weather` opcionais); esta tela é o
  primeiro lugar onde os dois se encontram e é responsável por mantê-los
  alinhados.

Testes existentes que este ticket invalida: **nenhum**. `App.tsx` recebe uma
linha de rota (o TCK-009 já removeu o chat de fumaça, que não tinha teste); os
testes de `SessionsScreen`, `TurnText` e `Hud` não são tocados. No backend, nada
muda.

## Contrato público

`GameScreen` é consumido apenas por `App.tsx`. O TCK-014 estende **este mesmo
arquivo** e depende da estrutura interna acordada aqui:

```ts
// frontend/src/screens/GameScreen.tsx
export function GameScreen(props: { sessionId: string }): JSX.Element
```

Pontos de extensão reservados para o TCK-014: o rodapé do layout (onde entra o
formulário), a lista de turnos renderizada (que passará a aceitar um turno
otimista e um bloco em streaming) e o estado `phase`, que ganhará o valor
`'streaming'`.

## Acceptance criteria

- [ ] `#/session/:id` renderiza a tela de jogo (rota registrada em `App.tsx`).
- [ ] Sessão nova (só prólogo) → prólogo + `game.empty.hint`.
- [ ] Sessão com 5 turnos → todos renderizados na ordem, com os rótulos de papel.
- [ ] O HUD recebe o `hud` do `GET`; enquanto carrega, recebe `null`.
- [ ] `GET` 404 → `game.notFound.*` com botão de volta para a lista e **sem**
      `common.retry`.
- [ ] `GET` 500 → `ErrorState` com `common.retry` que refaz a chamada com
      sucesso.
- [ ] `fetch` rejeitando → `error.offline.*` (via `describeError`).
- [ ] Botão voltar leva o hash para `#/`.
- [ ] `document.title` vira `game.documentTitle` interpolado com o nome do
      cenário e é restaurado ao desmontar.
- [ ] O foco vai para o `<h1>` ao entrar na tela.
- [ ] Nenhuma chave de i18n nova; nenhuma string literal na tela.
- [ ] `npm run check` verde.

## Verificação manual

Não aferível em jsdom (sem layout/scroll real) nem por e2e (`e2e: null`):

- Abrir uma sessão com 20 turnos e confirmar que o histórico começa no fim.
- Viewport 360px: sem scroll horizontal; nome de cenário longo truncado em uma
  linha com `title` completo.
- Criar sessão pela lista, jogar (depois do TCK-014), fechar o app, reabrir e
  confirmar o mesmo histórico e o mesmo HUD.

## Cenários de teste

- Feliz: sessão com prólogo + 2 turnos → 3 blocos na ordem, prólogo com o rótulo
  `game.prologue.label`.
- Feliz: prólogo com fala `**Chloe** | ...` renderizado pelo `TurnText` (nome em
  `<strong>`, sem `|` na tela).
- Feliz: navegar da lista para o jogo e voltar pelo botão → hash `#/`.
- Borda: `playGuide` nulo → nenhuma seção vazia.
- Borda: sessão com 0 turnos → `game.empty.hint` visível, sem `<ol>` vazio
  anunciado como lista.
- Borda: trocar o `sessionId` da rota → novo `GET`, tela remontada sem misturar
  histórico.
- Falha: `GET` 404 → estado próprio, sem botão de retry.
- Falha: `GET` 500 → `ErrorState` com retry funcional.
- Falha: `fetch` rejeita → família `error.offline.*`, não `error.unexpected.*`.

## Rollout e kill switch

N/A — tela de leitura, sem escrita e sem chamada de LLM. Rollback é reverter o
PR: a rota `#/session/:id` volta ao fallback da lista e nenhum dado é perdido (o
histórico mora no SQLite do backend).

## Observabilidade

Eventos: nenhum no frontend (a Fase 1 não tem canal de telemetria de UI). Os
sinais desta tela aparecem no backend, nos logs de `GET /api/sessions/{id}`.
Métrica de sucesso: reabrir uma sessão existente mostra o mesmo histórico e o
mesmo HUD de antes de fechar o app.

## i18n

Nenhuma chave nova. Consome `game.documentTitle`, `game.loading`, `game.back`,
`game.prologue.label`, `game.empty.hint`, `game.turn.playerLabel`,
`game.turn.narratorLabel`, `game.notFound.title`, `game.notFound.body`,
`common.back`, `common.retry`, `common.details` e as famílias de erro
`error.offline.*` / `error.unexpected.*`, todas criadas no TCK-008.
