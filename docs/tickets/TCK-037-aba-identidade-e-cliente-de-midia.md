---
id: TCK-037
title: Editar a identidade do cenario e subir a capa
status: done
points: 3
blockedBy: [TCK-029, TCK-036, TCK-044, TCK-046]
files:
  - frontend/src/components/builder/IdentityTab.tsx
  - frontend/src/components/builder/IdentityTab.test.tsx
  - frontend/src/builder/validate.ts
  - frontend/src/api.ts
  - frontend/src/strings.ts
migration: false
ui: true
risk: medium
---

## Problema

O shell do editor (TCK-036) tem abas com placeholder. A primeira delas é a
identidade do cenário — nome, tagline, descrição, tags, idioma e capa —, que é o
que aparece na lista e o que define o idioma dos prompts de sistema.

Este ticket também é o **dono do cliente de mídia no frontend**: `uploadMedia` e
`deleteMedia` em `api.ts` e as chaves `builder.media.error.*` nascem aqui,
porque a capa é o primeiro upload da fase. As abas de Mídia (TCK-039/TCK-049)
consomem os dois sem redeclarar nada — chave de i18n redeclarada quebraria o
`tsc -b`, já que `StringKey` deriva do objeto `en`.

## Escopo

Dentro:
- Aba Identidade: nome, tagline (com contador), descrição, tags em chips,
  idioma, capa por upload/remoção.
- `uploadMedia`, `deleteMedia` e `MediaTarget` em `api.ts`.
- Padrões de campo compartilhados pelas demais abas (documentados abaixo) e as
  chaves genéricas `builder.field.*` / `builder.detail.selected`.
- Regras de validação da identidade somadas a `validateDraft`.
- Chaves i18n de identidade e de erro de mídia.

Fora (explícito):
- Aba Mundo (TCK-047), Starts (TCK-038), Personagens (TCK-048), Mídia
  (TCK-039/TCK-049).
- Auto-generate por LLM em qualquer campo (Fase 8).
- Geração de capa (Fase 5): aqui é só upload.
- `fetchMediaIndex`, grid, órfãos — tudo isso é do TCK-039.

## Comportamento esperado

A pessoa preenche nome, tagline, descrição e tags, escolhe o idioma do cenário e
envia uma capa. A capa é gravada **na hora** (é binário, fora do ciclo de save
do YAML) e por isso **não** marca dirty; o resto entra no rascunho e vai no
save.

## Detalhes técnicos

### Padrões de campo (valem para TCK-047, 038 e 048)

- Todo campo é `<label>` explícito + controle; placeholder nunca é rótulo.
- Textarea longo cresce até um teto e depois rola (padrão do
  `.game-input-textarea`).
- Hint em `<p class="field-hint">` ligado por `aria-describedby`.
- Campo inválido: `aria-invalid="true"`, `aria-describedby` incluindo
  `<p role="alert" class="field-error">`, borda de erro **e** texto — cor nunca
  é o único sinal.
- Validação roda no blur e no save, nunca a cada tecla.
- Toda edição chama `onChange(next)` do `TabProps` (TCK-036); a aba não guarda
  estado do documento, só estado de UI.
- Contadores de caractere em `aria-live="polite"`, anunciando só perto do
  limite.

### Campos → `scenario.yaml`

| campo | controle | yaml | validação |
|---|---|---|---|
| Nome | input texto | `name` | obrigatório, ≤ 80 |
| Tagline | input texto | `tagline` | opcional, ≤ 120, contador a partir de 100 |
| Descrição | textarea markdown | `description` | opcional, ≤ 4000 |
| Tags | editor de chips | `tags` | cada tag ≤ 24, sem duplicata, máx. 12 |
| Idioma | select en / pt-br | `locale` | obrigatório |
| Capa | upload | `media/cover.*` | ver abaixo |

Campo opcional vazio vira `null` no rascunho (o backend omite do arquivo).

Tags: Enter e vírgula viram chip; Backspace no input vazio remove o último; cada
chip tem botão de remover com o nome da tag no `aria-label`. Duplicata **não** é
erro bloqueante: é ignorada com `builder.identity.tags.duplicate` numa região
polite. Vazio mostra o hint `builder.identity.tags.empty` (é campo, não lista —
não use `EmptyState`). Contêiner `role="list"`, chip `role="listitem"`.

Idioma: o hint `builder.identity.locale.hint` diz, com essas palavras, que muda
o idioma dos prompts de sistema e não o da interface — é a confusão previsível
aqui.

### Capa

Bloco com preview 3:4, botão de upload (`input file` com
`accept="image/png,image/jpeg,image/webp"`), botão de trocar e botão de remover.
Sem capa: placeholder com `builder.identity.cover.empty`. Durante o envio,
`aria-busy` no bloco e `builder.identity.cover.uploading`. O hint
`builder.identity.cover.hint` avisa que a capa é gravada na hora.

A URL de exibição vem da rota de serviço do TCK-032
(`/api/scenarios/{id}/media/cover.{ext}`), com a extensão devolvida pelo próprio
`uploadMedia`; ao montar a aba sem ter subido nada nesta sessão, tente
`.png`, `.jpg`, `.webp` no `onError`, como a lista faz (TCK-035), e caia no
placeholder. Depois de cada upload, acrescente `?t=<Date.now()>` na URL do
`<img>` para não mostrar a imagem antiga do cache.

Checagens no cliente antes de enviar: tipo em
`image/png|image/jpeg|image/webp` → senão `builder.media.error.type` sem
requisição; `file.size` acima de 8 MB → `builder.media.error.size` com
`{max}` = 8, também sem requisição.

Mapeamento de erro do servidor: 415 → `builder.media.error.type`; 413 →
`builder.media.error.size`; 500 → `builder.media.error.write`; 503 →
`builder.media.error.disabled`; remoção falhando →
`builder.media.error.removeFailed`; rede → `describeError`. Erro inline com
retry, sob `builder.identity.cover.error`.

### API de mídia (dono deste ticket)

```ts
export type MediaTarget = { kind: 'cover' | 'sprite' | 'background'; key: string; character?: string }
export function uploadMedia(id: string, target: MediaTarget, file: File): Promise<{ path: string; url: string }>
export function deleteMedia(id: string, target: MediaTarget): Promise<void>
```

`uploadMedia` monta `FormData` e **não** define `Content-Type` na mão (o browser
precisa gerar o boundary). `deleteMedia` responde 204: não passe pelo helper
`request<T>`, que faria `response.json()`.

### Validação somada a `validateDraft`

`ValidationError { tab: 'identity', field, label, message }` para: nome vazio ou
> 80; tagline > 120; descrição > 4000; tag > 24; mais de 12 tags.

### Responsividade

<900px campos em coluna única; <480px textareas menores, botões de largura
total, chips quebrando linha, alvos de 44px.

## Contrato público

```ts
// frontend/src/api.ts
export type MediaTarget
export function uploadMedia(id: string, target: MediaTarget, file: File): Promise<{ path: string; url: string }>
export function deleteMedia(id: string, target: MediaTarget): Promise<void>
```

As chaves genéricas `builder.field.*`, `builder.detail.selected` e
`builder.media.error.*` nascem aqui e são consumidas por TCK-047, 038, 048, 039
e 049 — nenhum deles as redeclara.

## Acceptance criteria

- [ ] Editar qualquer campo marca dirty e o valor sobrevive à troca de aba.
- [ ] Tag duplicada é ignorada com aviso, não com erro; a 13ª é recusada.
- [ ] Upload de capa grava na hora, mostra a miniatura nova e **não** marca
      dirty.
- [ ] Arquivo de tipo não suportado é recusado no cliente, sem requisição.
- [ ] 413/415/500/503 do servidor mostram cada um a sua mensagem.
- [ ] Remover a capa volta o bloco para o placeholder.
- [ ] Campo inválido tem `aria-invalid`, mensagem em `role="alert"` e borda de
      erro.
- [ ] `strings.en` e `strings['pt-br']` seguem com as mesmas chaves.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente do fluxo: **nenhuma** — não há teste de aba de builder hoje;
`i18n.test.ts::has the same keys in en and pt-br` cobre as chaves novas sem
alteração. Nenhuma asserção existente muda.

Cenários novos (`IdentityTab.test.tsx`, `fetch` mockado, `File` criado com
`new File([bytes], 'capa.png', { type: 'image/png' })`):
- Feliz: digitar o nome chama `onChange` com o rascunho novo.
- Feliz: Enter e vírgula criam chip; o botão remove.
- Feliz: upload de capa manda `FormData` com `kind=cover` e troca a miniatura.
- Borda: duplicata anunciada e não inserida.
- Borda: contador de tagline aparece em 100 e a validação bloqueia em 121.
- Borda: arquivo de 9 MB é recusado sem `fetch`.
- Falha: upload 413 mostra `builder.media.error.size` com retry.
- Falha: upload 503 mostra `builder.media.error.disabled`.
- Falha: `deleteMedia` 500 mostra `builder.media.error.removeFailed` e mantém a
  miniatura.

## Rollout e kill switch

Com `flags.builder: false`, o upload responde 503 e a aba mostra
`builder.media.error.disabled`; os campos de texto continuam editáveis, e é o
save (TCK-046) que avisa que nada será gravado. `risk: medium` por escrever
arquivo no disco a cada upload, sem confirmação — mitigado por ser um espaço só
(a capa), reversível por outro upload.

## Observabilidade

Eventos: nenhum no frontend; o backend emite `media_uploaded`, `media_removed` e
`media_rejected` (TCK-044).
Métrica de sucesso: subir uma capa e vê-la na lista de cenários depois de
recarregar.

## i18n — chaves novas

### Genéricas de campo

| chave | en | pt-br |
|---|---|---|
| `builder.field.required` | `This field is required.` | `Este campo é obrigatório.` |
| `builder.field.tooLong` | `Too long — {max} characters max.` | `Longo demais — máximo de {max} caracteres.` |
| `builder.field.counter` | `{count}/{max}` | `{count}/{max}` |
| `builder.field.slugInvalid` | `Use only lowercase letters, numbers and hyphens.` | `Use só letras minúsculas, números e hífens.` |
| `builder.field.slugTaken` | `{slug} is already used in this scenario.` | `{slug} já está em uso neste cenário.` |
| `builder.detail.selected` | `Editing {name}` | `Editando {name}` |

### Erros de mídia (compartilhados com TCK-039 e TCK-049)

| chave | en | pt-br |
|---|---|---|
| `builder.media.error.type` | `Only PNG, JPEG and WebP images.` | `Só imagens PNG, JPEG e WebP.` |
| `builder.media.error.size` | `Image is over {max} MB. Shrink it and try again.` | `A imagem passa de {max} MB. Reduza e tente de novo.` |
| `builder.media.error.write` | `The file wasn't written. Check that the media folder is writable.` | `O arquivo não foi escrito. Confira se a pasta media aceita escrita.` |
| `builder.media.error.removeFailed` | `The file wasn't removed. It's still on disk.` | `O arquivo não foi removido. Ele continua no disco.` |
| `builder.media.error.disabled` | `Writing is turned off: the builder flag is off in ~/.ooc-local/config.yaml.` | `A escrita está desligada: a flag builder está desligada em ~/.ooc-local/config.yaml.` |

### Identidade

| chave | en | pt-br |
|---|---|---|
| `builder.identity.heading` | `Identity` | `Identidade` |
| `builder.identity.name` | `Name` | `Nome` |
| `builder.identity.tagline` | `Tagline` | `Tagline` |
| `builder.identity.tagline.hint` | `One line, shown next to the scenario name.` | `Uma linha, mostrada ao lado do nome do cenário.` |
| `builder.identity.description` | `Description` | `Descrição` |
| `builder.identity.description.hint` | `Markdown. Shown to the player before starting.` | `Markdown. Mostrada ao jogador antes de começar.` |
| `builder.identity.tags` | `Tags` | `Tags` |
| `builder.identity.tags.hint` | `Enter or comma adds a tag.` | `Enter ou vírgula adiciona uma tag.` |
| `builder.identity.tags.empty` | `No tags yet.` | `Nenhuma tag ainda.` |
| `builder.identity.tags.remove` | `Remove tag {tag}` | `Remover a tag {tag}` |
| `builder.identity.tags.duplicate` | `{tag} is already in the list.` | `{tag} já está na lista.` |
| `builder.identity.tags.max` | `Up to 12 tags.` | `Até 12 tags.` |
| `builder.identity.locale` | `Scenario language` | `Idioma do cenário` |
| `builder.identity.locale.hint` | `Sets the language of the system prompts, not of this interface.` | `Define o idioma dos prompts de sistema, não o desta interface.` |
| `builder.identity.cover.legend` | `Cover` | `Capa` |
| `builder.identity.cover.hint` | `Saved to media/cover as soon as you upload it.` | `Salva em media/cover assim que você envia.` |
| `builder.identity.cover.empty` | `No cover yet` | `Sem capa ainda` |
| `builder.identity.cover.upload` | `Upload a cover` | `Enviar uma capa` |
| `builder.identity.cover.replace` | `Replace the cover` | `Trocar a capa` |
| `builder.identity.cover.remove` | `Remove the cover` | `Remover a capa` |
| `builder.identity.cover.uploading` | `Uploading the cover…` | `Enviando a capa…` |
| `builder.identity.cover.error` | `The cover wasn't saved. Try again.` | `A capa não foi salva. Tente de novo.` |
| `builder.identity.cover.alt` | `Cover of {scenario}` | `Capa de {scenario}` |
