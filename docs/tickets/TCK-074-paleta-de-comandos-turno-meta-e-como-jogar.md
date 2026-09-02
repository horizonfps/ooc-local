---
id: TCK-074
title: Paleta de comandos, turno meta no histórico e bloco Como jogar
status: in_review
points: 5
blockedBy: [TCK-060, TCK-071]
files:
  - frontend/src/components/CommandPalette.tsx
  - frontend/src/components/CommandPalette.test.tsx
  - frontend/src/components/commandPalette.css
  - frontend/src/components/PlayGuide.tsx
  - frontend/src/components/PlayGuide.test.tsx
  - frontend/src/components/playGuide.css
  - frontend/src/components/GamePanel.tsx
  - frontend/src/components/GamePanel.test.tsx
  - frontend/src/screens/game.css
  - frontend/src/strings/game.ts
migration: false
ui: true
risk: low
---

## Problema

O TCK-072 faz o backend resolver `!nome` e `/nome` como turno meta e devolver 422
`unknown_command` para nome errado; o TCK-060 já entrega
`SessionDetail.commands: CommandView[]` e `TurnView.meta`/`command`. Na tela não
existe nada disso: o jogador não tem como saber que comandos existem, não tem
como descobrir o nome certo, e um turno meta renderiza como bolha de jogador
azul, como se ele tivesse dito `!fofoca` em cena.

Duas consequências concretas:
- **422 vira "Alguma coisa quebrou nesta tela".** `classifyError`
  (`errors.ts:18-34`) não trata 422 e cai em `unexpected`, que é mentira: nada
  quebrou, o jogador errou o nome de um comando.
- **`playGuide` nunca foi exibido.** `SessionDetail.playGuide` existe desde o
  TCK-005 e está tipado em `api.ts:45`; Grep em `frontend/src` mostra que as
  únicas ocorrências fora do `api.ts` são fixtures de teste. O texto que o autor
  escreve em `starts/<id>.yaml: play_guide` nunca chegou ao jogador.

Há ainda uma armadilha de render: a chave da lista de turnos é
`` `${turn.index}-${turn.role}` `` (`GamePanel.tsx:475`). Um turno meta compartilha
o índice do turno corrente, então dois meta seguidos colidem e o React reordena
ou descarta nós.

## Escopo

Dentro:
- `frontend/src/components/CommandPalette.tsx` + `commandPalette.css` novos:
  painel sobre o rodapé com os comandos filtrados pelo que o jogador digitou.
- `frontend/src/components/PlayGuide.tsx` + `playGuide.css` novos: disclosure
  "Como jogar" com a prosa do `playGuide` e a lista de comandos.
- `frontend/src/components/GamePanel.tsx`: estado da paleta (aberta,
  `activeIndex`), teclado no `onKeyDown` que já existe, render do turno meta,
  contagem de turnos ignorando meta, chave de lista, tratamento do 422 e o
  `<PlayGuide />` entre o `InfoTracker` e o `.game-history`.
- `frontend/src/screens/game.css`: `.game-turn--meta`, `.game-turn-command` e
  `position: relative` no `.game-footer`.
- `frontend/src/strings/game.ts`: chaves novas nos dois dicionários.

Fora (explícito):
- Qualquer arquivo de `backend/`. `resolve_command`, os eventos
  `meta_player_turn`/`meta_narrator_turn`, o 422 e `SessionDetail.commands` são
  TCK-065 e TCK-072. **O TCK-072 roda na mesma wave e não é bloqueador**: os
  campos já existem com default desde o TCK-060, e esta UI é testada contra
  fixtures. Enquanto o TCK-072 não estiver mergeado, `commands: []` é o payload
  real e os estados vazios corretos aparecem.
- `frontend/src/errors.ts`. O 422 é desviado **antes** de `classifyError`, dentro
  do `catch` de `runTurn`: 422 só tem sentido de "comando desconhecido" neste
  endpoint, e mudar `ErrorKind` afetaria builder e sessões.
- `frontend/src/api.ts`. `streamTurn` já lança `ApiError` com `status` e `detail`
  para resposta não-ok (`api.ts:255-257`), que é tudo o que este ticket precisa.
- `Hud.tsx`, `CastRow.tsx`, `StatBars.tsx`, `InfoTracker.tsx`,
  `SuggestionChips.tsx`, `ModeSelector.tsx`: intocados.
- Editar os comandos globais: não há rota; o builder edita só os do cenário
  (TCK-073).
- **Persistência do colapso do "Como jogar" em `localStorage`** (a chave
  `ooc-local:guide` do design): nesta rodada o `<details>` é **não controlado**,
  com `open` por padrão, igual ao INFO do TCK-067. Destino: fase 4, junto com a
  do INFO — as duas preferências entram no mesmo lugar ou em nenhum.
- **Esconder o botão flutuante "Ir para o mais recente" enquanto a paleta está
  aberta**: exige estado atravessando dois blocos por um caso de sobreposição
  raro (o botão só existe fora do fim do histórico). O `z-index` da paleta fica
  **abaixo** do `.game-scrollLatest--floating` (`z-index: 2`, `game.css:152`),
  então nada fica coberto. Destino: fase 4.

## Comportamento esperado

Digitar `/` ou `!` como **primeiro caractere** do campo abre uma lista dos
comandos disponíveis, filtrada pelo que vem depois do sinal. Setas escolhem,
Enter completa o nome no campo, Esc fecha. O turno que roda um comando aparece no
histórico com aparência própria e rótulo do comando, e **não conta como turno**.
A lista completa vive num bloco "Como jogar", que também passa a mostrar o
`playGuide` do start.

```
┌──────────────────────────────────────────────────────┐
│ ▾ Como jogar                                         │  <- PlayGuide (novo)
│   Você é aluno novo. Fale com todo mundo…            │
│   Comandos                                           │
│   !fofoca   O que andam dizendo pelas costas         │
│   /diary    Diário do jogador sobre o dia            │
│   Digite / ou ! no campo de mensagem para usar um.   │
│ … histórico …                                        │
│  ┌ Comando !fofoca ────────────────────────────────┐ │  <- turno meta
│  │ Chloe acha que você é estranho. Aiko…           │ │
│  └─────────────────────────────────────────────────┘ │
│ ┌ Comandos disponíveis ───────────────────────────┐  │  <- paleta (nova)
│ │ !fofoca     O que andam dizendo pelas costas    │  │
│ │ !inventario Seus itens                          │  │
│ └─────────────────────────────────────────────────┘  │
│ [ Ação │ Fala │ Nar. ] [ !fo               ] [Enviar] │
└──────────────────────────────────────────────────────┘
```

### Prefixos são sintaxe, não texto

`!` (comando do cenário) e `/` (global) são gramática que o `resolve_command` do
backend parseia. Ficam como constantes de módulo em código (`SCENARIO_SIGIL`,
`GLOBAL_SIGIL`), exportadas de `frontend/src/components/CommandPalette.tsx`
(`export const SCENARIO_SIGIL = '!'`, `export const GLOBAL_SIGIL = '/'`) e
importadas por `GamePanel.tsx` e `PlayGuide.tsx`; **não** viram chave de i18n:
traduzi-los quebraria o parser. É a
única exceção deliberada à regra "nenhuma string literal em código" neste ticket.
Onde o sinal aparece dentro de uma frase, ele entra como parâmetro interpolado
(`game.commands.turnLabel`) ou como parte da própria frase traduzida
(`noMatch`, `emptyScenario`, `emptyGlobal`, `hint`), nunca concatenado com prosa.

### Estados — paleta

**Abre** quando, e só quando, `draft[0]` é `!` ou `/` e o campo não está em
streaming. `draft = 'vou ver /diary'` **não** abre: o backend só resolve comando
no primeiro caractere, e uma paleta abrindo no meio da frase seria promessa
falsa.

**Escopo pelo sinal:** `!` lista só `scope === 'scenario'`, `/` só
`scope === 'global'`. É o mesmo recorte do `resolve_command`; oferecer global sob
`!` seria oferecer o que vai dar 422.

**Filtro:** `name.startsWith(query.slice(1))`, casefold. Prefixo, não substring:
o jogador está digitando um nome, e prefixo mantém a lista estável enquanto ele
digita.

1. **Com resultados** — `role="listbox"` com `aria-label={t('game.commands.palette.label')}`
   (nome acessível do painel; não há título visível) e um `role="option"` por comando: nome
   com o sinal (`!fofoca`) em `<strong>` e a descrição na segunda linha. O
   primeiro item nasce ativo (`activeIndex = 0`).
2. **Vazio por filtro** (`!zzz`) — o painel **continua na tela** com
   `game.commands.noMatch`, que já diz a saída (Esc fecha). Nesse estado o painel
   **não** é `listbox`, o texto vai num `<p role="status">` e o `textarea` volta a
   `aria-expanded="false"`: `listbox` sem `option` é ARIA inválido, e Enter
   precisa voltar a ser "enviar" (que aí cai no caminho 422 abaixo, com mensagem).
3. **Vazio por ausência** — `!` num cenário sem `commands.yaml`:
   `game.commands.emptyScenario`, que aponta o `/` como alternativa; `/` sem
   globais: `game.commands.emptyGlobal`. Estado vazio com o próximo passo, não
   beco.
4. **Carregando** — não existe: `commands` vem no payload da sessão e o rodapé só
   existe com a sessão pronta. `commands: []` de um backend antigo cai no estado
   3, que é verdadeiro.
5. **Streaming** — a paleta fica fechada e não abre (o `textarea` está `disabled`
   durante o stream, `GamePanel.tsx:569`).
6. **Selecionar** — completa o campo para `<sinal><nome>` (sem espaço no fim, sem
   enviar), fecha a paleta e **mantém o foco no `textarea`** com o cursor no fim.
   Enter **não envia** aqui: Enter já é "enviar" no campo, e disparar um turno a
   partir da tecla usada para autocompletar é ação destrutiva por engano. O
   segundo Enter, com a paleta fechada, envia pelo caminho normal. Um comando tem
   descrição justamente para ser lido antes de rodar.
7. **Erro — comando inexistente** — enviar `!naoexiste` devolve **422
   `unknown_command`** antes do stream. O `catch` de `runTurn` passa a checar
   `err instanceof ApiError && err.status === 422` **antes** de `classifyError`, e
   renderiza `ErrorState` com `game.commands.unknown.title` /
   `game.commands.unknown.body`, `cause` = `err.detail` e **sem botão de tentar
   de novo** — repetir o mesmo nome falha igual. A recuperação é o
   `setDraft(message)` que o `catch` já faz (`GamePanel.tsx:294`): o texto volta
   ao campo, a paleta reabre sozinha (o primeiro caractere é `!`) e mostra os
   nomes válidos.
8. **Erro de rede / 5xx** — caminho existente, sem mudança.

### Estados — turno meta no histórico

`TurnView` traz `meta: boolean` e `command: string | null`.

1. **Render** — `<li className="game-turn game-turn--meta">` com um rótulo
   **visível** no topo: `t('game.commands.turnLabel', { command })`, onde
   `{command}` já vem com o sinal resolvido pelo escopo do comando em
   `SessionDetail.commands`. Comando que não está mais na lista (o autor removeu
   do cenário) → nome cru sem sinal, sem quebrar.
2. **Aparência própria** — borda tracejada e fundo `var(--surface)`, como
   `.game-turn--prologue` (`game.css:83-86`), largura total e alinhamento à
   esquerda. A bolha do **jogador** de um turno meta é **omitida**: o rótulo já
   diz qual comando rodou, e repetir `!fofoca` como mensagem é redundância —
   pior, renderizá-la como bolha azul à direita diria que ele falou aquilo em
   cena. Fica só o bloco do narrador, sob o rótulo.
3. **Não conta como turno** — três lugares:
   - `onTurnsChanged` (`GamePanel.tsx:166-170`) conta só `!turn.meta`;
   - `nextIndex()` (`:224-228`) ignora meta ao procurar o último índice, senão o
     próximo turno normal pula de número;
   - a condição da dica de histórico vazio (`:539`) conta só turnos não-meta:
     sessão cujos únicos turnos são meta ainda mostra `game.empty.hint`.
4. **Chave de lista** — passa a incluir a posição no array
   (`key={`${i}-${turn.index}-${turn.role}`}`). Dois meta seguidos compartilham
   `index` e `role`, e a chave atual colide. **É armadilha real** e tem cenário de
   teste próprio.
5. **Sem sugestões novas** — o turno meta não emite evento `suggestions`; os
   chips do TCK-071 mantêm a lista anterior, o que é correto: a história não
   avançou.
6. **HUD** — o SSE do meta devolve o `hud` atual no fim, como um turno normal;
   nada fica `stale`, nada pisca.
7. **Streaming de meta** — a bolha `pending` do narrador é renderizada já com o
   estilo meta e o rótulo do comando (derivados do `draft` no momento do envio) e
   **sem** etiqueta de modo do TCK-071: comando não tem modo.

### Estados — Como jogar

1. **Com guia e com comandos** — `<details open>` com `<summary>`
   `game.guide.label`, corpo com a prosa do `playGuide` (`white-space: pre-wrap`)
   e, abaixo, o rótulo `game.commands.listLabel` com um `<dl>`: `<dt>` = sinal +
   nome, `<dd>` = descrição. Ordem: a que a API entrega (cenário primeiro, depois
   globais); o sinal já distingue o escopo, sem subtítulos. Fecha com
   `game.commands.hint`, que ensina como acionar.
2. **Só guia** (`commands: []`) — bloco sem a seção de comandos.
3. **Só comandos** (`playGuide === null`) — bloco sem a prosa.
4. **Vazio total** — bloco **não renderizado**. Um "Como jogar" que abre e não tem
   nada dentro é pior que ausência.
5. **Carregando / erro** — nenhum estado próprio: vem no payload da sessão, e o
   skeleton e o `ErrorState` do `GamePanel` já cobrem.
6. **Aberto por padrão**, não controlado (ver "Fora"): o guia é exatamente o que
   se deve ler ao começar.

## Detalhes técnicos

### Contrato consumido (TCK-060, não redefinido aqui)

```ts
export type CommandView = { name: string; description: string; scope: 'scenario' | 'global' }
// SessionDetail.commands: CommandView[]
// SessionDetail.playGuide: string | null            (já existe, api.ts:45)
// TurnView.meta: boolean, TurnView.command: string | null
```

Do **TCK-071**: `game.mode.do/say/story` (para afirmar que o turno meta **não**
tem etiqueta de modo) e a assinatura de `streamTurn` com `mode`/`onSuggestions`.

### Componentes

```ts
export function CommandPalette(props: {
  commands: CommandView[]
  query: string          // texto do campo, começando por '!' ou '/'
  activeIndex: number
  listboxId: string
  optionId: (index: number) => string
  onPick: (command: CommandView) => void
})
export function PlayGuide(props: { playGuide: string | null; commands: CommandView[] })
```

- `CommandPalette` vive dentro do `<form className="game-footer">` (`:558`), que
  ganha `position: relative`; o painel é `position: absolute; bottom: 100%; left:
  0; right: 0`.
- `PlayGuide` é renderizado pelo `GamePanel` **entre o `InfoTracker` e o
  `.game-history`**.
- O `GamePanel` é dono do estado (`activeIndex`, aberto/fechado) porque o teclado
  chega pelo `onKeyDown` do `textarea`, que já existe (`:322-327`). O componente
  é apresentacional e recebe o índice ativo pronto — é o que o deixa testável sem
  simular digitação.

### Fiação no `GamePanel`

1. `const [commands, setCommands] = useState<CommandView[]>([])`, semeado no
   efeito que já faz `setHud`/`setCast` (`:151-156`) e zerado na troca de sessão
   (`:124-141`).
2. `paletteQuery = draft.startsWith(SCENARIO_SIGIL) || draft.startsWith(GLOBAL_SIGIL) ? draft : null`,
   derivado do render — sem estado duplicado. `paletteOpen` = `paletteQuery !== null`
   e `turnPhase !== 'streaming'` e não foi fechada por Esc (um
   `const [paletteDismissed, setPaletteDismissed] = useState(false)`, zerado a
   cada mudança de `draft`).
3. `activeIndex` volta a `0` sempre que a lista filtrada muda de tamanho ou de
   conteúdo (derive a lista com `useMemo` e reinicie no `useEffect` sobre a chave
   dela).
4. `handleKeyDown` (`:322-327`) intercepta `ArrowDown`, `ArrowUp`, `Enter`, `Esc`
   e `Tab` **antes** do ramo que envia, e **só** quando a paleta está aberta com
   opções. Com a paleta fechada, `Enter` continua enviando exatamente como hoje.
   `ArrowDown`/`ArrowUp` dão a volta no fim da lista (lista curta, volta é mais
   rápida que parede). `Esc` com a paleta fechada não faz nada — em particular
   **não** limpa o campo.
5. Turnos: `const visibleTurns = turns` (todos, meta inclusive) para o render, e
   `const playedTurns = turns.filter((t) => !t.meta)` para `onTurnsChanged`,
   `nextIndex()` e a dica de histórico vazio.
6. `PendingTurn` (`:40-43`) ganha uma variante local
   `{ …; status: 'error'; kind: 'command'; title: string; body: string; cause: string }`.
   **`ErrorKind` não muda** — `kind: 'command'` é literal local do arquivo, e por
   isso `errors.ts` fica fora do diff. O ramo de render correspondente usa
   `ErrorState` **sem** `onRetry`.
7. `commandLabel(name)`: procura `name` em `commands` e devolve
   `` `${scope === 'global' ? GLOBAL_SIGIL : SCENARIO_SIGIL}${name}` ``; não
   achou, devolve `name` cru.

### Acessibilidade

- **Paleta sem `role="combobox"` no `textarea`.** O campo continua
  `role="textbox"` e recebe apenas `aria-autocomplete="list"`, `aria-expanded`,
  `aria-controls={listboxId}` e `aria-activedescendant={optionId(activeIndex)}`.
  Pôr `role="combobox"` mudaria o papel do campo e quebraria de uma vez todos os
  `getByRole('textbox', { name: t('game.input.label') })` da suíte — e o ganho
  semântico não paga.
- O foco **nunca sai** do `textarea`: as opções não são focáveis (`tabIndex`
  ausente) e a seleção viaja por `aria-activedescendant`. Sem trap de foco:
  `Tab` fecha a paleta e segue para o botão Enviar.
- Clique na opção usa `onMouseDown` com `preventDefault`, para o `textarea` não
  perder o foco antes do `onPick`.
- Opção ativa entra no campo de visão com
  `el.scrollIntoView?.({ block: 'nearest' })`, com a mesma guarda de existência
  que o código já usa para `scrollTo` (`GamePanel.tsx:55`), porque jsdom não
  implementa.
- `listboxId` e os ids das opções derivam de `useId()`: dois `GamePanel` no mesmo
  documento (jogo + preview do builder) não podem compartilhar `id`.
- Alvo de toque: cada opção tem `min-height: 44px`, `padding: .5rem .75rem`,
  `cursor: pointer`. Opção ativa se distingue por fundo `var(--accent)` **e**
  peso 700 — nunca só por cor.
- Nenhum estado só por cor no turno meta: a borda tracejada e o rótulo textual
  `Comando !fofoca` carregam a informação.
- **Play Guide**: `<details>`/`<summary>` nativo, com `summary { min-height:
  44px }` — o reset global de `index.css:40-43` só cobre `button`. Lista de
  comandos em `<dl>`/`<dt>`/`<dd>`: par nome–descrição é definição. O nome com o
  sinal é texto real, não `::before` de CSS (conteúdo gerado não é selecionável
  nem copiável, e o jogador precisa copiar o nome).
- Nenhuma live region nova. `aria-expanded` no campo e `aria-activedescendant`
  já contam a história; o `<p role="status">` só existe no estado sem resultados,
  que é o único em que o silêncio confundiria.

### Responsividade

- Paleta: sempre da largura do rodapé, `max-height: 40vh; overflow-y: auto`,
  `z-index` acima do histórico e **abaixo** do `.game-scrollLatest--floating`
  (`z-index: 2`, `game.css:152`). Nome da opção em uma linha com ellipsis (nome
  de comando é `^[a-z0-9_-]+$`, curto por contrato) e descrição em até duas
  linhas com `overflow-wrap: anywhere`.
- Turno meta: `.game-turn--meta { width: 100%; align-self: flex-start }`, já
  coberto pela regra de 480px que existe (`game.css:204-209`). O rótulo do
  comando é `font-size: .75rem`, `var(--fg-muted)`, e quebra se precisar.
- Play Guide: `summary` em uma linha; corpo com `max-height: 40vh; overflow-y:
  auto` para que um guia longo não empurre o histórico para fora da tela em
  320px. `<dl>` em `display: grid; grid-template-columns: auto 1fr; gap: .25rem
  .5rem` acima de 480px; **uma coluna** abaixo disso, senão a descrição fica com
  ~150px.
- `@media (max-height: 520px)`: o Play Guide **não** é escondido — é um
  `<details>`, o jogador fecha.
- Sem animação de abertura na paleta e no guia: a paleta reage a cada tecla.

### Tamanho

`CommandPalette.tsx` (~85), `commandPalette.css` (~45), `PlayGuide.tsx` (~55),
`playGuide.css` (~35), `GamePanel.tsx` (~85 de fiação), `game.css` (+18),
`strings/game.ts` (+20) e os testes (~230). Cerca de 570 linhas, acima do alvo
de ~400; por isso 5 pontos. Exceção registrada pelo coordenador: os três pedaços
são a mesma feature vista em três momentos (descobrir o comando, rodar o comando,
ler o resultado); separar o Play Guide daria um bloco que lista comandos que
ninguém consegue disparar. Se o diff passar de ~650, agrupe os cenários de
teclado da paleta (setas, Home/End, Esc) num único `it.each`.

## Contrato público

N/A — `CommandPalette` e `PlayGuide` são usados só pelo `GamePanel`, no mesmo PR,
e nenhum ticket da fase 3 depende deste. O contrato consumido está inteiro na
seção "Contrato público" do TCK-060: campos de `SessionDetail`/`TurnView`, kinds
`meta_player_turn`/`meta_narrator_turn` e o 422 `unknown_command` (congelado lá,
entregue pelo TCK-072). Nada aqui depende do texto do TCK-072.

## Acceptance criteria

- [ ] Digitar `!` como primeiro caractere abre um `listbox` com os comandos de
      escopo `scenario`; `/` abre com os de escopo `global`; os dois conjuntos são
      disjuntos.
- [ ] Digitar `!fo` filtra por prefixo, casefold; `!zzz` mantém o painel com
      `game.commands.noMatch` num `role="status"`, **sem** `listbox`, e o
      `textarea` volta a `aria-expanded="false"`.
- [ ] `!` num cenário sem comandos mostra `game.commands.emptyScenario`; `/` sem
      globais mostra `game.commands.emptyGlobal`.
- [ ] `vou ver /diary` **não** abre a paleta.
- [ ] `ArrowDown`/`ArrowUp` movem `aria-activedescendant` com volta no fim da
      lista; `Enter` completa o campo para `<sinal><nome>`, fecha a paleta, mantém
      o foco no `textarea` e **não** dispara POST; o segundo `Enter` envia.
- [ ] `Esc` fecha a paleta e mantém o texto; `Esc` com a paleta fechada não
      limpa o campo.
- [ ] Clicar numa opção seleciona sem tirar o foco do `textarea`.
- [ ] Turno com `meta: true` renderiza `.game-turn--meta` com
      `game.commands.turnLabel` e o sinal resolvido pelo escopo, sem a bolha do
      jogador e sem etiqueta de modo.
- [ ] Turno meta não incrementa `onTurnsChanged`, não consome índice de turno, e
      uma sessão só com meta ainda mostra `game.empty.hint`.
- [ ] Dois turnos meta seguidos com o mesmo `index` não produzem warning de chave
      duplicada.
- [ ] 422 com `detail: 'unknown_command'` mostra `game.commands.unknown.title` /
      `.body`, **sem** botão `common.retry`, mantém o texto no `textarea` e a
      paleta reabre; 500 continua mostrando `game.turn.error` **com** retry.
- [ ] "Como jogar" mostra a prosa do `playGuide` e um `<dt>`/`<dd>` por comando,
      com `game.commands.hint` no fim; some por inteiro quando não há guia nem
      comandos.
- [ ] `errors.ts` não aparece no diff.
- [ ] `strings/game.ts` tem as chaves novas em `en` e `pt-br`, e os sinais `!` e
      `/` só aparecem em código como constantes de módulo ou dentro das frases
      traduzidas.
- [ ] `npm run check` verde.

## Cenários de teste

### `frontend/src/components/CommandPalette.test.tsx` (novo)

- Feliz: **renders one option per command with the sigil, the name and the
  description** — `getAllByRole('option')` com length 2 e os textos `!fofoca` e a
  descrição.
- Feliz: **filters by prefix as the query grows** — `query="!fo"` deixa uma
  opção.
- Feliz: **marks the active option with aria-selected** — `activeIndex={1}` marca
  só a segunda.
- Borda: **shows only scenario commands under `!` and only global ones under
  `/`** — a mesma lista mista renderiza conjuntos disjuntos conforme o sinal.
- Borda: **matches case-insensitively** — `query="!FO"` acha `fofoca`.
- Borda: **shows game.commands.noMatch and no listbox when nothing matches** —
  `queryByRole('listbox')` é `null` e o texto está num `role="status"`.
- Borda: **shows game.commands.emptyScenario when the scenario has no commands**
  — e `game.commands.emptyGlobal` no caso simétrico com `/`.
- Feliz: **calls onPick with the command when an option is clicked**.
- Borda: **does not blur the textarea when an option is pressed** — o handler é
  `onMouseDown` com `preventDefault`; assertiva: `document.activeElement`
  continua sendo o input renderizado ao lado no teste.

### `frontend/src/components/PlayGuide.test.tsx` (novo)

- Feliz: **renders the guide prose and one entry per command** — texto do
  `playGuide`, `!fofoca` + descrição, `/diary` + descrição, e
  `game.commands.hint`.
- Borda: **renders without the command section when commands is empty**.
- Borda: **renders without the prose when playGuide is null** — a seção de
  comandos continua.
- Borda: **renders nothing when there is neither guide nor commands** —
  `container.firstChild` é `null`.
- A11y: **starts open with a summary reachable by keyboard** — o `details` monta
  com `open` e o `summary` tem o texto `t('game.guide.label')`.

### `frontend/src/components/GamePanel.test.tsx` (existente, cenários novos)

- Feliz: **opens the palette when the first character is a sigil** — `user.type`
  de `!` mostra o `listbox`; `aria-expanded="true"` e `aria-controls` no
  `textarea`.
- Feliz: **arrow keys move aria-activedescendant and Enter completes the draft**
  — `{ArrowDown}` muda o `aria-activedescendant` para o id da segunda opção;
  `{Enter}` deixa `!inventario` no campo, fecha o `listbox` e **não** dispara
  POST (`expect(fetchMock).not.toHaveBeenCalledWith(expect.anything(),
  expect.objectContaining({ method: 'POST' }))`).
- Feliz: **the second Enter sends the completed command** — body do POST com
  `message: '!fofoca'`.
- Feliz: **renders a meta turn with the command label and its own style** — SSE
  de meta seguido de `fetchSession`:
  `getByText(t('game.commands.turnLabel', { command: '!fofoca' }))` e
  `document.querySelector('.game-turn--meta')` presente, sem bolha de jogador.
- Borda: **does not open the palette when the sigil is not the first character**
  — `user.type('vou ver /diary')` não mostra `listbox`.
- Borda: **Esc closes the palette and keeps the text** — o campo continua `!fo` e
  o foco continua no `textarea`.
- Borda: **Esc with the palette closed does not clear the draft**.
- Borda: **a meta turn does not increment onTurnsChanged** — o mock recebe o
  mesmo número antes e depois do comando.
- Borda: **a session whose only turns are meta still shows game.empty.hint**.
- Borda: **two meta turns in a row do not trigger a duplicate key warning** —
  spy em `console.error` sem chamadas (molde de `Hud.test.tsx:94-109`), com dois
  meta de mesmo `index`.
- Borda: **the mode badge is absent on a meta turn** — nenhum texto
  `game.mode.*` na bolha (o TCK-071 está mergeado; se por qualquer motivo não
  estiver, este é o único cenário que sai).
- Falha: **a 422 unknown_command shows the command error without a retry button
  and keeps the text in the textarea** — POST 422 com
  `{ detail: 'unknown_command' }`: `getByText(t('game.commands.unknown.title'))`,
  `queryByRole('button', { name: t('common.retry') })` é `null`, campo com
  `!naoexiste` e a paleta reaberta.
- Falha: **a 500 on a command still shows the generic turn error with retry** —
  prova que o desvio do 422 não engoliu o caminho existente.

### Inventário da suíte existente (preparação, nunca asserção)

| Arquivo | O que muda | Por quê |
|---|---|---|
| `frontend/src/components/GamePanel.test.tsx:16-28` | `session()` ganha `commands: [...]` **só nas fixtures dos cenários novos** (o campo já existe com default `[]` desde o TCK-060) | sem comandos, a paleta cai no estado "vazio por ausência", que é o correto e continua sendo o que os cenários antigos exercitam |
| `frontend/src/components/GamePanel.test.tsx:129-146` | nada muda no cenário `calls onTurnsChanged…` | ele joga turno normal, e turno normal continua contando |
| `frontend/src/components/GamePanel.test.tsx` (todos os `getByRole('textbox', …)`) | nada muda | o `textarea` continua `role="textbox"` com o mesmo nome acessível: é exatamente por isso que a paleta **não** usa `role="combobox"` |
| `frontend/src/screens/GameScreen.test.tsx`, `components/builder/BuilderPreview.test.tsx` | nada muda | as fábricas `session()` desses arquivos foram completadas pelo TCK-060; `playGuide: null` e `commands: []` deixam o bloco "Como jogar" fora da tela, como hoje |
| `frontend/src/errors.test.ts` | nada muda | `classifyError` não é tocado; 422 continua caindo em `unexpected` para todo o resto do app |
| `frontend/src/i18n.test.ts` | nada muda | a paridade de chaves passa a cobrir as novas |

Nenhum teste existente perde cobertura. O único ponto em que um teste antigo
muda de **caminho** (não de asserção) é a chave de lista dos turnos: a asserção
continua sendo "cada turno aparece uma vez", e a chave nova é estritamente mais
específica que a anterior.

## Rollout e kill switch

N/A — `risk: low`. Sem flag: paleta e guia são leitura do payload da sessão; o
turno meta é render condicional de um campo que já vem com default `false`; o 422
é um `if` antes do `classifyError` existente. Com o TCK-072 ausente,
`commands: []` e `meta: false` deixam tudo no estado atual da tela. Reverter é
remover `<CommandPalette />`, `<PlayGuide />` e o ramo `turn.meta` do
`GamePanel`.

## Observabilidade

Eventos: nenhum evento novo no frontend. Do lado do motor, os eventos
`meta_player_turn` / `meta_narrator_turn` (TCK-072) registram cada comando
rodado, com o nome em `command`.
Métrica de sucesso: rodar `!fofoca` e `/recap` numa sessão e ver o contador de
turnos da lista de sessões **não** subir, com os dois blocos aparecendo no
histórico com o rótulo certo; e um `!naoexiste` produzir a mensagem de comando
desconhecido, sem `ErrorState` genérico e sem turno gravado.

## i18n

Chaves novas em `frontend/src/strings/game.ts`, nos **dois** dicionários, num
bloco `game.commands.*` + `game.guide.*` depois de `game.cast.regionLabel`
(`game.ts:35` e `:95`) — ou seja, depois do bloco `game.info.*` do TCK-067.

| chave | en | pt-br |
|---|---|---|
| `game.commands.palette.label` | Available commands | Comandos disponíveis |
| `game.commands.noMatch` | No command with that name. Esc closes this list. | Nenhum comando com esse nome. Esc fecha esta lista. |
| `game.commands.emptyScenario` | This scenario has no commands. Type / to see the global ones. | Este cenário não tem comandos. Digite / para ver os globais. |
| `game.commands.emptyGlobal` | No global commands available. Type ! to see the ones from this scenario. | Nenhum comando global disponível. Digite ! para ver os deste cenário. |
| `game.commands.listLabel` | Commands | Comandos |
| `game.commands.hint` | Type / or ! in the message box to run one. | Digite / ou ! no campo de mensagem para usar um. |
| `game.commands.turnLabel` | Command {command} | Comando {command} |
| `game.commands.unknown.title` | That command doesn't exist | Esse comando não existe |
| `game.commands.unknown.body` | Nothing was sent to the narrator. Your text was kept — fix the name, or type / or ! to see the list. | Nada foi enviado ao narrador. Seu texto foi guardado — corrija o nome, ou digite / ou ! para ver a lista. |
| `game.guide.label` | How to play | Como jogar |

`{command}` em `game.commands.turnLabel` chega **com o sinal** (`!fofoca`),
resolvido em código a partir do escopo. Os sinais `!` e `/` aparecem literais
dentro das frases de `noMatch`/`emptyScenario`/`emptyGlobal`/`hint` porque ali são
sintaxe citada, e citação de sintaxe é conteúdo da própria frase traduzida.

### Chaves reaproveitadas (nada de chave nova para elas)

`game.input.label`, `game.input.hint`, `game.turn.playerLabel`,
`game.turn.narratorLabel`, `game.turn.thinking`, `game.turn.error`,
`game.turn.errorBody`, `game.empty.hint`, `common.details` (dentro do
`ErrorState`), `game.mode.*` (TCK-071, só para o cenário que prova a ausência da
etiqueta no turno meta).

Nome, descrição e prompt de comando, e o texto do `playGuide`, vêm do
cenário/config e nunca passam por `t()`.
