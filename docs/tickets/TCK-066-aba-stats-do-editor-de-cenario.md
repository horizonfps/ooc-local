---
id: TCK-066
title: Aba Stats do editor de cenário com validação
status: in_review
points: 5
blockedBy: [TCK-060]
files:
  - frontend/src/components/builder/StatsTab.tsx
  - frontend/src/components/builder/StatsTab.test.tsx
  - frontend/src/builder/validate.ts
  - frontend/src/builder/validate.test.ts
  - frontend/src/screens/BuilderEditorScreen.tsx
  - frontend/src/screens/BuilderEditorScreen.test.tsx
  - frontend/src/screens/builderEditor.css
  - frontend/src/useHashRoute.ts
  - frontend/src/useHashRoute.test.ts
  - frontend/src/strings/builder.ts
migration: false
ui: true
risk: low
---

## Problema

O TCK-060 põe `stats: StatDef[]` no `ScenarioDocument` e `allow_dynamic_stats` no
`ScenarioMeta`, e o engine da fase 3 passa a desenhar barra no HUD, aplicar
`[STAT:id:±N]` e mandar o texto de nível ao narrador. Do lado do editor não
existe caminho nenhum: `TAB_ORDER` (`BuilderEditorScreen.tsx:32`) tem cinco abas
e nenhuma delas desenha stat. Quem quiser usar o recurso precisa escrever
`scenarios/<id>/stats.yaml` na mão — exatamente o que o builder existe para
evitar.

Pior: a aba Stats é também a única superfície do `allow_dynamic_stats`. Sem ela,
o juiz de HUD (TCK-062/TCK-069) nunca pode ser ligado por um autor que não edite
YAML.

## Escopo

Dentro:
- `frontend/src/components/builder/StatsTab.tsx` novo: mestre-detalhe (lista à
  esquerda, formulário à direita) com id, nome, ícone, cor (campo hex), mínimo,
  máximo, valor inicial, descrição e níveis (adicionar/remover/editar), mais o
  toggle `allow_dynamic_stats` no topo e o `EmptyState` da lista vazia.
- `frontend/src/builder/validate.ts`: bloco de validação da aba `stats` e as
  constantes exportadas `STAT_ID_RE`, `STAT_COLOR_RE`, `MAX_STAT_NAME`,
  `MAX_STAT_ICON`, `MAX_STAT_DESCRIPTION`.
- `frontend/src/screens/BuilderEditorScreen.tsx`: `TAB_ORDER`, `TAB_LABEL_KEY`,
  `slice` (`case 'stats'` novo e descarte de `allow_dynamic_stats` no
  `case 'identity'`), `demoEdit` (`case 'stats'`) e a cadeia de render.
- `frontend/src/useHashRoute.ts`: `'stats'` na união `BuilderTab` e em
  `BUILDER_TABS`, entre `characters` e `media`.
- `frontend/src/screens/builderEditor.css`: bloco compartilhado novo
  `.builder-masterDetail` / `.builder-list*` (regras copiadas de
  `.builder-starts-*`, `builderEditor.css:696-812`, com nomes neutros) e as
  regras próprias `.builder-stats-*`.
- `frontend/src/strings/builder.ts`: chaves novas nos dois dicionários.
- Testes novos em `StatsTab.test.tsx`, `validate.test.ts`,
  `BuilderEditorScreen.test.tsx` e `useHashRoute.test.ts`.

Fora (explícito):
- Qualquer arquivo de `backend/`. O schema, o loader e o round-trip do
  `builder_doc` são o TCK-060.
- `frontend/src/api.ts`. Os tipos `StatDef`/`StatLevel` e o passthrough de
  `BuilderDraft`/`draftOf` chegam prontos do TCK-060. Se `draft.stats` ou
  `draft.meta.allow_dynamic_stats` não existirem no rascunho, **pare**: o defeito
  é do TCK-060 e não se conserta com um segundo caminho de leitura aqui.
- `frontend/src/strings/game.ts`, `GamePanel.tsx` e qualquer superfície de jogo.
  A barra do HUD é o TCK-067.
- **`<input type="color">` e o botão "limpar cor"**: nesta rodada a cor é só o
  campo de texto hex, com validação. Destino: fase 4. Motivo: o campo de texto é
  o único que expressa "sem cor" e já cobre o caso inteiro; o picker é conforto.
  As chaves `builder.stats.color.picker` e `builder.stats.color.clear` do design
  **não** entram.
- **Reordenação automática dos níveis por `from`** (e o anúncio
  `builder.stats.levels.reordered`): a validação `builder.validate.levelFromOrder`
  já obriga a ordem crescente e diz o que fazer. Destino: fase 4.
- **Aviso de lista longa** (`STATS_CROWDED` / `builder.stats.manyHint`): é aviso
  cosmético, nunca bloqueia salvar. Destino: fase 4.
- **Variante `select` em telas estreitas** (`useIsNarrow`, `(max-width: 899px)`,
  `.builder-list-selectRow`): a lista mestre-detalhe empilha acima do formulário
  abaixo de 900px e continua utilizável em 320px. As abas Starts e Personagens
  ficam como estão. Destino: fase 4 (paridade de mestre-detalhe estreito nas três
  abas novas). **O bloco de CSS compartilhado nasce sem
  `.builder-list-selectRow`/`.builder-list-selectActions`** — TCK-070 e TCK-073
  não podem contar com essas classes.
- Reordenar stats por arrastar ou por botões: a ordem é a de `stats.yaml`, stat
  novo entra no fim, e o hint `builder.stats.orderHint` diz isso.
- Prévia da barra do HUD dentro do builder.
- Migrar `.builder-starts-*` / `.builder-characters-*` para o bloco
  compartilhado: as abas antigas ficam como estão.

## Comportamento esperado

Uma aba **Stats** entre Personagens e Mídia. No topo, o toggle "Deixar o jogo
criar stats durante o jogo" com o hint que explica o juiz. Abaixo, a lista de
stats do cenário e o formulário do selecionado. Lista vazia mostra um
`EmptyState` explicando que o cenário joga sem stat e o que um stat dá, com o
botão "Novo stat" — e o toggle continua visível acima, porque ele é a segunda
saída desse estado.

```
Stats
[x] Deixar o jogo criar stats durante o jogo
    O juiz do HUD pode criar até 6 stats por sessão…

Stats deste cenário          Id            [ reputacao        ]
  ⭐ Reputação   0–100 · começa em 40   Nome  [ Reputação      ]
     [2 níveis]              [Remover]  Ícone [ ⭐ ]
  ⚡ Energia     0–100 · começa em 80   Cor   [ #f5c542 ]
                             [Remover]  Mín [0] Máx [100] Inicial [40]
  [ Novo stat ]                         Descrição […]
                                        Níveis
                                          Nível 1 começa em [0] Texto […] [Remover]
                                          [ Adicionar nível ]
```

### Seleção

Por **índice**, não por id: o id é campo editável e muda enquanto o autor digita.
`selectedIndex: number`; todo id de DOM e todo `field` de validação usa o índice
0-based (`stats.<i>.…`), como os blocos de lore da `WorldTab` já fazem.

Seleção inicial: o primeiro índice com erro de validação, se houver; senão `0`.
Só na montagem — a seleção nunca é arrastada por baixo do autor enquanto ele
digita. Quando `selectedIndex` sai do intervalo (remoção), cai para o último
índice válido (molde do `useEffect` de `StartsTab.tsx:63-68`).

### Item da lista

Botão `.builder-list-item` (`aria-current` quando selecionado) com: ícone em
`<span aria-hidden="true">` (ou nada); nome, ou o id, ou `builder.stats.unnamed`;
`builder.stats.itemMeta` (`{min}`, `{max}`, `{default}`) em `.field-hint`; badge
`.builder-starts-badge` com `builder.stats.levelsBadgeOne`/`…Other` quando há
níveis; e, com erro, `<span className="visually-hidden">` com
`builder.starts.itemInvalid` (**chave existente, reusada**, como a
`CharactersTab` já faz em `CharactersTab.tsx:353`). O `<li>` ganha `is-selected` e
`is-invalid` pelas mesmas regras da `StartsTab`. Ao lado, botão de remover com
texto visível `common.remove` e `aria-label` `builder.stats.remove.title`.

### Formulário

| Campo | `field` / id do DOM | Controle | Regras |
|---|---|---|---|
| Id | `stats.<i>.id` | `<input>` texto | `trim` no `onBlur` (molde de `CharactersTab.tsx:378`) |
| Nome | `stats.<i>.name` | `<input>` texto | `trim` no `onBlur`; é o `ref` que recebe foco ao trocar de stat |
| Ícone | `stats.<i>.icon` | `<input>` texto curto | `trim`; vazio → `null` |
| Cor | `stats.<i>.color` | `<input>` texto com o hex | `trim` no `onBlur`; vazio → `null`; hex inválido é erro de validação, nunca reescrito em silêncio |
| Mínimo | `stats.<i>.min` | `<input type="number" step="1">` | pendente numérico, abaixo |
| Máximo | `stats.<i>.max` | idem | idem |
| Valor inicial | `stats.<i>.default` | idem | idem, hint `builder.stats.default.hint` |
| Descrição | `stats.<i>.description` | `<textarea className="builder-field-textarea" rows={3}>` | texto cru como digitado; vazio após `trim` → `null` (molde de `starts.conflict`, `StartsTab.tsx:381`) |
| Níveis | `stats.<i>.levels.<j>.*` | `<fieldset className="builder-stats-levels">` | abaixo |

**Campos numéricos.** `type="number"`, `step={1}`, `inputMode="numeric"`.
Negativo é permitido. `''` e `'-'` não são número e o campo do rascunho é
`number`, então vale o molde de `pendingTitles` do `WorldTab.tsx:54`:

- estado local `pendingNumbers: Record<string, string>` chaveado pelo `field`;
- o valor exibido é `pendingNumbers[field] ?? String(valor)`;
- ao digitar algo que casa `/^-?\d+$/`, grava o número no rascunho e limpa o
  pendente; qualquer outra coisa fica só no pendente e **não** toca o rascunho;
- enquanto há pendente, o campo mostra `aria-invalid="true"` e o erro inline
  `builder.validate.integerRequired` (`role="alert"`, `.field-error`);
- **no `onBlur` o pendente é descartado** e o input volta a mostrar o valor
  gravado. Nunca existe estado em que a tela diz um número e o disco recebe
  outro.

**Níveis.** `<fieldset className="builder-stats-levels">` com `<legend>`
`builder.stats.levels.legend`, hint `builder.stats.levels.hint` e, com a lista
vazia, o parágrafo `builder.stats.levels.empty`. Cada linha
`.builder-stats-levelRow` tem `from`
(`builder-field-stats.<i>.levels.<j>.from`, label `builder.stats.levels.from`
com `{index}` 1-based), texto (`…levels.<j>.text`, label
`builder.stats.levels.text`) e remover (`common.remove` visível, `aria-label`
`builder.stats.levels.remove`).

- **Adicionar** (`builder.stats.levels.add`): entra no fim com `from` = `min`
  quando é o primeiro, senão `min(último from + 1, max)`, e `text: ''`. Foco vai
  para o campo de texto do nível novo (`requestAnimationFrame`, molde de
  `selectStart`, `StartsTab.tsx:102`); live region anuncia
  `builder.stats.levels.added`.
- **Remover**: imediato, sem diálogo — nada foi para o disco e
  Descartar/Recarregar desfazem (mesma decisão dos blocos de lore da `WorldTab`).
  Foco vai para o campo de texto do nível que assumiu a posição; se era o último,
  para o anterior; se não sobrou nenhum, para o botão "Adicionar nível". Anúncio
  `builder.stats.levels.removed`.

### Criar e remover stat

- **Criar** (`builder.stats.create`): entra no fim com id sugerido livre
  (`stat-1`, `stat-2`, …, molde de `nextSuggestedId`, `StartsTab.tsx:28`),
  `name: ''`, `min: 0`, `max: 100`, `default: 50`, `icon`/`color`/`description`
  `null`, `levels: []`. Vira o selecionado, o foco vai para o Nome e a live
  region anuncia `builder.stats.added` `{id}`. O erro "campo obrigatório" já
  aparece embaixo do campo focado: é orientação, some na primeira letra.
- **Remover**: imediato, com `aria-label` que diz qual stat sai e anúncio
  `builder.stats.removed`, que lembra que Descartar/Recarregar traz de volta.
  Foco vai para o item que assumiu a posição, ou para o botão "Novo stat" quando
  a lista esvazia. O foco nunca cai no `<body>`.
- Trocar de stat na lista: `setSelectedIndex`, anúncio `builder.detail.selected`
  (**chave existente**) e foco no campo Nome via `requestAnimationFrame`.

### Validação

Espelha o backend do TCK-060. Um erro por campo. O `label` do painel de validação
é `${rótulo do stat} — ${rótulo do campo}`, com o rótulo do stat =
`stat.name.trim() || stat.id || t('builder.stats.unnamed')` (molde de `withStart`,
`validate.ts:75`).

| Situação | `field` | Mensagem |
|---|---|---|
| id vazio | `stats.<i>.id` | `builder.field.required` *(existente)* |
| id fora de `^[a-z0-9_-]+$` | `stats.<i>.id` | `builder.field.slugUnderscoreInvalid` *(nova)* |
| id repetido | `stats.<i>.id`, **segundo e seguintes** | `builder.field.slugTaken` `{slug}` *(existente)* |
| nome vazio | `stats.<i>.name` | `builder.field.required` |
| nome > 40 | `stats.<i>.name` | `builder.field.tooLong` `{max: 40}` *(existente)* |
| ícone > 4 caracteres | `stats.<i>.icon` | `builder.field.tooLong` `{max: 4}` |
| cor não vazia fora de `^#[0-9a-fA-F]{6}$` | `stats.<i>.color` | `builder.validate.colorInvalid` *(nova)* |
| `max <= min` | `stats.<i>.max` | `builder.validate.statMaxAboveMin` *(nova)* |
| `default` fora de `[min, max]` | `stats.<i>.default` | `builder.validate.statDefaultRange` `{min}` `{max}` *(nova)* |
| descrição > 200 | `stats.<i>.description` | `builder.field.tooLong` `{max: 200}` |
| `from` fora de `[min, max]` | `stats.<i>.levels.<j>.from` | `builder.validate.levelFromRange` `{min}` `{max}` *(nova)* |
| `from` não maior que o anterior | `stats.<i>.levels.<j>.from`, a partir do segundo | `builder.validate.levelFromOrder` *(nova)* |
| texto do nível vazio após `trim` | `stats.<i>.levels.<j>.text` | `builder.field.required` |

Não é erro, por decisão: lista de stats vazia; `levels` vazio; descrição, ícone e
cor vazios. `allow_dynamic_stats` nunca é erro. `max <= min` **desliga** as
checagens de `default` e de `from` daquele stat: com o intervalo quebrado, as
outras mensagens seriam ruído derivado.

### Estados

| Estado | O que o autor vê |
|---|---|
| **Vazio** | `EmptyState` `builder.stats.empty.title`/`.body` com o botão "Novo stat" como `action` (molde literal de `CharactersTab.tsx:283-292`). O toggle `allow_dynamic_stats` e seu hint continuam acima |
| **Carregando** | Nada novo: validação e edição são síncronas sobre rascunho em memória. O carregamento do documento continua sendo o skeleton do `BuilderEditorScreen` (`.builder-skeleton-block` ×2 + `Loading visuallyHidden`) |
| **Erro de validação (campo)** | Erro inline `role="alert"` + `.field-error`, `aria-invalid` no controle, ligado por `aria-describedby` |
| **Erro de validação (salvar)** | Painel existente com "Ir para {campo}" por erro; `jumpToValidationError` (`BuilderEditorScreen.tsx:361-363`) foca `builder-field-<field>`. Stat não selecionado com erro já vem `is-invalid` na lista, e a seleção inicial cai no primeiro com erro |
| **Erro de número transitório** | `builder.validate.integerRequired` inline, rascunho intacto, `blur` restaura o valor gravado |
| **Erro ao salvar** | Inalterado (`builder.editor.save.error.*`, 409, 503) |
| **Sucesso** | O `role="status"` do topo passa de "Mudanças não salvas" para "Tudo salvo", o ponto de sujo some da aba, `builder.editor.saved` é anunciado. Dentro da aba, a live region anuncia criar/remover stat e criar/remover nível |

## Detalhes técnicos

### Contrato consumido (TCK-060, não redefinido aqui)

```ts
export type StatLevel = { from: number; text: string }
export type StatDef = {
  id: string
  name: string
  icon: string | null
  color: string | null
  min: number
  max: number
  default: number
  description: string | null
  levels: StatLevel[]
}
// ScenarioDocument.stats: StatDef[]      — a ordem é a ordem das barras no HUD
// ScenarioMeta.allow_dynamic_stats: boolean
// BuilderDraft/draftOf carregam os dois (passthrough do TCK-060)
```

### O que muda em `BuilderEditorScreen.tsx` e vizinhos

1. **`useHashRoute.ts:3-4`** — `'stats'` entra na união `BuilderTab` e no array
   `BUILDER_TABS`, depois de `characters` e antes de `media`. Sem isso o hash
   `#/builder/{id}/stats` cai em `identity`.
2. **`TAB_ORDER` (`BuilderEditorScreen.tsx:32`)** — `'stats'` entre
   `'characters'` e `'media'`. É o array que dita a ordem visual e o passeio de
   seta/Home/End no tablist.
3. **`TAB_LABEL_KEY` (`:34-40`)** — `stats: 'builder.editor.tab.stats'`. O
   `Record<BuilderTab, StringKey>` é total: sem a entrada o `tsc -b` reprova.
4. **`draftOf` (`:42-44`)** — nada a fazer; só conferir que `stats` e
   `meta.allow_dynamic_stats` chegam ao rascunho (TCK-060).
5. **`slice` (`:46-61`)** — dois pontos:
   - `case 'stats'` devolve
     `{ stats: draft.stats, allow_dynamic_stats: draft.meta.allow_dynamic_stats }`
     (molde do `case 'world'`, que já junta um campo de `meta` à fatia);
   - `case 'identity'` passa a **descartar `allow_dynamic_stats`** na
     desestruturação, junto de `world_mode` e `default_start` (`:49`). Sem isso,
     mexer no toggle acende o ponto de sujo na aba Identidade, que não tem esse
     controle.
6. **`demoEdit` (`:65-93`)** — `case 'stats'`: alterna o `DEMO_MARK` no `name` do
   primeiro stat e devolve o rascunho intacto com a lista vazia (molde do
   `case 'starts'`). O `switch` é exaustivo sobre `BuilderTab`; sem o `case` o
   `tsc -b` reprova.
7. **Render (`:598-610`)** — `activeTab === 'stats' ? <StatsTab {...tabProps} />`
   na cadeia, antes de `media`. Não remova o `TabPlaceholder`: ele continua sendo
   o fallback de tipo.
8. **`isTabDirty` (`:366-369`)** — inalterado: só `media` é excluído, e `stats`
   tem fatia de verdade.

### CSS

O padrão lista + formulário está hoje duplicado como `.builder-starts-*`
(`builderEditor.css:696-812`) e `.builder-characters-*` (`:814-938`). Este ticket
**não migra** as abas existentes: generaliza as mesmas regras, copiadas, com
nomes neutros, e a aba nova usa só isso:

```
.builder-masterDetail   (flex column; grid 260px + minmax(0,1fr) em ≥900px)
.builder-list           (ul sem marcador, gap .5rem)
.builder-list-label
.builder-list-item      (botão, min-height 44px, borda #33363f, texto à esquerda)
.builder-list li.is-selected .builder-list-item   (border-color var(--fg), peso 600)
.builder-list li.is-invalid  .builder-list-item   (border-color #ff8a8a)
@media (max-width: 479.98px) .builder-list li { flex-direction: column; align-items: stretch }
```

Regras próprias:
- `.builder-field input[type='number'] { min-height: 44px; padding: 0 .75rem; … }`
  — o seletor atual (`builderEditor.css:389-391`) cobre `text`, sem tipo e
  `select`; sem isso o campo numérico nasce fora do padrão de toque.
- `.builder-stats-numberRow` — mínimo/máximo/valor inicial em
  `grid-template-columns: repeat(3, minmax(0, 1fr))` a partir de 480px; abaixo,
  coluna.
- `.builder-stats-levels` / `.builder-stats-levelRow` — molde de
  `.builder-world-lore` / `.builder-world-lore-block` (`builderEditor.css:624-686`):
  cartão em coluna no menor breakpoint; em ≥480px, grid com `from` e texto na
  primeira linha e o remover ao lado, com `min-width: 0` nos campos.
- Badge: **reusa `.builder-starts-badge`** (a `CharactersTab` já reusa essa classe
  para o tier — precedente estabelecido). Campos: reusa `.builder-field`,
  `.builder-field-textarea`, `.field-hint`, `.field-error`. Vazio: reusa
  `components/EmptyState.tsx`.
- Sem scroll horizontal em 320px. `.builder-editor-tabs` já é `overflow-x: auto`:
  com 6 abas a barra rola em vez de esmagar os rótulos.

### Acessibilidade

- Ordem de tabulação no formulário: id → nome → ícone → cor → mínimo → máximo →
  valor inicial → descrição → níveis (from → texto → remover, por linha) →
  adicionar nível.
- Tudo é `<button type="button">` e controle nativo: Tab, Shift+Tab, Enter,
  Espaço e as setas do `type="number"` funcionam sem `onKeyDown` extra.
  `Ctrl/Cmd+S` continua salvando pelo atalho global.
- Alvo de toque ≥ 44px em botão, input e `select`.
- O ícone do item da lista é `aria-hidden`: o nome acessível do botão é o nome do
  stat, não um emoji lido em voz alta.
- A cor escolhida pelo autor **não** pinta texto nenhum no builder; nenhuma
  informação depende só de cor.
- Foco visível: o builder usa o `:focus-visible` global (`index.css:35-38`);
  nenhuma regra nova pode removê-lo.

### Tamanho

`StatsTab.tsx` (~300), `validate.ts` (+65), `builderEditor.css` (+90),
`strings/builder.ts` (+90, dois dicionários), `BuilderEditorScreen.tsx` (+15),
`useHashRoute.ts` (+2) e os testes (~220). Fica acima das 400 linhas mesmo depois
dos cortes declarados em "Fora": é uma aba inteira, e o precedente do repositório
para a mesma coisa é a `CharactersTab` (TCK-048, 1320 linhas em 5 pontos). Os
cortes reduziram a superfície em ~40% sem deixar a aba inutilizável; quebrar
outra vez produziria um PR de componente sem consumidor, que a regra proíbe.

## Contrato público

Consumido por **TCK-070** e **TCK-073** (as duas outras abas novas). Congela
aqui:

```ts
// frontend/src/builder/validate.ts
export const STAT_ID_RE = /^[a-z0-9_-]+$/      // com underscore, ao contrário de ID_RE
export const STAT_COLOR_RE = /^#[0-9a-fA-F]{6}$/
export const MAX_STAT_NAME = 40
export const MAX_STAT_ICON = 4
export const MAX_STAT_DESCRIPTION = 200
```

- `STAT_ID_RE` é a mesma classe de caracteres do nome de comando (TCK-073), que a
  importa (com alias legível, se quiser: `const COMMAND_NAME_RE = STAT_ID_RE`) e
  **nunca** escreve uma segunda expressão à mão.
- Chaves i18n compartilhadas, criadas aqui: `builder.field.slugUnderscoreInvalid`
  (usada por TCK-073) e `builder.validate.integerRequired` (campo numérico
  pendente). Nenhuma aba pode duplicá-las com outro nome.
- Bloco de CSS compartilhado: `.builder-masterDetail`, `.builder-list`,
  `.builder-list-label`, `.builder-list-item` e os modificadores `is-selected` /
  `is-invalid` no `<li>`. **Não** inclui `.builder-list-selectRow` nem
  `.builder-list-selectActions` (a variante `select` estreita ficou fora).
- `BuilderTab` passa a ter `'stats'`; `TAB_ORDER` fica
  `['identity','world','starts','characters','stats','media']`.

## Acceptance criteria

- [ ] O tablist mostra 6 abas, com Stats entre Personagens e Mídia, e o hash
      `#/builder/{id}/stats` seleciona a aba.
- [ ] Com `stats: []` a aba mostra o `EmptyState`, o botão "Novo stat" e o
      toggle `allow_dynamic_stats` ainda acessível.
- [ ] "Novo stat" cria `{id: 'stat-N' livre, name: '', min: 0, max: 100,
      default: 50, icon: null, color: null, description: null, levels: []}`, o
      seleciona e foca o campo Nome.
- [ ] Digitar nos campos grava no rascunho; ícone, cor e descrição vazios após
      `trim` gravam `null`, nunca `''`.
- [ ] Apagar um campo numérico mostra `builder.validate.integerRequired`, mantém
      o valor no rascunho e o `blur` devolve o valor gravado ao input.
- [ ] "Adicionar nível" cria `{from: min | min(último+1, max), text: ''}` e foca
      o texto do nível novo; remover devolve o foco ao nível que assumiu a
      posição ou ao botão de adicionar.
- [ ] `validateDraft` produz exatamente os erros da tabela de validação, com
      `tab: 'stats'` e `field` no padrão `stats.<i>.…`, e nenhum erro quando a
      lista de stats está vazia.
- [ ] `max <= min` produz erro em `stats.<i>.max` e **nenhum** erro em
      `stats.<i>.default` nem nos `from` daquele stat.
- [ ] Mexer no toggle `allow_dynamic_stats` deixa **só** a aba Stats com
      `is-dirty` (a Identidade fica limpa).
- [ ] "Ir para {campo}" do painel de validação foca
      `builder-field-stats.<i>.<campo>`.
- [ ] `strings/builder.ts` tem todas as chaves novas em `en` e `pt-br`, e nenhuma
      string literal de UI fora do dicionário.
- [ ] `npm run check` verde (inclui `tsc -b` e `vitest run`).

## Cenários de teste

Padrão da casa: `vitest` + `@testing-library/react`, `Harness` local com
`useState` + `validateDraft`, `<pre data-testid>` com o JSON do pedaço editado, e
busca por `t(chave)` — nunca por literal.

```tsx
function Harness(props: { initial: BuilderDraft }) {
  const [draft, setDraft] = useState(props.initial)
  const errors = validateDraft(draft)
  return (
    <>
      <StatsTab scenarioId="school" draft={draft} onChange={setDraft} errors={errors} goToTab={() => {}} />
      <pre data-testid="stats-debug">{JSON.stringify(draft.stats)}</pre>
      <pre data-testid="dynamic-debug">{String(draft.meta.allow_dynamic_stats)}</pre>
    </>
  )
}
```

### `frontend/src/components/builder/StatsTab.test.tsx` (novo)

- Feliz: **grava nome, mínimo, máximo e valor inicial no rascunho** —
  `fireEvent.change` nos quatro campos deixa `stats-debug` com
  `{name: 'Reputação', min: 0, max: 100, default: 40}`.
- Feliz: **cria um stat com id sugerido livre e foca o nome** — lista com
  `stat-1`; clicar em `builder.stats.create` acrescenta `stat-2` com
  `min: 0, max: 100, default: 50, levels: []` e
  `document.getElementById('builder-field-stats.1.name')` fica com o foco
  (`waitFor`).
- Feliz: **troca de stat pela lista, anuncia e foca o nome** — dois stats; clicar
  no segundo item foca `builder-field-stats.1.name` e mostra
  `builder.detail.selected` com o nome dele.
- Feliz: **adiciona nível com `from` derivado e foca o texto** — stat `0..100`
  sem níveis: o primeiro "Adicionar nível" grava `{from: 0, text: ''}` e foca
  `builder-field-stats.0.levels.0.text`; o segundo grava `from: 1`.
- Feliz: **marca o toggle de stats dinâmicos** — clicar no checkbox
  `builder.stats.allowDynamic` deixa `dynamic-debug` com `true`.
- Borda: **mostra o estado vazio com o toggle ainda visível** — `stats: []`:
  `builder.stats.empty.title` na tela, botão `builder.stats.create` presente e o
  checkbox ainda achável por `getByRole`.
- Borda: **restaura o valor gravado quando o campo numérico é apagado** — apagar
  o Máximo mostra `builder.validate.integerRequired`, mantém `stats-debug` com o
  `max` antigo e, no `blur`, devolve o valor ao input.
- Borda: **guarda ícone e descrição vazios como `null`** — preencher e apagar
  deixa `icon: null` e `description: null`, não `''`.
- Borda: **marca na lista um stat não selecionado com erro** — segundo stat com
  nome vazio: o `<li>` que contém `builder.starts.itemInvalid` tem `is-invalid` e
  o do primeiro não.
- Borda: **abre selecionando o primeiro stat com erro** — três stats, erro só no
  terceiro: `builder-field-stats.2.name` está na tela na montagem.
- Borda: **remove um nível do meio e devolve o foco ao que subiu** — três níveis,
  remover o segundo: foco em `builder-field-stats.0.levels.1.text` e anúncio
  `builder.stats.levels.removed`.
- Borda: **remove o único stat e devolve o foco ao botão de criar** — a tela
  passa a mostrar o `EmptyState` e o foco está no botão `builder.stats.create`.
- Falha: **erro de id repetido no segundo stat** — dois stats com id `vida`:
  `builder.field.slugTaken` `{slug: 'vida'}` visível, o input do segundo com
  `aria-invalid="true"` e o do primeiro sem.
- Falha: **erro de máximo abaixo do mínimo** — `min: 10, max: 5`:
  `builder.validate.statMaxAboveMin` num `role="alert"` ligado ao campo Máximo
  por `aria-describedby`.
- Falha: **erro de cor inválida sem reescrever o campo** — digitar `#zzz`:
  `builder.validate.colorInvalid` na tela e `stats-debug` com `color: '#zzz'`
  exatamente como digitado.
- Falha: **erro de nível fora do intervalo** — `from: 200` num stat `0..100`:
  `builder.validate.levelFromRange` com `{min: 0, max: 100}`.

### `frontend/src/builder/validate.test.ts` (existente, casos novos)

- Feliz: **não reclama de um cenário sem stat nenhum** — `stats: []` não produz
  erro de aba `stats`.
- Falha: **acusa id de stat fora do padrão** — `id: 'Vida Total'` dá
  `tab: 'stats'`, `field: 'stats.0.id'`, `builder.field.slugUnderscoreInvalid`;
  `id: 'vida_total'` **não** dá erro (underscore é permitido, ao contrário do id
  de start).
- Falha: **acusa o valor inicial fora do intervalo** — `min: 0, max: 10,
  default: 50` dá erro em `stats.0.default` com
  `builder.validate.statDefaultRange`.
- Borda: **cala as regras derivadas quando o intervalo está quebrado** —
  `min: 10, max: 5, default: 7`: existe erro em `stats.0.max` e **não** existe
  erro em `stats.0.default`.
- Falha: **acusa níveis em ordem não crescente** — `[{from: 40}, {from: 40}]` dá
  `builder.validate.levelFromOrder` em `stats.0.levels.1.from` e nada em
  `stats.0.levels.0.from`.
- Falha: **acusa texto de nível vazio** — `field` `stats.0.levels.0.text`,
  mensagem `builder.field.required`.
- Borda: **compõe o rótulo do erro com o nome do stat** — o `label` começa pelo
  nome e cai para o id quando o nome está vazio.

### `frontend/src/screens/BuilderEditorScreen.test.tsx` (existente, casos novos)

- Feliz: **mostra seis abas com Stats entre Personagens e Mídia** —
  `getAllByRole('tab')` tem 6 itens e o quinto é `t('builder.editor.tab.stats')`.
- Borda: **marca só a aba Stats como suja ao mexer no toggle** — render em
  `tab="stats"`, clicar no checkbox: a aba Stats tem `is-dirty` e a Identidade
  não. É o teste que prova o descarte de `allow_dynamic_stats` no
  `case 'identity'` do `slice`.
- Falha: **"Ir para {campo}" leva ao campo do stat** — documento com stat de nome
  vazio; Salvar abre o painel de validação e clicar no botão do erro foca
  `builder-field-stats.0.name`.

### `frontend/src/useHashRoute.test.ts` (existente, caso novo)

- Feliz: **resolve `#/builder/school/stats`** — `{ name: 'builderEditor',
  id: 'school', tab: 'stats' }`.

### Inventário da suíte existente (preparação, nunca asserção)

| Arquivo | O que muda | Por quê |
|---|---|---|
| `frontend/src/screens/BuilderEditorScreen.test.tsx:92` | `expect(tabs).toHaveLength(5)` vira `6` | a aba nova entra em `TAB_ORDER`. É contagem, não comportamento: a asserção continua sendo "o tablist tem uma aba por item de `TAB_ORDER`" |
| `frontend/src/screens/BuilderEditorScreen.test.tsx:7-43` | o literal `DOCUMENT` ganha `stats: []` e `meta.allow_dynamic_stats: false` | o `DOCUMENT` **não é anotado** (é corpo `unknown` de `jsonResponse`), então o `tsc -b` não exige os campos, mas sem eles `draft.stats` chega `undefined` na aba e o render quebra |
| `frontend/src/useHashRoute.test.ts` | nada muda | `falls back to identity for an unknown tab` usa `nope`, que continua desconhecido |
| `frontend/src/i18n.test.ts` | nada muda | `has the same keys in en and pt-br` passa a cobrir as chaves novas automaticamente |

Fixtures de `BuilderDraft` (`validate.test.ts`, `StartsTab.test.tsx`,
`WorldTab.test.tsx`, `CharactersTab.test.tsx`, `IdentityTab.test.tsx`,
`MediaTab.test.tsx`, `BuilderPreview.test.tsx`) **são responsabilidade do
TCK-060**: os campos novos de `ScenarioDocument` são obrigatórios e o `tsc -b` da
wave 1 não fecha sem eles. Se algum literal ainda estiver incompleto quando este
ticket rodar, complete-o com `stats: []` (e nada mais) como preparação; nenhuma
asserção desses arquivos muda.

Nenhum teste existente **perde** cobertura: os quatro arquivos de aba antigos
continuam exercitando as mesmas abas, e a validação existente não é tocada.

## Rollout e kill switch

N/A — `risk: low`. A aba é edição de rascunho em memória, sem rede nova e sem
migração: só o Salvar toca o disco, pelo caminho que já existe. Reverter é
remover `'stats'` de `TAB_ORDER`/`BUILDER_TABS` e o `<StatsTab />` da cadeia de
render; `stats.yaml` já escrito continua válido para o loader (TCK-060) e volta a
sobreviver por passthrough sem aparecer na tela.

## Observabilidade

Eventos: nenhum evento novo no frontend (o projeto não emite telemetria de
cliente). Do lado do servidor, salvar já emite `builder_doc_saved`
(`backend/app/builder_doc.py`) com `files_written`.
Métrica de sucesso: um cenário editado só pelo builder passa a ter `stats.yaml`
no disco com os ids que o autor digitou, e o save que só mexeu em stats grava
exatamente 1 arquivo, sem nenhum `builder_doc_invalid` depois.

## i18n

Bloco `// Builder stats tab` nos **dois** dicionários de
`frontend/src/strings/builder.ts`, depois do bloco de personagens
(`builder.ts:284-333` em `en`) e antes do de mídia. `builder.editor.tab.stats`
entra junto das outras `builder.editor.tab.*` (`:72-76` e `:446-450`);
`builder.field.*` e `builder.validate.*` entram nos blocos que já existem para
elas (`:138-157` e `:512-531`).

### Chaves novas

| Chave | en | pt-br |
|---|---|---|
| `builder.editor.tab.stats` | Stats | Stats |
| `builder.stats.heading` | Stats | Stats |
| `builder.stats.listLabel` | Stats in this scenario | Stats deste cenário |
| `builder.stats.create` | New stat | Novo stat |
| `builder.stats.added` | Stat {id} added | Stat {id} adicionado |
| `builder.stats.removed` | Stat {name} removed. Discard or reload brings it back. | Stat {name} removido. Descartar ou recarregar traz de volta. |
| `builder.stats.remove.title` | Remove the stat {name} | Remover o stat {name} |
| `builder.stats.unnamed` | Unnamed stat | Stat sem nome |
| `builder.stats.empty.title` | No stats yet | Nenhum stat ainda |
| `builder.stats.empty.body` | A scenario plays fine without stats. Declare one for each number the HUD should show: the narrator moves it with [STAT:id:±N] and reads its level text every turn. | Um cenário joga bem sem stat nenhum. Declare um para cada número que o HUD deve mostrar: o narrador mexe nele com [STAT:id:±N] e lê o texto do nível todo turno. |
| `builder.stats.orderHint` | The order here is the order of the bars in the HUD. A new stat goes to the end. | A ordem daqui é a ordem das barras no HUD. Stat novo entra no fim. |
| `builder.stats.itemMeta` | {min}–{max} · starts at {default} | {min}–{max} · começa em {default} |
| `builder.stats.levelsBadgeOne` | 1 level | 1 nível |
| `builder.stats.levelsBadgeOther` | {count} levels | {count} níveis |
| `builder.stats.id` | Id | Id |
| `builder.stats.id.hint` | Goes in the tag [STAT:id:+5] and in the judge's answer. Lowercase letters, numbers, hyphen and underscore. | Vai na tag [STAT:id:+5] e na resposta do juiz. Letras minúsculas, números, hífen e underscore. |
| `builder.stats.name` | Name | Nome |
| `builder.stats.icon` | Icon | Ícone |
| `builder.stats.icon.hint` | One emoji, or up to 4 characters. Empty means no icon. | Um emoji, ou até 4 caracteres. Vazio fica sem ícone. |
| `builder.stats.color` | Color | Cor |
| `builder.stats.color.hint` | Hex with 6 digits, like #f5c542. Empty uses the default HUD color. | Hex de 6 dígitos, como #f5c542. Vazio usa a cor padrão do HUD. |
| `builder.stats.min` | Minimum | Mínimo |
| `builder.stats.max` | Maximum | Máximo |
| `builder.stats.default` | Starting value | Valor inicial |
| `builder.stats.default.hint` | What a new session starts with. Sessions already played keep their own value. | Com o que uma sessão nova começa. Sessões já jogadas mantêm o valor delas. |
| `builder.stats.description` | Description | Descrição |
| `builder.stats.description.hint` | Goes to the narrator every turn, next to the value. Say what the number means. | Vai para o narrador todo turno, ao lado do valor. Diga o que o número significa. |
| `builder.stats.levels.legend` | Levels | Níveis |
| `builder.stats.levels.hint` | Optional. The active level is the last one whose starting value is at or below the current value; only its text goes to the narrator. | Opcional. O nível ativo é o último cujo valor inicial é menor ou igual ao valor atual; só o texto dele vai para o narrador. |
| `builder.stats.levels.empty` | No levels. The stat reaches the narrator as a bare number. | Nenhum nível. O stat chega ao narrador como número puro. |
| `builder.stats.levels.add` | Add level | Adicionar nível |
| `builder.stats.levels.from` | Level {index} starts at | Nível {index} começa em |
| `builder.stats.levels.text` | Level {index} text | Texto do nível {index} |
| `builder.stats.levels.remove` | Remove level {index} | Remover o nível {index} |
| `builder.stats.levels.added` | Level {index} added | Nível {index} adicionado |
| `builder.stats.levels.removed` | Level {index} removed | Nível {index} removido |
| `builder.stats.allowDynamic` | Let the game create stats during play | Deixar o jogo criar stats durante o jogo |
| `builder.stats.allowDynamic.hint` | The HUD judge may add up to 6 stats per session, on top of the ones declared here. They live in the session and never touch the scenario files. | O juiz do HUD pode criar até 6 stats por sessão, além dos declarados aqui. Eles vivem na sessão e nunca tocam os arquivos do cenário. |
| `builder.field.label.statId` | Stat id | Id do stat |
| `builder.field.slugUnderscoreInvalid` | Use only lowercase letters, numbers, hyphens and underscores. | Use só letras minúsculas, números, hífens e underscores. |
| `builder.validate.integerRequired` | Type a whole number. | Digite um número inteiro. |
| `builder.validate.colorInvalid` | Use a hex color with 6 digits, like #f5c542. | Use uma cor hex de 6 dígitos, como #f5c542. |
| `builder.validate.statMaxAboveMin` | The maximum must be greater than the minimum. | O máximo precisa ser maior que o mínimo. |
| `builder.validate.statDefaultRange` | The starting value must be between {min} and {max}. | O valor inicial precisa estar entre {min} e {max}. |
| `builder.validate.levelFromRange` | A level must start between {min} and {max}. | Um nível precisa começar entre {min} e {max}. |
| `builder.validate.levelFromOrder` | Each level must start above the one before it. | Cada nível precisa começar acima do anterior. |

### Chaves do design que **não** entram (cortes declarados em "Fora")

`builder.stats.color.picker`, `builder.stats.color.clear`,
`builder.stats.manyHint`, `builder.stats.levels.reordered`,
`builder.stats.name.hint`.

### Chaves reaproveitadas (nada de chave nova para elas)

`common.remove`, `common.cancel`, `common.optional`, `builder.detail.selected`,
`builder.field.required`, `builder.field.tooLong`, `builder.field.slugTaken`,
`builder.starts.itemInvalid`, `builder.editor.tab.dirty`,
`builder.editor.tab.invalid`, `builder.editor.validation.jump`,
`builder.editor.saved`, `builder.editor.save.error.*`.

`builder.stats.name` e `builder.stats.description` repetem valores de
`builder.starts.name` e `builder.identity.description` de propósito: é a
convenção do arquivo (cada aba tem a sua chave `…name`), e é o que deixa o teste
casar o campo por `t()` da chave da própria aba.
