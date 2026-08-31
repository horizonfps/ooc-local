---
id: TCK-023
title: Preservar o detail do backend e unificar a classificação de erro da tela de jogo
status: in_review
points: 3
blockedBy: [TCK-022]
files:
  - frontend/src/api.ts
  - frontend/src/errors.ts
  - frontend/src/errors.test.ts
  - frontend/src/screens/GameScreen.tsx
  - frontend/src/screens/GameScreen.test.tsx
migration: false
ui: true
risk: low
---

## Problema

Três defeitos no tratamento de erro e no primeiro frame da tela de jogo:

1. **O `detail` do FastAPI é jogado fora.** `request` (`frontend/src/api.ts:32`)
   e `streamTurn` (`:73`) fazem `throw new ApiError(response.status, `HTTP
   ${response.status}`)` sem ler o corpo. O backend responde
   `{"detail": "chat disabled by flag"}`, `{"detail": "session not found"}`,
   `{"detail": "scenario not found"}` e `{"detail": "message must not be
   empty"}` (`backend/app/main.py:65`, `:80`, `:125`, `:128`), e nada disso
   chega à tela: o `<details>` de detalhe técnico do `ErrorState`
   (`frontend/src/components/ErrorState.tsx:9`, alimentado por
   `describeError(...).cause`) mostra literalmente `"HTTP 503"`. O jogador que
   abre "Detalhes técnicos" para descobrir o que houve recebe menos informação
   do que o servidor mandou.
2. **Classificação de erro duplicada.** `describeError`
   (`frontend/src/errors.ts:10`) decide entre offline / chatDisabled /
   unexpected, e `GameScreen` refaz a mesma decisão em outra forma na linha 199:
   `err instanceof TypeError ? 'offline' : err instanceof ApiError && err.status
   === 503 ? 'chatDisabled' : 'unexpected'`, mais um `if` separado para 404
   (`:195`). São duas tabelas de decisão sobre os mesmos erros, em arquivos
   diferentes, e elas já divergem: `describeError` reconhece qualquer objeto com
   `status === 503` (`errors.ts:17`), `GameScreen` exige `instanceof ApiError`, e
   `describeError` não conhece 404 nenhum. Acrescentar um código novo exige
   lembrar dos dois lugares.
3. **O HUD pisca placeholder no primeiro frame.** `GameScreen` renderiza
   `<Hud hud={state.phase === 'ready' ? hud : null} ...>` (`:253`), mas `hud` é
   estado local preenchido por um `useEffect` (`:92`) que só roda **depois** do
   render em que `state.phase` virou `'ready'`. Nesse frame, `phase` é `ready` e
   `hud` ainda é `null`: o HUD renderiza `t('hud.placeholder')` (`—`) nos quatro
   campos e o `aria-live="polite"` do container (`Hud.tsx:92`) chega a anunciar
   o estado vazio antes do estado real. Visualmente é um flash; no leitor de
   tela é uma leitura errada.

Lacunas de cobertura declaradas do TCK-014: o caminho `error.offline` **do
turno** (o `fetch` do POST rejeitando com `TypeError`) não tem teste — o único
teste de offline é o do carregamento da sessão
(`frontend/src/screens/GameScreen.test.tsx:159`); e vários critérios de
acessibilidade da spec (`aria-live` do bloco em streaming, `aria-busy` do botão,
região de anúncio de turno pronto) não têm asserção de aria.

## Escopo

Dentro:
- `ApiError` com `detail`, preenchido a partir do corpo JSON do backend em
  `request` e em `streamTurn`.
- `classifyError` em `frontend/src/errors.ts` como **única** tabela de decisão,
  incluindo `notFound`; `describeError` reescrita em cima dela.
- `GameScreen` consumindo `classifyError`, sem lógica própria de classificação.
- HUD sem frame de placeholder ao terminar o carregamento.
- Cenários novos de teste: offline no turno, `detail` no `<details>`, e as
  asserções de aria faltantes.

Fora (explícito):
- Traduzir o `detail` do backend: ele é inglês técnico e vai para o
  `<details>` de detalhe técnico, que é justamente o lugar de texto não
  traduzido. Título e corpo do erro continuam vindo de `frontend/src/strings.ts`
  nos dois locales.
- Mapear o código `turn_failed` do SSE (TCK-018) para um texto próprio: o bloco
  de erro do turno continua usando `game.turn.error` / `game.turn.errorBody`.
- Mudar `ErrorState`, `Loading`, `EmptyState` ou o CSS de estados.
- Mudar o skeleton de carregamento do histórico (`:256`) ou o comportamento de
  `hudStale`.
- Retry automático, backoff, toast: a spec da fase não os prevê.
- Tocar em `SessionsScreen.tsx` — ela usa `describeError` e continua funcionando
  pela assinatura preservada, mas não é reescrita aqui.

### Testes existentes que este ticket invalida

Grep em `frontend/src/errors.test.ts` (5 testes) e
`frontend/src/screens/GameScreen.test.tsx` (23 testes):

- `errors.test.ts` `it('classifies an object with status 503 as chat disabled')`
  (`:13`) passa `{ status: 503 }` (objeto puro, não `ApiError`) e afere
  `cause === ''`. `classifyError` **precisa** continuar aceitando objeto com
  `status` e continuar devolvendo `cause` vazio quando não há `message` nem
  `detail`. Sem adaptação — e este é o teste que fixa a compatibilidade.
- `errors.test.ts` `it('classifies a network TypeError as offline')` (`:6`),
  `'generic Error as unexpected'` (`:20`), `'undefined'` (`:27`), `'null'`
  (`:34`): continuam válidos verbatim.
- `GameScreen.test.tsx` `it('shows the chat-disabled error family on a 503
  without dropping the player message')` (`:386`) monta a resposta com
  `jsonResponse({}, 503)` — corpo `{}`, sem `detail`. Continua válido: sem
  `detail`, a mensagem do `ApiError` permanece `"HTTP 503"`. **Adaptação de
  preparação** opcional e recomendada: passar `{ detail: 'chat disabled by
  flag' }` para exercitar o caminho novo. As asserções de título e de mensagem
  preservada não mudam.
- `it('shows an ErrorState with working retry on a 500')` (`:145`) usa
  `jsonResponse({}, 500)`. Continua válido.
- `it('shows the not-found state with a back button and no retry on a 404,
  keeping the typed text')` (`:399`) e `it('feeds the hud with null while
  loading and the real hud once loaded')` (`:123`): o segundo afere que o HUD
  recebe `null` **enquanto carrega** e o valor real **depois**. Isso continua
  verdadeiro: o que muda é o frame intermediário em que `phase` já é `ready` e
  `hud` ainda é `null`, que deixa de existir. Sem adaptação; verifique que
  continua verde.
- `it('marks the hud stale when the stream ends without a hud event')` (`:262`):
  continua válido — `hudStale` não é tocado.
- Nenhum teste afere hoje o texto dentro do `<details>`; os cenários de `detail`
  são novos.

## Comportamento esperado

Do ponto de vista do jogador:

- Abrir "Detalhes técnicos" num erro mostra o que o servidor disse
  (`HTTP 503 — chat disabled by flag`), não só o número.
- O HUD, ao terminar de carregar, aparece já com os valores da sessão: nenhum
  frame com `—` nos quatro campos.
- O backend caindo no meio do envio (fetch rejeitando) mostra a família
  `error.offline`, com a mensagem digitada preservada e botão de tentar de novo
   — o mesmo que já acontece no carregamento da sessão.

Do ponto de vista do chamador de `errors.ts`:

| Erro | `kind` |
|---|---|
| `TypeError` (fetch falhou) | `offline` |
| status 503 | `chatDisabled` |
| status 404 | `notFound` |
| qualquer outro | `unexpected` |

## Detalhes técnicos

- `ApiError` ganha `detail: string | null` e a `message` passa a ser
  `` `HTTP ${status}` `` quando não há detail e
  `` `HTTP ${status} — ${detail}` `` quando há. Como `cause` sai de
  `err.message` (`errors.ts:6`), o `<details>` melhora sem nenhuma mudança em
  `ErrorState`.
- Leitura do corpo de erro: `await response.json()` dentro de `try/catch`
  (resposta de erro pode não ser JSON, e no caso do SSE pode nem ter corpo), e
  `detail` só quando for `string`. FastAPI também emite `detail` como **lista**
  em erro de validação de corpo (422 automático do pydantic); nesse caso
  ignore e deixe `null` — serializar o array na tela não ajuda ninguém.
  **Armadilha**: os mocks da suíte devolvem objetos com `json: async () => body`
  e **sem** `text`; use `json()`, não `text()`, senão a suíte inteira quebra por
  método inexistente.
- `classifyError(err: unknown): { kind: ErrorKind; title: string; body: string;
  cause: string }`, com `ErrorKind = 'offline' | 'chatDisabled' | 'notFound' |
  'unexpected'`. `notFound` usa `game.notFound.title` / `game.notFound.body`,
  que já existem nos dois locales.
  `describeError` vira `const { title, body, cause } = classifyError(err)` —
  assinatura e retorno preservados, porque `SessionsScreen.tsx` a consome.
- `GameScreen`: `PreStreamKind` deixa de existir; o `catch` de `runTurn` usa
  `classifyError` e o `kind` resultante escolhe entre o bloco de "sessão não
  encontrada" (com botão voltar, sem retry) e o `ErrorState` com retry. A ordem
  do guard de abort do TCK-022 vem **antes** de `classifyError` e não é alterada
  aqui.
- HUD sem flash: `const hudView = state.phase === 'ready' ? (hud ?? state.session.hud)
  : null`, usado no `<Hud hud={hudView} .../>`. O `useEffect` que semeia `hud`
  (`:92`) continua existindo (é ele que guarda o HUD entre streams), só deixa de
  ser o caminho crítico do primeiro frame.
- Asserções de aria que faltam e entram aqui (comportamento especificado na
  spec de UI da fase, documento externo ao repositório; o conteúdo relevante
  está enumerado a seguir e é autocontido): bloco em streaming com
  `aria-live="off"`; indicador `game.turn.thinking` com `role="status"` e
  `aria-live="polite"`; botão de enviar com `aria-busy="true"` durante o turno;
  região oculta de anúncio com `game.turn.done` depois do `[DONE]`. Todos os
  atributos **já existem** no componente (`GameScreen.tsx:311`, `:317`, `:383`,
  `:357`) — o ticket acrescenta a asserção, não o atributo.

## Contrato público

```ts
// frontend/src/api.ts
export class ApiError extends Error {
  status: number
  detail: string | null
}
```

```ts
// frontend/src/errors.ts
export type ErrorKind = 'offline' | 'chatDisabled' | 'notFound' | 'unexpected'
export type ErrorDescription = { title: string; body: string; cause: string }

export function classifyError(err: unknown): ErrorDescription & { kind: ErrorKind }
export function describeError(err: unknown): ErrorDescription   // inalterada
```

## Acceptance criteria

- [ ] Uma resposta 503 com `{"detail": "chat disabled by flag"}` produz um
      `ApiError` com `detail` preenchido e `message` contendo o texto do detail.
- [ ] O `<details>` de detalhe técnico exibe esse texto.
- [ ] Resposta de erro sem corpo JSON não quebra: `detail` fica `null` e
      `message` continua `"HTTP 500"`.
- [ ] `detail` em formato de lista (422 do pydantic) resulta em `detail: null`.
- [ ] `classifyError` é a única ocorrência de comparação com `503`/`404` fora de
      `api.ts` (grep em `frontend/src/` não encontra `=== 503` nem `=== 404` em
      `GameScreen.tsx`).
- [ ] `describeError` mantém assinatura e resultados para os 5 casos já
      testados.
- [ ] Com `Hud` substituído por mock (`vi.mock`) que registra cada valor da
      prop `hud` recebido: após a chegada dos dados da sessão, nenhum render
      recebe `hud === null` (a sequência registrada é `null` durante o
      carregamento e valores reais dali em diante, sem `null` intercalado).
- [ ] `fetch` do POST rejeitando com `TypeError` mostra `error.offline.title`,
      preserva a mensagem digitada e oferece `common.retry`.
- [ ] Existem asserções para `aria-live="off"` no bloco em streaming,
      `role="status"` no indicador de escrita, `aria-busy` no botão e o anúncio
      `game.turn.done`.
- [ ] `npm run check` verde (tsc + vitest).

## Cenários de teste

- Feliz: 503 com `detail` → título `error.chatDisabled.title` e o texto do
  detail dentro do `<details>` (abrir o `<summary>` `common.details`).
- Feliz: com `Hud` mockado registrando a prop `hud` de cada render, carregar a
  sessão do fixture `session()` produz uma sequência sem `null` depois do
  primeiro valor real (`location: 'Hallway'`); o teste existente do estado
  final continua verde sem adaptação.
- Feliz (aria): durante o streaming, o container do texto tem
  `aria-live="off"`, o indicador tem `role="status"`, o botão tem
  `aria-busy="true"`; depois do `[DONE]`, a região de anúncio contém
  `t('game.turn.done', { index: 1 })`.
- Borda: `classifyError` para `TypeError`, `{status: 503}`, `{status: 404}`,
  `new Error('x')`, `undefined`, `null` → os quatro `kind` corretos e `cause`
  coerente.
- Borda: resposta de erro cujo `json()` rejeita → `detail: null`, sem exceção
  escapando de `request`.
- Borda: 404 no envio do turno → bloco "sessão não encontrada" com botão voltar
  e **sem** `common.retry` (comportamento já existente, agora vindo de
  `classifyError`).
- Falha: `fetch` do POST rejeitando com `TypeError('Failed to fetch')` →
  `error.offline.title`, texto do jogador visível em `.game-turn-text`, botão de
  retry presente, e um clique nele refaz o POST.

## Rollout e kill switch

N/A como flag: mudança de UI e de tipagem, sem estado persistido nem schema.
Rollback é `git revert` do PR. O kill switch de produto continua sendo a flag
**`chat`** do backend (default `true`, `~/.ooc-local/config.yaml`).

`risk: low`: o pior caso é um texto de erro menos informativo, e os cinco testes
existentes de `describeError` travam a compatibilidade da função que a outra
tela consome.

## Observabilidade

N/A no frontend — o projeto não tem telemetria de cliente (toda a
observabilidade vive em `backend/app/observability.py`). O sinal equivalente é a
suíte do vitest: os cenários de `detail`, de aria e de offline no turno são as
asserções que dizem se a mudança funcionou.

## i18n

Nenhuma chave nova. `classifyError` reusa chaves que já existem em `en` e
`pt-br` em `frontend/src/strings.ts`: `error.offline.title`/`body` (`:10`,
`:93`), `error.chatDisabled.title`/`body` (`:12`, `:95`),
`error.unexpected.title`/`body` (`:14`, `:97`), `game.notFound.title`/`body`
(`:55`, `:138`) e `common.details` (`:9`, `:92`). O `detail` do backend é texto
técnico não traduzido, por decisão declarada em "Fora de escopo".

A paridade de locales continua aferida por `frontend/src/i18n.test.ts`, que não
é tocado. `contentGates` está vazio em `.claude/pipeline.json`: nenhum gate de
conteúdo aplicável.
