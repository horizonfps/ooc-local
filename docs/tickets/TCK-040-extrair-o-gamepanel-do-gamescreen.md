---
id: TCK-040
title: Extrair o GamePanel reutilizavel de dentro do GameScreen
status: done
points: 3
blockedBy: []
files:
  - frontend/src/components/GamePanel.tsx
  - frontend/src/components/GamePanel.test.tsx
  - frontend/src/screens/GameScreen.tsx
  - frontend/src/screens/GameScreen.test.tsx
  - frontend/src/screens/game.css
migration: false
ui: false
risk: medium
---

## Problema

O preview do builder é a mesma engine e os mesmos componentes do jogo — a spec é
explícita: "preview que diverge do jogo é preview que mente". Hoje toda a lógica
de jogo (carregar sessão, streaming de turno, HUD, histórico com autoscroll,
tratamento de erro, foco) vive dentro do `GameScreen`, amarrada à rota e à
topbar de "voltar para as sessões".

Sem extrair isso primeiro, o TCK-041 copiaria o `GameScreen` — e a segunda
cópia começaria a divergir no primeiro bug corrigido só de um lado.

## Escopo

Dentro:
- Novo `frontend/src/components/GamePanel.tsx` com **todo** o comportamento de
  jogo hoje em `GameScreen`, exceto a topbar de rota.
- `GameScreen` vira o wrapper de rota: topbar (voltar + `h1` com o nome do
  cenário), `document.title` e `<GamePanel />`.
- CSS: as classes de jogo continuam em `game.css` e continuam com os mesmos
  nomes.

Fora (explícito):
- Qualquer mudança de comportamento. Este ticket é refactor puro: nenhuma
  string nova, nenhuma prop nova de produto, nenhum estado novo.
- Sprites e background (TCK-042) e o painel de preview (TCK-041) — os dois
  entram depois, em cima deste `GamePanel`.

## Comportamento esperado

Idêntico ao de hoje, do ponto de vista de quem joga. A prova disso é a suíte:
`GameScreen.test.tsx` continua passando inteira, com as mesmas asserções.

## Detalhes técnicos

`GamePanel` recebe:

```ts
export type GamePanelProps = {
  sessionId: string
  onNotFound?: () => void          // GameScreen usa para o botão "voltar"
  regionLabel?: string             // aria-label do container; ausente = sem label
  autoFocusInput?: boolean         // default true
}
```

Movem-se para dentro do `GamePanel`, sem alteração de lógica:

- estado `GameState`, `PendingTurn`, `load()`, o efeito de `fetchSession` e a
  classificação `notFound` vs `error`;
- todo o ciclo de turno (`runTurn`, `submit`, `retry`, `handleFormSubmit`,
  `handleKeyDown`), o `sendingRef`, o `AbortController` e o efeito de cleanup;
- HUD (`hud`, `hudStale`) e o `<Hud />`;
- histórico, autoscroll coalescido por `requestAnimationFrame`, `atBottom`,
  `jumpToLatest`, `isReducedMotion`, `scrollToBottom`;
- textarea auto-resize, `focusToken`, região live de `doneAnnouncement`;
- todos os ramos de erro de turno (`stream`, `chatDisabled`, `offline`,
  `unexpected`, `notFound`) exatamente como estão.

Ficam no `GameScreen`:

- `div.game-topbar` com o botão `game.back` (`navigate('#/')`) e o `h1` com o
  nome do cenário e foco na montagem;
- `document.title` interpolado com `game.documentTitle`;
- o botão de voltar do estado `notFound`, hoje dentro do bloco de erro — o
  `GamePanel` chama `onNotFound` e o wrapper decide o que oferecer.

Armadilhas conhecidas:

- **O nome do cenário e o HUD vivem no `GamePanel`**, porque vêm do
  `fetchSession`. Para a topbar do `GameScreen` continuar mostrando o nome, o
  `GamePanel` aceita `onSessionLoaded?: (session: SessionDetail) => void` e o
  wrapper guarda o nome. Não duplique o `fetch`.
- O elemento raiz do `GamePanel` **não** pode ser `<main>` (o wrapper já é):
  use `<div className="game-panel">` e mantenha as classes internas
  (`game-history`, `game-footer`, `game-turn*`) intactas, para o CSS e os
  seletores dos testes não mudarem.
- O `<label htmlFor="game-input">` e o `id="game-input"` viram únicos por
  instância (o preview e o jogo podem coexistir na mesma página): derive o id de
  `useId()` e passe para o `htmlFor`. Os testes buscam o textarea por `role` e
  por label, não por id — confirme isso ao adaptar.
- Efeitos que hoje dependem de `sessionId` para resetar estado continuam
  dependendo dele dentro do `GamePanel`; o teste "refetches without mixing
  history when the sessionId prop changes" cobre isso e não pode mudar.

## Contrato público

```ts
// frontend/src/components/GamePanel.tsx
export type GamePanelProps = {
  sessionId: string
  onNotFound?: () => void
  onSessionLoaded?: (session: SessionDetail) => void
  regionLabel?: string
  autoFocusInput?: boolean
}
export function GamePanel(props: GamePanelProps): React.JSX.Element
```

Consumidores: TCK-041 (painel de preview no editor) e TCK-042 (acrescenta a
camada de cena dentro do painel).

## Acceptance criteria

- [ ] `GameScreen.test.tsx` passa **inteiro**, sem asserção alterada.
- [ ] Duas instâncias de `GamePanel` na mesma página não colidem em id de
      elemento (o `htmlFor` do label aponta para o textarea da própria
      instância).
- [ ] Nenhuma string nova em `strings.ts`.
- [ ] `game.css` sem classe renomeada.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente do fluxo: `frontend/src/screens/GameScreen.test.tsx` — os ~40
testes de render, turno, streaming, erro, scroll, aborto e acessibilidade são a
rede de segurança deste refactor. **Adaptação permitida**: só de preparação
(import, helper de render, seletor que dependia de id fixo). Toda asserção fica
como está; asserção alterada aqui é sinal de que o refactor mudou
comportamento — e aí o refactor é que está errado.

Cenários novos (`GamePanel.test.tsx`, só o que o wrapper não cobre):
- Feliz: `GamePanel` isolado carrega a sessão, joga um turno e atualiza o HUD.
- Borda: duas instâncias montadas com `sessionId` diferentes mantêm históricos
  separados e labels apontando para os próprios textareas.
- Borda: `autoFocusInput={false}` não rouba o foco na montagem.
- Falha: 404 chama `onNotFound` uma única vez e não renderiza o botão de voltar
  (que é do wrapper).

## Rollout e kill switch

N/A — refactor sem flag. `risk: medium` por ser cirurgia num arquivo com muito
comportamento acumulado; a mitigação é a suíte existente passar sem alteração de
asserção.

## Observabilidade

Eventos: nenhum.
Métrica de sucesso: jogar um turno no jogo depois do refactor e não notar
diferença nenhuma.

## i18n

N/A — nenhuma chave nova; todas as strings de jogo continuam onde estão.
