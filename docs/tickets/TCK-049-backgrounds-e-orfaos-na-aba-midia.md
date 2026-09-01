---
id: TCK-049
title: Gerenciar backgrounds e sprites orfaos na aba Midia
status: in_review
points: 3
blockedBy: [TCK-039]
files:
  - frontend/src/components/builder/MediaTab.tsx
  - frontend/src/components/builder/MediaTab.test.tsx
  - frontend/src/components/builder/media.css
  - frontend/src/strings.ts
migration: false
ui: true
risk: medium
---

## Problema

A aba Mídia (TCK-039) cobre sprites e ignora duas coisas que a spec cobra:

1. `[BG:location]` não tem onde receber imagem — sem backgrounds, metade da
   camada visual da fase não existe;
2. arquivo que está na pasta mas cuja emoção o personagem não declara é
   invisível para o jogo **e** para a tela. Arquivo invisível é arquivo que a
   pessoa vai procurar por meia hora.

## Escopo

Dentro:
- Seção de backgrounds: grid 16:9, lista de locais semeada pelos starts,
  adicionar e remover espaço.
- Faixa de sprites órfãos por personagem, com "declarar" e "remover".
- Sumário do topo passando a contar também os espaços de background.
- Chaves i18n de backgrounds e órfãos.

Fora (explícito):
- Qualquer mudança na célula de sprite ou no upload (TCK-039) além de
  reaproveitá-los.
- Mapear background para o local do HUD automaticamente — quem troca o fundo em
  jogo é a tag `[BG:]` (TCK-042), e quem troca o local do HUD é `[LOC:]`
  (TCK-027). São coisas separadas de propósito.
- Geração de imagem (Fase 5).

## Comportamento esperado

Abaixo dos sprites, um grid de backgrounds com um espaço por local. Os locais
vêm dos `hud.location` dos starts, slugificados, mais o que já existir em
`media/backgrounds/`. Dá para acrescentar um local que ainda não apareceu em
start nenhum, e remover um espaço vazio que não veio de start.

Ao final de cada bloco de personagem, se houver arquivo sem emoção declarada,
uma faixa mostra os órfãos com duas saídas: declarar a emoção (vai para o
rascunho, marca dirty) ou apagar o arquivo.

## Detalhes técnicos

### Backgrounds

Grid de células 16:9 (`repeat(auto-fill, minmax(200px, 1fr))`), reaproveitando o
componente de célula do TCK-039 com as chaves `builder.media.bg.alt`,
`builder.media.bg.upload` e `builder.media.bg.remove`, e os mesmos estados
(vazio, enviando, preenchido, erro).

A lista de locais é a união de:

- `slugify(start.hud.location)` de **todos** os starts do rascunho — use a
  `slugify` exportada pelo TCK-045, não escreva outra; e
- as chaves de `index.backgrounds` (o que já está no disco).

Célula semeada por um start e ainda sem arquivo mostra
`builder.media.bg.fromStart` com `{start}` — explica de onde veio a linha.

Botão `builder.media.backgrounds.add` abre um campo de slug
(`builder.media.backgrounds.addLabel`/`.addHint`), reaproveitando
`builder.field.slugInvalid` e `builder.field.slugTaken` (TCK-037). Slug que não
é local de nenhum start e não tem arquivo pode ser removido da lista com
`builder.media.backgrounds.removeSlot` — não apaga nada no disco, porque não há
nada; é só estado de UI da aba.

O upload usa `kind: 'background'` e `key: slug`, **sem** `character` (o backend
recusa com 422 se vier, TCK-044).

### Órfãos

Para cada personagem, compare `index.sprites[folder]` (chaves do disco) com as
emoções declaradas no rascunho. As chaves que sobram são órfãs e vão numa faixa
ao final do bloco, com `builder.media.sprites.orphans.title`/`.body`, miniatura,
o nome do arquivo e duas ações:

- `builder.media.sprites.orphans.declare` com `{emotion}` — acrescenta a emoção
  ao personagem no rascunho via `onChange` do `TabProps` e marca dirty; a célula
  migra do bloco de órfãos para o grid na mesma renderização;
- `common.remove` — usa o mesmo diálogo e o mesmo `deleteMedia` da célula
  normal.

Pasta de sprites que não pertence a nenhum personagem (ex.: personagem
deletado) também é órfã, mas não tem onde declarar: liste-a numa faixa própria
no fim da seção de sprites, com o mesmo texto de corpo e só a ação de remover.

### Sumário

`builder.media.summary` passa a contar `{filled}`/`{total}` somando espaços de
sprite declarados e espaços de background da lista. Órfão **não** entra na
conta: ele não é espaço, é sobra.

### Responsividade

<480px: uma coluna de background, rótulo abaixo da thumb, alvos de 44px.

## Contrato público

N/A — a aba é consumidora do `TabProps` (TCK-036), do índice de mídia (TCK-039),
do cliente de mídia (TCK-037) e da `slugify` (TCK-045).

## Acceptance criteria

- [ ] Backgrounds são semeados pelos `hud.location` de todos os starts,
      slugificados, com `builder.media.bg.fromStart`.
- [ ] Local que só existe no disco também aparece no grid.
- [ ] Adicionar local com slug inválido ou repetido mostra a mensagem certa e
      não cria o espaço.
- [ ] Remover espaço vazio que não veio de start tira a célula sem chamar a API.
- [ ] Upload de background manda `kind=background` sem `character`.
- [ ] Arquivo com emoção não declarada aparece na faixa de órfãos.
- [ ] "Declarar" acrescenta a emoção ao personagem, marca dirty e a célula migra
      para o grid.
- [ ] Pasta de sprites sem personagem correspondente aparece com só a ação de
      remover.
- [ ] O sumário conta sprites e backgrounds, e não conta órfãos.
- [ ] `strings.en` e `strings['pt-br']` seguem com as mesmas chaves.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente que muda de preparação: `MediaTab.test.tsx` (TCK-039) ganha
casos; as asserções existentes ficam como estão — backgrounds e órfãos são
conteúdo adicional. Se algum teste do TCK-039 afirmar o total do sumário, ele é
adaptado na **preparação** (fixture sem background, para o total continuar o
mesmo), nunca no que afere.

Cenários novos:
- Feliz: dois starts com locais diferentes semeiam dois espaços.
- Feliz: upload de background preenche a célula e anuncia.
- Feliz: órfão `mocking` com "declarar" chama `onChange` com a emoção nova.
- Borda: start com `hud.location` acentuado (`pátio da escola`) vira
  `patio-da-escola`.
- Borda: dois starts com o mesmo local geram um espaço só.
- Borda: adicionar slug já existente mostra `builder.field.slugTaken`.
- Borda: remover espaço vazio semeado por start não é oferecido.
- Borda: pasta de sprites órfã inteira aparece com só "remover".
- Falha: upload de background 500 mostra `builder.media.error.write` só naquela
  célula.

## Rollout e kill switch

Com `flags.builder: false`, upload e remoção respondem 503 e a célula mostra
`builder.media.error.disabled`; a leitura continua. `risk: medium` por apagar
arquivo do disco sem undo — mitigado pelo diálogo com o caminho exato, herdado
do TCK-039.

## Observabilidade

Eventos: nenhum no frontend; o backend emite `media_uploaded` e `media_removed`
(TCK-044).
Métrica de sucesso: subir um background do pátio e vê-lo aparecer no preview
quando o narrador emitir `[BG:patio-da-escola]`.

## i18n — chaves novas

| chave | en | pt-br |
|---|---|---|
| `builder.media.sprites.orphans.title` | `Files with no matching emotion` | `Arquivos sem emoção correspondente` |
| `builder.media.sprites.orphans.body` | `These images are in the folder but the character doesn't declare the emotion. The game never shows them.` | `Estas imagens estão na pasta mas o personagem não declara a emoção. O jogo nunca as mostra.` |
| `builder.media.sprites.orphans.declare` | `Declare {emotion}` | `Declarar {emotion}` |
| `builder.media.sprites.orphans.folderTitle` | `Folders with no character` | `Pastas sem personagem` |
| `builder.media.backgrounds.heading` | `Backgrounds` | `Backgrounds` |
| `builder.media.backgrounds.add` | `Add a location` | `Adicionar um local` |
| `builder.media.backgrounds.addLabel` | `Location key` | `Chave do local` |
| `builder.media.backgrounds.addHint` | `Becomes media/backgrounds/{slug}.png and matches [BG:{slug}].` | `Vira media/backgrounds/{slug}.png e casa com [BG:{slug}].` |
| `builder.media.backgrounds.removeSlot` | `Remove the empty slot {location}` | `Remover o espaço vazio {location}` |
| `builder.media.bg.alt` | `Background of {location}` | `Background de {location}` |
| `builder.media.bg.upload` | `Upload the background for {location}` | `Enviar o background de {location}` |
| `builder.media.bg.remove` | `Remove the background of {location}` | `Remover o background de {location}` |
| `builder.media.bg.fromStart` | `Location of the start {start}` | `Local do start {start}` |
