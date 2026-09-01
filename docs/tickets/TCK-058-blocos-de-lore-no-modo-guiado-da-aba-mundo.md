---
id: TCK-058
title: Blocos de lore no modo guiado da aba Mundo
status: ready
points: 5
blockedBy: []
files:
  - frontend/src/builder/worldMarkdown.ts
  - frontend/src/builder/worldMarkdown.test.ts
  - frontend/src/builder/validate.ts
  - frontend/src/builder/validate.test.ts
  - frontend/src/components/builder/WorldTab.tsx
  - frontend/src/components/builder/WorldTab.test.tsx
  - frontend/src/screens/BuilderEditorScreen.test.tsx
  - frontend/src/screens/builderEditor.css
  - frontend/src/strings.ts
migration: false
ui: true
risk: medium
---

## Problema

O modo guiado da aba Mundo tem cinco campos fixos: Universo, Tom, Regras,
Conflito, Missão (`frontend/src/components/builder/WorldTab.tsx:11-17`). Dois
problemas somados:

1. **Conflito e missão não pertencem ao mundo.** Um mundo grande tem N starts,
   com N conflitos e N missões; o TCK-056 moveu os dois para o start e o TCK-057
   os coloca na aba Starts. Enquanto `builder.world.conflict` e
   `builder.world.mission` continuarem no modo guiado, o autor tem dois lugares
   para escrever a mesma coisa, e um deles não chega mais ao narrador da forma
   que ele espera.
2. **O mundo não cabe em três campos fixos.** Facções, lugares, história — cada
   pedaço merece cabeçalho próprio no `world.md`. Hoje o parse
   (`frontend/src/builder/worldMarkdown.ts:38`) devolve `null` para **qualquer**
   cabeçalho desconhecido: escrever `## Facções` derruba o arquivo inteiro para
   o modo custom. O autor perde o modo guiado por acrescentar uma seção.

## Escopo

Dentro:
- `worldMarkdown.ts`: `GuidedWorld` perde `conflict`/`mission` e ganha
  `lore: LoreBlock[]`; `WORLD_HEADINGS` cai para três; parse e serialização
  passam a tratar blocos de lore.
- `validate.ts`: um erro por bloco de lore com título vazio ou repetido.
- `WorldTab.tsx`: remoção dos dois campos, `fieldset` de blocos de lore com
  adicionar/remover/foco/live region, guarda de título reservado e a nota
  "conflito e missão mudaram de lugar" com botão para a aba Starts, no lugar que
  os campos removidos ocupavam.
- `builderEditor.css`: regras de `.builder-world-lore*`.
- `strings.ts`: 4 chaves removidas, 2 alteradas, 15 novas — nos dois
  dicionários.
- Todos os testes listados no inventário.

Fora (explícito):
- **Contador de tokens estimados (§5 do design): é o TCK-059.** Nenhuma
  constante `WORLD_TOKEN_WARN`, nenhuma chave `builder.world.tokens.*`, nenhum
  `Math.ceil(world.length / 4)` neste PR. O TCK-059 se insere no `WorldTab.tsx`
  já reestruturado por este ticket.
- Qualquer arquivo em `backend/`. O `world.md` continua sendo texto livre para o
  backend; nenhum campo, rota ou validação nova do lado de lá.
- A aba Starts (`StartsTab.tsx`) e o tipo `StartDoc`: os campos `conflict` e
  `mission` do start são do TCK-057. Este ticket não os cria, não os edita e não
  depende deles — só manda o usuário para lá com `goToTab('starts')`.
- Reordenar blocos de lore (arrastar, subir/descer) e limite de quantidade: sem
  isso nesta rodada, por decisão do design.
- Migração de arquivo no disco. `world.md` antigo com `## Conflict`/`## Mission`
  passa a abrir como dois blocos de lore com esses títulos, e abrir e salvar sem
  editar produz o mesmo arquivo byte a byte. Nenhum script de migração, nenhum
  rename automático.
- `builder.world.variables.*` e o modo custom: inalterados.

## Comportamento esperado

*(Seção fechada pelo design-specialist, copiada literalmente de
`design/tema-2-world-lore-blocks.md`. O §5, contador de tokens, está fora deste
ticket e não aparece aqui.)*

### 0. Contrato (congela para quem consome)

```ts
export type LoreBlock = { title: string; body: string }
export type GuidedWorld = { universe: string; tone: string; rules: string; lore: LoreBlock[] }
export const WORLD_HEADINGS = ['Universe', 'Tone', 'Rules'] as const
```

`conflict` e `mission` saem de `GuidedWorld` e de `WORLD_HEADINGS`. Nenhum outro
módulo além de `WorldTab.tsx` e `validate.ts` importa esse arquivo hoje.

### 1. Serialização (`serializeGuidedWorld`)

Ordem no `world.md`: `## Universe`, `## Tone`, `## Rules` (cada um omitido
quando o corpo, após `trim`, é vazio), depois **um `## <título>` por bloco de
lore, na ordem da lista**. Seções separadas por linha em branco (`\n\n`), igual
ao formato atual.

- Título do bloco é gravado com `trim`.
- **Título vazio gera a linha `## ` (dois hashes, um espaço, nada depois).**
  Nunca `trimEnd()` na linha do cabeçalho: `##` sozinho e o corpo colado no
  bloco anterior são os dois jeitos de corromper o arquivo.
- Bloco com título e corpo vazio é gravado só com o cabeçalho.
- Bloco totalmente vazio (título e corpo vazios) também é gravado, como `## `.
  Isso mantém o índice da lista renderizada igual ao índice do parse e ao índice
  do erro de validação. Esse estado é sempre inválido (ver §4), então nunca
  chega ao disco pelo modo guiado.

### 2. Parse (`parseGuidedWorld`)

Cabeçalho é a linha que casa `/^##(?:\s+(.*))?\s*$/` — ou seja, `## Título`,
`## ` e `##`; `###` e `#` não são cabeçalho e continuam sendo corpo.

Regras, nesta ordem:

1. Entrada vazia ou só espaço → `{ universe: '', tone: '', rules: '', lore: [] }`.
2. Texto não vazio antes do primeiro `##` → `null` (modo custom).
3. Os conhecidos `Universe`, `Tone`, `Rules` (case-sensitive, como hoje) só
   valem no prefixo do arquivo e nessa ordem; cada um é opcional e aparece no
   máximo uma vez.
4. O primeiro cabeçalho que não é conhecido abre a região de lore. Dali em
   diante, **todo** `##` é um bloco de lore, na ordem em que aparece, com
   títulos repetidos permitidos no parse.
5. Cabeçalho conhecido depois de um bloco de lore, ou fora de ordem no prefixo
   → `null` (modo custom).
6. Corpo de cada seção é o texto até o próximo `##`, com `trim`.

Consequência declarada: `world.md` antigo com `## Conflict` e `## Mission` abre
em modo guiado com dois blocos de lore chamados `Conflict` e `Mission`, na mesma
posição. Abrir e salvar sem editar produz um arquivo byte a byte igual.

### 3. UI do modo guiado

Ordem na tela:

1. Radiogroup de modo (inalterado).
2. Banner de fallback, quando houver (inalterado).
3. **Bloco do contador de tokens** (§5) — renderizado uma única vez, fora do
   `if (mode === 'guided')`, então aparece nos dois modos.
4. Campos guiados: Universo, Tom, Regras (os três `textarea` de hoje, com os
   mesmos ids `builder-field-universe`, `builder-field-tone`,
   `builder-field-rules`, hints e o erro de obrigatório do Universo).
5. **Nota "conflito e missão mudaram de lugar"** (§6), exatamente onde os campos
   Conflito e Missão ficavam.
6. **`<fieldset className="builder-world-lore">`** com os blocos de lore.

> **Escopo deste ticket sobre o §3**: o item 3 (bloco do contador) é o TCK-059.
> Entregue os itens 1, 2, 4, 5 e 6, e deixe o ponto de inserção livre: o bloco do
> contador entra depois do banner de fallback (`WorldTab.tsx:128-136` hoje) e
> antes do `mode === 'guided' ? ... : ...`. Não crie placeholder, wrapper vazio
> nem comentário reservando o lugar.

Cada bloco de lore é uma linha `.builder-world-lore-block` com:

| Elemento | id / atributos |
|---|---|
| input do título (`type="text"`) | `builder-field-world.lore.<i>.title`, `aria-describedby` = hint (`...-hint`) + erro quando houver (`...-error`), `aria-invalid` quando houver erro |
| hint do título | `builder-field-world.lore.<i>.title-hint`, texto `builder.world.lore.title.hint` |
| erro do título | `builder-field-world.lore.<i>.title-error`, `role="alert"`, `className="field-error"` |
| textarea do corpo | `builder-field-world.lore.<i>.body`, `rows={6}`, `className="builder-field-textarea"` |
| botão remover | texto visível `common.remove`, `aria-label` = `builder.world.lore.remove` com `{index}` |

O índice `<i>` é 0-based no id (para casar com o `field` da validação e com o
`jumpToValidationError`) e 1-based nos textos visíveis/`aria-label`. Os rótulos
são `builder.world.lore.titleLabel` e `builder.world.lore.bodyLabel`, ambos com
`{index}` 1-based, para que dois blocos nunca tenham o mesmo nome acessível.

Botão **`builder.world.lore.add`** fica depois da lista, sempre habilitado (sem
limite de blocos nesta rodada).

Ordem dos blocos = ordem da lista. Bloco novo entra no fim. Sem arrastar e
soltar nesta rodada; reordenar é editar no modo custom (ou ticket futuro).

### 4. Validação dos títulos

Em `validateDraft`, só quando `world_mode === 'guided'` **e**
`parseGuidedWorld(draft.world) !== null` (mesmo guarda do erro de Universo
obrigatório). Um erro por bloco, no campo `world.lore.<i>.title`, com
`label = t('builder.world.lore.titleLabel', { index: i + 1 })`:

| Situação | Mensagem | Efeito |
|---|---|---|
| Título vazio depois de `trim` (inclusive bloco recém-criado) | `builder.world.lore.title.required` | bloqueia o salvar |
| Título repetido (case-insensitive) de outro bloco | `builder.world.lore.title.duplicate` no **segundo e seguintes**, o primeiro fica limpo | bloqueia o salvar |

O título reservado (`Universe`/`Tone`/`Rules`, case-insensitive) não chega ao
`world.md` — ele é barrado antes, na UI (§4.1) — e por isso não tem regra em
`validateDraft`; o bloco correspondente cai na regra "título vazio", que é o que
bloqueia o salvar. A mensagem que o usuário lê é a precisa, a da UI.

#### 4.1 Título reservado

Digitar `Universe`, `Tone` ou `Rules` (em qualquer caixa) como título de bloco
**não pode** ser serializado: viraria cabeçalho conhecido fora de ordem e o
arquivo inteiro cairia para o modo custom no próximo parse (regra 5 do §2),
perdendo o modo guiado por causa de uma tecla.

Comportamento:

- O texto digitado continua visível no input (estado local do componente,
  `pendingTitles: Record<number, string>`, chaveado pelo índice do bloco; o
  valor exibido é `pendingTitles[i] ?? blocos[i].title`).
- O cabeçalho desse bloco é serializado vazio (`## `), o corpo é preservado.
- Erro inline `builder.world.lore.title.reserved` com `{title}`, substituindo a
  mensagem de "título obrigatório" naquele bloco.
- O modo **nunca** vira custom por causa disso; o banner de fallback não aparece.
- Corrigir o título limpa `pendingTitles[i]` e serializa normalmente. Adicionar
  ou remover bloco desloca as chaves de `pendingTitles` junto.

### 6. Nota de mudança de lugar (conflito e missão)

Parágrafo `builder.world.guided.movedHint` seguido de um botão que chama
`goToTab('starts')` com o texto `builder.world.guided.goToStarts`. Botão de
verdade (`<button type="button">`), com a classe de link já usada na aba Starts
(`.builder-starts-castEmptyLink`, promovida para uma classe compartilhada
`.builder-linkButton` se o implementador preferir), alvo de toque de 44px e
foco visível. Nada decorativo: o que parece clicável navega.

### 7. Estados

| Estado | Comportamento |
|---|---|
| **Vazio (nenhum bloco de lore)** | O `fieldset` aparece com a legenda, o hint `builder.world.lore.hint`, o texto `builder.world.lore.empty` e o botão "Adicionar bloco de lore". Nenhuma linha fantasma. A saída dali é o próprio botão. |
| **Vazio (campos guiados)** | Universo vazio segue com o erro de obrigatório já existente; Tom e Regras vazios apenas somem do `world.md`. |
| **Carregando** | Nada novo dentro da aba: parse e serialização são síncronos sobre um rascunho já em memória. O carregamento do documento continua sendo o skeleton (`.builder-skeleton-block` ×2 + `Loading visuallyHidden`) de `BuilderEditorScreen`. |
| **Erro — título** | Erro inline por bloco (`role="alert"`, `.field-error`), `aria-invalid` no input, ligação por `aria-describedby`, e entrada no painel "Conserte isto antes de salvar" com "Ir para {campo}" que foca o input do título. Toda mensagem diz o que fazer: dar um título, escolher outro, tirar a repetição. |
| **Erro — arquivo fora do formato guiado** | Banner de fallback existente (`builder.world.mode.fallback.*`), agora também disparado por cabeçalho conhecido fora de ordem ou depois de um bloco de lore. Recuperação: "Manter como custom", ou editar o texto até voltar ao formato. Texto do corpo do banner ajustado (§i18n). |
| **Erro — salvar** | Inalterado: `builder.editor.save.error.*` com "Tentar de novo", conflito de revisão com recarregar/sobrescrever. |
| **Sucesso** | Indicador `role="status"` do topo ("tem mudanças não salvas" → "salvo"), marcador de aba suja, anúncio `builder.editor.saved` ao salvar. Além disso, live region `polite` própria da aba anuncia `builder.world.lore.added` e `builder.world.lore.removed`. |

### 8. Foco e teclado

- A aba passa a ter uma live region própria:
  `<div role="status" aria-live="polite" className="visually-hidden">`, no mesmo
  molde da `StartsTab`.
- **Adicionar bloco**: o bloco entra no fim, o foco vai para o input de título
  do bloco novo (via `requestAnimationFrame`, padrão de `selectStart`), e a live
  region anuncia `builder.world.lore.added` com o índice. O erro "precisa de
  título" aparece imediatamente abaixo do campo já focado — é orientação, não
  acusação, e some na primeira letra.
- **Remover bloco**: o foco vai para o input de título do bloco que assumiu a
  posição removida; se era o último, para o input de título do bloco anterior;
  se não sobrou bloco nenhum, para o botão "Adicionar bloco de lore". O foco
  nunca cai no `<body>`. A live region anuncia `builder.world.lore.removed`.
- Remoção é imediata, sem diálogo de confirmação (o conteúdo volta com
  Descartar/Recarregar; a aba já tem guarda de mudanças não salvas). Bloco com
  corpo escrito é destrutivo, então o `aria-label` do botão diz qual bloco
  remove.
- Ordem de tabulação dentro de um bloco: título → corpo → remover.
- Todos os controles são `<button type="button">` e inputs nativos: Tab, Shift+Tab,
  Enter e Espaço funcionam sem `onKeyDown` extra.
- `Ctrl/Cmd+S` continua salvando (atalho global da tela) e, com bloco inválido,
  abre o painel de validação com foco nele.

### 9. Responsividade

Menor breakpoint do CSS do builder: `max-width: 479.98px` (com um degrau
intermediário em `899.98px`).

- `.builder-world-lore-block`: cartão em coluna (título, corpo, ações). Em
  ≥480px o input de título e o botão remover ficam na mesma linha
  (`display: flex; gap: .5rem; align-items: center`), com o input em `flex: 1` e
  `min-width: 0`.
- Em ≤479.98px, `flex-direction: column; align-items: stretch` (mesma regra que
  `.builder-starts-list li` e `.builder-characters-list li` já usam), botões com
  `width: 100%` e `justify-content: center`.
- Botões com `min-height: 44px` e inputs com `min-height: 44px`, como o resto do
  builder.
- Nada de scroll horizontal em 320px de largura.

*(A linha do §9 sobre o bloco do contador quebrar em duas linhas em telas
estreitas é do TCK-059.)*

## Detalhes técnicos

**1. `frontend/src/builder/worldMarkdown.ts` (58 linhas hoje, reescrita quase
integral)**

- `GuidedWorld` (`worldMarkdown.ts:1`), `WORLD_HEADINGS`
  (`worldMarkdown.ts:3`) e `FIELD_OF_HEADING` (`worldMarkdown.ts:5-11`) passam a
  refletir o contrato do §0. `FIELD_OF_HEADING` fica com três entradas.
- `serializeGuidedWorld` (`worldMarkdown.ts:13`) hoje monta
  `WORLD_HEADINGS.map(...).filter(text !== '').join('\n\n')`. Mantenha esse
  esqueleto para os três conhecidos e concatene as seções de lore depois.
  Armadilha de tipo: `FIELD_OF_HEADING` hoje é
  `Record<(typeof WORLD_HEADINGS)[number], keyof GuidedWorld>`; com `lore:
  LoreBlock[]` em `GuidedWorld`, `keyof GuidedWorld` inclui `'lore'` e o
  `w[...].trim()` deixa de compilar. Estreite o tipo do valor para
  `'universe' | 'tone' | 'rules'` (ou `Exclude<keyof GuidedWorld, 'lore'>`). A
  linha de cabeçalho é `` `## ${title.trim()}` `` **sem** `trimEnd` posterior no
  join: `## ` com espaço final é intencional (§1).
- `parseGuidedWorld` (`worldMarkdown.ts:20`) hoje casa `/^##\s+(.*)$/`
  (`worldMarkdown.ts:35`) e devolve `null` em cabeçalho desconhecido
  (`worldMarkdown.ts:38`). A regex nova é `/^##(?:\s+(.*))?\s*$/`, e o `return
  null` de desconhecido vira "abre região de lore". O `lastHeadingIndex`
  (`worldMarkdown.ts:27`) continua guardando a ordem dos conhecidos; some uma
  flag de "já entrou em lore" para aplicar a regra 5.
- Armadilha: `/^##(?:\s+(.*))?\s*$/` também casaria `###`? Não — o `#` extra cai
  no `(?:\s+...)`, que exige espaço. Escreva o teste do caso 9 antes de confiar
  na regex.
- Não exporte helper novo além de `LoreBlock`: só `WorldTab.tsx` e
  `validate.ts` importam este módulo (Grep por `worldMarkdown` em
  `frontend/src` confirma).

**2. `frontend/src/builder/validate.ts`**

O bloco do mundo está em `validate.ts:224-235`; o guarda de Universo
obrigatório, em `validate.ts:226-231` (`world_mode === 'guided'` + `guided`
não-nulo). Acrescente a varredura de blocos **dentro do mesmo `if`**, reusando o
`guided` já parseado — chamar `parseGuidedWorld` de novo é desperdício e abre
espaço para divergência. Use `error('world', \`world.lore.${i}.title\`, ...)`,
com o `label` do §4. Duplicata: compare por `title.trim().toLowerCase()`,
marcando só as ocorrências a partir da segunda.

**3. `frontend/src/components/builder/WorldTab.tsx` (245 linhas hoje)**

- `EMPTY_GUIDED` (`WorldTab.tsx:7`) vira
  `{ universe: '', tone: '', rules: '', lore: [] }`.
- `GUIDED_FIELDS` (`WorldTab.tsx:11-17`) perde as duas últimas entradas e os
  tipos literais de `labelKey`/`hintKey` correspondentes — é isso que o design
  chama de "remover os tipos literais em `GUIDED_FIELDS`". Com as chaves apagadas
  de `strings.ts`, deixar o literal quebra o `tsc -b`.
- `updateGuidedField` (`WorldTab.tsx:55`) continua servindo os três campos;
  acrescente funções irmãs para lore (`updateLoreTitle`, `updateLoreBody`,
  `addLore`, `removeLore`), todas terminando em
  `onChange({ ...draft, world: serializeGuidedWorld(next) })`.
- O componente hoje destrutura `const { draft, onChange, errors } = props`
  (`WorldTab.tsx:24`); passe a incluir `goToTab`, que já existe em `TabProps`
  (`screens/BuilderEditorScreen.tsx:24`) e é usado do mesmo jeito em
  `StartsTab.tsx:494`.
- Live region: copie o molde de `StartsTab.tsx:206`
  (`<div role="status" aria-live="polite" className="visually-hidden">` +
  `useState('')`).
- Foco: `requestAnimationFrame(() => ref?.focus())`, molde de
  `selectStart` (`StartsTab.tsx:102`). Guarde os inputs de título num
  `useRef<Record<number, HTMLInputElement | null>>` ou refaça a busca por
  `document.getElementById('builder-field-world.lore.<i>.title')` — o segundo
  caminho é o que o `jumpToValidationError`
  (`screens/BuilderEditorScreen.tsx:361-363`) já usa e não exige ref novo.
- `pendingTitles` é estado **local** do componente e some ao trocar de aba; isso
  é aceito (§4.1 fala em corrigir na hora). Ao remover o bloco `i`, desloque as
  chaves `> i` uma posição para baixo, senão o texto pendente reaparece no bloco
  errado.
- A nota do §6 fica dentro do ramo `mode === 'guided'`, entre o último campo
  guiado e o `fieldset` de lore — literalmente onde os campos Conflito e Missão
  eram renderizados pelo `GUIDED_FIELDS.map` (`WorldTab.tsx:140-167`).

**4. `frontend/src/screens/builderEditor.css` (883 linhas)**

É o CSS importado por `WorldTab.tsx:5`. As regras novas vão junto do bloco
`.builder-world-*` existente (`builderEditor.css:535-600`), e a variante estreita
no `@media (max-width: 479.98px)` já existente (`builderEditor.css:523` e
`:721`). Se promover `.builder-starts-castEmptyLink`
(`builderEditor.css:703-711`) para `.builder-linkButton`, atualize também
`StartsTab.tsx:494` — e nesse caso acrescente `StartsTab.tsx` a `files`, ciente
de que ele é arquivo do TCK-057 em outra wave. **Recomendação: não promova
nesta rodada**; duplique a regra com o nome novo e deixe a unificação para
depois. É uma classe de 7 linhas.

**5. `frontend/src/strings.ts`**

`en` começa em `strings.ts:1`, `ptBr` (`Record<StringKey, string>`) em
`strings.ts:455`, `StringKey = keyof typeof en` em `strings.ts:453`. Âncoras
reais para as inserções e remoções:

| O quê | `en` | `pt-br` |
|---|---|---|
| remover `builder.world.conflict(.hint)` e `builder.world.mission(.hint)` | `:245-248` | `:698-701` |
| trocar o texto de `builder.world.mode.switchToGuidedBody` | `:263` | `:716` |
| trocar o texto de `builder.world.mode.fallback.body` | `:259` | `:712` |
| inserir `builder.world.lore.*` e `builder.world.guided.*` | depois de `builder.world.rules.hint` (`:244`), antes de `builder.world.custom.label` (`:249`) | depois de `:697`, antes de `:702` |

Apagar chave em só um dos dicionários quebra o `tsc -b` (se sobrar em `en`,
falta em `pt-br`) ou o teste de paridade
`strings > has the same keys in en and pt-br` (`frontend/src/i18n.test.ts:78-84`,
compara `Object.keys(strings.en).sort()` com `Object.keys(strings['pt-br']).sort()`).
Depois de mexer, `grep -rn "builder.world.conflict\|builder.world.mission"
frontend/src` tem que voltar vazio.

**6. Janela entre tickets**

Este ticket é independente do TCK-056 e roda na mesma wave que ele; o TCK-057
vem depois. Entre o merge deste e o do TCK-057, o editor não tem campo dedicado
de conflito/missão em lugar nenhum — e isso é seguro, porque o texto que já
existe no `world.md` de cenários guiados vira **bloco de lore** com o mesmo
título e continua indo inteiro para o prompt (`backend/app/prompt.py:269`). Nada
some do disco nem do prompt; só deixa de ter rótulo próprio por uma wave. A nota
do §6 já aponta o caminho novo antes de ele existir, o que é aceito: o botão leva
para a aba Starts, que na pior hipótese ainda não tem os campos.

## Ressalva do coordenador sobre o tamanho

~600 linhas previstas, ~345 delas de teste. Fica num PR só, de propósito:
separar o contrato (`worldMarkdown.ts` + `validate.ts`) do consumidor
(`WorldTab.tsx`) deixaria o primeiro PR vermelho no `tsc -b`, porque
`GUIDED_FIELDS` (`WorldTab.tsx:11-17`) referencia as chaves `conflict` e
`mission` que o contrato remove de `GuidedWorld`. Um commit que não fica verde
sozinho não é um PR. O implementer não deve tentar recortar.

## Contrato público

Este ticket congela o módulo `frontend/src/builder/worldMarkdown.ts`:

```ts
export type LoreBlock = { title: string; body: string }
export type GuidedWorld = { universe: string; tone: string; rules: string; lore: LoreBlock[] }
export const WORLD_HEADINGS: readonly ['Universe', 'Tone', 'Rules']
export function serializeGuidedWorld(w: GuidedWorld): string
export function parseGuidedWorld(md: string): GuidedWorld | null
```

Consumidores: `frontend/src/components/builder/WorldTab.tsx:4` e
`frontend/src/builder/validate.ts:3`, ambos dentro deste ticket.

O que o **TCK-059** consome deste ticket não é este módulo, e sim a estrutura
nova de `WorldTab.tsx`: o contador entra como bloco único, depois do banner de
fallback (`WorldTab.tsx:128-136` no código atual) e antes do ramo
`mode === 'guided' ? ... : ...`, com `draft.world` já disponível no escopo do
componente. Nenhuma assinatura nova é exportada para ele.

Formato de arquivo (o que o backend lê): `world.md` continua sendo markdown
livre. A garantia nova é de round trip — `serializeGuidedWorld(parseGuidedWorld(md))`
devolve `md` para todo arquivo que o parse aceita.

## Acceptance criteria

- [ ] `WORLD_HEADINGS` é `['Universe', 'Tone', 'Rules']` e `GuidedWorld` tem
      `lore: LoreBlock[]`, sem `conflict` nem `mission`.
- [ ] `world.md` com `## Conflict` e `## Mission` abre em modo guiado, com dois
      blocos de lore de mesmo título e corpo, sem banner de fallback; salvar sem
      editar não muda um byte do arquivo.
- [ ] `## Facções` (cabeçalho desconhecido) não derruba mais o arquivo para o
      modo custom.
- [ ] Cabeçalho conhecido fora de ordem, ou depois de um bloco de lore, continua
      caindo no banner de fallback.
- [ ] Adicionar bloco põe o foco no título novo e anuncia na live region;
      remover devolve o foco pela regra do §8 e anuncia.
- [ ] Título vazio e título repetido produzem erro `world.lore.<i>.title` que
      bloqueia o salvar e aparece no painel de validação com "Ir para {campo}"
      funcionando.
- [ ] Digitar `Universe`, `Tone` ou `Rules` como título mostra o erro
      `builder.world.lore.title.reserved`, mantém o texto no input, mantém o
      modo guiado e serializa aquele bloco com cabeçalho vazio e corpo intacto.
- [ ] O botão da nota chama `goToTab('starts')`.
- [ ] `grep -rn "builder.world.conflict\|builder.world.mission" frontend/src`
      volta vazio, e `en`/`pt-br` têm exatamente as mesmas chaves.
- [ ] Nenhuma chave `builder.world.tokens.*` e nenhuma contagem de caracteres do
      `world.md` neste PR (é o TCK-059).
- [ ] `npm run check` verde (`tsc -b` + `vitest run` + pytest).

## Cenários de teste

*(Lista fechada pelo design-specialist, copiada literalmente. Os casos 27 e 28,
do contador de tokens, são do TCK-059 e não aparecem aqui; a numeração original
do design foi preservada para rastreabilidade.)*

### `frontend/src/builder/worldMarkdown.test.ts`

1. **Round trip com blocos de lore** — `{universe, tone, rules, lore: [{title:'Facções', body:'...'}, {title:'História', body:'...'}]}` → serializa → parseia igual.
2. **Ordem canônica** — a saída começa com `## Universe`, `## Tone`, `## Rules` e só depois os blocos, na ordem da lista.
3. **Seções vazias somem** — só `universe` preenchido e `lore: []` produz exatamente `## Universe\n\nA dusty old school.`; o parse devolve os três campos e `lore: []`.
4. **Migração do arquivo antigo** — `'## Universe\n\nU\n\n## Tone\n\nT\n\n## Rules\n\nR\n\n## Conflict\n\nC\n\n## Mission\n\nM'` parseia com `lore` = `[{title:'Conflict',body:'C'},{title:'Mission',body:'M'}]`, e reserializar devolve **a mesma string**.
5. **Cabeçalho conhecido depois de bloco de lore → `null`** — `'## Universe\n\nU\n\n## Facções\n\nF\n\n## Tone\n\nT'`.
6. **Cabeçalho conhecido fora de ordem → `null`** — `'## Tone\n\nT\n\n## Universe\n\nU'` (caso já existente, mantido).
7. **Texto antes do primeiro `##` → `null`** (caso já existente, mantido).
8. **Título vazio round-trip** — `{lore:[{title:'',body:'texto'}]}` serializa com a linha `## ` e parseia de volta com `title: ''` e `body: 'texto'`; o corpo **não** vaza para a seção anterior.
9. **`##` sem espaço também parseia como título vazio**; `### Sub` e `# H1` continuam sendo corpo.
10. **Títulos repetidos sobrevivem ao parse** — dois `## Notas` viram dois blocos (a proibição é da validação, não do parse).
11. **Acentos preservados byte a byte** em título e corpo (caso já existente, estendido ao título).
12. **Entrada vazia / só espaço** → `{universe:'',tone:'',rules:'',lore:[]}`; serializar isso devolve `''`.
13. **`WORLD_HEADINGS` é `['Universe','Tone','Rules']`** (o teste atual, que espera cinco, é atualizado).

### `frontend/src/builder/validate.test.ts`

14. **Título vazio bloqueia** — rascunho guiado com um bloco de corpo escrito e título vazio produz erro `tab: 'world'`, `field: 'world.lore.0.title'`, mensagem `builder.world.lore.title.required`.
15. **Repetido marca só o segundo** — dois blocos `Notas`/`notas`: erro em `world.lore.1.title` com `builder.world.lore.title.duplicate`, nada em `world.lore.0.title`.
16. **Modo custom não valida bloco** — mesmo `world.md`, `world_mode: 'custom'`: nenhum erro de `world.lore.*`.
17. **Fallback não valida bloco** — `world.md` que faz o parse devolver `null` com `world_mode: 'guided'`: nenhum erro de `world.lore.*` (só os que já existem).
18. **Universo obrigatório continua valendo** com blocos de lore presentes.
19. **Excesso de tokens não é erro** — `world.md` com 20 000 caracteres não produz nenhuma `ValidationError`.

### `frontend/src/components/builder/WorldTab.test.tsx`

20. **Modo guiado não tem mais Conflito nem Missão** — `queryByLabelText` das strings antigas volta `null`; os três campos restantes continuam lá. (O teste atual "confirmando a troca mostra os cinco campos" vira "mostra os três campos e nenhum bloco de lore".)
21. **Adicionar bloco foca o título e anuncia** — clicar em `builder.world.lore.add`; o input `builder-field-world.lore.0.title` recebe foco e a live region traz `builder.world.lore.added` com `{index: 1}`.
22. **Preencher bloco escreve no `world.md`** — título "Facções" + corpo "Duas."; o debug do `world` mostra `## Universe\n\nA dusty old school.\n\n## Facções\n\nDuas.`.
23. **Remover bloco do meio move o foco para o que subiu** — três blocos, remover o segundo: o input de título do índice 1 (antigo terceiro) fica com foco e a live region anuncia a remoção.
24. **Remover o único bloco devolve o foco ao botão adicionar.**
25. **Título reservado não derruba o modo guiado** — digitar `Universe` no título do bloco: o input continua mostrando `Universe`, aparece `builder.world.lore.title.reserved`, o banner de fallback **não** aparece, os campos guiados continuam na tela e o `world.md` do bloco sai com cabeçalho vazio e corpo intacto. Corrigir para `Universo antigo` limpa o erro e serializa o título.
26. **Título repetido mostra o erro inline no segundo bloco** e o input tem `aria-invalid="true"`.
29. **Nota de mudança de lugar leva para Starts** — em modo guiado, clicar no botão `builder.world.guided.goToStarts` chama `goToTab` com `'starts'` (mesmo padrão do teste de `builder.starts.cast.empty`).
30. **Arquivo antigo abre com dois blocos** — `world.md` com `## Conflict` e `## Mission` renderiza dois blocos com esses títulos e os corpos certos, em modo guiado, sem banner de fallback.
31. **`## Tone` depois de um bloco de lore cai no fallback** — banner `builder.world.mode.fallback.title` visível e o textarea custom com o texto integral.
32. **Bloco vazio bloqueia o salvar** — `BuilderEditorScreen.test.tsx`: adicionar um bloco e clicar em Salvar mostra o painel de validação com "Ir para {campo}" apontando para o título do bloco; clicar move o foco para `builder-field-world.lore.0.title`.
33. **Paridade de i18n** — coberta por `i18n.test.ts` (mesmas chaves em `en` e `pt-br`); as chaves removidas não podem sobrar em nenhum dos dois dicionários (busca por `builder.world.conflict`/`builder.world.mission` no repositório volta vazia).

### Inventário da suíte existente

Este ticket muda comportamento existente, então alguns testes descrevem um mundo
que deixa de existir. Classificação, teste a teste:

**`frontend/src/builder/worldMarkdown.test.ts` (61 linhas, 8 testes)** — o
arquivo é o mais afetado; o tipo `GuidedWorld` some sob os pés dele.

| Teste | O que fazer |
|---|---|
| `round-trips all five fields:5` | **Adaptação de preparação + renome.** Vira o caso 1 (`round-trips the guided fields and the lore blocks`): o fixture perde `conflict`/`mission` e ganha `lore: [...]`. A asserção continua sendo "serializa → parseia igual". |
| `omits empty sections and recovers them as empty strings:17` | **Adaptação de preparação.** `conflict: '', mission: ''` saem, entra `lore: []`. Asserção (`'## Universe\n\nOnly this.'`) idêntica. É o caso 3. |
| `returns null when a heading is out of order:24` | **Mantido sem tocar.** É o caso 6. |
| `returns null when there is prose before the first heading:29` | **Mantido sem tocar.** É o caso 7. |
| `returns null on an unknown heading:34` | **Removido.** Aferia exatamente a regra que este ticket derruba: `## Extra` agora vira bloco de lore. Não tem adaptação possível — a asserção é o comportamento antigo. O caso 5 (conhecido depois de lore) é quem passa a guardar a fronteira do fallback. |
| `preserves accented body text byte for byte:39` | **Adaptação de preparação**, estendida ao título pelo caso 11. |
| `exposes the canonical headings in order:51` | **Adaptação de asserção, declarada**: `['Universe','Tone','Rules','Conflict','Mission']` → `['Universe','Tone','Rules']`. É a definição do contrato novo; sem isso o teste afirma o contrato antigo. É o caso 13. |
| `parses empty and whitespace-only input as five empty guided fields:55` | **Adaptação de preparação + renome** (`... as three empty guided fields and no lore`). É o caso 12. |

**`frontend/src/components/builder/WorldTab.test.tsx` (157 linhas, 8 testes)**

| Teste | O que fazer |
|---|---|
| `confirming the switch from custom to guided shows the five fields empty:139` | **Adaptação**: as duas linhas `:152-153` (`getByLabelText(t('builder.world.conflict'))` e `...mission`) são **removidas** — o campo não existe mais, e teste de campo que deixa de existir não se adapta, se apaga. As três primeiras asserções ficam. O teste é renomeado para "…shows the three fields empty" e ganha a asserção do caso 20 (nenhum bloco de lore). |
| `filling the guided fields updates world with the canonical headings:51` | **Mantido sem tocar.** Só usa Tom e Universo. |
| `a hand-written world.md that does not match the guided headers opens in custom mode with a warning:81` | **Mantido sem tocar.** O fixture é prosa sem cabeçalho (regra 2), que continua caindo no fallback. |
| `switching from guided to custom shows the notice and keeps the text:91` | **Mantido sem tocar.** |
| `switching from custom to guided without confirming keeps custom mode:102` | **Mantido sem tocar.** |
| `an unclosed {{ produces a blocking validation error:118` | **Mantido sem tocar.** |
| `clicking "keep as custom" in the fallback banner records world_mode custom:127` | **Mantido sem tocar.** |
| `inserting a variable writes it at the cursor position:65` | **Mantido sem tocar.** |
| `baseDraft():10` | **Preparação**: o start literal em `:23-32` continua válido neste ticket. (Ele ganha `conflict`/`mission` no TCK-057, que roda na wave seguinte — colisão de arquivo declarada abaixo.) |
| `Harness:38-48` | **Preparação**: hoje `Harness(props: { initial: BuilderDraft })` passa `goToTab={() => {}}` fixo (`:43`); o caso 29 precisa espionar a chamada `goToTab('starts')`. Copie o molde de `StartsTab.test.tsx:50` (`props: { initial: BuilderDraft; goToTab?: (tab: string) => void }`) e `:60` (`goToTab={(props.goToTab as never) ?? (() => {})}`), com o teste correspondente em `StartsTab.test.tsx:207-217`. Os 8 testes existentes não passam `goToTab` e continuam iguais. |

**`frontend/src/builder/validate.test.ts` (89 linhas)**

| Teste | O que fazer |
|---|---|
| `returns no errors for a coherent document:47` | **Mantido sem tocar.** O fixture (`world: '## Universe\n\nA quiet town.'`, `:17`) não tem bloco de lore, então nenhuma regra nova dispara. Se ficar vermelho, é bug da implementação, não do teste. |
| `does not flag a missing universe when guided world_mode holds hand-written, non-canonical text:81` | **Mantido sem tocar.** É o caso 17 do design, já escrito. |
| `flags "}} text {{" as an unbalanced variable:86` | **Mantido sem tocar.** |
| demais testes de starts/personagens | **Mantidos sem tocar.** |

**`frontend/src/screens/BuilderEditorScreen.test.tsx`** — nenhum teste existente
muda; o arquivo é tocado só para **acrescentar** o caso 32. O `DOCUMENT`
(`:7-42`) é um literal sem anotação de tipo e não precisa de campo novo.

**`frontend/src/i18n.test.ts`** — não é editado. O teste
`strings > has the same keys in en and pt-br` (`:78-84`) é justamente o que pega
remoção pela metade; ele passa a valer sobre o dicionário novo sem nenhuma
mudança.

**Testes que aferem os textos alterados** — `builder.world.mode.switchToGuidedBody`
e `builder.world.mode.fallback.body`: nenhum teste afere o **texto** dessas duas
chaves. `WorldTab.test.tsx:87` e `:134` usam `t('builder.world.mode.fallback.title')`
e `t('...keepCustom')`, e `:110` usa `t('...switchToGuidedTitle')` — as três
chaves não mudam. Como todos os testes chamam `t(...)` em vez de literal, trocar
o valor de uma string nunca quebra a suíte; por isso a troca de texto do §i18n é
segura e **não** entra em nenhuma adaptação.

Falha: além dos caminhos já cobertos (fallback, título inválido), não há erro
novo. Nenhuma chamada de rede é adicionada.

## Rollout e kill switch

N/A — sem flag. O builder inteiro já está atrás da flag `builder`
(`backend/app/builder_doc.py:342`, que devolve 503 no `PUT` quando desligada);
uma flag por aba seria estado morto.

Reversão: reverter o commit devolve a aba de cinco campos. O que ficou no disco
continua legível pelas duas versões — `world.md` gravado por este ticket com um
bloco `## Facções` cai no modo custom na versão antiga (banner de fallback, texto
íntegro, nada perdido), e `world.md` antigo com `## Conflict`/`## Mission` é lido
pelas duas. Não há formato novo que só a versão nova entenda.

`risk: medium`: mexe no parser que decide se um `world.md` abre em modo guiado ou
custom, e um parser errado pode fazer o editor **reescrever** o arquivo do autor
ao salvar. O caso 4 (round trip byte a byte do arquivo antigo) é o teste que
guarda essa porta; sem ele verde, não mergeie.

## Observabilidade

Eventos: nenhum evento novo, no frontend ou no backend. Os existentes que dizem
se isto funcionou:

- `builder_doc_saved` (`backend/app/builder_doc.py:302`) com `files_written` — um
  save que só mexeu em blocos de lore escreve 1 arquivo (`world.md`).
- `builder_doc_read` (`builder_doc.py:329`) e `builder_doc_invalid`
  (`builder_doc.py:326`) — reabrir um cenário salvo pelo modo guiado não pode
  emitir `builder_doc_invalid`.

Métrica de sucesso: cenário guiado com blocos de lore reabre em modo guiado
(nenhum `builder_doc_invalid`, nenhum banner de fallback), e o `world.md` de um
cenário aberto e salvo sem edição continua com o mesmo `revision`
(`builder_doc.py:120`), prova de que o round trip não reescreveu nada.

## i18n

*(Tabelas fechadas pelo design-specialist, copiadas literalmente. As chaves
`builder.world.tokens.*` são do TCK-059 e não entram neste PR.)*

### Chaves removidas (nos dois locales)

| Chave | Motivo |
|---|---|
| `builder.world.conflict` | campo saiu do modo guiado; virou `builder.starts.conflict` (TEMA 1) |
| `builder.world.conflict.hint` | idem |
| `builder.world.mission` | virou `builder.starts.mission` (TEMA 1) |
| `builder.world.mission.hint` | idem |

Remover também os tipos literais correspondentes em `GUIDED_FIELDS` no
`WorldTab.tsx`. Chave órfã em qualquer dos dois dicionários é defeito do PR.

### Chaves com texto alterado (a chave continua)

| Chave | en (novo) | pt-br (novo) | Por quê |
|---|---|---|---|
| `builder.world.mode.switchToGuidedBody` | `Anything that doesn't fit the guided headings is dropped.` | `O que não couber nos cabeçalhos guiados é descartado.` | **Sim, muda.** O modo guiado não tem mais "cinco campos": tem três campos fixos e N blocos de lore. O texto antigo ("the five fields" / "os cinco campos") passaria a mentir. |
| `builder.world.mode.fallback.body` | `This file doesn't fit the guided layout, so it opened in custom mode. Nothing was lost.` | `Este arquivo não encaixa no formato guiado, então abriu em modo custom. Nada foi perdido.` | O fallback agora dispara também por cabeçalho fora de ordem ou conhecido depois de um bloco de lore, não só por "os cabeçalhos não estão lá". |

### Chaves novas

Nas duas colunas de valor, aspas simples e crase não fazem parte da string: o
valor é o texto puro.

| Chave | en | pt-br |
|---|---|---|
| `builder.world.lore.legend` | Lore blocks | Blocos de lore |
| `builder.world.lore.hint` | One block per chunk of world worth its own heading: factions, places, history. Each block becomes a heading in world.md. | Um bloco por pedaço de mundo que merece cabeçalho próprio: facções, lugares, história. Cada bloco vira um cabeçalho no world.md. |
| `builder.world.lore.empty` | No lore blocks yet. Add one for each piece of the world the narrator should always know. | Nenhum bloco de lore ainda. Adicione um para cada pedaço do mundo que o narrador sempre precisa saber. |
| `builder.world.lore.add` | Add lore block | Adicionar bloco de lore |
| `builder.world.lore.titleLabel` | Block {index} title | Título do bloco {index} |
| `builder.world.lore.title.hint` | Becomes a heading in world.md. | Vira um cabeçalho no world.md. |
| `builder.world.lore.bodyLabel` | Block {index} text | Texto do bloco {index} |
| `builder.world.lore.remove` | Remove lore block {index} | Remover o bloco de lore {index} |
| `builder.world.lore.added` | Lore block {index} added | Bloco de lore {index} adicionado |
| `builder.world.lore.removed` | Lore block {index} removed | Bloco de lore {index} removido |
| `builder.world.lore.title.required` | Every lore block needs a title. | Todo bloco de lore precisa de um título. |
| `builder.world.lore.title.reserved` | {title} is one of the guided fields above — pick another title. | {title} é um dos campos guiados aí em cima — escolha outro título. |
| `builder.world.lore.title.duplicate` | Another block already uses {title}. | Outro bloco já usa {title}. |
| `builder.world.guided.movedHint` | Conflict and mission moved: each start has its own now, so one world can hold many stories. | Conflito e missão mudaram de lugar: agora cada start tem os seus, então um mundo só comporta várias histórias. |
| `builder.world.guided.goToStarts` | Open the Starts tab | Abrir a aba Starts |

Posição no `strings.ts`: as chaves `builder.world.lore.*` e
`builder.world.guided.*` entram depois de `builder.world.rules.hint` e antes de
`builder.world.custom.label`. Mesma ordem nos dois dicionários, para o diff ficar
legível.

### Chaves reaproveitadas

`common.remove`, `common.cancel`, `builder.world.heading`,
`builder.world.universe(.hint)`, `builder.world.tone(.hint)`,
`builder.world.rules(.hint)`, `builder.world.mode.*`,
`builder.world.custom.*`, `builder.world.variables.*`,
`builder.editor.validation.jump`, `builder.editor.saved`.

## Colisão de arquivos declarada

- `frontend/src/components/builder/WorldTab.tsx`, `WorldTab.test.tsx`,
  `strings.ts` e `builderEditor.css`: também são tocados pelo **TCK-059**, que é
  `blockedBy: [TCK-058]` e roda depois. Colisão resolvida pela ordem.
- `frontend/src/strings.ts`: também é tocado pelo **TCK-057**. Aceitável porque o
  TCK-057 é `blockedBy: [TCK-056]` e cai em outra wave; as inserções são em
  blocos diferentes (`builder.starts.*` × `builder.world.*`), mas o guard de
  colisão deve enxergar o arquivo nos dois `files`.
- `frontend/src/components/builder/WorldTab.test.tsx`: também é tocado pelo
  TCK-057, que acrescenta `conflict: null, mission: null` ao start literal do
  `baseDraft()` (`:23-32`). Mesma justificativa: waves diferentes.
- `frontend/src/screens/BuilderEditorScreen.test.tsx`: só este ticket edita.
