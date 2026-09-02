---
id: TCK-071
title: Chips de sugestão e seletor de modo Do/Say/Story na tela de jogo
status: done
points: 5
blockedBy: [TCK-060, TCK-067]
files:
  - frontend/src/components/SuggestionChips.tsx
  - frontend/src/components/SuggestionChips.test.tsx
  - frontend/src/components/suggestions.css
  - frontend/src/components/ModeSelector.tsx
  - frontend/src/components/ModeSelector.test.tsx
  - frontend/src/components/modeSelector.css
  - frontend/src/components/GamePanel.tsx
  - frontend/src/components/GamePanel.test.tsx
  - frontend/src/api.ts
  - frontend/src/screens/game.css
  - frontend/src/strings/game.ts
migration: false
ui: true
risk: low
---

## Problema

A fase 3 dá ao jogador duas coisas que hoje não têm superfície nenhuma:

1. **Sugestões.** O narrador passa a terminar todo turno com três `[SUGGEST:…]`,
   o engine as grava e as manda pelo evento SSE `suggestions` (TCK-069), e o
   start já tem `suggestions` desde sempre — editável na aba Starts
   (`StartsTab.tsx:423-463`) e **nunca exibido**. O jogador olha para um campo de
   texto vazio e um `game.empty.hint` genérico.
2. **Modos de input.** O engine passa a formatar a mensagem do jogador como
   `(Ação)`, `(Fala)` ou `(Narração)` conforme `ChatRequest.mode` (TCK-072), o
   que muda como o narrador trata o texto. Sem seletor, `mode` nunca é enviado e
   todo turno continua indo cru: o recurso existe no motor e é inalcançável.

`streamTurn` (`api.ts:241-250`) monta o body com `{ message }` e ponto. Nenhum
caminho passa modo, e o parser de eventos (`:284-290`) não conhece `suggestions`.

## Escopo

Dentro:
- `frontend/src/components/SuggestionChips.tsx` + `suggestions.css` novos: até
  três chips com o texto da sugestão como rótulo do botão de enviar, e um botão
  "Editar" ao lado de cada.
- `frontend/src/components/ModeSelector.tsx` + `modeSelector.css` novos:
  `radiogroup` de três posições com rádios nativos, dica visível do modo
  selecionado e `name` único por instância.
- `frontend/src/api.ts`: `TurnHandlers.onSuggestions`, o campo `suggestions` em
  `TurnEvent`, o ramo do evento SSE no parser de `streamTurn` e o envio de `mode`
  no body. `InputMode` e `TurnOptions.mode` **já existem** desde o TCK-060 e não
  são redeclarados.
- `frontend/src/components/GamePanel.tsx`: estado de sugestões e de modo,
  persistência do modo por sessão, envio com modo, etiqueta de modo na bolha do
  jogador (inclusive na otimista), placeholder por modo.
- `frontend/src/screens/game.css`: `position`/`flex` do rodapé para os dois
  blocos novos e o bump de `--game-scrollLatest-bottom`.
- `frontend/src/strings/game.ts`: chaves novas nos dois dicionários e **remoção**
  de `game.input.placeholder`.

Fora (explícito):
- Qualquer arquivo de `backend/`. `ChatRequest.mode`, o `player_turn.payload.mode`,
  a formatação em `events_to_messages` e a emissão do evento `suggestions` são
  TCK-069 e TCK-072. Esta UI é construída **contra o contrato congelado, com
  fixtures nos testes**; enquanto o backend não preencher, `suggestions: []` é o
  payload real e o bloco simplesmente não aparece.
- `Hud.tsx`, `hud.css`, `CastRow.tsx`, `StatBars.tsx`, `InfoTracker.tsx`: o
  TCK-067 fechou o cabeçalho e este ticket mexe só no rodapé.
- Paleta de comandos, turno meta e Play Guide: TCK-074. Este ticket **não** trata
  `!`/`/` no campo, nem `TurnView.meta`, nem 422.
- `errors.ts`: nenhum caminho de erro novo aqui.
- `GameScreen.tsx` e `BuilderPreview.tsx`: o painel é compartilhado; o preview
  ganha os dois controles sem tocar em nenhum dos dois.
- Fila de ações, histórico de sugestões usadas, sugestão gerada pelo cliente:
  as três linhas vêm do motor e não são inventadas na UI.

## Comportamento esperado

Acima do campo de texto, até três chips com a ação sugerida pelo narrador; cada
chip envia na hora e um botão ao lado joga o texto no campo para o jogador
editar. À esquerda do campo, um seletor de três posições — Ação, Fala, Narração —
que diz como o motor deve interpretar o que for enviado. O modo escolhido fica
salvo por sessão e aparece como etiqueta em cada turno do jogador no histórico.

```
┌──────────────────────────────────────────────────────┐
│ … histórico …                                        │
│  ┌ Você  ( Fala ) ─────────────────────────────────┐ │
│  │ "Não fui eu."                                   │ │
│  └─────────────────────────────────────────────────┘ │
│ Ações sugeridas                                      │
│ [ Pegar o caderno            ] [ Editar ]            │
│ [ Perguntar para a Chloe     ] [ Editar ]            │
│ [ Sair da sala sem falar nada] [ Editar ]            │
│ [ Ação │ Fala │ Narração ] [ campo…        ] [Enviar]│
│ O que você tenta fazer. O narrador decide como termina│
│ Enter envia · Shift+Enter quebra linha               │
└──────────────────────────────────────────────────────┘
```

### Estados — chips

1. **Com sugestões** — até três `<li>`, na ordem recebida. Cada `<li>` tem um
   `<button>` cujo **rótulo visível é o texto da sugestão** (ação primária:
   enviar) com `aria-label={t('game.suggest.send.aria', { text })}`, e um
   `<button>` secundário `game.suggest.edit` com
   `aria-label={t('game.suggest.edit.aria', { text })}`. Os três botões de enviar
   teriam nome acessível idêntico se o rótulo fosse "Enviar"; por isso o texto da
   sugestão **é** o rótulo, e o `aria-label` contém o texto visível inteiro
   (WCAG 2.5.3 satisfeito nos dois locales).
2. **Vazio (`suggestions: []`)** — o bloco **não é renderizado**. Sem frase
   "nenhuma sugestão": o campo e o `game.input.hint` já são o caminho, e um aviso
   fixo em todo start sem sugestão é ruído. O bloco fica acima do campo e abaixo
   do `.game-history` (`flex: 1`), então aparecer e sumir encolhe o histórico e
   **não** move o campo de texto.
3. **Carregando** — não existe: o rodapé só é montado com
   `state.phase === 'ready'` (`GamePanel.tsx:557`) e as sugestões vêm no mesmo
   payload da sessão.
4. **Streaming** — o bloco **some** (`turnPhase === 'streaming'` esconde). As
   sugestões são do turno anterior e não há fila de ações; deixá-las clicáveis
   com o envio já desabilitado seria controle que parece funcionar e não
   funciona.
5. **Sucesso** — as novas chegam pelo evento `suggestions` (emitido antes do
   `hud`), então quando o stream acaba a lista nova já está no estado e o bloco
   reaparece preenchido. Turno que **não** trouxe evento `suggestions` mantém a
   lista anterior: não avançou a história, as sugestões continuam válidas.
6. **Erro** — a lista anterior volta assim que `turnPhase` volta para `idle`. É a
   ação de recuperação: o turno não aconteceu, a mesma sugestão pode ser
   reenviada. O `catch` de `runTurn` já faz `setDraft(message)`
   (`GamePanel.tsx:294`), então a sugestão enviada por chip cai no campo pronta
   para ajuste — comportamento preservado de propósito.
7. **Enviar** — chama `runTurn(text)` com o **modo atual**, exatamente como o
   Enter no campo. Feedback: a bolha aparece no histórico com a etiqueta de modo,
   e o `game.turn.done` que já existe é anunciado. Sem toast.
8. **Editar** — `setDraft(text)`, foca o `textarea` e põe o cursor no fim
   (`setSelectionRange(text.length, text.length)`), reusando o `focusToken`
   (`GamePanel.tsx:99,207-210`) para não competir com os outros efeitos de foco.
   O bloco **continua visível** (o jogador pode desistir e escolher outra). O
   próprio movimento de foco é o feedback; sem anúncio extra.
9. **Texto longo** (≤120 chars por contrato) — o chip quebra linha
   (`overflow-wrap: anywhere`), sem truncagem: sugestão cortada não é sugestão.

### Estados — seletor de modo

1. **Padrão** — `do`. Três `<input type="radio">` nativos dentro de um
   `<div role="radiogroup" aria-label={t('game.mode.regionLabel')}>`. Rádio
   nativo dá setas, Home/End e seleção-ao-focar de graça; nada de `role="radio"`
   na mão.
2. **`name` único por instância** — o `GamePanel` deriva `name` do `useId()` que
   ele já tem (`GamePanel.tsx:73`, `inputId`): `name={`game-mode-${inputId}`}`, e
   passa pela prop `name` do `ModeSelector`, que **não** chama `useId()`. O
   `GamePanel` é montado duas vezes no mesmo documento em teste
   (`GamePanel.test.tsx:92-118`) e no preview do builder; um `name` fixo faria os
   dois painéis compartilharem a seleção. É bug garantido se passar batido.
3. **Persistência** — `localStorage`, chave
   **`ooc-local:inputMode:<sessionId>`**. Leitura na montagem e no efeito de
   troca de sessão (`GamePanel.tsx:124-141`), que hoje zera o estado: ele passa a
   **reler** o modo da sessão nova em vez de resetar cego para `do`.
4. **Valor inválido gravado** (`"shout"`, `null`, lixo) → `do`, sem lançar.
   `localStorage` inacessível → `do`, e a escolha só não persiste (mesmo
   `try/catch` de `readStagePreference`, `GamePanel.tsx:17-32`).
5. **Streaming** — o seletor fica **desabilitado**, não escondido: é controle de
   estado persistente e sumir com ele faria o rodapé pular de altura a cada
   turno. Continua legível, mostrando o modo do turno em voo.
6. **Erro** — nenhum estado próprio. O modo não é perdido por turno que falhou;
   ao reenviar, vai o modo atual.
7. **Dica do modo** — abaixo do seletor, uma linha com `game.mode.<mode>.hint`,
   no estilo de `.game-input-hint`, referenciada por `aria-describedby` no
   `radiogroup`. Visível, não `title`: "Narração" é intraduzível sem explicação, e
   explicação que só existe em tooltip não existe no celular.
8. **Placeholder acompanha o modo** — `game.input.placeholder.do/.say/.story`.
   Campo dizendo "O que você faz?" no modo Fala é mentira de interface.

### Etiqueta de modo no histórico

`TurnView.mode` vira uma etiqueta **visível** dentro da bolha do turno do
jogador: `<span className="game-turn-mode">{t(`game.mode.${turn.mode}`)}</span>`,
usando **as mesmas chaves do seletor** — um conceito, um conjunto de chaves.

- `mode` nulo/ausente → sem etiqueta. Turnos antigos não ganham rótulo inventado.
- O `.game-turn-label` visualmente escondido (`Você`) **não muda**: continua
  sendo o rótulo de papel. A etiqueta de modo é conteúdo real dentro da bolha,
  então o leitor de tela ouve "Você, Fala, Não fui eu.".
- A bolha otimista (`pending`, `GamePanel.tsx:485-490`) também recebe a etiqueta
  do modo corrente, para o turno não trocar de aparência quando o stream termina.
- `extraTurns` passa a empilhar
  `{ index, role: 'player', text: message, mode }` (`GamePanel.tsx:276-280`); o
  turno do narrador continua sem modo. Compila porque o TCK-060 declara os quatro
  campos novos de `TurnView` como opcionais no TS; o turno otimista não preenche
  `meta`, `suggestions` nem `command` (o TCK-074 é quem cria turnos meta).

## Detalhes técnicos

### Contrato consumido (TCK-060) e o que este ticket acrescenta em `api.ts`

Do TCK-060 chegam prontos, **sem redeclarar nada aqui**:
`SessionDetail.suggestions: string[]`, `TurnView.mode: InputMode | null`,
`export type InputMode = 'do' | 'say' | 'story'`,
`TurnOptions = { signal?: AbortSignal; mode?: InputMode }` e o `ChatRequest.mode`
do lado do servidor. O TCK-060 declarou `TurnOptions.mode` e escreveu que **quem
passa a mandá-lo no body é este ticket**.

Este ticket é o **owner de `api.ts` na wave 3** e acrescenta só o que faltava:

```ts
export type TurnHandlers = {
  onDelta: (delta: string) => void
  onHud: (hud: TurnHudPayload) => void
  onSuggestions: (suggestions: string[]) => void
  onError: (err: unknown) => void
}

type TurnEvent = { delta?: string; hud?: TurnHudPayload; suggestions?: string[]; error?: string }
```

- `streamTurn` (`api.ts:241-250`) monta o body como
  `JSON.stringify({ message, ...(mode ? { mode } : {}) })`. O `mode` só viaja
  quando existe, para não mudar a forma do request de nenhum chamador que não
  passe modo.
- O parser (`api.ts:284-290`) ganha o ramo
  `else if (parsed.suggestions !== undefined) h.onSuggestions(parsed.suggestions)`,
  **depois** de `error` e `delta` e antes ou depois de `hud` — a ordem entre os
  dois não importa porque um evento traz um campo só.
- `onSuggestions` é obrigatório em `TurnHandlers`: o `GamePanel` é o único
  chamador de `streamTurn` no repositório (verificado por Grep), então não há
  consumidor para quebrar.

Regras de consumo:
- `SessionDetail.suggestions` semeia o estado; o evento SSE substitui a lista
  inteira (não é delta).
- A UI corta em **3** (`slice(0, 3)`) e descarta entradas vazias ou só com
  espaço. O engine já garante isso; a UI não confia em payload de fora.
- `TurnView.mode` ausente/`null` = turno sem etiqueta. A UI não inventa `do` para
  turno velho.
- O modo corrente vai **sempre** no body, inclusive quando é o default `do`: o
  backend precisa dele para escrever `(Ação)` em `events_to_messages`.

### Componentes

```ts
export function SuggestionChips(props: {
  suggestions: string[]
  onSend: (text: string) => void
  onEdit: (text: string) => void
})
export function ModeSelector(props: {
  value: InputMode
  onChange: (mode: InputMode) => void
  name: string          // único por instância de GamePanel
  disabled?: boolean
})
```

Os dois são fiados dentro do `<form className="game-footer">` que já existe
(`GamePanel.tsx:558`) e que já é `display: flex; flex-wrap: wrap; align-items:
flex-end`: `SuggestionChips` é o primeiro filho, com `flex-basis: 100%` (linha
própria acima do campo); `ModeSelector` é o segundo, `flex: none`, à esquerda do
`textarea`. Extrair os dois evita inchar o `GamePanel` (585 linhas hoje) e dá
teste unitário por comportamento, seguindo o precedente do `CastRow` (TCK-054).

### Fiação no `GamePanel`

1. `const [suggestions, setSuggestions] = useState<string[]>([])`, semeado no
   efeito que já faz `setHud`/`setCast` (`:151-156`), zerado no efeito de troca de
   sessão (`:124-141`), substituído no `onSuggestions`.
2. `const [mode, setMode] = useState<InputMode>(() => readInputMode(sessionId))`,
   com `readInputMode`/`writeInputMode` no molde de
   `readStagePreference`/`writeStagePreference` (`:17-32`), chave
   `ooc-local:inputMode:${sessionId}`; o efeito de troca de sessão faz
   `setMode(readInputMode(sessionId))` em vez de resetar para `do`.
3. `runTurn` passa `{ signal: controller.signal, mode }` como `options` de
   `streamTurn` (`:268`) e empilha `mode` no `extraTurns` do jogador (`:276-280`).
   `retry()` (`:312-315`) continua chamando `runTurn(lastMessage)`, que lê o
   `mode` corrente — turno que falhou não congela o modo antigo.
4. `handleSendSuggestion = (text) => { if (turnPhase === 'streaming') return; setDraft(''); void runTurn(text) }`
   (mesmo caminho do `submit`, `:305-310`).
5. `handleEditSuggestion = (text) => { setDraft(text); setFocusToken((n) => n + 1) }`,
   e o efeito de `focusToken` (`:207-210`) passa a posicionar o cursor no fim com
   `setSelectionRange` depois do `focus()`.
6. O `textarea` (`:562-572`) troca `placeholder={t('game.input.placeholder')}` por
   `t(\`game.input.placeholder.${mode}\`)`.

### CSS

- `suggestions.css`: `.suggestions { flex-basis: 100% }`, lista em
  `display: flex; flex-direction: column; gap: .25rem`, cada `<li>` em
  `display: flex; gap: .25rem` com o chip em `flex: 1; min-width: 0;
  text-align: left; padding: .5rem .75rem; overflow-wrap: anywhere` e o "Editar"
  em `flex: none; padding: 0 .75rem` (para não virar um quadrado de 44px colado
  no chip). Em 320px sobram ~200px para o texto do chip, que quebra em até 3
  linhas sem cortar.
- `modeSelector.css`: rádios `.visually-hidden` (a classe já existe,
  `states.css:39-49`) e `<label>` desenhando o segmento. **`input:focus-visible +
  label` recebe `outline: 2px solid var(--focus)` explicitamente**: o input
  escondido não desenha foco sozinho, e segmento sem foco visível é seletor
  inutilizável no teclado. O segmento selecionado se distingue por **duas**
  pistas — fundo `var(--accent)` e `font-weight: 700` —, nunca só por cor. A dica
  do modo é `flex-basis: 100%`, `font-size: .75rem`, `var(--fg-muted)`, as mesmas
  propriedades de `.game-input-hint` (`game.css:197-202`).
- `screens/game.css`: dentro do `@media (max-width: 480px)` que já existe
  (`:204-209`), o seletor ganha `flex-basis: 100%` e
  `display: grid; grid-template-columns: repeat(3, 1fr)` — linha própria acima do
  campo, para o `textarea` nunca ficar com menos de ~180px úteis. E
  `--game-scrollLatest-bottom` (`:10`, hoje `6rem`) é redeclarado para `9rem` no
  `.game-panel` quando há sugestões, para o botão flutuante "Ir para o mais
  recente" não cobrir o primeiro chip.
- Sem animação de entrada nos chips: o bloco aparece e some a cada turno, e
  animar isso é enjoo.

### Acessibilidade

- **Chips**: `<ul>` dentro de
  `<div role="group" aria-label={t('game.suggest.regionLabel')}>`; cada `<li>` com
  dois `<button type="button">` reais — clicáveis, focáveis, na ordem natural de
  tabulação, antes do seletor e do campo. Alvo de toque de 44px já é global
  (`index.css:40-43`).
- **Seletor**: `role="radiogroup"` com `aria-label` e `aria-describedby`
  apontando para a linha de dica, que é texto visível.
- Nenhuma live region nova. O feedback de envio é o que já existe:
  `game.turn.done` na região do `GamePanel` e a bolha aparecendo no histórico.
- Etiqueta de modo na bolha é texto real, sem `aria-label` e sem `title`.
- O `textarea` mantém `role="textbox"` e o `aria-labelledby` implícito do
  `<label htmlFor>`: os testes existentes buscam
  `getByRole('textbox', { name: t('game.input.label') })` e continuam válidos.

### Tamanho

`SuggestionChips.tsx` (~45), `suggestions.css` (~40), `ModeSelector.tsx` (~60),
`modeSelector.css` (~45), `api.ts` (+12), `GamePanel.tsx` (~65 de fiação),
`game.css` (+12), `strings/game.ts` (+30) e os testes (~230). Cerca de 540
linhas, acima do alvo de ~400. Exceção registrada pelo coordenador: os dois
controles são o mesmo turno visto de dois ângulos (o que enviar e como enviar) e
separá-los daria um PR de componente sem consumidor. Se o diff passar de ~600,
agrupe os cenários de persistência do modo (`localStorage` vazio, valor inválido,
valor válido) num único `it.each`.

## Contrato público

Exposto para o **TCK-074**, que é o próximo dono de `GamePanel.tsx` e de
`strings/game.ts`:

```ts
// frontend/src/api.ts  (InputMode e TurnOptions vêm do TCK-060, inalterados)
export type TurnHandlers = {
  onDelta: (delta: string) => void
  onHud: (hud: TurnHudPayload) => void
  onSuggestions: (suggestions: string[]) => void
  onError: (err: unknown) => void
}
export function streamTurn(sessionId: string, message: string, h: TurnHandlers, options?: TurnOptions): Promise<void>
```

- Body do POST: `{ message }` sempre, `mode` só quando definido.
- Evento SSE `{"suggestions": [...]}` reconhecido pelo parser e entregue em
  `onSuggestions`; a lista substitui a anterior por inteiro.
- `game.mode.do` / `.say` / `.story` são as chaves de rótulo do modo, usadas pelo
  seletor **e** pela etiqueta do histórico. O TCK-074 depende delas para afirmar
  "turno meta não tem etiqueta de modo".
- `game.input.placeholder` **deixa de existir**; quem quiser o texto usa
  `game.input.placeholder.do`.

## Acceptance criteria

- [ ] Sessão com `suggestions` desenha um chip por item (no máximo 3), com o
      texto da sugestão como rótulo visível do botão de enviar.
- [ ] Clicar no chip envia o texto exato, sem `trim` nem normalização, e o body
      do POST traz `mode` com o modo selecionado.
- [ ] Sem tocar no seletor, o body do POST traz `mode: 'do'`.
- [ ] Clicar em "Editar" põe o texto no `textarea`, foca o campo com o cursor no
      fim e mantém os chips na tela.
- [ ] O evento SSE `{ suggestions: [...] }` substitui a lista inteira; turno sem
      esse evento mantém a lista anterior.
- [ ] Durante o stream o bloco de sugestões some e volta quando `turnPhase` volta
      para `idle`, inclusive quando o turno falhou.
- [ ] `suggestions: []` não renderiza o bloco.
- [ ] O seletor é um `radiogroup` com três rádios nativos, `name` único por
      instância, marcado em `do` por padrão, desabilitado durante o stream.
- [ ] Trocar de modo grava `ooc-local:inputMode:<sessionId>`; remontar com o
      mesmo `sessionId` restaura o modo; outro `sessionId` volta a `do`; valor
      gravado inválido cai em `do` sem lançar; `localStorage` inacessível não
      quebra a tela.
- [ ] A dica do modo selecionado está visível e ligada ao `radiogroup` por
      `aria-describedby`; o placeholder do campo acompanha o modo.
- [ ] A bolha do jogador (otimista e definitiva) mostra a etiqueta do modo;
      `TurnView` sem `mode` não mostra etiqueta nenhuma.
- [ ] `game.input.placeholder` não existe mais em `strings/game.ts` e as três
      chaves novas existem em `en` e `pt-br`.
- [ ] `npm run check` verde.

## Cenários de teste

### `frontend/src/components/SuggestionChips.test.tsx` (novo)

- Feliz: **renders one chip per suggestion with the text as the button label** —
  três botões achados por
  `getByRole('button', { name: t('game.suggest.send.aria', { text }) })`.
- Feliz: **calls onSend with the exact suggestion text** — clique no chip;
  `toHaveBeenCalledWith('Pegar o caderno')`, sem trim nem normalização.
- Feliz: **calls onEdit with the exact text** — clique no "Editar" da segunda
  sugestão chama `onEdit` com a segunda string.
- Borda: **gives each edit button a distinct accessible name** — os três nomes
  acessíveis são diferentes entre si (evita "Editar, Editar, Editar").
- Borda: **renders nothing for an empty list** — `container.firstChild` é `null`.
- Borda: **drops whitespace-only entries** — `['a', '   ', 'b']` renderiza dois
  chips.
- Borda: **renders at most three chips** — lista com cinco renderiza as três
  primeiras.
- Borda: **keeps a long suggestion whole** — texto de 120 chars aparece inteiro
  (`getByRole` pelo nome completo), sem reticências.
- A11y: **exposes the block as a labelled group** — `role="group"` com
  `aria-label={t('game.suggest.regionLabel')}`.

### `frontend/src/components/ModeSelector.test.tsx` (novo)

- Feliz: **renders a radiogroup with the three modes and checks the current one**
  — `getByRole('radiogroup', { name: t('game.mode.regionLabel') })` e
  `getByRole('radio', { name: t('game.mode.do') })` com `toBeChecked()`.
- Feliz: **calls onChange when another mode is picked** — clique em
  `game.mode.say` chama `onChange('say')`.
- Feliz: **moves the selection with the arrow keys** —
  `user.keyboard('{ArrowRight}')` com foco no rádio ativo chama `onChange` com o
  próximo modo (comportamento nativo; o teste garante que ninguém trocou os
  inputs por `<button>`).
- Borda: **shows the hint of the selected mode** — `t('game.mode.say.hint')`
  visível com `value="say"`, e o `radiogroup` tem `aria-describedby` apontando
  para ele.
- Borda: **disables the three radios when disabled** — os três `toBeDisabled()`.
- Borda: **isolates two instances that get different names** — dois
  `ModeSelector` com `name` distinto: marcar um não desmarca o outro.

### `frontend/src/components/GamePanel.test.tsx` (existente, cenários novos)

- Feliz: **sends the suggestion text with the picked mode in the request body** —
  selecionar `Fala`, clicar no chip, e o body do POST é
  `{ message: 'Pegar o caderno', mode: 'say' }`.
- Feliz: **sends the default mode explicitly** — sem tocar no seletor, o body
  traz `mode: 'do'`.
- Feliz: **replaces the chips with the ones from the SSE suggestions event** — o
  evento `{ suggestions: ['A', 'B', 'C'] }` troca os três chips depois do stream.
- Feliz: **shows the mode badge on the player turn in the history** —
  `getByText(t('game.mode.say'))` dentro da bolha do jogador.
- Borda: **hides the chips during the stream and brings them back after** — gate
  de stream com `Promise` (molde de `GamePanel.test.tsx:363-388`): durante o
  stream `queryByRole('group', { name: t('game.suggest.regionLabel') })` é
  `null`.
- Borda: **keeps the previous chips when the turn brings no suggestions event** —
  turno só com `delta` + `hud` mantém a lista anterior.
- Borda: **edit puts the text in the textarea and focuses it** —
  `expect(textarea).toHaveValue(text)` e `document.activeElement === textarea`.
- Borda: **persists the mode per session** — trocar para `story`, remontar com o
  mesmo `sessionId`: o rádio `story` continua marcado; montar com outro
  `sessionId` volta para `do`.
- Borda: **falls back to do when the stored mode is garbage** — gravar `'shout'`
  na chave, montar, `do` marcado.
- Borda: **a turn without mode renders no badge** — turno vindo de
  `SessionDetail.turns` sem `mode`: nenhum dos três textos `game.mode.*` na
  bolha.
- Borda: **two panels get independent radio names** — estende o cenário de
  isolamento existente (`GamePanel.test.tsx:92`): marcar `Fala` no painel A deixa
  o painel B em `Ação`.
- Falha: **a failed turn restores the chips and puts the suggestion text back in
  the textarea** — POST 500: `ErrorState` aparece, os chips voltam, e o campo
  contém o texto da sugestão.
- Falha: **does not break when localStorage throws** — molde de
  `GamePanel.test.tsx:235-251`: o seletor renderiza em `do`.

### Inventário da suíte existente (preparação, nunca asserção)

| Arquivo | O que muda | Por quê |
|---|---|---|
| `frontend/src/components/GamePanel.test.tsx:46-59` | `mockRoutedFetch` passa a ler também `body.mode` (o tipo do `JSON.parse` vira `{ message: string; mode?: string }`) | os cenários novos precisam do campo; os existentes continuam lendo só `body.message` e não mudam de asserção |
| `frontend/src/components/GamePanel.test.tsx:16-28` | `session()` carrega `suggestions: []` (e os demais campos do TCK-060) | campo obrigatório de `SessionDetail`; com lista vazia, todos os cenários antigos seguem sem bloco de sugestões, exatamente como hoje |
| `frontend/src/components/GamePanel.test.tsx` (`afterEach`) | o `afterEach` que limpa `localStorage` sai do bloco `scene` (`:164-166`) para o `describe` de cima, ou ganha um irmão nos blocos novos | o modo é persistido por sessão; sem limpeza, um cenário contamina o seguinte. É preparação de isolamento, não asserção |
| `frontend/src/screens/GameScreen.test.tsx` | nada muda | não busca o campo por placeholder; usa `game.input.label` |
| `frontend/src/components/builder/BuilderPreview.test.tsx` | nada muda | idem |
| `frontend/src/i18n.test.ts` | nada muda | a paridade de chaves passa a cobrir as novas e deixa de cobrir a removida |

**Remoção de `game.input.placeholder`**: Grep em `frontend/src` mostra três
ocorrências — `GamePanel.tsx:568` (trocada por este ticket) e as duas linhas do
dicionário (`strings/game.ts:9` e `:69`). **Nenhum teste referencia a chave**; os
testes acham o campo por `getByRole('textbox', { name: t('game.input.label') })`,
que não muda. Manter as quatro chaves deixaria uma órfã e um par de nomes
assimétrico (`.placeholder` querendo dizer "modo do").

Nenhum teste existente perde cobertura.

## Rollout e kill switch

N/A — `risk: low`. Sem flag: os dois controles são rodapé, sem request novo
(o `mode` viaja no POST que já existe) e sem migração. Com o TCK-069/TCK-072
ausentes, `suggestions` fica `[]` (bloco não aparece) e o `mode` enviado é
ignorado pelo backend antigo — nenhum dos dois quebra o turno. Reverter é remover
os dois componentes do `<form className="game-footer">` e o `mode` do
`streamTurn`.

## Observabilidade

Eventos: nenhum evento novo no frontend. Do lado do motor, o TCK-069 grava
`narrator_turn.payload.suggestions` e o TCK-072 grava
`player_turn.payload.mode`, os dois legíveis nos eventos da sessão.
Métrica de sucesso: jogar 5 turnos no cenário exemplo com três chips presentes em
todos eles, e nenhum `player_turn` gravado sem `mode` depois de o TCK-072 entrar
— ou seja, todo turno enviado por esta tela carrega o modo, inclusive o default.

## i18n

Chaves novas em `frontend/src/strings/game.ts`, nos **dois** dicionários, num
bloco `game.suggest.*` + `game.mode.*` logo depois de `game.input.hint`
(`game.ts:12` e `:72`).

| chave | en | pt-br |
|---|---|---|
| `game.suggest.regionLabel` | Suggested actions | Ações sugeridas |
| `game.suggest.send.aria` | Send: {text} | Enviar: {text} |
| `game.suggest.edit` | Edit | Editar |
| `game.suggest.edit.aria` | Edit: {text} | Editar: {text} |
| `game.mode.regionLabel` | Input mode | Modo de escrita |
| `game.mode.do` | Do | Ação |
| `game.mode.say` | Say | Fala |
| `game.mode.story` | Story | Narração |
| `game.mode.do.hint` | What you try to do. The narrator decides how it turns out. | O que você tenta fazer. O narrador decide como termina. |
| `game.mode.say.hint` | What you say out loud, word for word. | O que você fala em voz alta, palavra por palavra. |
| `game.mode.story.hint` | Text that enters the story as something that happened. | Texto que entra na história como algo que aconteceu. |
| `game.input.placeholder.do` | What do you do? | O que você faz? |
| `game.input.placeholder.say` | What do you say? | O que você diz? |
| `game.input.placeholder.story` | What happens next? | O que acontece? |

### Chave removida

`game.input.placeholder` sai dos dois dicionários; o valor atual
(`What do you do?` / `O que você faz?`) migra intacto para
`game.input.placeholder.do`.

### Chaves reaproveitadas (nada de chave nova para elas)

`game.input.label`, `game.input.hint`, `game.input.send`, `game.input.sending`,
`game.turn.playerLabel`, `game.turn.done`, `game.turn.error`,
`game.turn.errorBody`, `common.retry` (dentro do `ErrorState`).

O texto da sugestão vem do narrador e nunca passa por `t()`.
