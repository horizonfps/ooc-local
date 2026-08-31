---
id: TCK-013
title: Navegar por hash e padronizar estados vazio, carregando e erro na UI
status: ready
points: 3
blockedBy: [TCK-008]
files:
  - frontend/src/useHashRoute.ts
  - frontend/src/useHashRoute.test.ts
  - frontend/src/errors.ts
  - frontend/src/errors.test.ts
  - frontend/src/components/EmptyState.tsx
  - frontend/src/components/Loading.tsx
  - frontend/src/components/ErrorState.tsx
  - frontend/src/components/states.test.tsx
  - frontend/src/components/states.css
  - frontend/src/index.css
migration: false
ui: true
risk: low
---

## Problema

A Fase 1 tem duas telas e cinco estados de erro distintos, e o app hoje não tem
navegação nenhuma: `frontend/src/App.tsx` renderiza uma tela só, e
`frontend/src/index.css` tem `height: 100vh` (`index.css:18`), nenhum estilo de
foco visível e nenhum tratamento de `prefers-reduced-motion`. Sem uma rota e sem
componentes de estado compartilhados, cada uma das quatro telas/componentes
seguintes inventaria os seus — com textos de erro diferentes para a mesma falha.

Este ticket é a outra metade do **interface freeze** de UI (a primeira é o
TCK-008). Consumidores já enfileirados: TCK-009, TCK-012, TCK-014.

## Escopo

Dentro:
- `useHashRoute()` + `navigate()`: rota por `location.hash`, sem dependência
  nova.
- `describeError(err)` em `frontend/src/errors.ts`: classifica falha em uma das
  três famílias de chave de erro.
- `EmptyState`, `Loading`, `ErrorState` + `states.css`.
- Linha de base de `index.css`: tokens de cor, foco visível, alvo de toque,
  `prefers-reduced-motion`, `100dvh`, breakpoint de 480px, sem scroll horizontal
  em 360px.

Fora (explícito):
- Chaves de i18n: todas já existem (TCK-008). Este ticket **não** cria chave.
- Qualquer tela: `App.tsx` não é tocado; quem o reescreve é o TCK-009.
- Router de biblioteca (react-router): a Fase 1 tem duas rotas.
- Tema claro, design system, animação de entrada — "nada de UI bonita antes da
  Fase 8" (plano, regra 5).
- Toast/snackbar: a Fase 1 não tem feedback flutuante (a spec diz explicitamente
  que sucesso não gera toast).

## Comportamento esperado

Adaptado do tema 00 da spec de UI.

### Navegação

| Hash | Rota devolvida |
|---|---|
| `#/` ou vazio | `{ name: 'sessions' }` |
| `#/session/:id` | `{ name: 'game', id }` |
| qualquer outro | `{ name: 'sessions' }` (fallback silencioso, hash normalizado para `#/`) |

- Hash é a fonte de verdade da tela; o botão Voltar do navegador funciona.
- `#/session/abc` colado direto na barra de endereços resolve para a rota de jogo
  com `id = 'abc'` (quem carrega do backend é a tela).
- O hook lê no boot e assina `hashchange`, removendo o listener no unmount.
- `navigate(hash)` é exportado para as telas trocarem de rota sem tocar em
  `location` diretamente.
- O hook devolve um objeto discriminado, não uma string: nenhuma tela faz regex
  de hash.

### Classificação de erro

Regra do projeto: toda mensagem de erro tem **o que falhou** + **o que fazer**.
`describeError(err)` devolve `{ title, body, cause }` já traduzidos:

| Entrada | Família |
|---|---|
| `TypeError` de `fetch` (backend fora do ar) | `error.offline.*` |
| erro com `status === 503` | `error.chatDisabled.*` |
| qualquer outra coisa, inclusive `undefined` | `error.unexpected.*` |

`cause` é a mensagem técnica original (ou string vazia), destinada ao
`<details>` do `ErrorState`. Erros de 404 na tela de jogo **não** passam por
aqui: têm texto próprio (`game.notFound.*`) e tratamento no TCK-012.

### Componentes de estado (reuso obrigatório nos consumidores)

| Componente | Uso |
|---|---|
| `EmptyState` | título + descrição + ação primária opcional |
| `Loading` | `role="status"` + `aria-live="polite"` + texto de i18n; sem spinner infinito mudo; opção de texto visível só para leitor de tela |
| `ErrorState` | título, mensagem legível (nunca só "algo deu errado"), causa técnica em `<details>` com rótulo `common.details` e botão `common.retry` opcional |

### Acessibilidade (linha de base para todos os temas)

- Contraste mínimo AA (4.5:1) sobre `#14151a`; o cinza `#8a8f9e`
  (`index.css:24`) passa e vira o token de texto secundário.
- Foco visível em todo elemento interativo: `:focus-visible` com outline de 2px e
  `outline-offset: 2px`. Proibido `outline: none` sem substituto.
- Alvo de toque mínimo 44×44px em botões e itens de lista clicáveis.
- Operável só por teclado: `Tab` na ordem visual, `Enter`/`Space` ativam.
- `prefers-reduced-motion: reduce` desliga transições e scroll suave.
- Conteúdo visível por padrão: nada condicionado a animação de entrada.

### Responsividade

Menor breakpoint suportado: **360px**. Coluna única, `max-width: 720px`
centralizado (já em `.chat`), padding 1rem caindo para 0.75rem abaixo de 480px,
`overflow-wrap: anywhere` no texto, botões em linha que não cabem viram bloco de
largura total, altura por `100dvh` (hoje `100vh`, `index.css:18`).

## Detalhes técnicos

- `useHashRoute` normaliza o hash com `location.replace` quando cai no fallback,
  para não empilhar entrada de histórico inválida.
- `#/session/` sem id resolve para `sessions` (id vazio não é sessão).
- Testes de rota manipulam `location.hash` e disparam `hashchange` no jsdom;
  Testing Library e vitest vêm do TCK-008.
- **CSS por componente**: cada componente traz seu `.css` importado do `.tsx`
  (Vite resolve). `index.css` fica só com tokens, reset e a linha de base. Essa
  convenção é contrato deste ticket e existe para os tickets de UI seguintes não
  disputarem `index.css`.
- Tokens como custom properties em `:root` (`--bg`, `--fg`, `--fg-muted`,
  `--accent`, `--surface`, `--focus`), com os valores já usados hoje, para os
  componentes pararem de repetir hex.
- `ErrorState` só renderiza o botão quando recebe `onRetry` — botão que não faz
  nada é pior que ausência de botão.
- `describeError` recebe `unknown` e nunca lança: é chamado de dentro de `catch`.

Testes existentes que este ticket invalida: **nenhum**. O frontend não tinha
teste antes do TCK-008, e `App.tsx` não é tocado. As regras novas de `index.css`
são aditivas (foco, tokens, media queries) fora a troca de `100vh` por `100dvh`,
que muda só a altura efetiva da coluna no mobile.

## Contrato público

```ts
// frontend/src/useHashRoute.ts
export type Route = { name: 'sessions' } | { name: 'game'; id: string }
export function useHashRoute(): Route
export function navigate(hash: string): void        // ex.: navigate('#/session/abc')

// frontend/src/errors.ts
export function describeError(err: unknown): { title: string; body: string; cause: string }

// frontend/src/components/*
export function EmptyState(props: { title: string; body: string; action?: ReactNode }): JSX.Element
export function Loading(props: { label: string; visuallyHidden?: boolean }): JSX.Element
export function ErrorState(props: { title: string; body: string; cause?: string; onRetry?: () => void }): JSX.Element
```

Tokens CSS expostos em `:root`: `--bg`, `--fg`, `--fg-muted`, `--surface`,
`--accent`, `--focus`.

## Acceptance criteria

- [ ] `useHashRoute` devolve `sessions` para `''`, `'#/'`, `'#/foo'` e
      `'#/session/'`, e `game` com o id para `'#/session/abc'`.
- [ ] Hash desconhecido é normalizado para `#/` sem empilhar histórico.
- [ ] `hashchange` atualiza a rota; o listener é removido no unmount.
- [ ] `navigate('#/session/abc')` muda `location.hash` e a rota devolvida.
- [ ] `Loading` tem `role="status"` e `aria-live="polite"`.
- [ ] `ErrorState` mostra a causa em `<details>` e só renderiza o botão quando
      recebe `onRetry`; o botão chama o handler.
- [ ] `EmptyState` renderiza a ação opcional quando recebida e nada quando não.
- [ ] `describeError` classifica `TypeError` de rede, objeto com `status: 503`,
      `Error` genérico e `undefined` nas famílias corretas, sem lançar.
- [ ] Nenhuma string literal nos componentes (todo texto vem por prop ou de
      `t()`).
- [ ] `npm run check` verde.

## Verificação manual

Não aferível em jsdom (sem layout) nem por e2e (`e2e: null` no
`.claude/pipeline.json`); conferido à mão antes do merge:

- Viewport 360×640 no navegador: nenhuma barra de rolagem horizontal na tela
  existente.
- `prefers-reduced-motion: reduce` ligado no SO/DevTools: nenhuma transição
  dispara.
- Percorrer a tela só com `Tab`: foco visível em todo elemento interativo.
- Contraste dos tokens conferido no DevTools (AA, 4.5:1).

## Cenários de teste

- Feliz: percurso `#/` → `#/session/abc` → Voltar → `#/`.
- Feliz: os três componentes de estado renderizam com os papéis ARIA corretos.
- Feliz: `describeError` nas quatro entradas da tabela.
- Borda: dois `hashchange` seguidos → última rota vence, sem listener duplicado.
- Borda: `ErrorState` sem `cause` → nenhum `<details>` vazio.
- Borda: `Loading` com `visuallyHidden` → texto presente no DOM e fora do fluxo
  visual.
- Falha: `navigate` com hash malformado (`'session/abc'`, sem `#/`) → normalizado
  para `#/`, sem lançar.
- Falha: `describeError(null)` → `error.unexpected.*`.

## Rollout e kill switch

N/A — módulos novos sem tela nova. Rollback é reverter o PR; o único efeito
visível no app existente é a linha de base de CSS.

## Observabilidade

Eventos: nenhum. O frontend da Fase 1 não tem canal de telemetria e este ticket
não abre esse canal.
Métrica de sucesso: TCK-009, TCK-012 e TCK-014 não implementam rota, estado de
erro nem componente de estado próprio — se algum implementar, o freeze falhou.

## i18n

Nenhuma chave nova. Consome, via `describeError` e via os consumidores,
`common.retry`, `common.details`, `common.loading`, `app.skipToContent` e as três
famílias `error.offline.*`, `error.chatDisabled.*` e `error.unexpected.*`,
criadas no TCK-008.
