---
id: TCK-009
title: Trocar o chat de fumaça pela tela de sessões com criação de sessão
status: in_review
points: 5
blockedBy: [TCK-001, TCK-005, TCK-008, TCK-013]
files:
  - frontend/src/App.tsx
  - frontend/src/api.ts
  - frontend/src/screens/SessionsScreen.tsx
  - frontend/src/screens/SessionsScreen.test.tsx
  - frontend/src/screens/sessions.css
  - frontend/src/strings.ts
  - frontend/src/i18n.test.ts
migration: false
ui: true
risk: low
---

## Problema

`frontend/src/App.tsx` ainda é o chat de fumaça da Fase 0: um `useState` de
mensagens contra `/api/chat`, sem sessão, sem cenário e sem navegação. O jogador
não tem como criar uma sessão nem voltar para uma sessão antiga — que é
literalmente o critério de verde da fase ("fecho o app, reabro, continuo").

## Escopo

Dentro:
- `frontend/src/api.ts`: cliente de `GET /api/scenarios` (contrato do TCK-001)
  e das rotas de sessão do TCK-005 (`GET /api/sessions`, `POST /api/sessions`,
  `GET /api/sessions/:id`) com os tipos do contrato e classificação de erro via
  `describeError` (TCK-013).
- `frontend/src/screens/SessionsScreen.tsx` + `sessions.css`: tela raiz com
  bloco "Nova sessão" e lista "Suas sessões", com todos os estados.
- `frontend/src/App.tsx` reescrito como shell: `<h1>` do app + `useHashRoute()`
  decidindo a tela. O chat de fumaça sai.
- Remoção das quatro chaves legadas de `frontend/src/strings.ts` que só o chat
  de fumaça usava.
- `SessionsScreen.test.tsx` cobrindo os cenários abaixo com `fetch` mockado.

Fora (explícito):
- A tela de jogo: quem registra a rota `#/session/:id` é o TCK-012. Até lá o
  shell trata esse hash pelo fallback do TCK-013 (volta para a lista). Estado
  intermediário aceito e declarado.
- Deletar/renomear sessão, filtro, busca, paginação — a Fase 1 não tem; "não
  desenhar controle que não funciona" (spec, tema 01).
- Remover a rota `/api/chat` do backend: ela continua existindo como rota de
  fumaça e mantém os testes `backend/tests/test_chat.py` e `test_flags.py`
  válidos. Este ticket só deixa de chamá-la.
- Capa/thumbnail de cenário (não há `media/` antes da Fase 2).

## Comportamento esperado

Adaptado do tema 01 da spec de UI.

### Layout

Coluna única: cabeçalho (`app.title`) → bloco "Nova sessão" → lista "Suas
sessões". O bloco de criação vem **antes** da lista: é a ação que sempre existe,
inclusive no primeiro uso. A tela **nunca** exibe `id` cru como rótulo
principal; `id` só aparece como `title`/tooltip de apoio.

### Nova sessão

- Um `<select>` de cenário rotulado por `<label for>`
  (`sessions.new.scenarioLabel`) + botão primário `sessions.new.submit`.
- Com **um único cenário disponível**, o select renderiza mesmo assim, já
  selecionado e habilitado — a UI não muda de forma quando a Fase 2 trouxer mais
  cenários.
- A tagline do cenário selecionado aparece abaixo do select como texto
  secundário, se houver.
- Ao submeter: botão entra em estado ocupado (`aria-busy="true"`, rótulo
  `sessions.new.submitting`, desabilitado), select desabilitado. Duplo clique
  não cria duas sessões.
- **Sucesso**: navega direto para `#/session/:id`. O feedback de sucesso é a tela
  de jogo com o prólogo — não há toast redundante.
- **Erro**: `ErrorState` inline abaixo do botão, com `title =
  error.unexpected.title` e `body = sessions.new.error`; controles voltam a
  ficar habilitados e o valor do select é preservado. Nenhuma navegação
  acontece.

### Lista de sessões

- `<ul>` de itens; cada item é um único elemento clicável contendo nome do
  cenário (linha 1, texto primário) e metadados (linha 2, texto secundário):
  `sessions.item.meta` com contagem de turnos + tempo relativo desde
  `updatedAt`.
- Contagem de turnos usa plural: 0 → `sessions.item.turnsZero`, 1 →
  `sessions.item.turnsOne`, N → `sessions.item.turnsOther`.
- Tempo relativo por `Intl.RelativeTimeFormat` no locale ativo (`intlLocale` do
  TCK-008); `updatedAt` completo vai no `title` do item.
- Ordenação vem pronta do backend (`updatedAt` desc); a tela não reordena.
- Clique/`Enter` navega para `#/session/:id`.
- Fase 1 **não** tem deletar nem renomear sessão.

### Estados

| Estado | Comportamento |
|---|---|
| **Carregando** | Skeleton de 3 itens de lista (altura fixa, sem texto) mais um `Loading` com texto `sessions.loading` visível só para leitor de tela. Skeleton porque a altura da lista é previsível e evita salto de layout. |
| **Vazio** | `EmptyState` com `sessions.empty.title` + `sessions.empty.body`, apontando para o bloco de nova sessão logo acima. Sem botão duplicado. |
| **Erro** | `ErrorState` no lugar da lista, com `common.retry` que refaz o `GET /api/sessions`. O bloco de nova sessão continua utilizável se os cenários carregaram. Backend fora do ar usa `error.offline.*`. |
| **Erro só nos cenários** | Select desabilitado com `sessions.new.scenariosError` e botão desabilitado; a lista de sessões existentes continua navegável. |
| **Sucesso** | Navegação para a tela de jogo. |

### Acessibilidade

- `<h1>` = `app.title`; `<h2>` = `sessions.new.heading` e `sessions.heading`.
- Lista é `<ul>`/`<li>`; item inteiro é o alvo clicável, altura mínima 44px.
- Select tem `<label>` associado, não `placeholder`-como-rótulo.
- Estado ocupado do botão via `aria-busy`, e o texto muda (não só o spinner).
- Ao entrar na tela, o foco vai para o `<h1>` (`tabIndex={-1}` + `focus()`).

### Responsividade (360px)

Select e botão empilham em coluna, ambos com largura total, abaixo de 480px;
metadados do item quebram em duas linhas em vez de truncar; nome de cenário
longo quebra por palavra, sem scroll horizontal.

## Detalhes técnicos

- `api.ts` exporta funções tipadas e uma classe `ApiError` com `status`, para
  `describeError` (TCK-013) mapear 503 e falha de rede nas chaves certas. Os
  tipos `SessionSummary`, `SessionDetail`, `ScenarioSummary`, `HudState` e
  `TurnView` vêm do contrato público do TCK-005/TCK-001 e ficam neste arquivo
  (o TCK-012 os reusa, não os redeclara).
- Proteção de duplo clique é por estado local (`submitting`), não por debounce de
  tempo: o `POST` só sai quando `submitting === false`.
- O carregamento de cenários e o de sessões são independentes: uma falha não
  bloqueia a outra (dois estados separados, não um `Promise.all`).
- Fetch relativo (`/api/...`), aproveitando o proxy do Vite já configurado no
  `dev` — nada de URL absoluta com porta fixa.
- `App.tsx` não guarda estado de tela: a rota é a fonte da verdade.

Testes existentes que este ticket invalida: a parte do `i18n.test.ts` (TCK-008)
que afere as quatro chaves legadas (`title`, `placeholder`, `send`, `error`) —
este ticket remove essas linhas do teste junto com as chaves. Nenhum outro teste
automatizado é afetado (o chat de fumaça que sai não tinha teste próprio).
O que mais se invalida é **comportamento manual da Fase 0**: mandar "oi" na
tela inicial e ver o modelo responder deixa de existir. Isso é intencional e
está no critério de verde da Fase 1, que substitui o da Fase 0. Os testes de
backend de `/api/chat` continuam válidos porque a rota não é removida.

## Contrato público

```ts
// frontend/src/api.ts  (consumido pelo TCK-012)
export class ApiError extends Error { status: number }
export type ScenarioSummary = { id: string; name: string; tagline: string | null; locale: string }
export type HudState = { turn: number; location: string; time: string; weather: string }
export type TurnView = { index: number; role: 'player' | 'narrator'; text: string }
export type SessionSummary = { id: string; scenarioId: string; scenarioName: string; turnCount: number; updatedAt: string; location: string }
export type SessionDetail = { id: string; scenarioId: string; scenarioName: string; prologue: string; playGuide: string | null; turns: TurnView[]; hud: HudState }

export function fetchScenarios(): Promise<ScenarioSummary[]>
export function fetchSessions(): Promise<SessionSummary[]>
export function createSession(scenarioId: string): Promise<SessionDetail>
export function fetchSession(id: string): Promise<SessionDetail>
```

## Acceptance criteria

- [ ] Sem sessões → `EmptyState` e bloco de criação utilizável.
- [ ] Com 3 sessões → 3 itens na ordem devolvida pela API, com plural correto de
      turnos em `en` e `pt-br`.
- [ ] `GET /api/sessions` pendente → skeleton de 3 itens, sem salto de layout.
- [ ] `GET /api/sessions` 500 → `ErrorState`; `common.retry` refaz a chamada.
- [ ] `fetch` rejeitando (backend desligado) → `error.offline.*`, não
      `error.unexpected.*`.
- [ ] `GET /api/scenarios` falhando → select desabilitado com
      `sessions.new.scenariosError`, lista ainda navegável.
- [ ] Dois cliques rápidos em "Criar" disparam **um** `POST /api/sessions`.
- [ ] `POST` 500 → erro inline, controles reabilitados, hash inalterado.
- [ ] `POST` 201 → hash vira `#/session/:id`.
- [ ] Clicar num item navega para o hash da sessão.
- [ ] Nenhuma string literal na tela; nenhuma chave nova em `strings.ts`.
- [ ] `npm run check` verde.

## Cenários de teste

- Feliz: lista com 3 sessões renderizada, ordem preservada, `title` com a data
  completa.
- Feliz: criar sessão → `POST` chamado uma vez → `location.hash ===
  '#/session/<id>'`.
- Feliz: plural 0/1/7 nos dois locales.
- Borda: um único cenário → select renderizado, habilitado e já selecionado.
- Borda: cenário sem tagline → nenhuma linha secundária vazia.
- Borda: `updatedAt` de agora e de 3 dias atrás → tempo relativo coerente nos
  dois locales.
- Falha: `GET /api/sessions` 500 → `ErrorState` + retry funcional.
- Falha: `POST /api/sessions` 500 → erro inline, sem navegação, select com o
  valor preservado.
- Falha: `fetch` rejeita → família `error.offline.*`.

Verificação manual (fora do `verify`; anotar no PR): viewport 360px → select e
botão em coluna, sem scroll horizontal.

## Rollout e kill switch

N/A — a troca da tela inicial é o objetivo do ticket; não há caminho de
convivência entre o chat de fumaça e a lista de sessões. Rollback é reverter o
PR (o backend não muda, então reverter a UI não deixa dado órfão).

## Observabilidade

Eventos: nenhum no frontend (a Fase 1 não tem canal de telemetria de UI). Os
sinais desta tela aparecem no backend: `session_created`
(TCK-005) por sessão criada.
Métrica de sucesso: sessão criada pela UI e reaberta pela lista depois de
recarregar a página, sem passar por URL digitada à mão.

## i18n

Nenhuma chave nova: consome `app.title`, `common.retry`, `common.details`,
`common.loading`, `error.offline.*`, `error.unexpected.*` e toda a família
`sessions.*` criada no TCK-008. Remove de `strings.ts` as quatro chaves legadas
da Fase 0 (`title`, `placeholder`, `send`, `error`), que só o chat de fumaça
usava.
