---
id: TCK-044
title: Gravar e remover imagem do cenario por upload manual
status: done
points: 3
blockedBy: [TCK-032, TCK-034]
files:
  - backend/app/media.py
  - backend/tests/test_media_write.py
migration: false
ui: false
risk: high
---

## Problema

A varredura e o serviço de imagem existem (TCK-032) e não há como colocar
imagem na pasta pelo app. Sem upload, o banco de sprites continua sendo `cp` na
mão e a aba Mídia não tem o que fazer.

## Escopo

Dentro:
- `POST` e `DELETE` de mídia, acrescentados ao `router` que o TCK-032 já
  registrou em `main.py` — **este ticket não toca `main.py`**.
- Validação de tipo por assinatura, limite de tamanho durante o streaming,
  destino ditado pelo espaço.
- Kill switch por `flags.builder`.
- Suíte nova `backend/tests/test_media_write.py`.

Fora (explícito):
- Geração de imagem, fila, estúdio de personagem (Fase 5).
- Converter, redimensionar ou otimizar a imagem.
- Cartas de ending (Fase 4).
- Qualquer alteração no índice ou na rota de serviço (TCK-032).

## Comportamento esperado

Quem edita o cenário envia um arquivo para um **espaço** identificado por tipo:
capa, sprite (personagem + emoção) ou background (local). O nome do arquivo no
disco é ditado pelo espaço, nunca pelo nome do arquivo enviado. Enviar de novo
sobrescreve. Remover apaga do disco na hora.

Arquivo grande demais, tipo errado ou conteúdo que não é imagem são recusados
antes de tocar o disco, com código próprio para a UI diferenciar a mensagem.

Com `flags.builder: false`, as duas rotas respondem 503 e nada é gravado ou
apagado.

## Detalhes técnicos

### Rotas

| método | rota | corpo | resposta |
|---|---|---|---|
| POST | `/api/builder/scenarios/{id}/media` | multipart: `kind`, `key`, `character?`, `file` | 201 `{path, url}` |
| DELETE | `/api/builder/scenarios/{id}/media` | query: `kind`, `key`, `character?` | 204 |

`kind ∈ cover | sprite | background`. Para `cover`, `key` é ignorado
(`key = "cover"`); para `sprite`, `character` é obrigatório; para `background`,
`character` é proibido. `key` e `character` passam pelo `KEY_RE` do TCK-032
antes de qualquer I/O; fora dele → 422 `invalid key`.

### Kill switch

`load_config().flag("builder")` no começo das duas rotas; `False` → 503
`{"detail": "builder disabled by flag"}` com `emit("builder_rejected", ...)`.
`Config.flag(name, default=True)` já existe em `backend/app/config.py` e é o
mesmo mecanismo de `chat` e `compact` — nenhum campo novo em `Config`. É o mesmo
nome de flag usado pelo TCK-043; desligar uma coisa desliga a escrita inteira do
builder, que é o comportamento desejado.

### Detecção de tipo

Não confie no `content-type` do multipart. Leia os primeiros 16 bytes e case:

- PNG: `\x89PNG\r\n\x1a\n`
- JPEG: `\xff\xd8\xff`
- WebP: `RIFF` nos bytes 0–3 e `WEBP` nos bytes 8–11

Nenhum casa → 415 `unsupported media type`. O `accept` do input e a checagem no
cliente (TCK-037/TCK-039) são conveniência; a validação que vale é esta.

Tamanho: leia em blocos de 64 KB e aborte ao passar de `MAX_UPLOAD_BYTES`
(8 MB, constante do TCK-032) → 413 `file too large`, sem gravar. Nunca faça
`await file.read()` de uma vez.

### Gravação

O arquivo é gravado com a extensão do tipo detectado: `{key}.png`, `{key}.jpg`
ou `{key}.webp`. Ao gravar num espaço, os irmãos com as outras duas extensões
são removidos — um espaço tem no máximo um arquivo, que é a invariante que a
varredura do TCK-032 assume.

Grave em arquivo temporário no diretório de destino e faça `os.replace`. Crie os
diretórios intermediários com `mkdir(parents=True, exist_ok=True)`. Falha de I/O
→ 500 `write failed` com `emit`.

`DELETE` remove o arquivo do espaço (qualquer uma das três extensões); espaço
vazio → 404 `asset not found`; `OSError` → 500 `delete failed`.

## Contrato público

```
POST   /api/builder/scenarios/{id}/media          -> 201 { path, url }
       multipart: kind=cover|sprite|background, key, character?, file
DELETE /api/builder/scenarios/{id}/media?kind=&key=&character=  -> 204

Erros: 404 scenario not found | 404 asset not found | 413 file too large
       | 415 unsupported media type | 422 invalid key | 500 write failed
       | 503 builder disabled by flag
```

Consumidores: TCK-037 (capa), TCK-039 (grid de sprites), TCK-049 (backgrounds e
órfãos).

## Acceptance criteria

- [ ] Upload de PNG para `sprite` grava `media/sprites/{character}/{key}.png` e
      devolve a URL que serve o arquivo.
- [ ] A URL devolvida responde 200 com os mesmos bytes enviados.
- [ ] Enviar JPEG para um espaço que tinha PNG deixa **um** arquivo só no
      espaço.
- [ ] Arquivo de 9 MB é 413 e nada é gravado.
- [ ] Arquivo `.png` cujo conteúdo é texto é 415 e nada é gravado.
- [ ] `key`/`character` fora de `[a-z0-9-]+` é 422.
- [ ] `kind: sprite` sem `character` e `kind: background` com `character` são
      422.
- [ ] `DELETE` remove o arquivo e o espaço some do índice; espaço vazio é 404.
- [ ] `flags.builder: false` faz `POST` e `DELETE` responderem 503 sem tocar o
      disco.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente do fluxo: `backend/tests/test_media.py` (TCK-032) cobre
varredura e serviço e **não é alterada** — os cenários novos ficam em
`test_media_write.py`. `test_flags.py` é o padrão de monkeypatch de
`load_config` a seguir. Nenhuma asserção existente muda.

- Feliz: subir capa, sprite e background; o índice do TCK-032 passa a trazer os
  três.
- Feliz: subir duas vezes no mesmo espaço — o segundo conteúdo vence.
- Feliz: `DELETE` de sprite existente → 204 e o espaço some do índice.
- Borda: `webp` com `RIFF....WEBP` é aceito e gravado como `.webp`.
- Borda: substituir `.png` por `.webp` deixa só o `.webp` na pasta.
- Borda: upload para cenário sem pasta `media/` cria a árvore.
- Falha: 9 MB → 413; texto renomeado para `.png` → 415; `key` com maiúscula →
  422.
- Falha: `os.replace` monkeypatchado para `OSError` → 500 `write failed` e
  evento `media_write_failed`.
- Falha: `flags.builder: false` → 503 nas duas rotas, com o disco inalterado.
- Falha: id de cenário com traversal → 404/422.

## Rollout e kill switch

Flag `builder` em `~/.ooc-local/config.yaml` (`flags: {builder: false}`), lida
por `Config.flag("builder")`, default **on**, sem restart. Desligada, esta rota
e o `PUT` do documento (TCK-043) respondem 503.

`risk: high` por ser a rota que escreve arquivo binário vindo do browser. Os
dois vetores clássicos estão fechados por construção: nome do destino ditado
pelo espaço (traversal por nome de arquivo deixa de existir) e tipo detectado
por assinatura com tamanho limitado durante o streaming.

## Observabilidade

Eventos:
- `media_uploaded` — `scenario_id`, `kind`, `key`, `bytes`, `ext`
- `media_removed` — `scenario_id`, `kind`, `key`
- `media_rejected` — `scenario_id`, `kind`, `reason` (`type` | `size` | `key`)
- `media_write_failed` — `scenario_id`, `path`, `error`
- `builder_rejected` — `scenario_id`, `reason="builder disabled by flag"`

Métrica de sucesso: no verde da fase, subir os sprites de teste de 2 NPCs sem
nenhum `media_rejected` inesperado.

## i18n

N/A — as mensagens de tela (`builder.media.error.type|size|write|removeFailed`)
são declaradas no TCK-037, mapeadas a partir do status HTTP (413 → size,
415 → type, 500 → write).
