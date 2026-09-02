---
id: TCK-070
title: Aba Lorebook do editor de cenário com quebra do mundo em entradas
status: ready
points: 5
blockedBy: [TCK-060, TCK-066]
files:
  - frontend/src/components/builder/LorebookTab.tsx
  - frontend/src/components/builder/LorebookTab.test.tsx
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

O TCK-060 põe `lorebook: Record<string, LoreEntryDoc>` no `ScenarioDocument` e o
`lore.py` (TCK-064/TCK-075) passa a injetar entrada por keyword no prompt do
narrador. Sem aba, a única forma de criar `lorebook/<id>.yaml` é escrever YAML na
mão.

O problema é maior do que "falta uma aba". O TCK-058 deixou o modo guiado da aba
Mundo aceitar blocos livres (`## Facções`, `## O caderno`), e todo bloco livre vai
para o narrador **todo turno**, dentro do `world.md`. O lorebook existe
justamente para tirar de lá o que só precisa entrar quando o assunto aparece na
cena. Sem um caminho de mão única do mundo para o lorebook, quem já escreveu o
mundo em blocos não tem como aproveitá-lo — e o orçamento de prompt que o TCK-059
mede continua estourando pelo mesmo motivo.

## Escopo

Dentro:
- `frontend/src/components/builder/LorebookTab.tsx` novo: mestre-detalhe com
  título, keywords em chips, texto, escopo (`keyword` | `always`) e ativo; criar
  por diálogo (id + título), deletar por diálogo de confirmação.
- Bloco **"Quebrar mundo em entradas"**: com o mundo em modo guiado, cada bloco
  livre vira uma entrada com id slugificado do título e keyword = título, e sai
  do `world.md`. Confirmação por diálogo, aplicação num único `onChange`.
- `frontend/src/builder/validate.ts`: bloco de validação da aba `lorebook`.
- `frontend/src/screens/BuilderEditorScreen.tsx`: `TAB_ORDER`, `TAB_LABEL_KEY`,
  `slice` (`case 'lorebook'`), `demoEdit` (`case 'lorebook'`) e a cadeia de
  render.
- `frontend/src/useHashRoute.ts`: `'lorebook'` na união `BuilderTab` e em
  `BUILDER_TABS`, entre `stats` e `media`.
- `frontend/src/screens/builderEditor.css`: `.builder-lorebook-*` e a correção de
  largura do botão `×` dos chips em ≤479.98px.
- `frontend/src/strings/builder.ts`: chaves novas nos dois dicionários.
- Testes novos em `LorebookTab.test.tsx`, `validate.test.ts`,
  `BuilderEditorScreen.test.tsx` e `useHashRoute.test.ts`.

Fora (explícito):
- Qualquer arquivo de `backend/`. Schema, loader, `select_lore` e injeção no
  prompt são TCK-060, TCK-064 e TCK-075.
- `frontend/src/api.ts` — `LoreEntryDoc` e `ScenarioDocument.lorebook` chegam
  prontos do TCK-060.
- **`frontend/src/builder/worldMarkdown.ts`.** Decisão tomada depois de ler o
  arquivo: `parseGuidedWorld` já devolve `lore: LoreBlock[]` com título e corpo
  separados (`worldMarkdown.ts:26-79`) e `serializeGuidedWorld` já reescreve o
  markdown a partir da lista (`:12-24`). A quebra é
  `parse → filtrar/mover → serialize`, sem helper novo. Acrescentar função lá
  significaria mexer no módulo congelado pelo TCK-058 sem nenhum ganho.
- **`WorldTab.tsx`.** A quebra reescreve `draft.world` por `serializeGuidedWorld`;
  o componente da aba Mundo não é tocado. A aba Mundo aparecer suja depois da
  quebra é esperado e está escrito no corpo do diálogo.
- `frontend/src/strings/game.ts`, `GamePanel.tsx` e qualquer superfície de jogo.
- **Caminho inverso** (juntar entradas de volta no `world.md`): não existe. O
  desfazer é Descartar/Recarregar antes de salvar, e o diálogo diz isso.
- **Edição do campo `priority`.** Nesta rodada a prioridade não tem controle na
  tela: entrada nova nasce com `priority: 0` e o valor de quem já tem sobrevive ao
  round-trip. Destino: fase 4. Motivo: prioridade só muda o resultado quando o
  orçamento de lore estoura (`LORE_BUDGET_TOKENS`, TCK-064), e o controle exige a
  máquina de número pendente inteira do TCK-066 para um caso de borda. As chaves
  `builder.lorebook.priority` e `.hint` **não** entram.
- **Aviso de orçamento** `builder.lorebook.alwaysBudget` / `ALWAYS_WARN`: aviso
  cosmético, nunca erro. Destino: fase 4.
- **Variante `select` em telas estreitas** (`useIsNarrow`,
  `.builder-list-selectRow`): o bloco compartilhado do TCK-066 nasce **sem** essas
  classes; a lista empilha acima do formulário abaixo de 900px. Destino: fase 4,
  junto com as outras duas abas novas.
- Prévia de quais entradas casariam com um texto de teste, ordenar a lista por
  prioridade e reordenar por arrastar: a lista segue `Object.keys(draft.lorebook)`
  e quem ordena de verdade na injeção é o backend.

## Comportamento esperado

Uma aba **Lorebook** entre Stats e Mídia, com o bloco de quebrar o mundo sempre
no mesmo lugar (acima do mestre-detalhe) e a lista de entradas abaixo.

```
Lorebook
┌ Quebrar o mundo em entradas ─────────────────────────┐
│ 2 blocos livres na aba Mundo podem virar entradas.   │
│ [ Quebrar o mundo em entradas ]                      │
└──────────────────────────────────────────────────────┘
Entradas deste cenário        Título    [ O caderno        ]
  O caderno                   Palavras-chave
  1 palavra-chave  [Deletar]    (caderno ×) (diário ×)
  Sala do grêmio                [ Adicionar palavra-chave ]
  [todo turno] [desligada]    Texto     [ … ]
  [ Nova entrada ]            Quando entra no prompt
                                (•) Quando uma das palavras-chave aparece
                                ( ) Todo turno
                              [x] Ativa
```

### Lista e seleção

Seleção por **id** (o id é o nome do arquivo e não é editável depois de criado,
como em starts e characters): `selectedId: string`, ids do DOM
`builder-field-lorebook.<id>.<campo>`, `field` de validação idêntico.

Seleção inicial: o primeiro id com erro de validação; senão o primeiro id da
ordem de `Object.keys`. Só na montagem — a seleção nunca muda sozinha enquanto o
autor digita. Um `useEffect` sobre `draft.lorebook` devolve a seleção ao primeiro
id quando o selecionado deixa de existir (molde de `CharactersTab.tsx:74-79`).

Item da lista (`.builder-list-item`, `aria-current` quando selecionado): título
(ou o id, quando vazio); badges `.builder-starts-badge` com
`builder.lorebook.alwaysBadge` quando `scope === 'always'` e
`builder.lorebook.disabledBadge` quando `enabled === false`; contagem de keywords
em `.field-hint` (`builder.lorebook.keywordCountZero/One/Other`); e, com erro,
`<span className="visually-hidden">` com `builder.starts.itemInvalid` (**chave
existente**). Ao lado, botão `builder.lorebook.delete` com `aria-label`
`builder.lorebook.delete.title` `{title}`.

### Formulário

| Campo | `field` / id do DOM | Controle | Regras |
|---|---|---|---|
| Título | `lorebook.<id>.title` | `<input>` texto | `trim` no `onBlur`; recebe o foco ao trocar de entrada |
| Keywords | `lorebook.<id>.keywords` | chips + input | abaixo |
| Texto | `lorebook.<id>.body` | `<textarea className="builder-field-textarea" rows={8}>` | texto cru, como digitado (sem `trim` na gravação) |
| Escopo | `lorebook.<id>.scope` | `role="radiogroup"` com dois `<input type="radio">` nativos, `name` comum | `builder.lorebook.scope.keyword` / `.always` |
| Ativo | `lorebook.<id>.enabled` | `<input type="checkbox">` | hint `builder.lorebook.enabled.hint` |

**Keywords como chips** — molde literal das tags da `IdentityTab`
(`.builder-tags-list` + `.builder-tag-chip`, `IdentityTab.tsx:180-190`):

- `<div role="list" className="builder-tags-list">` com um chip por keyword; cada
  chip tem botão `×` com `aria-label` `builder.lorebook.keywords.remove`
  `{keyword}`. O chip em si não é clicável — quem remove é o botão de dentro.
- input na mesma caixa, `<label>` `builder.lorebook.keywords.add`, hint
  `builder.lorebook.keywords.hint`. **Enter** e **vírgula** confirmam o texto
  atual; `Backspace` com o input vazio remove a última (mesmo comportamento das
  tags de identidade).
- A keyword é gravada com `trim`, **preservando acento e caixa** — quem normaliza
  é o `select_lore` do backend. Texto vazio depois do `trim` é ignorado sem erro.
- Repetida (comparação `trim().toLowerCase()` sem acento, via
  `normalize('NFD').replace(/[̀-ͯ]/g, '')`, igual à do backend): não
  entra e mostra `builder.identity.tags.duplicate` `{tag}` (**chave existente,
  reusada**) num `role="alert"` abaixo do input, que some ao digitar de novo.
- Lista vazia: `builder.lorebook.keywords.empty` como `.field-hint`, nunca chip
  fantasma.

**Criar e deletar.** Entrada é um arquivo (`lorebook/<id>.yaml`), então segue o
padrão de starts e characters, não o de linhas em lista:

- **Criar**: `<dialog className="builder-editor-dialog">` com id (`<input>`, hint
  `builder.lorebook.create.idHint`) e título; validação no submit com
  `builder.field.slugInvalid` (regex `^[a-z0-9-]+$`, **sem** underscore — igual a
  starts/characters) e `builder.field.slugTaken` `{slug}`. Entrada nova nasce
  `{title, keywords: [], body: '', scope: 'keyword', priority: 0, enabled: true}`,
  vira a selecionada e o foco vai para o Título ao fechar o diálogo. Molde de
  `StartsTab.tsx:577-619`.
- **Deletar**: `<dialog>` de confirmação com `builder.lorebook.delete.title` e
  `builder.lorebook.delete.body` (`lorebook/{id}.yaml` sai quando você salvar).
  Sem limite mínimo: o cenário pode ficar com zero entradas e volta o
  `EmptyState`. Foco volta ao botão de criar quando a lista esvazia; senão, para o
  item que assumiu a posição.

### Quebrar mundo em entradas

O bloco vive em `.builder-lorebook-split` (moldura de `.builder-world-fallback`,
`builderEditor.css:560-572`), sempre no mesmo lugar, com quatro estados
**mutuamente exclusivos** e todos textuais — nada de botão escondido, nada de
botão desabilitado sem explicação:

| Situação | O que aparece |
|---|---|
| `world_mode !== 'guided'`, ou `parseGuidedWorld(draft.world) === null` | `builder.lorebook.split.unavailable` + botão `.builder-linkButton` `builder.lorebook.split.goToWorld`, que chama `goToTab('world')`. Nenhum botão de quebrar |
| guiado, mas `guided.lore.length === 0` | `builder.lorebook.split.empty` + o mesmo botão de link. Nenhum botão de quebrar |
| guiado com N blocos livres | `builder.lorebook.split.availableOne` / `…Other` `{count}` + botão `builder.lorebook.split` habilitado |
| depois de quebrar | volta ao estado "sem bloco livre", e a live region traz `builder.lorebook.split.done` |

Clicar abre confirmação (`<dialog className="builder-editor-dialog">`,
`aria-labelledby`, foco inicial no Cancelar, `onCancel` com `preventDefault`
fechando pelo estado):

- título `builder.lorebook.split.title`;
- corpo `builder.lorebook.split.body` `{count}`, que diz as três coisas que
  importam: os blocos **saem** do `world.md`; o `world.md` vai ao narrador todo
  turno, e a entrada só entra quando a keyword aparece na cena; nada é escrito no
  disco antes de salvar;
- ações: `common.cancel` (**existente**) e `builder.lorebook.split.submit`.

Aplicação, para cada bloco de `guided.lore`, **na ordem da lista**:

1. bloco com `title.trim() === ''` é **pulado** e continua no mundo (a `WorldTab`
   já trata título vazio como erro; não é papel desta aba consertar);
2. `id = slugify(title)`; se der string vazia, `id = 'lore'`;
3. colisão com id já existente no lorebook **ou** com id gerado antes nesta mesma
   execução: sufixo `-2`, `-3`, … até sobrar livre (molde de `dedupeFolder`,
   `BuilderListScreen.tsx:33-39`; a função é privada daquele módulo, então
   reescreva o laço aqui — não exporte nada de lá);
4. entrada nova: `{title: title.trim(), keywords: [title.trim()], body,
   scope: 'keyword', priority: 0, enabled: true}`;
5. os blocos aproveitados saem de `guided.lore`; os pulados ficam.

O rascunho é atualizado com **um único `onChange`** contendo o `lorebook` novo e o
`world` reserializado. Um `onChange` só = uma marca de sujo, um Descartar desfaz
tudo. Nenhuma chamada de rede: é edição de rascunho, e só o Salvar toca o disco.

Depois de aplicar: a primeira entrada criada vira a selecionada e o foco vai para
o Título dela; a live region traz `builder.lorebook.split.done` `{count}` e,
quando algum bloco foi pulado, também `builder.lorebook.split.skipped` `{count}`
(as duas frases na mesma string anunciada, separadas por espaço).

### Validação

`label` do painel = `${título ou id} — ${rótulo do campo}`.

| Situação | `field` | Mensagem |
|---|---|---|
| id fora de `^[a-z0-9-]+$` | `lorebook.<id>` | `builder.field.slugInvalid` *(existente)* |
| título vazio após `trim` | `lorebook.<id>.title` | `builder.field.required` *(existente)* |
| título > 80 | `lorebook.<id>.title` | `builder.field.tooLong` `{max: 80}` *(existente)* |
| `scope === 'keyword'` e nenhuma keyword não vazia | `lorebook.<id>.keywords` | `builder.validate.loreKeywordRequired` *(nova)* |
| keyword > 60 | `lorebook.<id>.keywords` | `builder.field.tooLong` `{max: 60}` |

Não é erro, por decisão: corpo vazio (a entrada existe e não injeta nada — o hint
`builder.lorebook.body.hint` explica); `scope: 'always'` sem keyword; prioridade
negativa; entrada desligada com qualquer conteúdo; lorebook vazio. Chave
duplicada em `Object.keys` é impossível por construção, e o diálogo de criação já
barra id repetido.

### Estados

| Estado | O que o autor vê |
|---|---|
| **Vazio** | `EmptyState` `builder.lorebook.empty.title`/`.body` com "Nova entrada" como `action`. Duas saídas na tela: o botão e o bloco de quebrar o mundo, com o texto do estado que se aplica |
| **Vazio, sem mundo guiado** | O bloco de quebrar mostra `builder.lorebook.split.unavailable` e o link para a aba Mundo. O autor nunca fica olhando para um botão morto |
| **Carregando** | Nada novo: parse do mundo, slug e validação são síncronos sobre rascunho em memória. O skeleton do `BuilderEditorScreen` continua cobrindo o carregamento do documento |
| **Erro de validação (campo)** | Erro inline `role="alert"` + `.field-error`, `aria-invalid` no controle, ligado por `aria-describedby`. A mensagem de keyword diz as duas saídas: dar uma keyword ou trocar o escopo |
| **Erro de validação (salvar)** | Painel existente com "Ir para {campo}"; item com erro `is-invalid` na lista; seleção inicial cai na primeira entrada com erro |
| **Erro ao salvar** | Inalterado (`builder.editor.save.error.*`, 409, 503) |
| **Sucesso** | Topo passa a "Tudo salvo", ponto de sujo some, `builder.editor.saved` anunciado. Dentro da aba, a live region anuncia entrada selecionada, keyword repetida e o resultado da quebra |

## Detalhes técnicos

### Contrato consumido

Do **TCK-060**:

```ts
export type LoreEntryDoc = {
  title: string
  keywords: string[]
  body: string
  scope: 'keyword' | 'always'
  priority: number
  enabled: boolean
}
// ScenarioDocument.lorebook: Record<string, LoreEntryDoc>   — chave = stem do arquivo
```

Do **TCK-058** (congelado, sem alteração aqui):

```ts
export function parseGuidedWorld(md: string): GuidedWorld | null
export function serializeGuidedWorld(w: GuidedWorld): string
export type LoreBlock = { title: string; body: string }   // GuidedWorld.lore
```

Do **TCK-066**: as classes `.builder-masterDetail` / `.builder-list*` do
`builderEditor.css`. **Não** existe `.builder-list-selectRow`. `slugify` é
exportado por `frontend/src/screens/BuilderListScreen.tsx:22` (NFD, remove
acento, `[^a-z0-9]+` → `-`, corta em 64, apara hífens): **importe essa função**;
extrair para módulo próprio está fora do escopo.

### O que muda em `BuilderEditorScreen.tsx` e vizinhos

1. **`useHashRoute.ts:3-4`** — `'lorebook'` na união `BuilderTab` e em
   `BUILDER_TABS`, depois de `stats` e antes de `media`.
2. **`TAB_ORDER` (`BuilderEditorScreen.tsx:32`)** — `'lorebook'` entre `'stats'`
   e `'media'`.
3. **`TAB_LABEL_KEY` (`:34-40`)** — `lorebook: 'builder.editor.tab.lorebook'` (o
   `Record` é total; sem a entrada o `tsc -b` reprova).
4. **`draftOf` (`:42-44`)** — nada a fazer; `lorebook` já vem do TCK-060.
5. **`slice` (`:46-61`)** — `case 'lorebook'` devolve `draft.lorebook` (molde do
   `case 'characters'`, que devolve o mapa cru). A quebra do mundo mexe em
   `draft.world`, então a aba **Mundo** também acende como suja: correto e
   avisado no diálogo. Nenhuma fatia precisa mudar por causa disso.
6. **`demoEdit` (`:65-93`)** — `case 'lorebook'`: alterna o `DEMO_MARK` no
   `title` da primeira entrada; mapa vazio devolve o rascunho intacto (molde do
   `case 'characters'`). Sem o `case` o `switch` deixa de ser exaustivo e o
   `tsc -b` reprova.
7. **Render (`:598-610`)** — `activeTab === 'lorebook' ? <LorebookTab {...tabProps} />`
   entre `stats` e `media`.
8. **`isTabDirty` (`:366-369`)** — inalterado; só `media` fica de fora.

### CSS

- Reusa `.builder-masterDetail`, `.builder-list*` (TCK-066),
  `.builder-starts-badge`, `.builder-field`, `.builder-field-textarea`,
  `.field-hint`, `.field-error`, `.builder-tags-list`, `.builder-tag-chip`,
  `.builder-linkButton`, `.builder-editor-dialog(-actions)` e `EmptyState`.
- `.builder-lorebook-split`: moldura de `.builder-world-fallback`
  (`builderEditor.css:560-572`) — borda 1px, raio 8px, `padding: .75rem 1rem`,
  margem inferior —, com título em peso 600 e o texto do estado em `.field-hint`.
- `.builder-lorebook-scope`: `fieldset` com os dois rádios em coluna e o hint
  abaixo (molde de `.builder-starts-cast`).
- **Correção necessária em ≤479.98px**: a regra existente
  `.builder-editor-panel button { width: 100% }` (`builderEditor.css:363-365`)
  também pega o `×` dos chips. Acrescente
  `.builder-lorebook-tab .builder-tag-chip button { width: auto }` dentro do mesmo
  `@media`, para a lista de keywords não virar uma coluna de botões gigantes em
  320px. **Não** altere o comportamento da aba Identidade neste ticket.
- Em ≤479.98px o `<li>` empilha (regra do bloco compartilhado) e o botão de
  deletar ocupa a largura toda. Sem scroll horizontal em 320px; com 7 abas o
  tablist rola (`.builder-editor-tabs { overflow-x: auto }`, já existente).

### Acessibilidade

- Trocar de entrada: anúncio `builder.detail.selected` (**existente**) e foco no
  Título via `requestAnimationFrame`.
- Diálogos (criar, deletar, quebrar): `showModal()`, foco inicial no botão de
  escape (Cancelar), `onCancel` com `preventDefault` fechando pelo estado, foco
  de volta ao botão que abriu. Molde de `StartsTab.tsx:577-641`.
- Radiogroup de escopo: `<input type="radio">` nativos com `name` comum — setas
  navegam sem `onKeyDown` próprio.
- Ordem de tabulação: título → input de keyword → chips (botões `×`) → corpo →
  escopo → ativo.
- Alvo de toque ≥ 44px em botões e inputs; o `×` do chip mantém os 24×24 já
  definidos em `.builder-tag-chip button`, dentro de uma linha de 44px.
- Nenhuma informação depende só de cor: a entrada desligada tem badge com texto,
  não só opacidade.
- Foco visível preservado; nenhuma regra nova mexe em `:focus-visible`.

### Tamanho

`LorebookTab.tsx` (~300), `validate.ts` (+45), `builderEditor.css` (+45),
`strings/builder.ts` (+80, dois dicionários), `BuilderEditorScreen.tsx` (+15),
`useHashRoute.ts` (+2) e testes (~230). Acima das 400 linhas mesmo com os cortes
declarados: é uma aba inteira mais um movimento de dados entre duas abas. O
precedente do repositório para uma aba nova é a `CharactersTab` (TCK-048, 1320
linhas em 5 pontos). Separar a quebra do mundo em outro ticket criaria um PR de
botão sem tela onde morar.

## Contrato público

N/A — `LorebookTab` é usado só pelo `BuilderEditorScreen`, no mesmo PR. O que
este ticket **acrescenta** ao contrato compartilhado do editor, e que o TCK-073
enxerga, é apenas: `BuilderTab` passa a ter `'lorebook'` e `TAB_ORDER` fica
`['identity','world','starts','characters','stats','lorebook','media']`. Nenhuma
função nova é exportada.

## Acceptance criteria

- [ ] O tablist mostra 7 abas, com Lorebook entre Stats e Mídia, e o hash
      `#/builder/{id}/lorebook` seleciona a aba.
- [ ] Com `lorebook: {}` a aba mostra o `EmptyState` com "Nova entrada" e o bloco
      de quebrar o mundo no estado que se aplica ao rascunho.
- [ ] Criar pela caixa de diálogo grava
      `{title, keywords: [], body: '', scope: 'keyword', priority: 0,
      enabled: true}` na chave digitada, seleciona a entrada e foca o Título.
- [ ] Id fora de `^[a-z0-9-]+$` ou já usado no diálogo de criação mostra
      `builder.field.slugInvalid` / `builder.field.slugTaken` e **não** cria.
- [ ] Enter e vírgula adicionam keyword; `Backspace` no input vazio remove a
      última; keyword repetida (sem acento e sem caixa) não entra e mostra
      `builder.identity.tags.duplicate`.
- [ ] Deletar pede confirmação e, ao confirmar, remove a chave do rascunho.
- [ ] Com mundo guiado e blocos livres, confirmar a quebra grava as entradas com
      `keywords: [título]`, `scope: 'keyword'`, `priority: 0`, `enabled: true`, e
      reescreve `draft.world` **sem** os blocos aproveitados, num único
      `onChange`.
- [ ] Id gerado que colide ganha sufixo `-2`, `-3`, … e nenhuma entrada existente
      é sobrescrita.
- [ ] Bloco de título vazio continua no `world.md` e o anúncio traz
      `builder.lorebook.split.skipped`.
- [ ] Cancelar o diálogo de quebra deixa `lorebook` e `world` byte a byte iguais.
- [ ] Com `world_mode: 'custom'` (ou parse `null`) não existe botão de quebrar, e
      o link abre a aba Mundo via `goToTab('world')`.
- [ ] `validateDraft` produz exatamente os erros da tabela, com `tab: 'lorebook'`
      e `field` no padrão `lorebook.<id>.…`, e nenhum erro com `lorebook: {}`.
- [ ] Depois da quebra, as abas Lorebook e Mundo aparecem `is-dirty` e as demais
      não.
- [ ] `strings/builder.ts` tem todas as chaves novas em `en` e `pt-br`.
- [ ] `npm run check` verde.

## Cenários de teste

```tsx
function Harness(props: { initial: BuilderDraft; goToTab?: (tab: string) => void }) {
  const [draft, setDraft] = useState(props.initial)
  const errors = validateDraft(draft)
  return (
    <>
      <LorebookTab
        scenarioId="school"
        draft={draft}
        onChange={setDraft}
        errors={errors}
        goToTab={(props.goToTab as never) ?? (() => {})}
      />
      <pre data-testid="lorebook-debug">{JSON.stringify(draft.lorebook)}</pre>
      <pre data-testid="world-debug">{draft.world}</pre>
    </>
  )
}
```

### `frontend/src/components/builder/LorebookTab.test.tsx` (novo)

- Feliz: **grava título, corpo, escopo e ativo** — `fireEvent.change` no título e
  no corpo, clique no rádio `builder.lorebook.scope.always` e no checkbox
  `builder.lorebook.enabled`: `lorebook-debug` reflete os quatro campos.
- Feliz: **adiciona keyword por Enter e por vírgula** — digitar `caderno` +
  Enter e `diário,` deixa `keywords: ['caderno', 'diário']` e dois chips na tela.
- Feliz: **remove keyword pelo botão do chip** — clicar em
  `builder.lorebook.keywords.remove` `{keyword: 'caderno'}` deixa
  `keywords: ['diário']`.
- Feliz: **cria uma entrada pelo diálogo e a seleciona** — id `sala-do-gremio`,
  título `Sala do grêmio`: `lorebook-debug` tem a chave nova com
  `{scope: 'keyword', priority: 0, enabled: true, keywords: []}` e o foco fica em
  `builder-field-lorebook.sala-do-gremio.title`.
- Feliz: **deleta uma entrada pelo diálogo** — confirmar deixa `lorebook-debug`
  sem a chave, e com a lista vazia aparece `builder.lorebook.empty.title`.
- Feliz (quebra): **quebra os blocos livres do mundo em entradas** — mundo
  `'## Universe\n\nU\n\n## O caderno\n\nUm caderno preto.\n\n## Sala do grêmio\n\nCheira a café.'`,
  `world_mode: 'guided'`, lorebook vazio: confirmar em
  `builder.lorebook.split.submit` deixa `lorebook-debug` com `o-caderno` e
  `sala-do-gremio` (título, `keywords: ['O caderno']` / `['Sala do grêmio']`,
  corpo do bloco, `scope: 'keyword'`, `priority: 0`, `enabled: true`) e
  `world-debug` igual a `'## Universe\n\nU'`.
- Feliz (quebra): **anuncia a quebra e seleciona a primeira entrada criada** —
  `builder.lorebook.split.done` `{count: 2}` na live region e foco em
  `builder-field-lorebook.o-caderno.title`.
- Borda (quebra): **desambigua id que já existe** — lorebook já com `o-caderno`:
  a quebra cria `o-caderno-2` e não sobrescreve a entrada anterior.
- Borda (quebra): **deixa no mundo o bloco sem título** — só o bloco com título
  vira entrada, o outro continua em `world-debug`, e o anúncio traz
  `builder.lorebook.split.skipped` `{count: 1}`.
- Borda (quebra): **não quebra sem confirmação** — abrir o diálogo e clicar em
  `common.cancel` deixa `lorebook-debug` e `world-debug` byte a byte iguais.
- Borda (quebra): **esconde o botão quando o mundo é custom** —
  `world_mode: 'custom'`: `queryByRole('button', { name: t('builder.lorebook.split') })`
  é `null`, `builder.lorebook.split.unavailable` está na tela, e clicar em
  `builder.lorebook.split.goToWorld` chama `goToTab` com `'world'`.
- Borda (quebra): **esconde o botão quando não há bloco livre** — mundo guiado só
  com `## Universe`: `builder.lorebook.split.empty` na tela e nenhum botão de
  quebrar.
- Borda (quebra): **quebra o mundo num único `onChange`** — `onChange`
  espionado com `vi.fn` encadeado ao `setDraft`: a confirmação dispara **uma**
  chamada, com `lorebook` e `world` já atualizados no mesmo objeto.
- Borda: **recusa keyword repetida sem acento nem caixa** — com `['Diário']`,
  digitar `diario` + Enter mantém uma keyword só e mostra
  `builder.identity.tags.duplicate`.
- Borda: **mostra o badge de desligada e o de todo turno** — `enabled: false` e
  `scope: 'always'` põem os dois badges no item da lista.
- Borda: **recusa id repetido no diálogo de criação** — `builder.field.slugTaken`
  `{slug}` visível e a entrada existente intacta.
- Falha: **erro de entrada por keyword sem keyword** — entrada
  `scope: 'keyword'` com `keywords: []`:
  `builder.validate.loreKeywordRequired` num `role="alert"` ligado à lista de
  chips por `aria-describedby`.
- Falha: **marca na lista uma entrada não selecionada com erro** — o `<li>` que
  contém `builder.starts.itemInvalid` tem a classe `is-invalid`.

### `frontend/src/builder/validate.test.ts` (existente, casos novos)

- Feliz: **não reclama de um lorebook vazio** — `lorebook: {}` não produz erro de
  aba `lorebook`.
- Falha: **acusa entrada por keyword sem keyword** — `tab: 'lorebook'`,
  `field: 'lorebook.caderno.keywords'`, `builder.validate.loreKeywordRequired`.
- Borda: **não exige keyword em entrada `always`** — a mesma entrada com
  `scope: 'always'` não produz erro.
- Falha: **acusa título vazio** — `field` `lorebook.caderno.title`, mensagem
  `builder.field.required`.
- Falha: **acusa id fora de `[a-z0-9-]`** — chave `Caderno Preto` dá
  `builder.field.slugInvalid` em `lorebook.Caderno Preto`.
- Borda: **aceita corpo vazio** — entrada com `body: ''` e keyword válida não
  produz erro nenhum.

### `frontend/src/screens/BuilderEditorScreen.test.tsx` (existente, casos novos)

- Feliz: **mostra sete abas com Lorebook entre Stats e Mídia** —
  `getAllByRole('tab')` tem 7 itens e o sexto é
  `t('builder.editor.tab.lorebook')`.
- Borda: **marca Lorebook e Mundo como sujos depois da quebra** — render em
  `tab="lorebook"` com mundo guiado e um bloco livre; confirmar a quebra deixa as
  duas abas com `is-dirty` e as demais limpas.

### `frontend/src/useHashRoute.test.ts` (existente, caso novo)

- Feliz: **resolve `#/builder/school/lorebook`** — `{ name: 'builderEditor',
  id: 'school', tab: 'lorebook' }`.

### Inventário da suíte existente (preparação, nunca asserção)

| Arquivo | O que muda | Por quê |
|---|---|---|
| `frontend/src/screens/BuilderEditorScreen.test.tsx:92` | `expect(tabs).toHaveLength(6)` (posto lá pelo TCK-066) vira `7` | uma aba a mais em `TAB_ORDER`; a asserção continua sendo "uma aba por item de `TAB_ORDER`" |
| `frontend/src/screens/BuilderEditorScreen.test.tsx:7-43` | o literal `DOCUMENT` ganha `lorebook: {}` | o `DOCUMENT` não é anotado, então o `tsc -b` não exige o campo, mas sem ele `draft.lorebook` chega `undefined` na aba |
| `frontend/src/components/builder/WorldTab.test.tsx` | nada muda | a `WorldTab` não é tocada; a quebra usa só `serializeGuidedWorld` |
| `frontend/src/builder/worldMarkdown.test.ts` | nada muda | o módulo não é tocado |
| `frontend/src/i18n.test.ts` | nada muda | a paridade de chaves passa a cobrir as novas |

Fixtures de `BuilderDraft` (`validate.test.ts`, `StartsTab.test.tsx`,
`WorldTab.test.tsx`, `CharactersTab.test.tsx`, `IdentityTab.test.tsx`,
`MediaTab.test.tsx`, `BuilderPreview.test.tsx`) são responsabilidade do
**TCK-060**, que os completou para fechar o `tsc -b` da wave 1. Se algum literal
ainda estiver incompleto, acrescente `lorebook: {}` e nada mais.

Nenhum teste existente perde cobertura.

## Rollout e kill switch

N/A — `risk: low`. A aba é edição de rascunho em memória, sem rede nova e sem
migração. A operação mais destrutiva é a quebra do mundo, e ela: (a) pede
confirmação com o efeito escrito no corpo do diálogo; (b) acontece num único
`onChange`, então Descartar ou Recarregar desfaz tudo de uma vez; (c) só chega ao
disco no Salvar, pelo caminho que já existe. Reverter o ticket é remover
`'lorebook'` de `TAB_ORDER`/`BUILDER_TABS` e o `<LorebookTab />` da cadeia de
render; `lorebook/*.yaml` já escrito continua válido para o loader e volta a
sobreviver por passthrough.

## Observabilidade

Eventos: nenhum evento novo no frontend. Do lado do servidor, salvar emite
`builder_doc_saved` com `files_written` (que passa a contar os
`lorebook/<id>.yaml` escritos e podados), e o TCK-075 emite `lore_injected`
`{session_id, turn, ids, tokens}` quando a entrada realmente entra no prompt.
Métrica de sucesso: quebrar um mundo guiado com 3 blocos produz um save com
`files_written` = 4 (`world.md` + 3 entradas), sem `builder_doc_invalid`, e o
`lore_injected` seguinte cita só a entrada cuja keyword apareceu na cena.

## i18n

Bloco `// Builder lorebook tab` nos **dois** dicionários de
`frontend/src/strings/builder.ts`, depois do bloco de stats (TCK-066) e antes do
de mídia. `builder.editor.tab.lorebook` entra junto das outras
`builder.editor.tab.*`; `builder.field.*` e `builder.validate.*` entram nos
blocos que já existem para elas.

### Chaves novas

| Chave | en | pt-br |
|---|---|---|
| `builder.editor.tab.lorebook` | Lorebook | Lorebook |
| `builder.lorebook.heading` | Lorebook | Lorebook |
| `builder.lorebook.listLabel` | Entries in this scenario | Entradas deste cenário |
| `builder.lorebook.create` | New entry | Nova entrada |
| `builder.lorebook.create.title` | New entry | Nova entrada |
| `builder.lorebook.create.idLabel` | File name | Nome do arquivo |
| `builder.lorebook.create.idHint` | Becomes lorebook/{id}.yaml. | Vira lorebook/{id}.yaml. |
| `builder.lorebook.create.submit` | Create entry | Criar entrada |
| `builder.lorebook.empty.title` | No lorebook entries yet | Nenhuma entrada de lorebook ainda |
| `builder.lorebook.empty.body` | An entry only reaches the narrator when one of its keywords shows up in the scene. It is where the world keeps what the prompt shouldn't carry every turn. | Uma entrada só chega ao narrador quando uma palavra-chave dela aparece na cena. É onde o mundo guarda o que o prompt não precisa carregar todo turno. |
| `builder.lorebook.title` | Title | Título |
| `builder.lorebook.title.hint` | Becomes the heading of the entry in the prompt. | Vira o cabeçalho da entrada no prompt. |
| `builder.lorebook.keywords.add` | Add keyword | Adicionar palavra-chave |
| `builder.lorebook.keywords.hint` | Enter or comma adds a keyword. Accents and case don't count when matching. | Enter ou vírgula adiciona uma palavra-chave. Acento e maiúscula não contam na hora de casar. |
| `builder.lorebook.keywords.empty` | No keywords yet. | Nenhuma palavra-chave ainda. |
| `builder.lorebook.keywords.remove` | Remove the keyword {keyword} | Remover a palavra-chave {keyword} |
| `builder.lorebook.keywordCountZero` | no keywords | sem palavra-chave |
| `builder.lorebook.keywordCountOne` | 1 keyword | 1 palavra-chave |
| `builder.lorebook.keywordCountOther` | {count} keywords | {count} palavras-chave |
| `builder.lorebook.body` | Text | Texto |
| `builder.lorebook.body.hint` | What the narrator receives when the entry is active. Empty means nothing is injected. | O que o narrador recebe quando a entrada está ativa. Vazio não injeta nada. |
| `builder.lorebook.scope.legend` | When it goes into the prompt | Quando entra no prompt |
| `builder.lorebook.scope.keyword` | When one of the keywords shows up | Quando uma das palavras-chave aparece |
| `builder.lorebook.scope.always` | Every turn | Todo turno |
| `builder.lorebook.scope.hint` | Every turn spends prompt budget on every turn. Keep it for what the story can't run without. | Todo turno gasta orçamento de prompt em todo turno. Guarde para o que a história não roda sem. |
| `builder.lorebook.enabled` | Active | Ativa |
| `builder.lorebook.enabled.hint` | Off keeps the file on disk and leaves the entry out of the prompt. | Desligada mantém o arquivo no disco e deixa a entrada fora do prompt. |
| `builder.lorebook.alwaysBadge` | every turn | todo turno |
| `builder.lorebook.disabledBadge` | off | desligada |
| `builder.lorebook.delete` | Delete entry | Deletar entrada |
| `builder.lorebook.delete.title` | Delete the entry {title}? | Deletar a entrada {title}? |
| `builder.lorebook.delete.body` | lorebook/{id}.yaml is removed when you save. | lorebook/{id}.yaml é removido quando você salvar. |
| `builder.lorebook.split` | Break the world into entries | Quebrar o mundo em entradas |
| `builder.lorebook.split.availableOne` | 1 free block in the World tab can become an entry. | 1 bloco livre na aba Mundo pode virar entrada. |
| `builder.lorebook.split.availableOther` | {count} free blocks in the World tab can become entries. | {count} blocos livres na aba Mundo podem virar entradas. |
| `builder.lorebook.split.title` | Move the world blocks into the lorebook? | Mover os blocos do mundo para o lorebook? |
| `builder.lorebook.split.body` | The {count} free blocks leave world.md and become entries with keyword scope, each with one keyword: the block title. What changes: world.md goes to the narrator every turn, while an entry only goes in when its keyword shows up in the scene. Nothing is written to disk until you save. | Os {count} blocos livres saem do world.md e viram entradas com escopo por palavra-chave, cada uma com uma palavra-chave: o título do bloco. O que muda: o world.md vai para o narrador todo turno, e a entrada só entra quando a palavra-chave dela aparece na cena. Nada é escrito no disco antes de você salvar. |
| `builder.lorebook.split.submit` | Move the blocks | Mover os blocos |
| `builder.lorebook.split.done` | {count} entries created from the world. The blocks left the World tab. | {count} entradas criadas a partir do mundo. Os blocos saíram da aba Mundo. |
| `builder.lorebook.split.skipped` | {count} blocks stayed in the world because they have no title. | {count} blocos ficaram no mundo por não terem título. |
| `builder.lorebook.split.empty` | The World tab has no free blocks to break out. Blocks you add there show up here. | A aba Mundo não tem bloco livre para quebrar. Blocos adicionados lá aparecem aqui. |
| `builder.lorebook.split.unavailable` | Only the guided world mode has separate blocks. The custom prompt is one single text. | Só o modo guiado do mundo tem blocos separados. O prompt custom é um texto só. |
| `builder.lorebook.split.goToWorld` | Open the World tab | Abrir a aba Mundo |
| `builder.field.label.loreId` | Entry id | Id da entrada |
| `builder.validate.loreKeywordRequired` | An entry scoped by keyword needs at least one keyword — or switch it to every turn. | Uma entrada com escopo por palavra-chave precisa de pelo menos uma palavra-chave — ou troque o escopo para todo turno. |

### Chaves do design que **não** entram (cortes declarados em "Fora")

`builder.lorebook.priority`, `builder.lorebook.priority.hint`,
`builder.lorebook.alwaysBudget`.

### Chaves reaproveitadas (nada de chave nova para elas)

`common.cancel`, `common.remove`, `builder.detail.selected`,
`builder.field.required`, `builder.field.tooLong`, `builder.field.slugInvalid`,
`builder.field.slugTaken`, `builder.identity.tags.duplicate` (chip repetido — a
mensagem "{tag} já está na lista" serve palavra por palavra),
`builder.starts.itemInvalid`, `builder.editor.tab.dirty`,
`builder.editor.tab.invalid`, `builder.editor.validation.jump`,
`builder.editor.saved`, `builder.editor.save.error.*`.
