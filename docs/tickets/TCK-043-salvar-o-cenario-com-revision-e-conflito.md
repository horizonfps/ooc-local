---
id: TCK-043
title: Salvar o cenario com escrita seletiva, revision e 409 de conflito
status: ready
points: 3
blockedBy: [TCK-031]
files:
  - backend/app/builder_doc.py
  - backend/tests/test_builder_doc_write.py
migration: false
ui: false
risk: high
---

## Problema

A leitura do documento existe (TCK-031) e nada grava de volta. Sem `PUT`, o
editor é um visualizador.

Dois requisitos não negociáveis vêm da spec de UI: (a) editar o YAML fora do app
e salvar por cima na tela não pode apagar a edição externa em silêncio — daí
`revision` e 409; (b) salvar não pode reescrever a pasta inteira, senão o diff
no git vira ruído e um erro no meio destrói mais do que precisava.

## Escopo

Dentro:
- `PUT /api/builder/scenarios/{id}`, acrescentado ao `router` que o TCK-031 já
  registrou em `main.py` — **este ticket não toca `main.py`**.
- Escrita seletiva por arquivo, remoção de start/personagem que saiu do payload,
  validações de coerência.
- Kill switch por `flags.builder` no `config.yaml`.
- Suíte nova `backend/tests/test_builder_doc_write.py`.

Fora (explícito):
- Merge automático de conflito: o backend só detecta e recusa; quem decide é a
  pessoa, na UI (TCK-046).
- Mídia: `media/` nunca é tocada por este ticket (TCK-044).
- Renomear a pasta do cenário (TCK-030 cobre com duplicar + deletar).

## Comportamento esperado

`PUT` recebe o documento inteiro mais o `revision` que o cliente tinha. Se o
`revision` do disco ainda é o mesmo, grava e devolve o `revision` novo. Se
mudou, devolve 409 e **não escreve nada**, a menos que o corpo traga
`force: true`.

Gravar só toca arquivo cujo conteúdo serializado mudou de bytes: quem não mudou
mantém `mtime` e o diff no git fica limpo. Start ou personagem que sumiu do
payload tem o arquivo apagado; start/personagem novo tem o arquivo criado.

Com `flags.builder: false` no `~/.ooc-local/config.yaml`, o `PUT` responde 503 e
nada é escrito.

## Detalhes técnicos

### Ordem da operação

1. `load_config().flag("builder")` — `False` → 503
   `{"detail": "builder disabled by flag"}`, com `emit("builder_rejected", ...)`.
   O helper `Config.flag(name, default=True)` já existe em
   `backend/app/config.py` e é o mesmo mecanismo de `chat` e `compact`; não
   acrescente campo novo em `Config`, só use o nome `builder`.
2. Valide o documento inteiro **antes** de qualquer I/O; falhou → 422 com a
   lista de erros resumida.
3. Recalcule `compute_revision` (TCK-031). Diferente do enviado e `force`
   ausente/false → 409 `{"detail": "revision conflict"}`, sem escrever nada.
4. Serialize cada arquivo alvo em bytes.
5. Compare com os bytes do disco; escreva só os diferentes, cada um por arquivo
   temporário no mesmo diretório + `os.replace` (atômico por arquivo).
6. Apague os `starts/*` e `characters/*` que não estão mais no payload,
   inclusive o par `.yml`, para não deixar arquivo fantasma que o loader depois
   acusa como duplicata.
7. Devolva 200 `{"revision": <novo>}`.

### Serialização

`yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)`.
`world.md` é o texto cru em UTF-8, com `\n` no fim se não tiver. Campo `None` é
omitido do arquivo. `id` **não** vai para o `starts/{id}.yaml` (o arquivo não
carrega o próprio nome); ao receber, se a chave do dicionário e o `id` do corpo
divergirem, a chave manda.

Ordem canônica dos campos — é o que mantém o diff estável:

- `scenario.yaml`: `name`, `tagline`, `description`, `locale`, `world_mode`,
  `tags`, `default_start`.
- `starts/{id}.yaml`: `name`, `prologue`, `opening_scene`, `play_guide`,
  `suggestions`, `hud` (`location`, `time`, `weather`), `characters`.
- `characters/{id}.yaml`: a ordem congelada no contrato do TCK-029.

### Validações de coerência (422)

- ao menos um start;
- `meta.default_start` presente em `starts`;
- todo id em `start.characters` presente em `characters`;
- chaves de `starts` e `characters` casando `^[a-z0-9-]+$`.

**Não** exija ao menos um personagem: rascunho sem elenco é legítimo e o
bloqueio disso é decisão de UI (`builder.characters.error.atLeastOne`, TCK-048).

### Falha de I/O

Capture `OSError`, emita `builder_doc_write_failed` e devolva 500
`write failed`. Parte dos arquivos pode já ter sido gravada — está declarado
aqui e a UI manda recarregar do disco depois de um 500 (TCK-046).

## Contrato público

```
PUT /api/builder/scenarios/{id}
  body: ScenarioDocument + { force?: boolean }
  200 { "revision": string }
  409 { "detail": "revision conflict" }
  422 validation | 404 scenario not found | 500 write failed
  503 { "detail": "builder disabled by flag" }   quando flags.builder = false
```

```python
# backend/app/builder_doc.py
def write_document(scenario_id: str, doc: ScenarioDocument, *, force: bool) -> str: ...
```

Consumidor: TCK-046 (save, conflito e reload no editor).

## Acceptance criteria

- [ ] `PUT` com o `revision` correto grava e devolve `revision` novo e
      diferente.
- [ ] `PUT` com `revision` velho devolve 409 e o disco fica byte a byte igual.
- [ ] `PUT` com `force: true` e `revision` velho grava.
- [ ] Arquivo cujo conteúdo não mudou mantém o `mtime` depois do `PUT`.
- [ ] Start removido do payload some do disco; start novo aparece.
- [ ] `PUT` com `default_start` inexistente é 422 e não escreve nada.
- [ ] Round-trip: `GET` → `PUT` sem alteração → `revision` **não** muda.
- [ ] `flags.builder: false` faz o `PUT` responder 503 sem escrever.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente do fluxo: **nenhuma** — não há teste de escrita de cenário no
repo; `test_builder_doc.py` (TCK-031) cobre só leitura e não é alterado.
`test_flags.py` mostra o padrão de monkeypatch de `load_config` a ser seguido
aqui.

- Feliz: `GET`, mudar `meta.name` e um prólogo, `PUT`, `GET` de novo → valores
  novos, `revision` novo.
- Feliz: adicionar personagem no payload → `characters/nova.yaml` no disco com
  os campos na ordem canônica e acentuação preservada.
- Borda: `PUT` idêntico ao lido não muda `revision` nem `mtime` de nenhum
  arquivo.
- Borda: editar `world.md` por fora entre o `GET` e o `PUT` → 409, disco
  intacto; `PUT` com `force: true` depois disso grava.
- Borda: `world` vazio grava `world.md` vazio e relê como `""`.
- Borda: cenário com `starts/default.yml` salvo com o mesmo id deixa só o
  `.yaml`.
- Borda: personagem com `emotions` fora de ordem é normalizado pelo validador do
  TCK-029 antes de ir para o disco.
- Falha: chave de start `Start Um` → 422.
- Falha: `starts: {}` → 422.
- Falha: `os.replace` monkeypatchado para `OSError` → 500 `write failed` e
  evento `builder_doc_write_failed`.
- Falha: `flags.builder: false` → 503 e nenhum arquivo tocado.

## Rollout e kill switch

Flag `builder` em `~/.ooc-local/config.yaml` (`flags: {builder: false}`), lida
por `Config.flag("builder")`, default **on**, sem restart do servidor (a config
é lida por requisição). Desligada, esta rota e a de escrita de mídia (TCK-044)
respondem 503 e o app volta a ser só leitura e jogo.

`risk: high` porque este é o ticket que **sobrescreve trabalho autoral**. As
mitigações são verificáveis nos critérios: `revision` por conteúdo com 409,
escrita seletiva por arquivo com `os.replace`, validação antes de qualquer I/O e
o kill switch acima.

## Observabilidade

Eventos:
- `builder_doc_saved` — `scenario_id`, `files_written`, `files_deleted`,
  `forced`, `revision`
- `builder_doc_conflict` — `scenario_id`, `client_revision`, `disk_revision`
- `builder_doc_write_failed` — `scenario_id`, `path`, `error`
- `builder_rejected` — `scenario_id`, `reason="builder disabled by flag"`

Métrica de sucesso: `files_written` num save que mudou um campo só é 1 — prova
de que a escrita é seletiva.

## i18n

N/A — mensagens de tela ficam no TCK-046.

## Ressalvas registradas na wave 3

- O TCK-031 mergeado le `world.md` com `read_text` (normaliza CRLF para LF) e o `revision` hasheia bytes crus. Ao salvar, grave SEMPRE com newline LF (`
`), assim o arquivo converge para LF no primeiro save e o hash passa a bater com o texto servido.
- Comportamento real do GET: pasta existente sem `scenario.yaml` retorna **404** (paridade com TCK-030), nao 422. Code contra isso.
