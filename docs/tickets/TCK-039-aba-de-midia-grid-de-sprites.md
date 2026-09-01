---
id: TCK-039
title: Subir sprites por personagem e emocao na aba Midia
status: in_review
points: 3
blockedBy: [TCK-032, TCK-036, TCK-037, TCK-048]
files:
  - frontend/src/components/builder/MediaTab.tsx
  - frontend/src/components/builder/MediaTab.test.tsx
  - frontend/src/components/builder/media.css
  - frontend/src/api.ts
  - frontend/src/strings.ts
migration: false
ui: true
risk: medium
---

## Problema

A API de mídia existe (TCK-032 lê, TCK-044 escreve) e as emoções são declaradas
nos personagens (TCK-048), mas não há tela para subir sprite. Sem ela, o banco
de imagens do cenário continua sendo `cp` na mão — e o critério de verde da fase
("sprites soltos de teste, sprite trocando de emoção no preview") não fecha.

Este ticket entrega a aba com o **grid de sprites**. Backgrounds e a faixa de
órfãos são o TCK-049, quebrado por tamanho.

## Escopo

Dentro:
- Aba Mídia: carregamento do índice, sumário, hint do topo e um bloco de grid
  por personagem, com upload, troca e remoção por célula.
- `fetchMediaIndex` em `api.ts` (o `uploadMedia`/`deleteMedia` vem do TCK-037).
- Drag and drop sobre a célula, com equivalente por teclado.
- Chaves i18n do grid de sprites.

Fora (explícito):
- Backgrounds, faixa de órfãos e o botão de adicionar local (TCK-049).
- Capa (aba Identidade, TCK-037).
- Geração de imagem, fila, estúdio de personagem, ComfyUI (Fase 5).
- Declarar emoção nova (é do TCK-049, junto com os órfãos, e da aba Personagens).

## Comportamento esperado

A aba mostra quantos espaços estão preenchidos de quantos. Cada personagem tem
uma linha de células, uma por emoção declarada, `default` primeiro. Célula vazia
recebe upload; célula cheia mostra a miniatura e permite trocar ou remover.

Imagem é gravada **no disco na hora**, fora do botão de salvar. A aba diz isso
uma vez, no topo (`builder.media.hint`) — misturar "salvar YAML" com "escrever
PNG" num botão só é a fonte previsível de arquivo órfão.

## Detalhes técnicos

Carregamento: `GET /api/builder/scenarios/{id}/media` na montagem da aba, com
estado próprio de carregando/erro (o shell não carrega mídia). Depois de cada
upload ou remoção, atualize o índice em memória a partir da resposta, sem refazer
o GET inteiro.

Layout: hint no topo, sumário em `role="status"` com `builder.media.summary`
(`{filled}`/`{total}`, contando só espaços de sprite neste ticket) e a seção
`builder.media.sprites.heading`. O TCK-049 acrescenta a seção de backgrounds
abaixo e passa a somar os espaços dela no mesmo sumário — deixe a contagem numa
função isolada para ele estender.

### Sprites

Uma `<section>` por personagem do rascunho, com `h3` = nome e a pasta de destino
em `--fg-muted` (`builder.media.sprites.folder` com `{folder}` =
`character.sprite || id`). Dentro, `ul role="list"` de células, uma por emoção
declarada, `default` primeiro e depois a ordem do YAML.

Célula:
- thumb quadrada (`object-fit: contain`, fundo `--surface`), `alt` =
  `builder.media.sprite.alt` com `{character}` e `{emotion}`;
- rótulo textual da emoção — valor cru do YAML, é chave de arquivo;
- upload ocupando a célula inteira: `<label>` envolvendo um `input[type=file]`
  visualmente escondido mas **focável** (foco visível na célula via
  `:focus-within`), com nome acessível completo (`builder.media.sprite.upload`
  com personagem e emoção);
- botão de remover no canto quando há asset, com `builder.media.sprite.remove`.

Estados da célula: **vazio** (moldura tracejada + `builder.media.cell.empty`; na
célula `default`, `builder.media.cell.emptyDefault`, porque sem ele toda tag
daquele personagem é ignorada), **enviando** (`aria-busy="true"`, thumb com
opacidade reduzida, `builder.media.cell.uploading`, botão desabilitado),
**preenchido** (thumb + remover, `title` com o nome do arquivo) e **erro**
(mensagem inline `role="alert"` na própria célula, com `common.retry`; erro numa
célula nunca derruba o grid).

Personagem só com `default`: hint `builder.media.sprites.addEmotions` com link
para a aba Personagens via `goToTab` (troca interna, não passa pelo guard).
Nenhum personagem: `EmptyState` com `builder.media.sprites.empty.title`/`.body`
e ação levando à aba Personagens.

Nenhuma imagem em lugar nenhum: `EmptyState` `builder.media.empty.title`/`.body`
acima do grid, **sem escondê-lo** — o texto diz que o jogo é texto-first e que
tag sem asset é ignorada, para a pessoa saber que pode simplesmente jogar assim.

### Upload

- `accept="image/png,image/jpeg,image/webp"` no input + checagem de `file.type`
  e `file.size` (8 MB) no cliente antes de enviar; a validação que vale é a do
  backend.
- O nome do arquivo de destino é ditado pelo espaço, nunca pelo nome de origem.
- Substituir espaço preenchido sobrescreve sem confirmação (é troca de imagem,
  reversível por outro upload) e anuncia `builder.media.replaced`.
- Erros: mapeamento e chaves do TCK-037 (`builder.media.error.type|size|write|
  disabled|removeFailed`), nunca redeclarados aqui.
- Drag and drop sobre a célula (`dragover` destaca; `drop` usa
  `event.dataTransfer.files[0]`), com `preventDefault` no `dragover`, senão o
  browser abre o arquivo. O `input[type=file]` continua sendo o caminho
  equivalente por teclado.
- Cache: depois de trocar a imagem de um espaço a URL é a mesma; acrescente
  `?t=<Date.now()>` na URL do `<img>` após cada upload.

Remoção: diálogo pequeno `builder.media.remove.title`/`.body` com `{path}`
concreto + `common.cancel`/`common.remove`. Remoção é imediata no disco, sem
undo, e anuncia `builder.media.removed`.

Anúncios (`builder.media.uploaded`/`.replaced`/`.removed`) vão para uma região
`aria-live="polite"` única da aba, separada da região do shell.

### API

```ts
export type MediaIndex = { cover: string | null
                           sprites: Record<string, Record<string, string>>
                           backgrounds: Record<string, string> }
export function fetchMediaIndex(id: string): Promise<MediaIndex>
```

### Responsividade

`grid-template-columns: repeat(auto-fill, minmax(120px, 1fr))`; <480px duas
colunas, rótulo abaixo da thumb, botão de remover em linha própria (para não
competir com o alvo de toque do upload), alvos de 44px.

## Contrato público

```ts
// frontend/src/api.ts
export type MediaIndex
export function fetchMediaIndex(id: string): Promise<MediaIndex>
```

Consumidor: TCK-049 (acrescenta backgrounds e órfãos usando o mesmo índice e a
mesma célula).

## Acceptance criteria

- [ ] O grid mostra uma célula por emoção declarada, com `default` primeiro.
- [ ] Upload numa célula grava e a miniatura aparece sem recarregar a página.
- [ ] Substituir a imagem mostra a nova (sem imagem de cache).
- [ ] Remover apaga o arquivo depois da confirmação e a célula volta a vazia.
- [ ] Tipo não suportado é recusado no cliente, sem requisição.
- [ ] Erro numa célula não afeta as outras.
- [ ] Personagem só com `default` mostra o hint com link para Personagens.
- [ ] Cenário sem personagem mostra o `EmptyState` com ação para Personagens.
- [ ] Todo input de arquivo tem nome acessível com personagem e emoção.
- [ ] `strings.en` e `strings['pt-br']` seguem com as mesmas chaves.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente do fluxo: **nenhuma**; `i18n.test.ts` cobre a paridade de chaves
sem alteração. Nenhuma asserção existente muda. Nos testes, construa `File` com
`new File([bytes], 'x.png', { type: 'image/png' })` e mocke `fetch` para as
rotas de mídia.

Cenários novos (`MediaTab.test.tsx`):
- Feliz: índice com um sprite → uma célula preenchida, as demais vazias, sumário
  `1 de N`.
- Feliz: upload manda `FormData` com `kind=sprite`, `key` e `character`; a
  célula fica preenchida e anuncia.
- Feliz: remover com confirmação manda DELETE e a célula volta a vazia.
- Borda: célula `default` vazia mostra `builder.media.cell.emptyDefault`.
- Borda: drop de arquivo na célula sobe o mesmo que o input.
- Borda: substituir anuncia `builder.media.replaced` e a URL ganha `?t=`.
- Falha: upload 413 mostra `builder.media.error.size` com retry só naquela
  célula.
- Falha: upload 503 mostra `builder.media.error.disabled`.
- Falha: `fetch` do índice rejeitando mostra `ErrorState` com retry, sem quebrar
  a aba.

## Rollout e kill switch

Com `flags.builder: false`, upload e remoção respondem 503 e a célula mostra
`builder.media.error.disabled`; a leitura do índice e as miniaturas continuam
funcionando. `risk: medium` por apagar arquivo do disco sem undo — mitigado pelo
diálogo que mostra o caminho exato.

## Observabilidade

Eventos: nenhum no frontend; o backend emite `media_uploaded`, `media_removed` e
`media_rejected` (TCK-044).
Métrica de sucesso: subir os sprites de teste de 2 NPCs pela aba e vê-los
aparecerem no preview no turno seguinte à troca de emoção.

## i18n — chaves novas

| chave | en | pt-br |
|---|---|---|
| `builder.media.heading` | `Media` | `Mídia` |
| `builder.media.hint` | `Images are written to disk the moment you upload them, outside the save button.` | `As imagens são gravadas no disco assim que você envia, fora do botão de salvar.` |
| `builder.media.summary` | `{filled} of {total} slots filled` | `{filled} de {total} espaços preenchidos` |
| `builder.media.empty.title` | `No images yet` | `Nenhuma imagem ainda` |
| `builder.media.empty.body` | `The game is text-first: a sprite or background tag with no image is simply ignored. Upload whenever you want.` | `O jogo é texto-first: tag de sprite ou background sem imagem é simplesmente ignorada. Envie quando quiser.` |
| `builder.media.sprites.heading` | `Sprites` | `Sprites` |
| `builder.media.sprites.folder` | `media/sprites/{folder}/` | `media/sprites/{folder}/` |
| `builder.media.sprites.empty.title` | `No characters to give sprites to` | `Nenhum personagem para receber sprite` |
| `builder.media.sprites.empty.body` | `Create a character first — the sprite grid comes from the emotions declared there.` | `Crie um personagem primeiro — o grid de sprites vem das emoções declaradas lá.` |
| `builder.media.sprites.addEmotions` | `Only default here. Declare more emotions in the Characters tab to get more slots.` | `Só o default aqui. Declare mais emoções na aba Personagens para ganhar mais espaços.` |
| `builder.media.cell.empty` | `Empty` | `Vazio` |
| `builder.media.cell.emptyDefault` | `Empty — without default this character shows no sprite at all.` | `Vazio — sem o default este personagem não mostra sprite nenhum.` |
| `builder.media.cell.uploading` | `Uploading…` | `Enviando…` |
| `builder.media.cell.upload` | `Upload an image` | `Enviar uma imagem` |
| `builder.media.cell.replace` | `Replace the image` | `Trocar a imagem` |
| `builder.media.sprite.alt` | `{character}, {emotion}` | `{character}, {emotion}` |
| `builder.media.sprite.upload` | `Upload the {emotion} sprite for {character}` | `Enviar o sprite {emotion} de {character}` |
| `builder.media.sprite.remove` | `Remove the {emotion} sprite of {character}` | `Remover o sprite {emotion} de {character}` |
| `builder.media.uploaded` | `{name} uploaded` | `{name} enviado` |
| `builder.media.replaced` | `{name} replaced` | `{name} trocado` |
| `builder.media.removed` | `{name} removed` | `{name} removido` |
| `builder.media.remove.title` | `Remove this image?` | `Remover esta imagem?` |
| `builder.media.remove.body` | `{path} is deleted from disk. There's no undo.` | `{path} é apagado do disco. Não tem como desfazer.` |
