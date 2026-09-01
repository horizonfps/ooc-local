---
id: TCK-054
title: Exibir a linha de elenco em cena abaixo do HUD na tela de jogo
status: done
points: 5
blockedBy: [TCK-050]
files:
  - frontend/src/components/CastRow.tsx
  - frontend/src/components/CastRow.test.tsx
  - frontend/src/components/cast.css
  - frontend/src/components/GamePanel.tsx
  - frontend/src/components/GamePanel.test.tsx
  - frontend/src/strings.ts
migration: false
ui: true
risk: low
---

## Problema

Com o director (TCK-055) trocando o elenco em cena a cada turno, o jogador não
tem como saber quem o motor considera presente. O palco de sprites
(`GamePanel.tsx:405`) não serve de resposta: ele desenha só quem tem arte, e
personagem sem sprite fica invisível mesmo estando em cena. A informação existe
no contrato desde o TCK-050 (`SessionDetail.cast` e `cast` em `TurnHudPayload`) e
não é exibida em lugar nenhum.

## Escopo

Dentro:
- `frontend/src/components/CastRow.tsx` + `cast.css` novos: a linha de elenco,
  grudada embaixo do HUD.
- `frontend/src/components/GamePanel.tsx`: estado do elenco (semeado por
  `state.session.cast`, atualizado em `onHud`), render do `CastRow` como irmão de
  `<Hud />`, e anúncio de troca de elenco compondo com o de cena na live region
  que já existe.
- Chaves i18n novas em `frontend/src/strings.ts`, nos dois locales.

Fora (explícito):
- Qualquer arquivo de backend. O `cast` vem pronto; a UI não deriva elenco de
  tag, de `scene.ts` nem de `assets`.
- Chip clicável, ficha de personagem, tooltip com biografia, reordenação,
  tradução ou title-case de nome, cap de quantidade com "+N".
- Reconciliar elenco com `scene.sprites`: são coisas diferentes (quem o motor
  considera em cena × quem está desenhado) e podem divergir de propósito.
- Aviso visual quando o director falha. A falha é recuperada no motor e o elenco
  exibido é exatamente o que narrou; não há nada para o jogador fazer.
- `frontend/src/components/Hud.tsx` e `hud.css` — o elenco é irmão do HUD, não
  filho (motivo abaixo).
- `GameScreen.tsx`, `BuilderPreview.tsx`: o painel é compartilhado, então preview
  do builder e jogo ganham a linha sem tocar em nenhum dos dois.

## Comportamento esperado

Abaixo do HUD, uma linha fina com o rótulo `Em cena` e um chip por personagem
presente. Ao fim de cada turno a linha troca de uma vez, junto com o HUD, e o
leitor de tela ouve o elenco novo uma única vez. Durante o stream, os chips do
turno anterior continuam ali, esmaecidos. Cena sem ninguém mostra um chip apagado
`Ninguém`; sessão carregando mostra `—`.

```
┌──────────────────────────────────────────────┐
│ Turno 12 │ Local … │ Hora … │ Clima …        │  <- Hud (existente)
│ Em cena  ( Aiko ) ( Cydonia )                │  <- CastRow (novo)
└──────────────────────────────────────────────┘
```

## Detalhes técnicos

### Contrato consumido (congelado no TCK-050)

```ts
export type CastMember = { id: string; name: string }
export type TurnHudPayload = HudState & { cast?: CastMember[] }
// SessionDetail.cast: CastMember[]   -> estado inicial
```

Regras de consumo:
- `name` é o rótulo exibido; se vier vazio, exibe `id`. A UI nunca faz
  title-case, tradução ou reordenação — a ordem do array é a ordem de exibição.
- `cast` ausente no payload do evento `hud` significa **inalterado**: o elenco
  anterior permanece. Ausência nunca é lida como lista vazia; lista vazia só
  existe quando vem `cast: []` explícito.
- Nenhuma relação com `scene.sprites`. Podem divergir e a UI não tenta
  reconciliar.

Este ticket **não** depende do TCK-055: sem ele (ou com o flag `director`
desligado) o elenco exibido é o estático do start, que é o comportamento correto
nesse estado.

### Onde vive

Componente novo renderizado em `GamePanel.tsx` **imediatamente depois** de
`<Hud hud={hudView} busy={...} stale={hudStale} />` (`GamePanel.tsx:420`), como
irmão. Não dentro do `<Hud>`: o wrapper `.hud` é
`aria-live="polite" aria-atomic="true"` (`Hud.tsx:92`), e o elenco lá dentro
faria o HUD inteiro ser reanunciado a cada troca e duplicaria o anúncio da live
region de cena.

```ts
export function CastRow(props: { cast: CastMember[] | null; busy?: boolean; stale?: boolean })
```

`GamePanel` passa `busy={turnPhase === 'streaming'}` e `stale={hudStale}`,
espelhando o que já passa para `<Hud>`. O elenco vive num
`useState<CastMember[] | null>(null)`, semeado no mesmo efeito que já faz
`setHud(state.session.hud)` (`GamePanel.tsx:144`) e atualizado dentro de `onHud`
(`GamePanel.tsx:244`) **só quando `newHud.cast !== undefined`**. O efeito de troca
de sessão (`GamePanel.tsx:120`) zera o elenco junto com o resto.

### Estados

1. **Com elenco** — um chip por membro, na ordem do array.
2. **Vazio (`cast: []`)** — a linha continua renderizada, com o rótulo e **um**
   chip em estilo apagado (`.cast__chip--empty`, cor `var(--hud-label)`, borda
   tracejada) com o texto `game.cast.empty`. Cena vazia é estado legítimo do
   jogo, não é "ainda não sei"; sumir com a linha faria o HUD pular de altura a
   cada turno.
3. **Carregando (`cast === null`)** — rótulo + um chip com `t('hud.placeholder')`
   (`—`) e `title={t('game.cast.unavailable')}`, mesmo tratamento que o `Hud` dá
   a campo desconhecido (`Hud.tsx:38`). Sem skeleton próprio: o skeleton do
   histórico já cobre a espera.
4. **Streaming** — o elenco do turno anterior **permanece visível**; a linha
   recebe `aria-busy="true"` e opacidade 0.7, como `.hud[aria-busy='true']`. A
   troca acontece de uma vez quando o evento `hud` chega. Piscar para vazio no
   meio do stream inventaria uma saída de cena que não aconteceu.
5. **Erro** — silencioso: nenhum aviso, ícone ou texto extra. A falha do director
   é recuperada no motor e o elenco exibido é o que narrou. Quando o **turno
   inteiro** falha, `hudStale` já é `true` e a frase `hud.stale` do `Hud` cobre
   HUD e elenco; o `CastRow` recebe `stale` e aplica só o esmaecimento
   (`.cast--stale { opacity: .7 }`), **sem** repetir a frase — uma frase de stale
   por tela.

### Anúncio: dois estados, uma única string derivada no render

O texto do elenco **não** é escrito dentro do `onHud`. O `useEffect` de
`GamePanel.tsx:355-379` continua sendo o dono exclusivo do texto de cena
(`sceneAnnouncement`). Acrescente:

- `const [castAnnouncement, setCastAnnouncement] = useState('')`;
- `const castKey = (cast ?? []).map((m) => m.id).join('|')` (membro `null` vira
  chave sentinela distinta de `''`, que é o elenco vazio);
- um `useEffect` próprio, com dependência `[castKey]`, guardando o valor anterior
  num `useRef` no mesmo padrão do `prevAnnounceRef` já existente: primeira
  passagem só registra; `castKey` igual → não escreve nada; diferente →
  `setCastAnnouncement(t('game.cast.announce', { characters }))`, com os nomes
  juntados por `, ` e `game.cast.empty` como `{characters}` quando a lista está
  vazia;
- no início de `runTurn` (`GamePanel.tsx:220`), zere os dois
  (`setSceneAnnouncement('')`, `setCastAnnouncement('')`), para que a fala de um
  turno nunca carregue a frase do turno anterior;
- a região live existente (`GamePanel.tsx:519`) renderiza
  `[sceneAnnouncement, castAnnouncement].filter(Boolean).join(' ')`.

Nenhuma região nova: duas regiões concorrendo no mesmo turno viram fala
sobreposta. O fraseado distinto (`Agora em cena`, contra `Em cena` do anúncio de
cena, que descreve sprites com emoção) deixa claro que são duas informações
diferentes numa fala só, por exemplo:
`"Cena: praça. Em cena: Aiko (feliz). Agora em cena: Aiko, Cydonia."`

Como o `castKey` deriva do estado que só muda no `onHud`, o anúncio dispara no
fim do turno, nunca a cada delta.

### Acessibilidade

- Container: `<div className="cast" role="group" aria-label={t('game.cast.regionLabel')}>`,
  com `aria-busy="true"` durante o stream. **Não** é live region.
- Rótulo visível `game.cast.label` dentro do grupo, com `aria-hidden="true"` para
  não duplicar o `aria-label` do grupo.
- Chips são `<span>`, sem `tabindex` e sem `role`. A ordem de foco da tela
  (voltar → toggle de arte → histórico → textarea → enviar) fica inalterada.
- Estado vazio é texto real (`Ninguém`), não ausência de conteúdo, para que o
  leitor de tela encontre algo ao navegar pelo grupo.
- Contraste: chip normal usa `var(--hud-value)` sobre `var(--surface)`; chip
  vazio usa `var(--hud-label)` — ambos já validados no HUD atual.

### Visual e responsividade (`cast.css`)

Reuso, não invenção:
- linha grudada no HUD: mesmo `background` e `border-bottom` de `.hud`,
  `position: sticky` logo abaixo dele;
- rótulo no estilo `.hud__field dt` (`0.75rem`, `var(--hud-label)`);
- chips com o tratamento de pílula de `.game-stage-toggle button`
  (`border-radius: 999px`, `border: 1px solid #33363f`,
  `background: var(--surface)`, `font-size: 0.75rem`), porém não interativos;
- `display: flex; flex-wrap: wrap; gap: 4px 6px` — os chips quebram linha, sem
  corte e sem scroll horizontal em 320px;
- padding `8px 16px` (igual ao do HUD); `4px 16px` abaixo de 480px, regra
  própria do CastRow (o HUD não muda padding no breakpoint);
- `@media (max-width: 479px)`: rótulo em linha própria
  (`flex-direction: column; align-items: flex-start`), acompanhando o breakpoint
  que o HUD já usa;
- nome longo: `max-width: 12ch` no chip, com
  `overflow: hidden; text-overflow: ellipsis; white-space: nowrap` e `title` com o
  nome completo (mesmo padrão de `.hud__field dd`);
- sem cap de quantidade e sem chip "+N": elenco de cena é pequeno por construção
  e a quebra de linha resolve; um cap esconderia justamente a informação do
  ticket;
- `@media (max-height: 520px)`: a linha **permanece** (é texto barato); só o
  palco de sprites some, como já acontece hoje;
- sem animação além de `opacity`, dentro de
  `@media (prefers-reduced-motion: no-preference)`, como `hud.css` já faz.

### Tamanho

Um PR só: `CastRow.tsx` (~55 linhas), `cast.css` (~55), `strings.ts` (+10),
`GamePanel.tsx` (~35 de fiação) e os dois arquivos de teste enxutos (~120),
cerca de 275 linhas. Separar componente e fiação criaria um PR de componente sem
nenhum consumidor — foundation sem consumidor, que a regra proíbe.

## Contrato público

N/A — `CastRow` é usado só pelo `GamePanel`, no mesmo PR. Nenhum outro ticket
consome esta seção.

## Acceptance criteria

- [ ] Sessão recém-carregada mostra um chip por membro de `SessionDetail.cast`,
      na ordem do array.
- [ ] Evento `hud` com elenco diferente troca os chips e a live region passa a
      conter o texto de `game.cast.announce` uma única vez.
- [ ] Evento `hud` com o mesmo elenco não acrescenta anúncio de elenco.
- [ ] Evento `hud` **sem** `cast` mantém os chips anteriores.
- [ ] Turno em que nem a cena nem o elenco mudam deixa a live region vazia.
- [ ] `cast: []` mostra o chip `Ninguém` e anuncia `Agora em cena: Ninguém.`
- [ ] `cast === null` mostra `—` com `title` `game.cast.unavailable`.
- [ ] Durante o stream os chips anteriores continuam no DOM, com
      `aria-busy="true"`.
- [ ] Turno com erro não acrescenta texto de erro na linha; só o `hud.stale` já
      existente aparece.
- [ ] Membro com `name` vazio exibe o `id`.
- [ ] `cast.css` declara `flex-wrap: wrap` no container e `max-width: 12ch` com
      `text-overflow: ellipsis` no chip (é o que sustenta 320px sem corte e sem
      scroll horizontal, verificado no gate atual por inspeção do arquivo, já que
      não há E2E no projeto).
- [ ] A mesma linha aparece no preview do builder, sem código duplicado.
- [ ] `strings.en` e `strings['pt-br']` seguem com as mesmas chaves e nenhuma
      string literal de UI fora de `strings.ts`.
- [ ] `npm run check:web` verde.

## Cenários de teste

Suíte existente que muda de preparação (asserções preservadas):
- `frontend/src/components/GamePanel.test.tsx` — a fábrica `session()` já ganhou
  `cast: []` no TCK-050. Os testes que jogam um turno e mandam `{ hud: {...} }`
  no SSE continuam sem `cast`, o que agora exercita o caminho "inalterado".
  Nenhuma asserção existente muda, inclusive a do anúncio de cena, que segue
  saindo pela mesma região live.
- `frontend/src/components/Hud.test.tsx` e `frontend/src/i18n.test.ts` — não
  mudam; o teste de paridade de chaves passa a cobrir as chaves novas
  automaticamente.

Cenários novos (enxutos de propósito, um por comportamento que pode regredir):
- `CastRow.test.tsx` — feliz: lista com dois membros renderiza os dois nomes e o
  rótulo `game.cast.label`; borda: `cast={[]}` mostra `game.cast.empty`; borda:
  `cast={null}` mostra `hud.placeholder` com `title` `game.cast.unavailable`;
  borda: `busy` aplica `aria-busy="true"` e o container é `role="group"` com
  `aria-label`.
- `GamePanel.test.tsx` — feliz: `onHud` com elenco diferente atualiza os chips e
  a live region contém `game.cast.announce` uma vez só; borda: `onHud` sem `cast`
  mantém os chips anteriores; borda: durante o stream os chips anteriores seguem
  no DOM com `aria-busy="true"`.

## Rollout e kill switch

N/A — `risk: low`. A linha é texto barato, aditiva, sem estado persistido e sem
request novo. Com o TCK-055 ausente ou com o flag `director` desligado, ela
mostra o elenco estático do start, que é informação correta. Reverter é remover o
`<CastRow />` do `GamePanel`.

## Observabilidade

Eventos: nenhum no frontend (o projeto não emite telemetria de cliente). Os
eventos `director_applied` / `director_rejected` / `director_failed` do TCK-055
explicam, do lado do motor, por que o elenco mudou ou não.
Métrica de sucesso: jogar 5 turnos no exemplo vendo a linha acompanhar o elenco
do motor, sem nenhum turno em que os chips fiquem vazios no meio do stream.

## i18n

Chaves novas em `frontend/src/strings.ts`, no bloco `game.*` logo depois de
`game.scene.empty`, nos **dois** locales:

| chave | en | pt-br |
|---|---|---|
| `game.cast.label` | `In scene` | `Em cena` |
| `game.cast.empty` | `No one` | `Ninguém` |
| `game.cast.unavailable` | `Not known yet` | `Ainda não se sabe` |
| `game.cast.announce` | `Now in scene: {characters}.` | `Agora em cena: {characters}.` |
| `game.cast.regionLabel` | `Characters in scene` | `Personagens em cena` |

Reuso sem chave nova: `hud.placeholder` (estado 3) e `hud.stale` (estado 5). Nome
de personagem vem do backend e nunca passa por `t()`.
