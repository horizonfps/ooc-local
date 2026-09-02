---
id: TCK-073
title: Aba Comandos do editor de cenário
status: in_review
points: 5
blockedBy: [TCK-060, TCK-066, TCK-070]
files:
  - frontend/src/components/builder/CommandsTab.tsx
  - frontend/src/components/builder/CommandsTab.test.tsx
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

O TCK-060 põe `commands: CommandDoc[]` no `ScenarioDocument` e o TCK-072 faz o
`!nome` do jogador virar turno meta. Do lado do autor não existe caminho: para
declarar um comando é preciso escrever `scenarios/<id>/commands.yaml` na mão, e o
TCK-074 vai listar no Guia de jogo comandos que o builder não sabe criar.

É também a última aba da fase: sem ela, `TAB_ORDER` fica com sete abas e a ordem
prometida no plano (`identity, world, starts, characters, stats, lorebook,
commands, media`) não fecha.

## Escopo

Dentro:
- `frontend/src/components/builder/CommandsTab.tsx` novo: mestre-detalhe com
  nome, invocação de leitura (`!nome`), descrição e prompt; criar e remover
  direto na lista, sem diálogo.
- `frontend/src/builder/validate.ts`: bloco de validação da aba `commands`,
  reusando `STAT_ID_RE` do TCK-066 (alias legível permitido:
  `export const COMMAND_NAME_RE = STAT_ID_RE`; **nunca** uma segunda expressão
  escrita à mão).
- `frontend/src/screens/BuilderEditorScreen.tsx`: `TAB_ORDER`, `TAB_LABEL_KEY`,
  `slice` (`case 'commands'`), `demoEdit` (`case 'commands'`) e a cadeia de
  render.
- `frontend/src/useHashRoute.ts`: `'commands'` na união `BuilderTab` e em
  `BUILDER_TABS`, entre `lorebook` e `media`. Com isto a união fecha em 8 abas.
- `frontend/src/screens/builderEditor.css`: `.builder-commands-*`.
- `frontend/src/strings/builder.ts`: chaves novas nos dois dicionários.
- Testes novos em `CommandsTab.test.tsx`, `validate.test.ts`,
  `BuilderEditorScreen.test.tsx` e `useHashRoute.test.ts`.

Fora (explícito):
- Qualquer arquivo de `backend/`. `CommandDef`, o `commands.yaml` do cenário, o
  arquivo global e o `resolve_command` são TCK-060 e TCK-065/TCK-072.
- `frontend/src/api.ts` — `CommandDoc` chega pronto do TCK-060.
- **Editar os comandos globais** (`~/.ooc-local/commands.yaml`): não há rota de
  builder para eles, e o hint `builder.commands.globalsHint` diz onde moram.
  Destino: ticket futuro, se houver.
- Paleta de comandos, turno meta e a listagem no Guia de jogo: é o TCK-074, em
  `GamePanel.tsx` / `strings/game.ts`.
- Testar o comando dentro do preview do builder.
- Reordenar comandos: a ordem é a de `commands.yaml`, comando novo entra no fim,
  e a ordem não afeta o motor (a resolução é por nome).
- **Variante `select` em telas estreitas** (`useIsNarrow`,
  `.builder-list-selectRow`): o bloco compartilhado do TCK-066 nasce sem essas
  classes e a lista empilha acima do formulário abaixo de 900px. Destino: fase 4,
  junto com Stats e Lorebook.

## Comportamento esperado

Uma aba **Comandos** entre Lorebook e Mídia. Dois hints fixos no topo explicam o
que o autor está criando; abaixo, lista à esquerda e formulário à direita.

```
Comandos
Os comandos deste cenário aparecem no Guia de jogo e na paleta que o jogador
abre digitando !.
Os comandos globais (/nome) ficam em ~/.ooc-local/commands.yaml e não são
editados aqui.

Comandos deste cenário       Nome       [ fofoca                   ]
  !fofoca                    !fofoca
  O que andam dizendo…       Descrição  [ O que andam dizendo…      ]
                 [Remover]   Prompt     [ Fora da narrativa, liste… ]
  [ Novo comando ]
```

O comando é uma **linha em `commands.yaml`**, não um arquivo: por isso este é o
único dos três editores novos sem diálogo de criar nem de deletar (mesma regra
que separa os blocos de lore da `WorldTab` das entradas do lorebook).

### Lista e seleção

**Seleção por índice** (`selectedIndex`), porque o nome é campo editável do
formulário: ids do DOM e `field` de validação usam `commands.<i>.…`, 0-based,
como nos stats do TCK-066. Seleção inicial: o primeiro índice com erro de
validação; senão `0`. Só na montagem. Índice fora do intervalo depois de uma
remoção cai para o último válido.

Item (`.builder-list-item`, `aria-current` quando selecionado): invocação
`builder.commands.invocation` `{name}` (`!fofoca`) em
`.builder-commands-invocation`, fonte monoespaçada — ou
`builder.commands.unnamed` quando o nome está vazio; descrição em `.field-hint`,
truncada por CSS; e, com erro, `<span className="visually-hidden">` com
`builder.starts.itemInvalid` (**chave existente**). Ao lado, botão de remover com
texto visível `common.remove` e `aria-label` `builder.commands.remove.title`
`{name}`.

### Formulário

| Campo | `field` / id do DOM | Controle | Regras |
|---|---|---|---|
| Nome | `commands.<i>.name` | `<input>` texto | `trim` no `onBlur`; recebe o foco ao trocar de comando e ao criar |
| Invocação | — | `<p className="builder-commands-invocation">` de leitura | mostra `builder.commands.invocation` `{name}` em tempo real, ou `builder.commands.invocation.empty` com o nome vazio. É texto, não controle: sem `role`, sem `tabindex`, sem cursor de ponteiro |
| Descrição | `commands.<i>.description` | `<input>` texto | uma linha; texto cru como digitado, `trim` no `onBlur` |
| Prompt | `commands.<i>.prompt` | `<textarea className="builder-field-textarea" rows={8}>` | texto cru, **sem** `trim` na gravação (molde de `starts.conflict`, `StartsTab.tsx:381`) |

Hints: `builder.commands.name.hint`, `builder.commands.description.hint`,
`builder.commands.prompt.hint`. Este último diz o que o motor garante: a resposta
sai fora da narrativa, o turno não avança e o texto não entra na memória da
sessão.

### Criar e remover

- **Criar** (`builder.commands.create`): entra no fim com `description: ''`,
  `prompt: ''` e um nome sugerido livre no padrão `command-1`, `command-2`, …
  (molde de `nextSuggestedId`, `StartsTab.tsx:28`). O nome sugerido é dado de
  arquivo e sai igual nos dois locales da interface: precisa casar
  `^[a-z0-9_-]+$`, e é o autor quem troca por algo com sentido. O comando novo
  vira o selecionado, o foco vai para o Nome e a live region anuncia
  `builder.commands.added` `{name}`. O erro de prompt obrigatório já aparece
  embaixo do campo correspondente: é orientação, e some quando o autor escreve.
- **Remover**: imediato, sem diálogo — é uma linha do `commands.yaml`, nada foi
  para o disco e Descartar/Recarregar desfazem (mesma decisão dos blocos de lore
  da `WorldTab` e dos níveis do TCK-066). O `aria-label` diz qual comando sai e o
  anúncio `builder.commands.removed` lembra do caminho de volta. Foco vai para o
  item que assumiu a posição; sem lista, para o botão "Novo comando". O foco
  nunca cai no `<body>`.
- Trocar de comando na lista: anúncio `builder.detail.selected` (**existente**),
  com o nome ou o fallback, e foco no campo Nome via `requestAnimationFrame`.

### Validação

`label` do painel = `${nome ou o fallback} — ${rótulo do campo}`, com o fallback
`builder.commands.unnamed`.

| Situação | `field` | Mensagem |
|---|---|---|
| nome vazio após `trim` | `commands.<i>.name` | `builder.field.required` *(existente)* |
| nome fora de `^[a-z0-9_-]+$` | `commands.<i>.name` | `builder.field.slugUnderscoreInvalid` *(do TCK-066)* |
| nome > 32 | `commands.<i>.name` | `builder.field.tooLong` `{max: 32}` *(existente)* |
| nome repetido (comparação exata, depois do `trim`) | `commands.<i>.name`, **segundo e seguintes** | `builder.field.slugTaken` `{slug}` *(existente)* |
| descrição > 140 | `commands.<i>.description` | `builder.field.tooLong` `{max: 140}` |
| prompt vazio após `trim` | `commands.<i>.prompt` | `builder.field.required` |

**Prompt vazio é erro por decisão desta aba, não do backend**: um comando sem
prompt aparece no Guia de jogo, o jogador digita `!nome` e não acontece nada. O
backend aceita a string vazia; o editor não deixa salvar um controle morto.

Descrição vazia **não** é erro: a paleta e o Guia de jogo mostram só o nome, e o
hint diz o que se perde. Lista de comandos vazia também não é erro.

### Estados

| Estado | O que o autor vê |
|---|---|
| **Vazio** | `EmptyState` `builder.commands.empty.title`/`.body` (o corpo diz o que um comando é — a fofoca que corre, uma recapitulação, o que um NPC está pensando — e que ele responde sem avançar o turno) com "Novo comando" como `action`. Os dois hints fixos continuam acima: quem chega aqui pela primeira vez precisa entender `!nome` e os globais `/nome` antes de criar |
| **Carregando** | Nada novo: validação síncrona sobre rascunho em memória. O skeleton do `BuilderEditorScreen` continua cobrindo o carregamento do documento |
| **Erro de validação (campo)** | Erro inline `role="alert"` + `.field-error`, `aria-invalid` no controle, ligado por `aria-describedby`. As mensagens dizem o que fazer: dar um nome, usar só minúsculas/números/hífen/underscore, escrever o prompt |
| **Erro de validação (salvar)** | Painel existente com "Ir para {campo}"; item com erro `is-invalid` na lista; seleção inicial cai no primeiro comando com erro |
| **Erro ao salvar** | Inalterado (`builder.editor.save.error.*`, 409, 503) |
| **Sucesso** | Topo passa a "Tudo salvo", ponto de sujo some da aba, `builder.editor.saved` anunciado. Dentro da aba, a live region anuncia comando criado, removido e a troca de seleção |

## Detalhes técnicos

### Contrato consumido

Do **TCK-060**:

```ts
export type CommandDoc = { name: string; description: string; prompt: string }
// ScenarioDocument.commands: CommandDoc[]
```

Do **TCK-066**, em `frontend/src/builder/validate.ts`:

```ts
export const STAT_ID_RE = /^[a-z0-9_-]+$/   // mesma classe de caracteres do nome de comando
```

O nome de comando usa **a mesma regex** e a **mesma mensagem**
(`builder.field.slugUnderscoreInvalid`) do id de stat. Se o TCK-066 não tiver
entrado, crie-as aqui com esses nomes exatos; nunca um sinônimo.

Do **TCK-066/TCK-070**: as classes `.builder-masterDetail` / `.builder-list*` do
`builderEditor.css` (sem `.builder-list-selectRow`).

### O que muda em `BuilderEditorScreen.tsx` e vizinhos

1. **`useHashRoute.ts:3-4`** — `'commands'` na união `BuilderTab` e em
   `BUILDER_TABS`, depois de `lorebook` e antes de `media`.
2. **`TAB_ORDER` (`BuilderEditorScreen.tsx:32`)** — `'commands'` entre
   `'lorebook'` e `'media'`.
3. **`TAB_LABEL_KEY` (`:34-40`)** — `commands: 'builder.editor.tab.commands'` (o
   `Record<BuilderTab, StringKey>` é total; sem a entrada o `tsc -b` reprova).
4. **`draftOf` (`:42-44`)** — nada a fazer; `commands` já vem do TCK-060.
5. **`slice` (`:46-61`)** — `case 'commands'` devolve `draft.commands` (o array
   cru; o `deepEqual` de `validate.ts:30-47` compara array elemento a elemento).
6. **`demoEdit` (`:65-93`)** — `case 'commands'`: alterna o `DEMO_MARK` na
   `description` do primeiro comando e devolve o rascunho intacto com a lista
   vazia (molde do `case 'starts'`). Sem o `case`, o `switch` deixa de ser
   exaustivo e o `tsc -b` reprova.
7. **Render (`:598-610`)** — `activeTab === 'commands' ? <CommandsTab {...tabProps} />`
   entre `lorebook` e `media`.
8. **`isTabDirty` (`:366-369`)** — inalterado: só `media` fica de fora.
9. **Verificação de fechamento**: depois deste ticket `TAB_ORDER` é exatamente
   `['identity','world','starts','characters','stats','lorebook','commands','media']`.
   O cenário de teste que afirma a ordem inteira existe por isso: é a última aba
   a entrar e ninguém mais vai olhar para esse array.

### CSS

- Reusa `.builder-masterDetail`, `.builder-list*`, `.builder-field`,
  `.builder-field-textarea`, `.field-hint`, `.field-error`, `.builder-tag-chip`
  e `EmptyState`.
- A invocação (`!nome`) é renderizado com a classe existente `.builder-tag-chip`
  (`builderEditor.css:460-467`, `inline-flex` com `border-radius: 999px`), sem
  classe nova e sem cor copiada à mão; o `<p className="builder-commands-invocation">`
  do formulário só envolve o chip e ganha `margin: 0` no bloco CSS deste ticket.
- Item da lista em duas linhas (invocação em cima, descrição embaixo), no molde
  de `.builder-characters-listItemText` (`builderEditor.css:876-886`), com
  `min-width: 0` para o `ellipsis` funcionar.
- Em ≤479.98px o `<li>` empilha (regra do bloco compartilhado) e o botão de
  remover ocupa a largura toda, pela regra existente
  `.builder-editor-panel button { width: 100% }` (`:363-365`).
- Sem scroll horizontal em 320px: nome longo trunca com reticências em vez de
  esticar a linha. Com 8 abas o tablist rola (`overflow-x: auto`, já existente).

### Acessibilidade

- Ordem de tabulação: nome → descrição → prompt → (lista: item → remover).
- Tudo é `<button type="button">` e controle nativo; nenhum `onKeyDown` próprio.
  `Ctrl/Cmd+S` continua salvando pelo atalho global.
- Alvo de toque ≥ 44px em botões e inputs.
- A invocação `!nome` é texto com fundo de chip, **sem** `role`, `tabindex` ou
  `cursor: pointer`: informação, não controle.
- Foco visível preservado (`:focus-visible` global, `index.css:35-38`).
- Contraste: a invocação herda o contraste de `.builder-tag-chip`, já em uso.

### Tamanho

`CommandsTab.tsx` (~200), `validate.ts` (+25), `BuilderEditorScreen.tsx` (+15),
`useHashRoute.ts` (+2), `builderEditor.css` (+10), `strings/builder.ts` (+40) e
os testes (~180: 15 cenários de `CommandsTab`, 4 de `validate`, 3 de
`BuilderEditorScreen`, 1 de `useHashRoute`). Cerca de 470 linhas, acima do alvo
de ~400; por isso 5 pontos, como as duas abas irmãs (TCK-066, TCK-070). Se o
diff passar de ~550, agrupe os cenários de validação de nome (vazio, inválido,
duplicado) num único `it.each`.

## Contrato público

N/A — `CommandsTab` é usado só pelo `BuilderEditorScreen`, no mesmo PR. O que
este ticket fecha, e nenhum outro ticket da fase consome, é a união `BuilderTab`
em oito abas e a ordem final de `TAB_ORDER`.

## Acceptance criteria

- [ ] O tablist mostra 8 abas, na ordem `identity, world, starts, characters,
      stats, lorebook, commands, media`, e o hash `#/builder/{id}/commands`
      seleciona a aba.
- [ ] Com `commands: []` a aba mostra o `EmptyState`, o botão "Novo comando" e os
      dois hints fixos.
- [ ] "Novo comando" acrescenta `{name: 'command-N' livre, description: '',
      prompt: ''}` no fim, seleciona e foca o campo Nome.
- [ ] Digitar no Nome atualiza a invocação `!nome` em tempo real; nome vazio
      mostra `builder.commands.invocation.empty`.
- [ ] O Nome é aparado no `onBlur`; o Prompt é gravado byte a byte, com quebras e
      espaços no fim.
- [ ] Remover é imediato, devolve o foco ao item que assumiu a posição (ou ao
      botão de criar) e anuncia `builder.commands.removed`.
- [ ] `validateDraft` produz exatamente os erros da tabela, com `tab: 'commands'`
      e `field` no padrão `commands.<i>.…`; `name: 'fofoca_2'` **não** produz erro
      (underscore é permitido) e `name: 'Fofoca'` produz
      `builder.field.slugUnderscoreInvalid`.
- [ ] Nome repetido acusa só a partir do segundo comando.
- [ ] Prompt vazio é erro; descrição vazia não é.
- [ ] A invocação não é alcançável por `getByRole('button')` e não tem
      `tabindex`.
- [ ] Editar o prompt deixa **só** a aba Comandos com `is-dirty`.
- [ ] "Ir para {campo}" foca `builder-field-commands.<i>.<campo>`.
- [ ] `strings/builder.ts` tem todas as chaves novas em `en` e `pt-br`.
- [ ] `npm run check` verde.

## Cenários de teste

```tsx
function Harness(props: { initial: BuilderDraft }) {
  const [draft, setDraft] = useState(props.initial)
  const errors = validateDraft(draft)
  return (
    <>
      <CommandsTab scenarioId="school" draft={draft} onChange={setDraft} errors={errors} goToTab={() => {}} />
      <pre data-testid="commands-debug">{JSON.stringify(draft.commands)}</pre>
    </>
  )
}
```

### `frontend/src/components/builder/CommandsTab.test.tsx` (novo)

- Feliz: **grava nome, descrição e prompt no rascunho** — `fireEvent.change` nos
  três campos deixa `commands-debug` com
  `[{name: 'fofoca', description: 'O que andam dizendo', prompt: 'Fora da narrativa…'}]`.
- Feliz: **cria um comando com nome sugerido livre e foca o nome** — lista já com
  `command-1`: clicar em `builder.commands.create` acrescenta
  `{name: 'command-2', description: '', prompt: ''}` e
  `document.getElementById('builder-field-commands.1.name')` fica com o foco
  (`waitFor`).
- Feliz: **troca de comando pela lista, anuncia e foca o nome** — dois comandos;
  clicar no segundo item foca `builder-field-commands.1.name` e mostra
  `builder.detail.selected` com o nome dele.
- Feliz: **mostra a invocação `!nome` em tempo real** — digitar `fofoca` no nome
  deixa `t('builder.commands.invocation', { name: 'fofoca' })` na tela; apagar o
  nome troca pelo texto de `builder.commands.invocation.empty`.
- Feliz: **remove um comando e devolve o foco ao que assumiu a posição** — três
  comandos, remover o segundo: `commands-debug` fica com dois, o foco vai para
  `builder-field-commands.1.name` e a live region traz
  `builder.commands.removed` com o nome removido.
- Borda: **mostra o estado vazio com os hints de invocação** — `commands: []`:
  `builder.commands.empty.title`, o botão `builder.commands.create` e os textos
  `builder.commands.playGuideHint` e `builder.commands.globalsHint` na tela.
- Borda: **remove o único comando e devolve o foco ao botão de criar** — a tela
  passa a mostrar o `EmptyState` e o foco está no botão
  `builder.commands.create`.
- Borda: **apara espaços do nome no blur e guarda o prompt como digitado** — nome
  `  fofoca  ` vira `fofoca`; prompt com quebra de linha e espaço no fim
  permanece byte a byte.
- Borda: **marca na lista um comando não selecionado com erro** — segundo comando
  com prompt vazio: o `<li>` que contém `builder.starts.itemInvalid` tem
  `is-invalid` e o do primeiro não.
- Borda: **abre selecionando o primeiro comando com erro** — três comandos, erro
  só no terceiro: `builder-field-commands.2.name` está na tela na montagem.
- Borda: **mostra a invocação como texto, não como botão** —
  `queryByRole('button', { name: /!fofoca/ })` volta `null` e o elemento não tem
  `tabindex`.
- Falha: **erro de nome com caractere proibido** — digitar `Fofoca Geral`:
  `builder.field.slugUnderscoreInvalid` num `role="alert"` ligado ao campo por
  `aria-describedby`, e o input com `aria-invalid="true"`.
- Falha: **aceita underscore no nome** — `boca_de_sino` não produz erro nenhum (é
  o par negativo do caso acima e a prova de que a regex não é a de starts).
- Falha: **erro de nome repetido no segundo comando** — dois comandos `fofoca`:
  `builder.field.slugTaken` `{slug: 'fofoca'}` visível, o segundo input com
  `aria-invalid="true"` e o primeiro sem.
- Falha: **erro de prompt vazio** — `builder.field.required` embaixo do textarea,
  ligado por `aria-describedby`.

### `frontend/src/builder/validate.test.ts` (existente, casos novos)

- Feliz: **não reclama de um cenário sem comando** — `commands: []` não produz
  erro de aba `commands`.
- Falha: **acusa nome de comando fora do padrão** — `name: 'Fofoca'` dá
  `tab: 'commands'`, `field: 'commands.0.name'`,
  `builder.field.slugUnderscoreInvalid`; `name: 'fofoca_2'` não dá erro.
- Falha: **acusa nome repetido só a partir do segundo** — erro em
  `commands.1.name` com `builder.field.slugTaken`, nada em `commands.0.name`.
- Falha: **acusa prompt vazio e aceita descrição vazia** — erro em
  `commands.0.prompt` com `builder.field.required` e nenhum erro em
  `commands.0.description`.

### `frontend/src/screens/BuilderEditorScreen.test.tsx` (existente, casos novos)

- Feliz: **mostra as oito abas na ordem final** —
  `getAllByRole('tab').map((el) => el.textContent)` casa, na ordem, com
  `identity, world, starts, characters, stats, lorebook, commands, media` (todos
  por `t(...)`). É o teste que fecha a ordem das abas da fase.
- Borda: **marca só a aba Comandos como suja ao editar um prompt** — render em
  `tab="commands"`, alterar o textarea: a aba Comandos tem `is-dirty` e as demais
  não.
- Falha: **"Ir para {campo}" leva ao campo do comando** — documento com comando
  de prompt vazio: Salvar abre o painel de validação e clicar no erro foca
  `builder-field-commands.0.prompt`.

### `frontend/src/useHashRoute.test.ts` (existente, caso novo)

- Feliz: **resolve `#/builder/school/commands`** — `{ name: 'builderEditor',
  id: 'school', tab: 'commands' }`.

### Inventário da suíte existente (preparação, nunca asserção)

| Arquivo | O que muda | Por quê |
|---|---|---|
| `frontend/src/screens/BuilderEditorScreen.test.tsx:92` | `expect(tabs).toHaveLength(7)` (posto lá pelo TCK-070) vira `8` | uma aba a mais em `TAB_ORDER`. O cenário novo de ordem completa **substitui** essa contagem por uma asserção mais forte, então mantenha os dois: a contagem continua barata e o de ordem é o que fecha a fase |
| `frontend/src/screens/BuilderEditorScreen.test.tsx:7-43` | o literal `DOCUMENT` ganha `commands: []` | o `DOCUMENT` não é anotado, então o `tsc -b` não exige o campo, mas sem ele `draft.commands` chega `undefined` na aba |
| `frontend/src/i18n.test.ts` | nada muda | a paridade de chaves passa a cobrir as novas |

Fixtures de `BuilderDraft` são responsabilidade do **TCK-060**; se algum literal
ainda estiver incompleto, acrescente `commands: []` e nada mais.

Nenhum teste existente perde cobertura.

## Rollout e kill switch

N/A — `risk: low`. Edição de rascunho em memória, sem rede nova, sem migração; só
o Salvar toca o disco, pelo caminho que já existe. Reverter é remover
`'commands'` de `TAB_ORDER`/`BUILDER_TABS` e o `<CommandsTab />` da cadeia de
render; `commands.yaml` já escrito continua válido para o loader e volta a
sobreviver por passthrough.

## Observabilidade

Eventos: nenhum evento novo no frontend. Do lado do servidor, salvar emite
`builder_doc_saved` com `files_written` (que passa a incluir `commands.yaml`).
Métrica de sucesso: um comando criado só pelo builder aparece na lista de
`SessionDetail.commands` da sessão seguinte e roda como turno meta pelo TCK-072,
sem nenhum `builder_doc_invalid` no meio.

## i18n

Bloco `// Builder commands tab` nos **dois** dicionários de
`frontend/src/strings/builder.ts`, depois do bloco de lorebook (TCK-070) e antes
do de mídia. `builder.editor.tab.commands` entra junto das outras
`builder.editor.tab.*`.

### Chaves novas

| Chave | en | pt-br |
|---|---|---|
| `builder.editor.tab.commands` | Commands | Comandos |
| `builder.commands.heading` | Commands | Comandos |
| `builder.commands.listLabel` | Commands in this scenario | Comandos deste cenário |
| `builder.commands.create` | New command | Novo comando |
| `builder.commands.added` | Command {name} added | Comando {name} adicionado |
| `builder.commands.removed` | Command {name} removed. Discard or reload brings it back. | Comando {name} removido. Descartar ou recarregar traz de volta. |
| `builder.commands.remove.title` | Remove the command {name} | Remover o comando {name} |
| `builder.commands.unnamed` | Unnamed command | Comando sem nome |
| `builder.commands.empty.title` | No commands yet | Nenhum comando ainda |
| `builder.commands.empty.body` | A command is a question the player can ask outside the story: the gossip going around, a recap, what an NPC is thinking. It answers without advancing the turn. | Um comando é uma pergunta que o jogador faz fora da história: a fofoca que corre, uma recapitulação, o que um NPC está pensando. Ele responde sem avançar o turno. |
| `builder.commands.playGuideHint` | Commands of this scenario show up in the Play Guide and in the palette the player opens by typing !. | Os comandos deste cenário aparecem no Guia de jogo e na paleta que o jogador abre digitando !. |
| `builder.commands.globalsHint` | Global commands (/name) live in ~/.ooc-local/commands.yaml and aren't edited here. | Os comandos globais (/nome) ficam em ~/.ooc-local/commands.yaml e não são editados aqui. |
| `builder.commands.name` | Name | Nome |
| `builder.commands.name.hint` | The player calls it by typing ! and this name. Lowercase letters, numbers, hyphen and underscore. | O jogador chama digitando ! e este nome. Letras minúsculas, números, hífen e underscore. |
| `builder.commands.invocation` | !{name} | !{name} |
| `builder.commands.invocation.empty` | Name it and the player will be able to call it. | Dê um nome e o jogador vai poder chamar. |
| `builder.commands.description` | Description | Descrição |
| `builder.commands.description.hint` | One line, read by the player in the Play Guide and in the palette. Empty leaves only the name there. | Uma linha, lida pelo jogador no Guia de jogo e na paleta. Vazia deixa só o nome lá. |
| `builder.commands.prompt` | Prompt | Prompt |
| `builder.commands.prompt.hint` | What the narrator is asked, outside the narrative. The turn doesn't advance, and the answer stays out of the memory of the session. | O que é pedido ao narrador, fora da narrativa. O turno não avança, e a resposta fica fora da memória da sessão. |
| `builder.field.label.commandName` | Command name | Nome do comando |

### Chaves reaproveitadas (nada de chave nova para elas)

`common.remove`, `builder.detail.selected`, `builder.field.required`,
`builder.field.tooLong`, `builder.field.slugTaken`,
`builder.field.slugUnderscoreInvalid` *(do TCK-066)*,
`builder.starts.itemInvalid`, `builder.editor.tab.dirty`,
`builder.editor.tab.invalid`, `builder.editor.validation.jump`,
`builder.editor.saved`, `builder.editor.save.error.*`.

`builder.commands.name`, `.description` e `.prompt` repetem valores que já
existem em outras abas: é a convenção do arquivo (identity, starts, characters e
stats já têm cada um a sua chave `…name`), e é o que deixa o teste casar o campo
por `t()` da chave da própria aba.
