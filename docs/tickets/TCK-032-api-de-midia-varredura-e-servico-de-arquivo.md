---
id: TCK-032
title: Varrer a pasta de midia do cenario e servir os arquivos
status: ready
points: 3
blockedBy: [TCK-029, TCK-030, TCK-031]
files:
  - backend/app/media.py
  - backend/app/main.py
  - backend/tests/test_media.py
migration: false
ui: false
risk: medium
---

## Problema

Na Fase 2 o banco de imagens do cenário é alimentado só por upload manual
(geração é Fase 5). Antes de gravar qualquer coisa, falta o lado da leitura: uma
varredura de `media/` que diga quais espaços estão preenchidos e uma rota que
sirva o PNG para o `<img>` do jogo e do builder.

Sem servir o arquivo, `[SPRITE:chloe:sad]` continua sendo tag sem imagem e o
critério de verde da fase é impossível.

## Escopo

Dentro:
- Novo módulo `backend/app/media.py`: varredura de `media/` e serviço de
  arquivo, confinados à pasta do cenário.
- `GET /api/builder/scenarios/{id}/media` (índice) e
  `GET /api/scenarios/{id}/media/{path:path}` (arquivo).
- Registro do router em `backend/app/main.py` — **este ticket é o único da
  dupla que toca `main.py`**; o TCK-044 acrescenta as rotas de escrita no mesmo
  router.
- Suíte nova `backend/tests/test_media.py`.

Fora (explícito):
- Upload e remoção de arquivo (TCK-044).
- Manifesto dentro do `SessionDetail` (TCK-034, que consome `scan_media` e
  `media_url` daqui).
- Geração de imagem, fila, âncora, `style_preset`, ComfyUI (Fase 5).
- Redimensionar, converter ou otimizar imagem — nenhuma dependência nova de
  imagem entra no projeto nesta fase.

## Comportamento esperado

O builder pergunta o que existe na pasta e recebe um índice cru do disco,
incluindo arquivo cuja emoção o personagem não declara (órfão) — arquivo
invisível é arquivo que a pessoa vai procurar por meia hora.

O jogo pede a imagem por URL e recebe os bytes. Pedir qualquer coisa fora de
`media/` é 404.

## Detalhes técnicos

### Estrutura no disco

```
media/
  cover.png
  sprites/{spriteFolder}/{emotion}.png
  backgrounds/{location}.png
```

`{spriteFolder}` é o campo `sprite` do personagem (default = id do arquivo).
`{emotion}` é uma das emoções declaradas (TCK-029). `{location}` é slug livre.
Todos casam `^[a-z0-9-]+$`.

### Extensão

Aceitamos PNG, JPEG e WebP e não convertemos (converter exigiria Pillow, que o
projeto não tem e a fase não justifica). Um espaço tem no máximo um arquivo; a
varredura resolve espaço → arquivo real na ordem `.png`, `.jpg`, `.webp`.
Arquivo com nome fora de `^[a-z0-9-]+\.(png|jpg|webp)$` é **ignorado** na
varredura, sem erro.

### Índice

```json
{
  "cover": "/api/scenarios/escola/media/cover.png",
  "sprites": { "chloe": { "default": "<url>", "sad": "<url>" } },
  "backgrounds": { "patio": "<url>" }
}
```

As chaves de `sprites` são os nomes das pastas em `media/sprites/`, não os ids
de personagem — quem cruza com o YAML e decide o que é órfão é a aba Mídia
(TCK-039/TCK-049). Cenário sem pasta `media/` devolve índice vazio, não 404.

### Serviço do arquivo

`GET /api/scenarios/{id}/media/{path:path}`: resolva
`scenario_path(id) / "media" / path` (helper público do TCK-029), chame
`.resolve()` e recuse com 404 se a pasta `media` resolvida não estiver entre os
`parents` do resultado — o `{path:path}` do FastAPI aceita `..`, e esta checagem
é o que segura traversal. Recuse também extensão fora de `png|jpg|jpeg|webp` e
qualquer coisa que não seja arquivo regular. Responda com `FileResponse` e
`Cache-Control: no-cache` (o arquivo é trocado durante a edição; cache agressivo
faria a pessoa ver o sprite antigo depois de subir um novo).

A rota fica fora do prefixo `/api/builder` de propósito: o jogo também a usa, e
o builder não é pré-requisito para jogar.

## Contrato público

```
GET /api/builder/scenarios/{id}/media    -> 200 MediaIndex | 404 scenario not found
GET /api/scenarios/{id}/media/{path}     -> 200 image | 404

MediaIndex: { cover: string|null,
              sprites: { [folder]: { [emotion]: string } },
              backgrounds: { [location]: string } }
```

```python
# backend/app/media.py
MAX_UPLOAD_BYTES: int          # 8 * 1024 * 1024, usado pelo TCK-044
ALLOWED_EXTENSIONS: tuple[str, ...]   # ("png", "jpg", "webp")
KEY_RE: re.Pattern[str]        # ^[a-z0-9-]+$
router: APIRouter
class MediaIndex(BaseModel): ...
def media_url(scenario_id: str, relative: str) -> str: ...
def media_root(scenario_id: str) -> Path: ...
def scan_media(scenario_id: str) -> MediaIndex: ...
```

Consumidores: TCK-034 (manifesto do jogo), TCK-035 (miniatura da capa na lista),
TCK-039/TCK-049 (aba Mídia), TCK-044 (escrita, reusa `KEY_RE`, `media_root`,
`MAX_UPLOAD_BYTES` e `media_url`).

## Acceptance criteria

- [ ] `GET` do índice lista capa, sprites por pasta e backgrounds existentes.
- [ ] Cenário sem `media/` devolve índice vazio com 200.
- [ ] `GET` da URL de um sprite devolve os bytes do arquivo com
      `Cache-Control: no-cache`.
- [ ] `GET /api/scenarios/{id}/media/../../scenario.yaml` é 404 e não vaza o
      arquivo.
- [ ] Arquivo com nome fora do padrão é ignorado no índice, sem erro.
- [ ] Espaço com `.png` e `.jpg` ao mesmo tempo resolve para o `.png`.
- [ ] Id de cenário com traversal é 404/422 nas duas rotas.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente do fluxo: **nenhuma** — não há teste de mídia no repo e nenhum
teste existente é alterado (rotas novas, `scenario.py` intocado). Nos testes,
escreva os PNGs à mão a partir da assinatura
(`b"\x89PNG\r\n\x1a\n" + b"..."`), sem biblioteca de imagem.

- Feliz: pasta com capa, dois sprites e um background → índice com os quatro.
- Feliz: baixar cada URL do índice e conferir os bytes.
- Borda: `media/sprites/chloe/` com `Sad.PNG` (maiúsculas) é ignorado.
- Borda: cenário sem `media/` e cenário com `media/` vazia devolvem índice
  vazio.
- Borda: `default.png` e `default.jpg` no mesmo espaço → índice aponta para o
  `.png`.
- Falha: `path` com `..`, com barra invertida e com extensão `.yaml` são 404.
- Falha: `path` apontando para diretório é 404.

## Rollout e kill switch

N/A — rotas de **leitura**. O kill switch da fase (`flags.builder`) vale para as
rotas que escrevem, no TCK-043 e no TCK-044; bloquear leitura de imagem
quebraria o jogo sem proteger nada.

`risk: medium` pelo vetor de traversal na rota de arquivo, fechado por
resolução + comparação contra a pasta `media` e por lista branca de extensão.

## Observabilidade

Eventos: `media_scanned` — `scenario_id`, `sprite_folders`, `sprite_files`,
`backgrounds`, `has_cover`; `media_forbidden` — `scenario_id`, `path` (tentativa
recusada na rota de arquivo).
Métrica de sucesso: `media_forbidden` em zero no uso normal e o índice batendo
com o que está na pasta.

## i18n

N/A — sem texto de usuário; as mensagens de erro de tela ficam no TCK-037
(`builder.media.error.*`).
