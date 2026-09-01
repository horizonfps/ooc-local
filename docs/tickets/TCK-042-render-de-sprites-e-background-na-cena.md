---
id: TCK-042
title: Renderizar sprites e background a partir das tags do turno
status: ready
points: 5
blockedBy: [TCK-028, TCK-034, TCK-040, TCK-041]
files:
  - frontend/src/scene.ts
  - frontend/src/scene.test.ts
  - frontend/src/components/GamePanel.tsx
  - frontend/src/components/GamePanel.test.tsx
  - frontend/src/components/TurnText.tsx
  - frontend/src/components/stage.css
  - frontend/src/api.ts
  - frontend/src/strings.ts
  - scenarios/exemplo-escola/media/sprites/chloe/default.png
  - scenarios/exemplo-escola/media/sprites/chloe/sad.png
  - scenarios/exemplo-escola/media/backgrounds/patio-da-escola.png
migration: false
ui: true
risk: medium
---

## Problema

`[SPRITE:chloe:sad]` e `[BG:patio]` são parseadas desde a Fase 1 e jogadas fora.
O manifesto de assets já viaja com a sessão (TCK-034) e o banco de imagens já é
alimentável pela aba Mídia (TCK-039/TCK-049). Falta o último elo: transformar a
sequência de tags do turno em estado de cena e desenhar.

É a parte final do critério de verde da fase: "jogo 5 turnos no preview com
sprite trocando de emoção".

`blockedBy` explica cada dependência: TCK-028 (edita `TurnText.tsx`, que este
ticket também toca para exportar um helper), TCK-034 (o manifesto), TCK-040 (o
`GamePanel`), TCK-041 (último ticket a editar `GamePanel.tsx`, `api.ts` e
`strings.ts` antes deste — dependência de colisão de arquivo).

## Escopo

Dentro:
- `frontend/src/scene.ts`: redutor de cena puro (tags → `SceneState`) e
  resolução de asset contra o manifesto.
- Camada de background e faixa de sprites dentro do `GamePanel` (vale no jogo e
  no preview, porque os dois usam o mesmo painel).
- Exportar `findUnclosedBracket` do `TurnText` (hoje privada) para o redutor
  reusar durante o stream.
- `SessionAssets` e o campo `assets` em `SessionDetail`, no `api.ts`.
- Toggle de arte dentro do painel, com preferência em `localStorage`.
- Anúncio de mudança de cena para leitor de tela.
- Sprites e background de exemplo em `scenarios/exemplo-escola/`.
- Chaves i18n da cena.

Fora (explícito):
- `[SCENE:...]` e geração ao vivo (Fases 5 e 7).
- `[STAT:...]`, que continua parseada e ignorada (Fase 3).
- `[LOC:...]`, que muda o HUD e não a arte (TCK-027).
- Qualquer estado de erro visível de mídia na tela de jogo — asset faltando é
  assunto da aba Mídia, não do jogo.
- Mexer no `GameScreen` ou no `game.css`: o toggle **não** vai para a topbar de
  rota (ver decisão abaixo), então nenhum dos dois é tocado.

## Comportamento esperado

Enquanto o turno chega, a cena acompanha: a tag fecha no texto parcial e o
sprite ou o fundo já mudam. Se não houver imagem nenhuma no cenário, a tela é
**pixel a pixel** a da Fase 1 — nada de layout que abre buraco esperando asset.

Emoção sem arquivo cai no `default`; personagem sem arquivo nenhum faz a tag ser
ignorada. Background sem arquivo mantém o último válido.

## Detalhes técnicos

### Onde fica o toggle (correção de contrato)

O TCK-040 estabelece que a topbar (voltar + nome do cenário) fica no
`GameScreen` e que o `GamePanel` **não tem topbar**. Portanto o toggle de arte
**não** vai para a topbar: ele é um botão dentro do próprio painel, numa barra
fina `div.game-stage-toggle` acima da faixa de sprites, com `aria-pressed`. É o
único lugar que funciona nos dois contextos — no jogo e no preview do builder —,
e é justamente no builder que ele mais serve, para o autor comparar com e sem
arte.

### Redutor de cena

```ts
export type SceneState = {
  background: string | null                              // location key
  sprites: { character: string; emotion: string }[]      // ordem de aparição
}
export const MAX_SPRITES = 3
export const EMPTY_SCENE: SceneState
export function reduceScene(state: SceneState, text: string): SceneState
```

- Lê as **mesmas** tags do `TAG_RE` já exportado por
  `components/TurnText.tsx` (importe de lá; duplicar o regex seria o erro que o
  comentário de contrato daquele arquivo previne).
- Estado acumulado do prólogo até o último turno; cada turno aplica suas tags por
  cima do anterior; turno sem tag não muda nada.
- `[BG:location]` substitui o background.
- `[SPRITE:char:emotion]` define/atualiza a emoção daquele personagem e o
  **promove ao fim da fila**; acima de `MAX_SPRITES`, o mais antigo sai.
- Tag com forma inválida (argumento vazio, três partes) é ignorada em silêncio,
  igual à Fase 1 e ao `_validate` do backend.
- Durante o stream, tag incompleta (`[SPRIT`) é ignorada: trunque o texto em
  `findUnclosedBracket(text)` antes de reduzir. Essa função existe em
  `TurnText.tsx` e é privada — **exporte-a** (`export function
  findUnclosedBracket`), sem mudar o corpo. É a única alteração no arquivo, e é
  por isso que ele está em `files` e o ticket depende do TCK-028, que também o
  edita.
- Chaves normalizadas com `trim()` + `toLowerCase()`.

Recompute a cena como derivação do histórico (`useMemo` sobre prólogo + turnos +
texto parcial). Estado acumulado por efeito divergiria ao trocar de sessão;
derivar é mais simples e o volume de texto é pequeno.

### Resolução de asset

```ts
export function resolveSprite(assets: SessionAssets, character: string, emotion: string): string | null
export function resolveBackground(assets: SessionAssets, location: string): string | null
```

Ordem, exatamente como a spec pede:
1. `assets.sprites[char][emotion]` → usa;
2. `assets.sprites[char]['default']` → usa;
3. personagem sem asset nenhum → `null`, tag ignorada, nada renderizado.

Background: `assets.backgrounds[location]`; ausente → mantém o último válido; se
nunca houve nenhum, o fundo permanece `--bg`. Tudo no cliente a partir do
manifesto, **sem request por tag**.

### Tipos no api.ts

O TCK-034 declara o manifesto só no pydantic. Aqui o `api.ts` ganha:

```ts
export type SessionAssets = {
  sprites: Record<string, Record<string, string>>
  backgrounds: Record<string, string>
}
// SessionDetail ganha: assets: SessionAssets
```

Como o backend sempre devolve os dois dicionários (nunca `null`), o campo é
obrigatório no tipo; os fixtures de teste existentes passam a incluí-lo.

### Render

Background: `div.game-stage-bg`, `position: absolute; inset: 0; z-index: 0`,
`background-size: cover`, `background-position: center`, `aria-hidden="true"`.
Sobre ela, um véu (`linear-gradient` com `--bg` em ~80% de opacidade) que
garante o contraste do texto por construção. Transição de 200ms em `opacity`; a
regra global de `prefers-reduced-motion` do `index.css` já zera a duração.

Sprites: faixa `div.game-stage-sprites` acima do histórico, altura
`clamp(96px, 18vh, 180px)`, alinhados à base, `object-fit: contain`. Sem nenhum
sprite resolvido, a faixa **não é renderizada** (não ocupa altura). Cada `<img>`
com `alt` = `game.sprite.alt` (`{character}`, `{emotion}`), `loading="lazy"`,
`decoding="async"` e fade de 150ms na entrada, sem movimento lateral. `onError`
(arquivo sumiu do disco entre o load e o turno): o sprite é descartado e a tag
passa a ser ignorada — sem ícone quebrado, sem mensagem. Como a cena é derivada,
guarde as URLs quebradas num `useState<Set<string>>` e filtre por ele.

A faixa não é focável e não entra na ordem de tab.

### Anúncio

Mudança de cena vai para a região `aria-live="polite"` que o `GamePanel` já tem
(a do `game.turn.done`): `game.scene.announce` com `{background}` e
`{characters}`; quando só um dos dois muda,
`game.scene.announceBackground` ou `game.scene.announceCharacters`. Cada
personagem formatado com `game.scene.characterEmotion`; lista vazia usa
`game.scene.empty`.

### Toggle de arte

Botão `div.game-stage-toggle > button` com `aria-pressed`, alternando
`game.stage.hide` / `game.stage.show`. Desligado: sem background, sem faixa,
texto puro. Preferência em `localStorage` sob `ooc-local:stage`, lida **antes do
primeiro paint** (inicializador do `useState`, não `useEffect`) para não piscar.
`localStorage` indisponível não pode quebrar a tela: leitura e escrita em
`try/catch`.

### Responsividade

≥720px até 3 sprites lado a lado; <720px até 2, altura
`clamp(80px, 14vh, 120px)`; <480px até 1 (o mais recente); em qualquer largura,
`@media (max-height: 520px)` omite a faixa — teclado aberto no celular não pode
comer o texto do turno.

### Cenário exemplo

Regra 3 do plano ("se a feature não aparece no cenário exemplo, ela não
existe"): adicione um sprite `default` e um `sad` para a Chloe e um background
do pátio, como PNGs pequenos de cor sólida (não é arte final; é fixture
visível). O background usa o slug do `hud.location` do start
(`patio-da-escola`), que é o que a aba Mídia semeia. A Chloe já declara
`emotions: [default, sad, angry, smile]` desde o TCK-029 e o campo `sprite` é
ausente (a pasta é o id), então nenhum YAML muda.

## Contrato público

```ts
// frontend/src/scene.ts
export type SceneState = { background: string | null; sprites: { character: string; emotion: string }[] }
export const MAX_SPRITES: number
export const EMPTY_SCENE: SceneState
export function reduceScene(state: SceneState, text: string): SceneState
export function resolveSprite(assets: SessionAssets, character: string, emotion: string): string | null
export function resolveBackground(assets: SessionAssets, location: string): string | null

// frontend/src/components/TurnText.tsx
export function findUnclosedBracket(text: string): number   // passa a ser exportada

// frontend/src/api.ts
export type SessionAssets
// SessionDetail ganha assets: SessionAssets
```

Nenhum outro ticket da fase consome esta seção.

## Acceptance criteria

- [ ] `[BG:patio]` troca o fundo; `[SPRITE:chloe:sad]` mostra o sprite `sad`.
- [ ] Emoção sem arquivo mostra o `default` do personagem.
- [ ] Personagem sem asset nenhum não renderiza nada e não deixa buraco.
- [ ] Quarto sprite empurra o mais antigo para fora.
- [ ] Cenário sem imagem nenhuma renderiza exatamente como na Fase 1.
- [ ] Durante o stream, a cena muda assim que a tag fecha no texto parcial.
- [ ] `onError` de uma imagem descarta o sprite sem mostrar erro.
- [ ] O toggle desliga a arte, persiste em `localStorage` e não pisca ao
      recarregar.
- [ ] A mudança de cena é anunciada na região live existente.
- [ ] O mesmo comportamento aparece no preview do builder, sem código
      duplicado.
- [ ] `strings.en` e `strings['pt-br']` seguem com as mesmas chaves.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente que muda de preparação (asserções preservadas):
`GameScreen.test.tsx`, `GamePanel.test.tsx` e `BuilderPreview.test.tsx` — as
sessões mockadas passam a ter `assets: { sprites: {}, backgrounds: {} }`, que é
**mudança de preparação** (o fixture ganha um campo exigido pelo tipo); a
asserção de cada teste continua a mesma. O teste
`filters inline tags out of streamed deltas` continua válido: a tag some do
texto e agora também alimenta a cena; não altere a asserção dele, acrescente um
teste novo para o efeito visual. `TurnText.test.tsx` não muda: exportar
`findUnclosedBracket` não altera comportamento.

Cenários novos:
- `scene.test.ts` — feliz: sequência de turnos com `[BG:]` e `[SPRITE:]` produz
  o `SceneState` esperado; borda: quarto sprite remove o mais antigo; borda:
  mesma personagem com emoção nova atualiza e promove ao fim da fila; borda:
  turno sem tag preserva o estado; borda: `[SPRIT` no fim do texto parcial é
  ignorado; borda: `[SPRITE:chloe:]` e `[SPRITE:a:b:c]` são ignoradas; borda:
  `[SPRITE:CHLOE:Sad]` casa em minúsculas; feliz: `resolveSprite` cai no
  `default`; borda: `resolveSprite` devolve `null` para personagem desconhecido;
  borda: `resolveBackground` ausente mantém o anterior.
- `GamePanel.test.tsx` — feliz: sessão com `assets` e turno com `[BG:]` e
  `[SPRITE:]` renderiza a camada de fundo e a `<img>` com o `alt` interpolado;
  borda: sessão sem asset não renderiza faixa nem camada; borda: disparar
  `error` na `<img>` remove o sprite; feliz: toggle esconde a arte e grava a
  preferência; borda: `localStorage` que lança erro não quebra a tela; feliz: o
  anúncio de cena aparece na região live.

## Rollout e kill switch

O toggle de arte (`ooc-local:stage`, ligado por default) é o kill switch de
usuário: desligado, a tela volta a ser a da Fase 1, sem deploy e sem flag de
servidor. `risk: medium` porque a camada visual entra por baixo do texto do
jogo; o véu de contraste e a omissão total da faixa quando não há asset são as
mitigações.

## Observabilidade

Eventos: nenhum no frontend. No backend, `session_assets` (TCK-034) já diz
quantos arquivos o cenário tem.
Métrica de sucesso: jogar 5 turnos vendo o sprite trocar de emoção pelo menos
uma vez, sem nenhuma imagem quebrada na tela.

## i18n — chaves novas

| chave | en | pt-br |
|---|---|---|
| `game.sprite.alt` | `{character}, {emotion}` | `{character}, {emotion}` |
| `game.stage.hide` | `Hide the artwork` | `Esconder a arte` |
| `game.stage.show` | `Show the artwork` | `Mostrar a arte` |
| `game.scene.announce` | `Scene: {background}. On screen: {characters}.` | `Cena: {background}. Em cena: {characters}.` |
| `game.scene.announceBackground` | `Scene: {background}.` | `Cena: {background}.` |
| `game.scene.announceCharacters` | `On screen: {characters}.` | `Em cena: {characters}.` |
| `game.scene.characterEmotion` | `{character} ({emotion})` | `{character} ({emotion})` |
| `game.scene.empty` | `no one` | `ninguém` |
