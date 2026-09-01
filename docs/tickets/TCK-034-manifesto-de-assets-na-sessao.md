---
id: TCK-034
title: Entregar o manifesto de sprites e backgrounds junto do SessionDetail
status: ready
points: 2
blockedBy: [TCK-032]
files:
  - backend/app/sessions.py
  - backend/app/media.py
  - backend/tests/test_media_manifest.py
migration: false
ui: false
risk: low
---

## Problema

O jogo resolve `[SPRITE:char:emotion]` e `[BG:location]` **no cliente**, sem uma
requisição por tag — é o que a spec §3.1 exige (custo zero, latência zero). Para
isso o cliente precisa saber, de antemão, quais assets existem e em que URL.

`SessionDetail` hoje devolve prólogo, turnos e HUD. Falta o mapa de assets do
cenário daquela sessão.

## Escopo

Dentro:
- `assets` no `SessionDetail` (`GET /api/sessions/{id}` e resposta do
  `POST /api/sessions`).
- Função `session_assets(scenario)` em `backend/app/media.py`, que traduz a
  varredura de disco para chaves de personagem.
- Testes novos em `backend/tests/test_media_manifest.py`.

Fora (explícito):
- Endpoint separado de manifesto: o dado viaja com a sessão, não em uma segunda
  chamada.
- Invalidação/atualização do manifesto durante a sessão — quem sobe sprite no
  builder reinicia o preview (a UI já avisa isso com
  `builder.preview.outdated`).
- Qualquer render (é o TCK-042).

## Comportamento esperado

Quem abre uma sessão recebe, junto do resto:

```json
"assets": {
  "sprites": { "chloe": { "default": "<url>", "sad": "<url>" } },
  "backgrounds": { "patio": "<url>" }
}
```

Cenário sem nenhuma imagem devolve `{"sprites": {}, "backgrounds": {}}` — nunca
`null`, para o cliente não precisar de guarda.

## Detalhes técnicos

```python
# backend/app/media.py
class SessionAssets(BaseModel):
    sprites: dict[str, dict[str, str]] = {}
    backgrounds: dict[str, str] = {}

def session_assets(scenario: LoadedScenario) -> SessionAssets: ...
```

Regras de chaveamento — é aqui que mora a decisão:

- Para cada personagem do cenário, a pasta de sprites é `character.sprite or char_id`.
  A entrada do manifesto é indexada pelo **id do arquivo do personagem**
  (`chloe`), porque é assim que a tag casa (game-sprites-bg: id primeiro, campo
  `sprite` em segundo).
- Quando `character.sprite` existe e é diferente do id, o mesmo mapa também é
  publicado sob essa chave — dois apelidos apontando para o mesmo dicionário
  de URLs. É o que faz `[SPRITE:sprite-folder:sad]` funcionar sem lógica extra
  no cliente.
- Chaves são emitidas em minúsculas; o cliente faz `toLowerCase()` na tag antes
  de procurar.
- Só entram emoções com arquivo no disco. Emoção declarada no YAML sem arquivo
  **não** aparece — o fallback para `default` é decisão do cliente e depende
  justamente de a chave estar ausente.
- Pasta de sprites que não pertence a nenhum personagem (órfã) é ignorada aqui;
  ela só existe para a aba Mídia (TCK-032).
- `backgrounds` é a varredura de `media/backgrounds/` sem filtro: qualquer slug
  com arquivo entra.

`sessions.py`:

- `SessionDetail` ganha `assets: SessionAssets` (nome já camelCase-compatível,
  sem alias novo).
- `get_session()` já carrega o cenário para pegar o start; passe o mesmo objeto
  para `session_assets`, sem segunda leitura de disco.
- `create_session()` idem, com o cenário que já carregou.
- Cuidado com import circular: `sessions.py` já importa de `app.scenario`;
  `media.py` deve importar de `app.scenario`, nunca de `app.sessions`.

Custo: uma varredura de diretório por abertura de sessão. Aceitável — pasta de
cenário tem dezenas de arquivos, e a alternativa (cache) traz invalidação que a
fase não precisa.

## Contrato público

```
GET  /api/sessions/{id}  -> SessionDetail
POST /api/sessions       -> SessionDetail

SessionDetail ganha:
  assets: {
    sprites:     { [characterOrSpriteFolder: string]: { [emotion: string]: string } },
    backgrounds: { [location: string]: string }
  }
```

```python
# backend/app/media.py
class SessionAssets(BaseModel): ...
def session_assets(scenario: LoadedScenario) -> SessionAssets: ...
```

Consumidor: TCK-042 (redutor de cena e render), que resolve nesta ordem:
`sprites[char][emotion]` → `sprites[char]["default"]` → tag ignorada.

## Acceptance criteria

- [ ] `GET /api/sessions/{id}` de um cenário com sprites devolve `assets` com as
      URLs corretas, que respondem 200 na rota de mídia.
- [ ] Cenário sem `media/` devolve `assets` com os dois dicionários vazios.
- [ ] Personagem com `sprite: outro-nome` aparece sob o id **e** sob
      `outro-nome`, com o mesmo conteúdo.
- [ ] Emoção declarada no YAML sem arquivo não aparece no manifesto.
- [ ] `POST /api/sessions` devolve o mesmo `assets` do `GET`.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente que muda de preparação: os testes de sessão que afirmam campos
específicos do corpo (`test_sessions.py::test_post_sessions_route_happy_path`
checa `body["turns"]`, `body["prologue"]`, `body["hud"]["turn"]`) continuam
passando sem alteração, porque o campo é aditivo e nenhum teste compara o
dicionário inteiro. Confirme isso ao implementar: se algum teste passar a
comparar corpo inteiro, ele é adaptado só na preparação (acrescentando `assets`
esperado), nunca mudando o que afere.

Cenários novos:
- Feliz: cenário com `media/sprites/chloe/default.png` e
  `media/backgrounds/patio.png` → manifesto com as duas entradas.
- Feliz: URL do manifesto baixada pela rota de mídia devolve os bytes.
- Borda: personagem `chloe` com `sprite: chloe-alt` publica as duas chaves.
- Borda: arquivo em `media/sprites/desconhecido/` (pasta órfã) não entra.
- Borda: emoção `sad` declarada no YAML sem PNG não entra; `default` com PNG
  entra.
- Borda: sessão de cenário cuja pasta foi apagada continua devolvendo 404
  `scenario not found` como hoje (o manifesto não muda esse caminho).

## Rollout e kill switch

N/A — campo aditivo em resposta JSON; cliente antigo ignora.

## Observabilidade

Eventos: `session_assets` — `session_id`, `sprite_characters`,
`sprite_files`, `backgrounds`, emitido na abertura da sessão.
Métrica de sucesso: no verde da fase, `sprite_files` maior que zero na sessão de
preview do cenário criado pela UI.

## i18n

N/A — sem texto de usuário.
