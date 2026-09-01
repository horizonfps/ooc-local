---
id: TCK-036
title: Montar o shell do editor com rota por aba, rascunho e dirty
status: in_review
points: 3
blockedBy: [TCK-031, TCK-035, TCK-045]
files:
  - frontend/src/useHashRoute.ts
  - frontend/src/useHashRoute.test.ts
  - frontend/src/App.tsx
  - frontend/src/api.ts
  - frontend/src/strings.ts
  - frontend/src/builder/validate.ts
  - frontend/src/builder/validate.test.ts
  - frontend/src/screens/BuilderEditorScreen.tsx
  - frontend/src/screens/BuilderEditorScreen.test.tsx
  - frontend/src/screens/builderEditor.css
migration: false
ui: true
risk: medium
---

## Problema

A lista do builder já leva para `#/builder/{id}/identity` e não existe tela
nenhuma nesse endereço. Falta o esqueleto que segura as quatro abas de edição, a
aba Mídia e o preview: rota com aba, carregamento do documento, rascunho único
por cenário, indicador de sujo e os estados de erro.

Este ticket entrega o shell **de leitura e rascunho**, com placeholder no lugar
de cada aba. Save, conflito, reload e guard de saída são o TCK-046 — quebrado
por tamanho e porque tudo que escreve no disco fica atrás do mesmo kill switch,
num PR só.

## Escopo

Dentro:
- `Route` ganha `{ name: 'builderEditor'; id: string; tab: BuilderTab }`.
- `BuilderEditorScreen`: topbar, tablist WAI-ARIA, painel, estados de
  carregando/erro/não encontrado/inválido.
- Rascunho (`loaded` + `draft`), `dirty` derivado por `deepEqual`, indicador de
  sujo por aba.
- `frontend/src/builder/validate.ts` — **este ticket é o dono do arquivo** e o
  cria com as regras **estruturais**; TCK-037, 047, 038 e 048 acrescentam as
  regras de campo de cada aba.
- `fetchScenarioDocument` em `api.ts` e o contrato `TabProps` para as abas.
- `frontend/src/screens/builderEditor.css`.

Fora (explícito):
- Save, `PUT`, 409, reload do disco, guard de saída, painel de validação e
  atalho Ctrl+S (TCK-046).
- Conteúdo das abas: Identidade (TCK-037), Mundo (TCK-047), Starts (TCK-038),
  Personagens (TCK-048), Mídia (TCK-039/TCK-049).
- Preview jogável (TCK-041) — este ticket só reserva o `aside` e o toggle de
  visibilidade.
- Autosave: não existe nesta fase.

## Comportamento esperado

`#/builder/{id}/identity` abre o editor do cenário. Trocar de aba muda o hash
(back/forward do browser andam entre abas) e **não** perde edição — o rascunho é
um só, por cenário; as abas são views dele. Editar marca "Mudanças não salvas"
no indicador; desfazer a edição na unha volta para "Tudo salvo".

Cenário que o backend não consegue ler abre em estado de erro **sem formulário**:
o builder não escreve por cima do que não leu.

## Detalhes técnicos

### Rota

```ts
export type BuilderTab = 'identity' | 'world' | 'starts' | 'characters' | 'media'
export type Route =
  | { name: 'sessions' }
  | { name: 'game'; id: string }
  | { name: 'builderList' }
  | { name: 'builderEditor'; id: string; tab: BuilderTab }
```

- `#/builder/{id}/{tab}` casa `^#\/builder\/([^/]+)\/([^/]+)\/?$`; aba fora da
  lista cai em `identity`.
- `#/builder/{id}` resolve `builderEditor` com `tab: 'identity'` e dispara
  `location.replace('#/builder/{id}/identity')` — sem entrada nova no
  histórico, mesma política do `replace` da rota raiz.

### Layout

```
main.builder-editor
├─ header.builder-editor-topbar   (voltar · nome · pasta · status)
├─ nav[role=tablist].builder-editor-tabs
└─ div.builder-editor-body
   ├─ section[role=tabpanel].builder-editor-panel
   └─ aside.builder-editor-preview   (slot do preview; placeholder até TCK-041)
```

- ≥1100px: `grid-template-columns: minmax(0, 1fr) minmax(360px, 420px)`, preview
  sticky em `100dvh`.
- 720–1100px: preview vira painel recolhível abaixo do editor, controlado por
  `builder.editor.previewToggle.show`/`.hide` com `aria-expanded`.
- <720px: preview fechado por default; aberto ocupa a tela cheia com botão de
  voltar ao editor como primeiro elemento tabulável.
- <720px a tablist rola com `overflow-x: auto` e `scroll-snap-align: start`;
  <480px padding `0.75rem`, campos em coluna, botões de largura total.

Topbar: botão `builder.editor.back` → `#/builder` (o guard que intercepta essa
saída chega no TCK-046; aqui a navegação é direta), `h1` com o nome do cenário
(`tabIndex={-1}`, foco na montagem e a cada troca de `id`, `title` com o nome
completo, ellipsis como `.game-topbar h1`), caminho da pasta em `--fg-muted`
(`builder.editor.folder`) e o indicador `aria-live="polite"`
(`builder.editor.clean` / `builder.editor.dirty`). O botão de salvar entra no
TCK-046; deixe o slot `div.builder-editor-actions` pronto na topbar.

Tablist: `role="tablist"` com `aria-label` = `builder.editor.tabs.label`; cada
aba é `<a role="tab" href="#/builder/{id}/{tab}">` com `aria-selected` e
`tabIndex` roving (←/→ movem, Home/End vão às pontas, Enter/Espaço ativam).
Painel `role="tabpanel"` com `aria-labelledby` da aba ativa e `tabIndex={0}`.
Aba com edição pendente ganha ponto visual + texto sr-only
`builder.editor.tab.dirty`; com erro de validação, marca +
`builder.editor.tab.invalid`.

### Estados

- **Carregando**: topbar real com nome vazio, tablist desabilitada, dois
  `.builder-skeleton-block` `aria-hidden` e
  `<Loading label={t('builder.editor.loading')} visuallyHidden />`.
- **Não encontrado** (404): `ErrorState` `builder.editor.notFound.*` + botão
  voltar para `#/builder`.
- **Inválido no disco** (422): `ErrorState` `builder.editor.invalid.title` e
  `.body` interpolando `{reason}`, `cause` com o detalhe e `onRetry`
  recarregando. Sem abas de edição e sem rascunho.
- **Erro de rede/servidor**: `describeError` + `ErrorState` com `onRetry`.
- **Pronto**: abas e painel a partir do rascunho.

### Rascunho e dirty

- No load, guarde `loaded` (imutável, do `GET`) e `draft` (editável); o
  `revision` vem do documento e fica no estado para o TCK-046 usar.
- `dirty = !deepEqual(draft, loaded)` — derivado, nunca um booleano setado à
  mão. Escreva o `deepEqual` no próprio módulo (comparação estrutural de objeto,
  array, string, número, boolean e null); não adicione dependência.
- Granularidade por aba só para o indicador: compare a fatia que cada aba edita
  (`meta` → identity, `world` + `meta.world_mode` → world, `starts` +
  `meta.default_start` → starts, `characters` → characters; media não tem
  rascunho).
- Contrato de extensão para as abas:

```ts
export type BuilderDraft = Omit<ScenarioDocument, 'revision'>
export type ValidationError = { tab: BuilderTab; field: string; label: string; message: string }
export type TabProps = {
  scenarioId: string
  draft: BuilderDraft
  onChange: (next: BuilderDraft) => void
  errors: ValidationError[]
  goToTab: (tab: BuilderTab) => void      // troca interna, sem guard
}
```

  O shell renderiza `<IdentityTab {...tabProps} />` etc.; até o ticket da aba
  existir, renderize um `<p>` com o rótulo da aba (`builder.editor.tab.*`),
  sem chave nova.

### validate.ts

```ts
export function validateDraft(draft: BuilderDraft): ValidationError[]
```

Regras **estruturais** deste ticket: ao menos um start; `meta.default_start`
existente em `starts`; todo id em `start.characters` existente em `characters`;
chaves de `starts` e `characters` casando `^[a-z0-9-]+$`. Cada erro carrega a
aba de destino, para o painel de validação do TCK-046 poder saltar até o campo.
O shell já chama `validateDraft` para pintar a marca de aba inválida; bloquear o
save com ela é do TCK-046.

### API

```ts
export type ScenarioDocument = { revision: string; meta: ScenarioMeta; world: string
                                 starts: Record<string, StartDoc>
                                 characters: Record<string, CharacterDoc> }
export function fetchScenarioDocument(id: string): Promise<ScenarioDocument>
```

O payload é **snake_case**, espelho do arquivo (contrato do TCK-031) — não
converta para camelCase: o tipo do TS declara os nomes como vêm. 422 precisa
chegar na tela com o `detail`: use `classifyError`/`ApiError` já existentes e
trate `status === 422` como o estado "inválido no disco".

## Contrato público

```ts
// frontend/src/useHashRoute.ts
export type BuilderTab = 'identity' | 'world' | 'starts' | 'characters' | 'media'
// Route ganha { name: 'builderEditor'; id: string; tab: BuilderTab }

// frontend/src/screens/BuilderEditorScreen.tsx
export type BuilderDraft, TabProps, ValidationError

// frontend/src/builder/validate.ts
export function validateDraft(draft: BuilderDraft): ValidationError[]

// frontend/src/api.ts
export type ScenarioDocument, StartDoc, CharacterDoc
export function fetchScenarioDocument(id: string): Promise<ScenarioDocument>
```

Consumidores: TCK-046 (save/guard, usa `draft`, `loaded`, `revision` e
`validateDraft`), TCK-037/047/038/048/039/049 (recebem `TabProps` e ampliam
`validateDraft`), TCK-041 (recebe o slot do preview, `draft` e `dirty`).

## Acceptance criteria

- [ ] `#/builder/x/world` abre o editor na aba Mundo; `#/builder/x` redireciona
      para `.../identity` sem empilhar histórico; aba desconhecida cai em
      `identity`.
- [ ] Setas, Home e End navegam a tablist; a aba ativa tem
      `aria-selected="true"`.
- [ ] Editar pelo `onChange` de uma aba marca dirty; desfazer volta para limpo.
- [ ] Trocar de aba com rascunho pendente não perde nada.
- [ ] 404 mostra `builder.editor.notFound.*`; 422 mostra
      `builder.editor.invalid.*` com `{reason}` e nenhum campo editável.
- [ ] `validateDraft` acusa `default_start` inexistente e id de personagem
      citado por start e ausente do documento.
- [ ] `strings.en` e `strings['pt-br']` seguem com as mesmas chaves.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente que muda de preparação (asserções preservadas):
`frontend/src/useHashRoute.test.ts` — os casos de hash desconhecido mantêm a
asserção; se algum usa `#/builder/...` como exemplo de desconhecido, troque o
literal. Acrescente casos para `#/builder/{id}/{tab}` e para o `replace` da aba
ausente. Nenhum outro teste existente toca este fluxo: **hoje não há teste de
editor**, a cobertura de frontend é de sessões, jogo e componentes.

Cenários novos:
- `validate.test.ts` — feliz: documento coerente devolve `[]`; borda:
  `default_start` inexistente; borda: start citando personagem ausente; borda:
  chave `Start Um`; borda: `starts` vazio.
- `BuilderEditorScreen.test.tsx` — feliz: carrega e renderiza a tablist com a
  aba do hash selecionada; feliz: `onChange` de um placeholder marca dirty e
  desfazer limpa; feliz: troca de aba pelo link e pelas setas preservando o
  rascunho; borda: `#/builder/x` faz `location.replace` uma única vez; falha:
  404 e 422 com os estados corretos; falha: 500 com `ErrorState` e retry.

## Rollout e kill switch

N/A neste ticket: o shell só **lê**. O kill switch do builder (`flags.builder`,
`Config.flag` em `backend/app/config.py`) protege as rotas de escrita e é
consumido pela UI no TCK-046, que trata o 503 do `PUT` com mensagem própria.
`risk: medium` porque a tela é a base de tudo que escreve depois, mas ela mesma
não escreve nada.

## Observabilidade

Eventos: nenhum (sem telemetria de frontend).
Métrica de sucesso: abrir o cenário exemplo no editor e ver nome, pasta e as
cinco abas, com o indicador em "Tudo salvo".

## i18n — chaves novas

| chave | en | pt-br |
|---|---|---|
| `builder.editor.documentTitle` | `{scenario} — builder — ooc-local` | `{scenario} — builder — ooc-local` |
| `builder.editor.back` | `Back to scenarios` | `Voltar para os cenários` |
| `builder.editor.folder` | `scenarios/{folder}` | `scenarios/{folder}` |
| `builder.editor.loading` | `Loading scenario…` | `Carregando cenário…` |
| `builder.editor.error.title` | `Couldn't open this scenario` | `Não consegui abrir este cenário` |
| `builder.editor.error.body` | `The scenario didn't come back from the server. Nothing on disk was changed.` | `O cenário não voltou do servidor. Nada no disco foi alterado.` |
| `builder.editor.notFound.title` | `Scenario not found` | `Cenário não encontrado` |
| `builder.editor.notFound.body` | `There's no folder with this id in scenarios/. Go back and pick another one.` | `Não existe pasta com esse id em scenarios/. Volte e escolha outro.` |
| `builder.editor.invalid.title` | `This scenario has a file the app can't read` | `Este cenário tem um arquivo que o app não consegue ler` |
| `builder.editor.invalid.body` | `{reason}. Fix the file on disk and reload — the builder won't overwrite what it can't read.` | `{reason}. Conserte o arquivo no disco e recarregue — o builder não sobrescreve o que não consegue ler.` |
| `builder.editor.tabs.label` | `Scenario sections` | `Seções do cenário` |
| `builder.editor.tab.identity` | `Identity` | `Identidade` |
| `builder.editor.tab.world` | `World` | `Mundo` |
| `builder.editor.tab.starts` | `Starts` | `Starts` |
| `builder.editor.tab.characters` | `Characters` | `Personagens` |
| `builder.editor.tab.media` | `Media` | `Mídia` |
| `builder.editor.tab.dirty` | `has unsaved changes` | `tem mudanças não salvas` |
| `builder.editor.tab.invalid` | `has a field to fix` | `tem campo para consertar` |
| `builder.editor.dirty` | `Unsaved changes` | `Mudanças não salvas` |
| `builder.editor.clean` | `Everything saved` | `Tudo salvo` |
| `builder.editor.previewToggle.show` | `Show preview` | `Mostrar preview` |
| `builder.editor.previewToggle.hide` | `Hide preview` | `Esconder preview` |

## Ressalvas registradas na wave 3

- Comportamento real do `GET /api/builder/scenarios/{id}` (TCK-031 mergeado): pasta existente sem `scenario.yaml` retorna **404** como pasta inexistente; o estado "cenario invalido no disco" (422) so acontece com `scenario.yaml` presente e invalido. Trate 404 como cenario inexistente.
