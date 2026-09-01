---
id: TCK-035
title: Abrir a rota #/builder com a lista de cenarios
status: done
points: 3
blockedBy: [TCK-030, TCK-032]
files:
  - frontend/src/useHashRoute.ts
  - frontend/src/useHashRoute.test.ts
  - frontend/src/App.tsx
  - frontend/src/api.ts
  - frontend/src/strings.ts
  - frontend/src/screens/BuilderListScreen.tsx
  - frontend/src/screens/BuilderListScreen.test.tsx
  - frontend/src/screens/builder.css
  - frontend/src/screens/SessionsScreen.tsx
  - frontend/src/screens/SessionsScreen.test.tsx
migration: false
ui: true
risk: low
---

## Problema

A API do builder existe (TCK-030) e nenhuma tela a usa. O app não tem sequer uma
porta de entrada para o builder, e não há como ver quais pastas existem em
`scenarios/` — nem quais estão quebradas, que são justamente as que a pessoa
precisa achar para consertar.

Este ticket entrega **só a leitura** da lista. Criar, duplicar e deletar são o
TCK-045, quebrado por tamanho (três diálogos modais, validação de slug e
polyfill de `<dialog>` no ambiente de teste não cabem no mesmo PR).

## Escopo

Dentro:
- `Route` ganha `{ name: 'builderList' }` para `#/builder`.
- `BuilderListScreen` com os estados carregando/vazio/erro/carregado, item
  inválido e reload.
- `fetchBuilderScenarios` em `api.ts`.
- `frontend/src/screens/builder.css` — folha das **telas de lista** do builder
  (o editor tem a própria, `builderEditor.css`, criada no TCK-036).
- Link `sessions.builderLink` no topo do `SessionsScreen`.
- Chaves i18n de shell/comum e da lista.

Fora (explícito):
- Criar, duplicar e deletar (TCK-045) — inclusive o formulário e os diálogos.
- A rota do editor `#/builder/{id}/{tab}` e qualquer tela de edição (TCK-036).
- Upload de capa (TCK-037); aqui a capa só é exibida.
- Componente de estado novo: use `EmptyState`, `ErrorState` e `Loading`.

## Comportamento esperado

Do `#/` a pessoa clica em "Abrir o builder" e cai em `#/builder`. Vê a lista de
pastas de `scenarios/`, **inclusive as quebradas**, marcadas com o motivo.
Clicar num cartão válido navega para `#/builder/{id}/identity` (rota que só
ganha tela no TCK-036: até lá, cai no fallback de hash desconhecido, que
normaliza para `#/` — comportamento aceito e temporário). O botão de recarregar
relê o disco.

## Detalhes técnicos

### Rota

`parseHash` ganha, antes do fallback:

```ts
if (/^#\/builder\/?$/.test(hash)) return { name: 'builderList' }
```

Cuidado com a normalização existente: hoje `apply()` faz
`location.replace('#/')` para qualquer hash que resolva `sessions` e não seja
`''`/`'#/'`. Essa regra não pode engolir `#/builder` — o `replace` só vale
quando `next.name === 'sessions'`, e `#/builder` não resolve para `sessions`.
`#/builder/algo` ainda resolve para `sessions` neste ticket e é normalizado,
como qualquer hash desconhecido.

### Tela

`<main class="builder-list">`, largura máxima 960px, mesmo padding de
`.sessions`. `h1` com `tabIndex={-1}` recebe foco na montagem;
`document.title = t('builder.documentTitle')` restaurado no unmount (padrão do
`GameScreen`). Botão `builder.list.back` volta para `#/`.

Estados:

- **Carregando**: `ul.builder-list-skeleton` com 3 cartões `aria-hidden` +
  `<Loading label={t('builder.list.loading')} visuallyHidden />`.
- **Vazio**: `EmptyState` com `builder.list.empty.title`/`.body`. A ação
  `builder.list.empty.action` entra no TCK-045, junto com o formulário para o
  qual ela move o foco; neste ticket o `EmptyState` vai sem `action`.
- **Erro**: `ErrorState` com `builder.list.error.title`/`.body`, `cause` do
  `describeError(err)` e `onRetry` recarregando.
- **Carregado**: `ul` de cartões em grid
  `repeat(auto-fill, minmax(260px, 1fr))`.

Cada cartão: nome em `<strong>`, tagline em `--fg-muted` (omitida se `null`),
meta com `builder.list.item.meta` combinando os plurais de starts e personagens,
badge de idioma (`builder.create.locale.en`/`.ptBr`), miniatura da capa quando
`hasCover`, e o cartão inteiro como `<a href="#/builder/{id}/identity">` com
`aria-label` = `builder.list.item.edit`. O TCK-045 acrescenta os botões de
duplicar e deletar como **irmãos** da âncora, fora dela — já deixe o cartão com
o slot para isso (um `<div class="builder-card-actions">` vazio), para o outro
ticket não precisar remexer na estrutura.

Item com `status: 'invalid'`: borda de aviso, editar desabilitado (renderize um
`<span>` no lugar da âncora, não um link com `aria-disabled`), e um `ErrorState`
compacto embutido com `builder.list.item.broken` +
`builder.list.item.brokenBody` interpolando `{reason}`.

Reload: botão `builder.list.reload` recarrega e anuncia `builder.list.reloaded`
na região `role="status" aria-live="polite"` única da tela — a mesma que o
TCK-045 vai usar para criado/duplicado/deletado.

### Miniatura da capa

`BuilderScenarioItem` (TCK-030) expõe `hasCover: boolean` e **não** expõe URL,
porque o arquivo pode ter três extensões. A URL é montada contra a rota de
serviço do TCK-032:

```ts
const COVER_EXTENSIONS = ['png', 'jpg', 'webp'] as const
// /api/scenarios/{id}/media/cover.{ext}
```

Renderize `<img>` só quando `hasCover`, começando por `.png`; no `onError`,
avance para a próxima extensão; esgotadas as três, caia no placeholder com a
inicial do nome (`aria-hidden`, sem string). Item sem capa vai direto para o
placeholder, sem requisição. É feio de propósito e é o menor custo: a
alternativa seria uma chamada de índice de mídia por cartão.

### API

```ts
export type BuilderScenarioItem = {
  id: string; name: string; tagline: string | null; locale: string
  startCount: number; characterCount: number; hasCover: boolean
  updatedAt: string; status: 'ok' | 'invalid'; reason?: string
}
export function fetchBuilderScenarios(): Promise<BuilderScenarioItem[]>
```

Reaproveite o helper `request<T>` existente.

### Responsividade e acessibilidade

`@media (max-width: 480px)`: uma coluna, padding `0.75rem`, alvos de 44px.
Ordem de tab: voltar → h1 → reload → cartões. Foco visível herdado do
`:focus-visible` global.

## Contrato público

```ts
// frontend/src/useHashRoute.ts
export type Route = { name: 'sessions' } | { name: 'game'; id: string } | { name: 'builderList' }
// frontend/src/api.ts
export type BuilderScenarioItem
export function fetchBuilderScenarios(): Promise<BuilderScenarioItem[]>
```

`frontend/src/screens/builder.css` é a folha das telas de **lista** (classes
`.builder-list*`, `.builder-card*`), consumida também pelo TCK-045.
O bloco de chaves "compartilhadas" abaixo nasce aqui e não é redeclarado por
nenhum outro ticket da fase.

## Acceptance criteria

- [ ] `#/builder` renderiza a lista; `#/` continua renderizando as sessões.
- [ ] Cartão inválido mostra o motivo e não tem link de editar.
- [ ] Cartão válido é um link para `#/builder/{id}/identity`.
- [ ] Capa com `hasCover` tenta `.png`, `.jpg`, `.webp` e cai no placeholder.
- [ ] Reload refaz o GET e anuncia `builder.list.reloaded`.
- [ ] Erro no GET mostra `ErrorState` com retry funcionando.
- [ ] `strings.en` e `strings['pt-br']` têm exatamente as mesmas chaves.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente que muda de preparação (asserções preservadas):

- `frontend/src/useHashRoute.test.ts` — os casos de hash desconhecido continuam
  com a mesma asserção; se algum usa literalmente `#/builder`, troque o literal
  por `#/nao-existe`. Acrescente casos novos para `#/builder` e `#/builder/`.
- `frontend/src/screens/SessionsScreen.test.tsx` — as consultas existentes
  continuam valendo; o link novo é conteúdo adicional. Acrescente um caso para
  ele.
- `frontend/src/i18n.test.ts::has the same keys in en and pt-br` cobre as chaves
  novas sem alteração.

Cenários novos (`BuilderListScreen.test.tsx`, `fetch` mockado no padrão de
`SessionsScreen.test.tsx`):
- Feliz: dois cenários renderizam nome, tagline e meta com plural certo
  (1 start / 2 starts, sem personagens / 1 personagem).
- Feliz: clicar no cartão leva o hash para `#/builder/{id}/identity`.
- Borda: item `status: 'invalid'` mostra o motivo e nenhum link de edição.
- Borda: `hasCover: true` com `.png` falhando tenta `.jpg`; falhando as três,
  aparece o placeholder.
- Borda: lista vazia mostra o `EmptyState`.
- Falha: GET 500 → `ErrorState` com retry.
- Falha: `fetch` rejeitando (`TypeError`) → família offline do `describeError`.

## Rollout e kill switch

N/A — tela de leitura atrás de uma rota nova; não navegar para `#/builder` é o
desligamento.

## Observabilidade

Eventos: nenhum (não há telemetria de frontend).
Métrica de sucesso: a lista mostra as mesmas pastas que existem em
`scenarios/`, incluindo uma quebrada de propósito.

## i18n — chaves novas

Formato de `frontend/src/strings.ts`: chave e valor em aspas simples, `{param}`
interpolado por `t()`. Toda chave existe em `en` e em `pt-br`.

### Compartilhadas (bloco "Shell and common", declaradas aqui uma única vez)

| chave | en | pt-br |
|---|---|---|
| `common.save` | `Save` | `Salvar` |
| `common.delete` | `Delete` | `Deletar` |
| `common.discard` | `Discard` | `Descartar` |
| `common.close` | `Close` | `Fechar` |
| `common.remove` | `Remove` | `Remover` |
| `common.add` | `Add` | `Adicionar` |
| `common.reload` | `Reload from disk` | `Recarregar do disco` |
| `common.optional` | `optional` | `opcional` |

### Lista

| chave | en | pt-br |
|---|---|---|
| `sessions.builderLink` | `Open the builder` | `Abrir o builder` |
| `builder.documentTitle` | `Builder — ooc-local` | `Builder — ooc-local` |
| `builder.list.heading` | `Your scenarios` | `Seus cenários` |
| `builder.list.back` | `Back to sessions` | `Voltar para as sessões` |
| `builder.list.loading` | `Loading scenarios…` | `Carregando cenários…` |
| `builder.list.empty.title` | `No scenarios yet` | `Nenhum cenário ainda` |
| `builder.list.empty.body` | `A scenario is a folder in scenarios/. Create one here, or drop a folder there and reload.` | `Um cenário é uma pasta em scenarios/. Crie um aqui, ou solte uma pasta lá e recarregue.` |
| `builder.list.error.title` | `Couldn't load your scenarios` | `Não consegui carregar seus cenários` |
| `builder.list.error.body` | `The folder list didn't come back from the server. Nothing on disk was changed.` | `A lista de pastas não voltou do servidor. Nada no disco foi alterado.` |
| `builder.list.reload` | `Reload from disk` | `Recarregar do disco` |
| `builder.list.reloaded` | `Scenario list reloaded from disk` | `Lista de cenários recarregada do disco` |
| `builder.list.item.meta` | `{starts} · {characters}` | `{starts} · {characters}` |
| `builder.list.item.startsOne` | `1 start` | `1 start` |
| `builder.list.item.startsOther` | `{count} starts` | `{count} starts` |
| `builder.list.item.charactersZero` | `no characters` | `sem personagens` |
| `builder.list.item.charactersOne` | `1 character` | `1 personagem` |
| `builder.list.item.charactersOther` | `{count} characters` | `{count} personagens` |
| `builder.list.item.edit` | `Edit {scenario}` | `Editar {scenario}` |
| `builder.list.item.broken` | `This folder can't be opened` | `Não dá para abrir esta pasta` |
| `builder.list.item.brokenBody` | `{reason}. Fix the file on disk and reload — the builder won't overwrite what it can't read.` | `{reason}. Conserte o arquivo no disco e recarregue — o builder não sobrescreve o que não consegue ler.` |
| `builder.list.item.coverAlt` | `Cover of {scenario}` | `Capa de {scenario}` |
| `builder.create.locale.en` | `English` | `Inglês` |
| `builder.create.locale.ptBr` | `Portuguese (Brazil)` | `Português (Brasil)` |
