---
id: TCK-067
title: Barras de stat e bloco INFO na tela de jogo
status: in_review
points: 5
blockedBy: [TCK-060]
files:
  - frontend/src/components/StatBars.tsx
  - frontend/src/components/StatBars.test.tsx
  - frontend/src/components/statBars.css
  - frontend/src/components/InfoTracker.tsx
  - frontend/src/components/InfoTracker.test.tsx
  - frontend/src/components/infoTracker.css
  - frontend/src/components/GamePanel.tsx
  - frontend/src/components/GamePanel.test.tsx
  - frontend/src/strings/game.ts
migration: false
ui: true
risk: low
---

## Problema

O TCK-060 põe `stats: StatView[]` e `minds: Record<string, MindView>` em
`SessionDetail` e em `TurnHudPayload`, e a fase 3 vai enchê-los: o engine de
stats (TCK-061), o juiz de HUD e o `minds.py` (TCK-069). Nada disso aparece na
tela: o `GamePanel` renderiza `<Hud>` e `<CastRow>` e mais nada
(`GamePanel.tsx:447-448`). O jogador perde reputação e não vê; o narrador passa a
acompanhar o que cada NPC sente e o jogador nunca lê.

Atributo que muda sem aviso é a informação mais fácil de perder de vista, e é
justamente a que o resto da fase gasta um call de utility por turno para
produzir.

## Escopo

Dentro:
- `frontend/src/components/StatBars.tsx` + `statBars.css` novos: uma barra por
  `StatView`, com highlight de 600 ms na linha que mudou de valor.
- `frontend/src/components/InfoTracker.tsx` + `infoTracker.css` novos: bloco INFO
  colapsável, uma linha por membro do elenco com emoji, nome, atitude e último
  evento.
- `frontend/src/components/GamePanel.tsx`: estado `stats`/`minds` (semeado pela
  sessão, atualizado no `onHud` com a regra "ausente = inalterado"), render dos
  dois componentes como irmãos de `<Hud>`/`<CastRow>`, e o anúncio de mudança de
  atributo compondo na live region que já existe.
- Chaves i18n novas em `frontend/src/strings/game.ts`, nos dois dicionários.
- Testes novos nos dois componentes e cenários novos em `GamePanel.test.tsx`.

Fora (explícito):
- **`frontend/src/components/Hud.tsx` e `hud.css`.** As barras são **irmãs** do
  HUD, não filhas: o wrapper `.hud` é `aria-live="polite" aria-atomic="true"`
  (`Hud.tsx:92`), e barras lá dentro fariam o leitor de tela reler nome, valor,
  máximo e texto de nível de cada atributo a cada turno. É a mesma decisão que
  fez o `CastRow` virar irmão no TCK-054. "Abaixo da grade do HUD" é posição
  visual, resolvida por CSS (mesmo `background`, mesma `border-bottom`, mesmo
  `position: sticky` de `.cast`), não por aninhamento no DOM.
- `frontend/src/screens/game.css`: os dois blocos trazem o próprio arquivo de
  CSS, importado pelo componente, como `CastRow.tsx:3` já faz com `cast.css`.
  Nenhuma regra de `.game-*` muda.
- Qualquer arquivo de `backend/` e o `frontend/src/api.ts`. Os tipos e os campos
  chegam prontos do TCK-060; esta UI é construída **contra o contrato congelado,
  com fixtures nos testes**. Quem preenche os dados são o TCK-061 (stats) e o
  TCK-069 (juiz, minds), que rodam em paralelo ou depois. Enquanto eles não
  entrarem, `stats: []` e `minds: {}` são o payload real e os dois blocos mostram
  os estados vazios corretos.
- `GameScreen.tsx` e `BuilderPreview.tsx`: o painel é compartilhado, então o
  preview do builder ganha os blocos sem tocar em nenhum dos dois.
- Chips de sugestão, seletor de modo, paleta de comandos: TCK-071 e TCK-074.
- **Persistência do colapso do INFO em `localStorage`** (a chave
  `ooc-local:info` do design). Nesta rodada o `<details>` é **não controlado**,
  com `open` por padrão: o jogador fecha e ele reabre na próxima montagem.
  Destino: fase 4. Motivo: a persistência custa estado controlado, dois efeitos e
  três testes (incluindo o de `localStorage` que estoura) para uma preferência
  que se refaz com um clique.
- Qualquer aviso visual de falha do juiz ou do `minds`: a falha é recuperada no
  motor e o que está na tela continua sendo a última leitura válida.

## Comportamento esperado

Entre o HUD e a linha de elenco entra uma faixa com uma barra por atributo.
Depois da linha de elenco entra o bloco **INFO**: uma linha por personagem em
cena com emoji, nome, atitude e último evento, dentro de um disclosure que o
jogador pode fechar.

```
┌──────────────────────────────────────────────┐
│ Turno 12 │ Local … │ Hora … │ Clima …        │  <- Hud (existente, intocado)
│ ⭐ Reputação           55/100                 │  <- StatBars (novo)
│ ███████████░░░░░░░░░                          │
│ Nível: Você é um aluno comum.                 │
│ ⚡ Energia              80/100                 │
│ ████████████████░░░░                          │
│ Em cena  ( Aiko ) ( Chloe )                   │  <- CastRow (existente)
│ ▾ INFO — o que pensam                         │  <- InfoTracker (novo)
│   🤨 Chloe · desconfiada, mas curiosa         │
│      Último: viu você pegar o caderno         │
│   — Aiko · Ainda não lido                     │
└──────────────────────────────────────────────┘
```

### Estados — StatBars

1. **Com atributos** — um `<li>` por `StatView`, na ordem do array. Cada linha:
   ícone (`aria-hidden="true"`, como o emoji de clima em `Hud.tsx:109`), nome,
   `hud.stat.value` (`{value}/{max}`), a barra, e a linha secundária
   `hud.stat.level` quando `level` não é nulo.
2. **Vazio (`stats: []`)** — o bloco **não é renderizado**. Diferente do
   `CastRow`, que sempre renderiza: elenco vazio oscila turno a turno; cenário
   sem `stats.yaml` nunca vai ter atributo nenhum, é ausência permanente e nada
   oscila. Rótulo de seção vazia seria ruído fixo em todo cenário sem stats.
3. **Carregando (`stats === null`)** — nada renderizado, **sem skeleton**: não
   sabemos quantas barras virão, e um skeleton de tamanho errado empurra o
   histórico e depois recua. O `.game-history--skeleton` já comunica a espera.
4. **Streaming** — as barras do turno anterior **permanecem** com os valores
   antigos; o container recebe `aria-busy="true"` e `opacity: .7`, como
   `.hud[aria-busy='true']`. Nada de valor otimista.
5. **Valor mudou** — a linha inteira ganha `.statBars__item--highlight` por
   **600 ms**, reusando o padrão exato do `Hud` (`HIGHLIGHT_MS`, `prevRef`,
   `setTimeout`, `clearTimeout` no unmount — `Hud.tsx:33,61-77`). Só as linhas
   que mudaram. Comparação **por id**, não por posição: stat dinâmico pode ser
   inserido no fim.
6. **Erro** — silencioso. Com o turno inteiro falhando, `hudStale` já é `true` e
   a frase `hud.stale` do `Hud` cobre o cabeçalho todo; `StatBars` recebe `stale`
   e aplica **só** o esmaecimento. Uma frase de stale por tela (regra do
   TCK-054).

Render da barra:
- preenchimento = `(value - min) / (max - min)`, **clampado em [0, 1]** e
  formatado em `%`. `max <= min` (o contrato proíbe, mas o payload vem de fora) →
  `0%`, sem `NaN` e sem exceção. `value` fora de `[min, max]` → a barra clampa,
  mas o **texto mostra o valor cru**: a UI não corrige estado do motor (mesma
  postura do `Hud` com turno negativo, `Hud.test.tsx:143`);
- `color` entra como `style={{ background: stat.color ?? undefined }}` na fill;
  sem cor, a fill herda `var(--accent)` do CSS. A cor nunca carrega informação
  sozinha — o valor está em texto ao lado —, então não há gate de contraste sobre
  ela;
- a barra inteira é `aria-hidden="true"`: é redundante com o texto `55/100` da
  mesma linha. Sem `role="meter"` e sem `<progress>`;
- `icon` pode ter até 4 chars; slot de largura fixa para as barras alinharem;
- a linha de nível tem **altura reservada** (`min-height` no
  `.statBars__levelSlot`) mesmo com `level` nulo: um stat entra e sai de nível
  conforme o valor, e o bloco não pode saltar por isso.

### Estados — InfoTracker

1. **Com mentes** — uma linha por membro do `cast`, **na ordem do elenco**:
   `emoji` (`aria-hidden="true"`), nome (`member.name || member.id`, mesmo
   fallback do `CastRow.tsx:23`), atitude, e a linha secundária `game.info.event`
   com o último evento. `event: ''` → a linha secundária não é renderizada.
2. **Elenco vazio (`cast: []`)** — o disclosure continua no lugar e o corpo
   mostra **`game.cast.empty`**, a chave que já existe. Bloco sumindo e voltando
   a cada troca de cena empurra o histórico.
3. **Ninguém lido ainda** (`minds` sem entrada para nenhum do elenco) — corpo com
   uma única linha `game.info.pending`, que diz o que fazer: jogar um turno. É
   também o texto correto e permanente quando a flag `minds` está desligada no
   backend.
4. **Parcial** — membro do elenco sem entrada em `minds` aparece com
   `game.info.unknown` no lugar da atitude e sem linha de evento. A linha existe
   porque a pessoa está em cena; o que falta é a leitura.
5. **Carregando (`cast === null`)** — nada renderizado.
6. **Streaming** — as linhas anteriores permanecem, `aria-busy="true"`,
   `opacity: .7`. A troca acontece de uma vez quando o evento `hud` chega.
7. **Erro** — silencioso; com `stale`, só o esmaecimento.

`minds` pode conter id que não está mais no elenco (a cena mudou depois da última
leitura). O `InfoTracker` itera sobre **`cast`**, não sobre `minds`: quem manda em
"quem está em cena" é o elenco.

**INFO não é live region e não anuncia.** Anunciar atitude e evento de 2–3 NPCs
todo turno, por cima de cena + elenco + atributos, vira fala sobreposta e
inutiliza a região que já existe. O bloco é painel de consulta.

## Detalhes técnicos

### Contrato consumido (TCK-060, não redefinido aqui)

```ts
export type StatView = {
  id: string; name: string; icon: string | null; color: string | null
  value: number; min: number; max: number; level: string | null
}
export type MindView = { attitude: string; emoji: string; event: string }
// SessionDetail.stats: StatView[]              -> estado inicial
// SessionDetail.minds: Record<string, MindView> -> estado inicial
// TurnHudPayload ganha stats?: StatView[] e minds?: Record<string, MindView>
```

Regras de consumo:
- `hud.stats` **ausente** no payload do evento `hud` significa **inalterado**: as
  barras anteriores permanecem. Ausência nunca é lida como lista vazia; lista
  vazia só existe com `stats: []` explícito. É a mesma regra que o `cast` já
  segue (`GamePanel.tsx:260`), com a mesma guarda `!= null` (que também cobre o
  `null` explícito — há teste existente que manda `cast: null` de propósito,
  `GamePanel.test.tsx:325`).
- `hud.minds` segue a mesma regra e, quando vem, é o **mapa completo**, não
  delta: substitui o anterior inteiro.
- A ordem de `stats` é a ordem de exibição. A UI não ordena, não agrupa e não
  distingue stat declarado de dinâmico: para o jogador não há diferença.
- `name`, `level`, `icon`, `attitude`, `emoji` e `event` vêm prontos do backend e
  **nunca** passam por `t()`.

### Onde vive

Dois componentes novos, irmãos, renderizados em `GamePanel.tsx:447-448`:

```tsx
<Hud hud={hudView} busy={turnPhase === 'streaming'} stale={hudStale} />
<StatBars stats={statsView} busy={turnPhase === 'streaming'} stale={hudStale} />
<CastRow cast={castView} busy={turnPhase === 'streaming'} stale={hudStale} />
<InfoTracker minds={mindsView} cast={castView} busy={turnPhase === 'streaming'} stale={hudStale} />
```

```ts
export function StatBars(props: { stats: StatView[] | null; busy?: boolean; stale?: boolean })
export function InfoTracker(props: {
  minds: Record<string, MindView> | null
  cast: CastMember[] | null
  busy?: boolean
  stale?: boolean
})
```

`StatBars` fica **entre** `Hud` e `CastRow` (é estado do jogador, colado no HUD);
`InfoTracker` fica **depois** de `CastRow` (é leitura sobre quem o `CastRow`
acabou de listar).

### Fiação no `GamePanel`

1. `const [stats, setStats] = useState<StatView[] | null>(null)` e
   `const [minds, setMinds] = useState<Record<string, MindView> | null>(null)`,
   ao lado de `cast` (`:93`).
2. Semeados no efeito que já faz `setHud`/`setCast` (`:151-156`).
3. Zerados no efeito de troca de sessão (`:124-141`), junto de `setCast(null)`.
4. Atualizados dentro de `onHud` (`:256-261`), **só quando o campo veio**:
   `if (newHud.stats != null) setStats(newHud.stats)` e o mesmo para `minds`.
5. `statsView`/`mindsView` derivados como `castView` (`:331`):
   `state.phase === 'ready' ? (stats ?? state.session.stats) : null`.

### Anúncio de atributos (uma região, string composta)

Entra na **live region que já existe** (`GamePanel.tsx:547-549`), no padrão do
TCK-054:

- `const [statsAnnouncement, setStatsAnnouncement] = useState('')`;
- `const statsKey = stats === null ? '\0null' : stats.map((s) => `${s.id}:${s.value}`).join('|')`
  (sentinela distinta de `''`, que é a lista vazia — molde de `castKey`, `:396`);
- um `useEffect` com dependência `[statsKey]` e um `useRef` do valor anterior, no
  molde de `prevCastKeyRef` (`:398-407`): primeira passagem só registra (carregar
  a sessão **não** anuncia); chave igual → não escreve nada; diferente → anuncia
  **só os stats cujo valor mudou**, via `hud.stats.change` juntado por `, `
  dentro de `hud.stats.announce`;
- `setStatsAnnouncement('')` no início de `runTurn`, junto dos dois resets que já
  existem (`:237-238`);
- a região renderiza
  `[sceneAnnouncement, castAnnouncement, statsAnnouncement].filter(Boolean).join(' ')`.

Nenhuma região nova. Como `statsKey` deriva de estado que só muda no `onHud`, o
anúncio sai no fim do turno, nunca a cada delta.

### Acessibilidade

- **StatBars**: `<div className="statBars" role="group" aria-label={t('hud.stats.regionLabel')}>`
  com `aria-busy` durante o stream. **Não** é live region. Lista em `<ul>`/`<li>`,
  um `<li>` por atributo, com `data-stat={stat.id}` para o teste alcançar a linha.
- Ícone e barra são `aria-hidden="true"`; toda a informação está em texto real.
  Nada depende de cor, largura ou emoji.
- **InfoTracker**: `<details open>` / `<summary>` nativos — `aria-expanded` e
  Enter/Espaço vêm de graça, sem `role="button"` manual. Nome acessível do
  disclosure = o texto visível `game.info.label`. Corpo em `role="group"` com
  `aria-label={t('game.info.regionLabel')}`.
- Alvo de toque: `summary { min-height: 44px; display: flex; align-items: center }`.
  O reset global de `index.css:40-43` só cobre `button`, então a regra é
  obrigatória aqui.
- Foco visível: `:focus-visible` global (`index.css:35-38`) já desenha o foco do
  `summary`; nada de `outline: none`.
- Nenhum elemento focável nos dois blocos além do `<summary>`. A ordem de foco da
  tela ganha exatamente um ponto de parada.
- Estados vazios são texto real, nunca ausência de conteúdo.
- Contraste: rótulos e textos secundários em `var(--hud-label, #9aa0ab)` sobre
  `var(--hud-bg, #14161c)`, valores em `var(--hud-value, #f2f3f5)` — os mesmos
  pares já usados no HUD e no `CastRow`. Trilho da barra em
  `rgba(255,255,255,.08)` (a mesma cor da `border-bottom` do `.hud`).

### Responsividade

Menor breakpoint tratado hoje: `@media (max-width: 479px)` em `hud.css`/`cast.css`.
Alvo real: 320px.

- `.statBars`: `padding: 8px 16px` (igual ao `.hud`), uma linha por atributo,
  cabeçalho em `display: flex; gap: .5rem` com o nome em
  `flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap` e `title` com o nome completo — mesmo tratamento de
  `.hud__field dd` (`hud.css:35-42`). O valor `55/100` é `flex: none`.
- Barra: `height: 6px; border-radius: 999px; width: 100%`. Nada de largura fixa,
  nada de scroll horizontal.
- Texto de nível: `font-size: .75rem`, `var(--hud-label)`, uma linha com ellipsis
  e `title` com o texto completo.
- `@media (max-width: 479px)`: `padding: 4px 16px` (acompanha o `.cast`), nome em
  `.8rem`.
- `.info`: linhas em `display: grid; grid-template-columns: auto 1fr` (emoji,
  conteúdo). Atitude e evento com `overflow-wrap: anywhere` e **sem truncagem** —
  o backend já corta em 120 chars e frase pela metade não serve para nada.
- `@media (max-height: 520px)`: os dois blocos **permanecem** (são texto barato);
  só o palco de sprites some, como já acontece em `stage.css:102`.
- Animação: só `opacity`, dentro de `@media (prefers-reduced-motion:
  no-preference)`, como `hud.css:50` e `cast.css:46` já fazem. O highlight de
  600 ms é mudança de peso/sublinhado (molde de `.hud__field--highlight`), não
  movimento.

### Tamanho

`StatBars.tsx` (~70), `statBars.css` (~50), `InfoTracker.tsx` (~60),
`infoTracker.css` (~40), `GamePanel.tsx` (~50 de fiação), `strings/game.ts`
(+20) e os testes (~260: 15 cenários de `StatBars`, 11 de `InfoTracker`, 8 em
`GamePanel.test.tsx`). Cerca de 550 linhas, acima do alvo de ~400. Os cortes já
feitos (persistência do colapso do INFO, movida para a fase 4) são a mitigação;
se o diff passar de ~600, agrupe os cenários de `StatBars` sobre `value`/`max`
(`max == min`, valor fora da faixa, cor ausente) num único `it.each`.

### Literais `TurnView` no `GamePanel`

Este ticket é dono de `GamePanel.tsx` na wave 2 e **não** precisa tocar os
literais `{ index, role, text }` de `GamePanel.tsx:276-280`: o TCK-060 declara
`mode`, `meta`, `suggestions` e `command` como **opcionais** no TS de `TurnView`
justamente para esses literais continuarem compilando. Não os altere aqui; o
TCK-071 acrescenta `mode` e o TCK-074 acrescenta `meta`/`command`.

## Contrato público

N/A — `StatBars` e `InfoTracker` são usados só pelo `GamePanel`, no mesmo PR.
Nenhum outro ticket consome esta seção. O contrato que este ticket **consome**
está na seção "Contrato público" do TCK-060.

## Acceptance criteria

- [ ] Sessão carregada com `SessionDetail.stats` desenha uma barra por item, na
      ordem do array, com nome, `{value}/{max}` e o texto de nível quando existe.
- [ ] `stats: []` não renderiza o bloco de barras, e o `CastRow` continua
      imediatamente abaixo do `Hud`.
- [ ] Evento `hud` com `stats` diferente atualiza as barras e a live region passa
      a conter `hud.stats.announce` **uma única vez**, citando só os stats que
      mudaram de valor.
- [ ] Evento `hud` **sem** `stats` (e sem `minds`) mantém barras e linhas de INFO
      anteriores.
- [ ] Carregar a sessão não escreve anúncio de atributo na live region.
- [ ] O preenchimento da barra usa `min` e `max` (`min: -50, max: 50, value: 0` →
      50%), clampa em 0%/100% e nunca produz `NaN` com `max === min`; o texto
      mostra o valor cru recebido.
- [ ] A linha que mudou de valor ganha `.statBars__item--highlight` e a perde
      depois de 600 ms; a que não mudou nunca ganha; a comparação é por id.
- [ ] Desmontar com o timer de highlight pendente não emite warning de `setState`
      após unmount.
- [ ] O INFO renderiza uma linha por membro do `cast`, na ordem do elenco,
      ignorando ids de `minds` que não estão em cena.
- [ ] Membro sem mente mostra `game.info.unknown`; ninguém lido mostra
      `game.info.pending`; elenco vazio mostra `game.cast.empty`.
- [ ] Durante o stream os dois blocos continuam no DOM com `aria-busy="true"` e
      os valores do turno anterior.
- [ ] Turno com erro mostra `hud.stale` exatamente uma vez na tela, com os dois
      blocos esmaecidos e ainda no DOM.
- [ ] Nenhum elemento focável novo além do `<summary>` do INFO.
- [ ] `Hud.tsx` e `hud.css` não aparecem no diff.
- [ ] `strings/game.ts` tem as chaves novas em `en` e `pt-br`, e não existe
      string literal de UI fora do dicionário.
- [ ] `npm run check` verde.

## Cenários de teste

Padrão da casa: vitest + testing-library, sem mock de componente, tudo por
`getByRole`/`getByText` com `t(...)` (nunca literal), `container.querySelector`
para classe e `data-*` quando o alvo não tem papel.

### `frontend/src/components/StatBars.test.tsx` (novo)

- Feliz: **renders one row per StatView with name, value/max and the level line**
  — dois `StatView` renderizam os dois nomes, dois textos
  `t('hud.stat.value', { value, max })` e o `t('hud.stat.level', { level })` do
  que tem nível.
- Feliz: **fills the bar proportionally to min and max** — `min: -50, max: 50,
  value: 0` produz `width: 50%` na fill
  (`container.querySelector('.statBars__fill')`, `style.width`), provando que a
  conta usa `min` e não assume zero.
- Feliz: **applies the author color to the fill and leaves it to the CSS when
  color is null** — `#f5c542` aparece no `style` da fill; `color: null` não
  escreve `background` inline.
- Borda: **clamps the fill to 0% and 100% but prints the raw value** — `value`
  acima de `max` mostra a barra cheia e o texto com o valor recebido.
- Borda: **renders without a NaN width when max equals min** — `min: 5, max: 5` →
  `width: 0%`, e o render não lança.
- Borda: **omits the level line but keeps the row height when level is null** —
  `.statBars__level` ausente, `.statBars__levelSlot` presente.
- Borda: **renders nothing when stats is an empty list** e **renders nothing when
  stats is null** — `container.firstChild` é `null` nos dois, sem skeleton.
- Borda: **highlights only the stat whose value changed and clears it after
  600 ms** — `vi.useFakeTimers()`, `rerender` dentro de `act`, assertiva por
  `[data-stat="reputacao"]` com `.statBars__item--highlight` e o outro sem;
  `advanceTimersByTime(600)` limpa. Cópia de `Hud.test.tsx:73-92`.
- Borda: **highlights by id, not by position** — inserir um stat dinâmico no
  início do array não destaca os stats que só mudaram de posição.
- Falha: **does not warn about setState after unmount while the highlight timer
  is pending** — spy em `console.error`, molde de `Hud.test.tsx:94-109`.
- Falha/a11y: **hides the icon and the bar from assistive tech**
  (`aria-hidden="true"` nos dois nós), **has no focusable or interactive
  elements** (`container.querySelectorAll('button, a, input, [tabindex]')` com
  length 0, molde de `Hud.test.tsx:150`), **applies aria-busy on the group when
  busy** (`role="group"` com `aria-label` = `t('hud.stats.regionLabel')`) e
  **does not render a second stale sentence** (com `stale`,
  `queryByText(t('hud.stale'))` é `null`).

### `frontend/src/components/InfoTracker.test.tsx` (novo)

- Feliz: **renders one row per cast member with emoji, name, attitude and last
  event** — emoji com `aria-hidden`, nome, atitude e
  `t('game.info.event', { event })`.
- Feliz: **follows the cast order, not the minds map order** — `minds` com as
  chaves invertidas ainda renderiza na ordem do `cast`.
- Borda: **ignores minds entries for characters that left the scene** — id
  presente em `minds` e ausente do `cast` não aparece.
- Borda: **shows game.info.unknown for a cast member without a mind yet** — o
  outro membro continua com sua atitude.
- Borda: **shows game.info.pending when nobody in the cast has been read** —
  `minds={{}}` com dois membros.
- Borda: **shows game.cast.empty when the cast is empty** — reuso da chave
  existente.
- Borda: **renders nothing when cast is null**.
- Borda: **falls back to the id when name is empty** — molde de
  `CastRow.test.tsx:35`.
- Borda: **omits the event line when the event field is empty**.
- A11y: **exposes the disclosure as a summary reachable by keyboard and starts
  open** — o `summary` tem o texto `t('game.info.label')` e o `details` monta com
  `open`.
- A11y: **applies aria-busy when busy** — corpo em `role="group"` com
  `aria-busy="true"`.

### `frontend/src/components/GamePanel.test.tsx` (existente, cenários novos)

- Feliz: **an SSE hud event with stats updates the bars and announces the change
  once** — a live region contém `t('hud.stats.announce', …)` uma única vez.
- Feliz: **an SSE hud event with minds fills the INFO rows** — a atitude aparece
  no bloco.
- Borda: **loading a session does not announce stats** — molde de
  `GamePanel.test.tsx:309`.
- Borda: **a hud event without stats keeps the previous bars** — e, sem `minds`,
  mantém as linhas de INFO.
- Borda: **only the changed stat appears in the announcement** — dois stats no
  payload, um com o mesmo valor: a frase cita só um.
- Borda: **during the stream both blocks keep the previous values with
  aria-busy** — gate de stream com `Promise`, molde de
  `GamePanel.test.tsx:363-388`.
- Borda: **a scenario without stats renders no bars block** —
  `document.querySelector('.statBars')` é `null`.
- Falha: **a failed turn shows hud.stale exactly once** —
  `getAllByText(t('hud.stale'))` tem length 1, com os dois blocos esmaecidos e
  ainda no DOM.

### Inventário da suíte existente (preparação, nunca asserção)

| Arquivo | O que muda | Por quê |
|---|---|---|
| `frontend/src/components/GamePanel.test.tsx:16-28` | a fábrica `session()` carrega `stats: []`, `minds: {}`, `commands: []`, `suggestions: []` | são campos obrigatórios de `SessionDetail` desde o TCK-060, que é quem fecha o `tsc -b` da wave 1. Se algum faltar, acrescente — é preparação, nenhuma asserção muda |
| `frontend/src/components/GamePanel.test.tsx` (bloco `cast`) | nada muda | os testes que mandam `{ hud: {...} }` sem `stats`/`minds` passam a exercitar o caminho "inalterado", de graça |
| `frontend/src/components/Hud.test.tsx`, `CastRow.test.tsx` | nada muda | os dois componentes não são tocados |
| `frontend/src/screens/GameScreen.test.tsx`, `components/builder/BuilderPreview.test.tsx` | nada muda neste ticket | as fábricas `session()` desses arquivos são completadas pelo TCK-060 |
| `frontend/src/i18n.test.ts` | nada muda | `has the same keys in en and pt-br` passa a cobrir as chaves novas |

Nenhum teste existente perde cobertura: o `Hud` continua com os mesmos 15 casos,
o `CastRow` com os mesmos 5, e a ordem `Hud → CastRow` no DOM continua afirmada
pelo cenário "a scenario without stats renders no bars block".

## Rollout e kill switch

N/A — `risk: low`. Os dois blocos são texto barato, aditivos, sem request novo e
sem estado persistido (o colapso do INFO ficou não controlado de propósito). Com
o TCK-061/TCK-069 ausentes, `stats: []` e `minds: {}` são o payload real e os
estados vazios corretos aparecem. Reverter é remover `<StatBars />` e
`<InfoTracker />` do `GamePanel`.

## Observabilidade

Eventos: nenhum no frontend (o projeto não emite telemetria de cliente). Do lado
do motor, `judge_applied` / `judge_rejected` / `judge_failed` e
`minds_applied` / `minds_rejected` / `minds_failed` (TCK-062/063/069) explicam por
que um valor mudou ou não.
Métrica de sucesso: jogar 5 turnos no cenário exemplo vendo as barras
acompanharem os eventos `stat` do motor, sem nenhum turno em que uma barra
apareça vazia no meio do stream, e com a live region citando só os stats que
mudaram.

## i18n

Chaves novas em `frontend/src/strings/game.ts`, nos **dois** dicionários
(`gameEn` e `gamePtBr`). Bloco `hud.*` logo depois de `hud.announce`
(`game.ts:45` e `:105`); bloco `game.info.*` logo depois de
`game.cast.regionLabel` (`:35` e `:95`).

| chave | en | pt-br |
|---|---|---|
| `hud.stats.regionLabel` | Player stats | Atributos do jogador |
| `hud.stat.value` | {value}/{max} | {value}/{max} |
| `hud.stat.level` | Level: {level} | Nível: {level} |
| `hud.stats.change` | {name} now {value} | {name} agora {value} |
| `hud.stats.announce` | Stats: {changes}. | Atributos: {changes}. |
| `game.info.label` | INFO — what they think | INFO — o que pensam |
| `game.info.regionLabel` | What the characters in scene think | O que os personagens em cena pensam |
| `game.info.pending` | Nobody read yet. Play a turn and the narrator starts tracking how each one feels. | Ninguém lido ainda. Jogue um turno e o narrador começa a acompanhar o que cada um sente. |
| `game.info.unknown` | Not read yet | Ainda não lido |
| `game.info.event` | Last: {event} | Último: {event} |

`hud.stat.value` tem o mesmo valor nos dois locales de propósito: é chave para não
existir literal em código (mesmo caso de `game.documentTitle`).

Reuso, sem chave nova: `game.cast.empty` (corpo do INFO com elenco vazio),
`hud.stale` (só no `Hud`), `hud.placeholder` (campo desconhecido, se preciso).

Nunca passam por `t()`: `name`, `icon` e `level` do `StatView`; `attitude`,
`emoji` e `event` do `MindView` — vêm do cenário/LLM, já no locale do cenário.
