---
id: TCK-031
title: Ler o cenario inteiro do disco com revision estavel
status: ready
points: 3
blockedBy: [TCK-029, TCK-030]
files:
  - backend/app/builder_doc.py
  - backend/app/main.py
  - backend/tests/test_builder_doc.py
migration: false
ui: false
risk: medium
---

## Problema

O builder é um editor de arquivos: o disco é a fonte da verdade e o app é só uma
tela em cima dele. Falta o meio do caminho — uma rota que devolva o cenário
inteiro (meta, `world.md`, todos os starts, todos os personagens) num payload
só, tolerando rascunho incompleto e recusando arquivo que não parseia.

Este ticket entrega **só a leitura** e o cálculo de `revision`. A escrita, com
409 de conflito, é o TCK-043 — quebrado por tamanho e porque a leitura é o que
todas as abas precisam para existir.

## Escopo

Dentro:
- Novo módulo `backend/app/builder_doc.py`: `ScenarioDocument`, leitura
  tolerante e `compute_revision`.
- `GET /api/builder/scenarios/{id}`.
- Registro do router em `backend/app/main.py` (uma linha,
  `app.include_router(builder_doc.router)`) — **este ticket é o único da dupla
  que toca `main.py`**; o TCK-043 acrescenta a rota de escrita no mesmo router.
- Suíte nova `backend/tests/test_builder_doc.py`.

Fora (explícito):
- `PUT`, escrita seletiva, 409, `force` (TCK-043).
- Mídia: `media/` nunca é lida por este ticket (TCK-032).
- Serializar campos de fase futura (`stats.yaml`, `lorebook.yaml`,
  `endings.yaml`, `commands.yaml`).

## Comportamento esperado

`GET` devolve o cenário inteiro mais um `revision`. Cenário em rascunho (sem
personagem, sem prólogo) é lido normalmente — quem exige elenco é o jogo, não o
editor. Se algum arquivo não parseia, a resposta é 422 com a razão e o caminho,
e a UI abre o estado "cenário inválido no disco" sem formulário e sem save.

## Detalhes técnicos

### Documento

O payload espelha o YAML 1:1, em **snake_case** (é um editor de arquivo, não uma
API de produto; o único campo que não existe no disco é `revision`). Isso
diverge de propósito do camelCase de `SessionSummary`/`SessionDetail`, e a
divergência é o ponto: o que a tela edita é o arquivo.

```python
class ScenarioDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str
    meta: ScenarioMeta                    # de app.scenario, com world_mode (TCK-029)
    world: str
    starts: dict[str, StartConfig]        # chave = nome do arquivo sem extensão
    characters: dict[str, Character]      # idem
```

`StartConfig` exige `id`; ao ler, injete `id = stem` (o loader já faz assim).

### Leitura

Não use `load_scenario()`: ele exige `characters/` não vazia e `default_start`
existente, e o builder precisa abrir rascunho incompleto. Leia arquivo por
arquivo com `yaml.safe_load` + validação pydantic, aceitando:

- `characters/` vazia ou inexistente → `characters: {}`;
- `starts/` vazia ou inexistente → `starts: {}`;
- `world.md` ausente → `world: ""`.

E recusando com 422 (`{"detail": "<caminho>: <razão>"}`, razão em uma linha,
truncada em 300 caracteres, mesmo formato do `_summarize` de `scenario.py`):

- `scenario.yaml` ausente, ilegível ou inválido;
- qualquer arquivo em `starts/` ou `characters/` que não parseia ou não valida;
- stem duplicado entre `.yaml` e `.yml` (mesma regra do loader).

Confinamento sempre via `scenario_path` (TCK-029). Id inválido → 422
`invalid folder`, paridade com TCK-030. Pasta inexistente → 404
`scenario not found`.

### Revision

```python
def compute_revision(scenario_id: str) -> str:
    """sha256 over sorted (relpath, bytes) of every scenario file outside media/."""
```

- Percorre `scenario.yaml`, `world.md`, `starts/*.yaml|*.yml`,
  `characters/*.yaml|*.yml`, ordenado por caminho relativo com `/` como
  separador (nunca use `os.sep` no hash: o `revision` tem que ser igual em
  Windows e Linux).
- Alimenta o hash com `relpath.encode()` + `b"\0"` + `str(len(bytes)).encode()` +
  `b"\0"` + `bytes` de cada arquivo.
- Devolve os 16 primeiros caracteres do hexdigest.
- É **conteúdo**, não `mtime`: reescrever um arquivo com o mesmo conteúdo não
  muda o `revision`, e é isso que faz "salvar duas vezes seguidas" não dar
  conflito falso no TCK-043.

## Contrato público

```
GET /api/builder/scenarios/{id}
  200 ScenarioDocument | 404 scenario not found | 422 <path>: <reason>

ScenarioDocument (JSON, snake_case, espelho dos arquivos):
{
  revision: string,
  meta: { name, tagline, description, locale, world_mode, tags, default_start },
  world: string,
  starts:     { [id]: { id, name, prologue, opening_scene, play_guide,
                        suggestions, hud: {location, time, weather}, characters } },
  characters: { [id]: { name, role, appearance, personality, voice,
                        mind: {feeling, goal, opinion_of_player, secret_plan},
                        sprite, anchor, emotions } }
}
```

```python
# backend/app/builder_doc.py
router: APIRouter                      # sem prefixo próprio; rotas completas
class ScenarioDocument(BaseModel): ...
def read_document(scenario_id: str) -> ScenarioDocument: ...
def compute_revision(scenario_id: str) -> str: ...
```

Consumidores: TCK-043 (escrita, reusa `ScenarioDocument` e `compute_revision`),
TCK-036 (carrega o editor), TCK-041 (sabe quais starts existem no disco).

## Acceptance criteria

- [ ] `GET` devolve meta, world, todos os starts e todos os personagens, com
      `revision` estável entre duas chamadas sem escrita.
- [ ] `GET` de cenário com `characters/` vazia devolve 200 com `characters: {}`.
- [ ] `GET` de cenário sem `world.md` devolve `world: ""`.
- [ ] `GET` de cenário com `characters/chloe.yaml` inválido devolve 422 com o
      caminho do arquivo na mensagem, em uma linha.
- [ ] `GET` de pasta inexistente é 404; id com traversal é 422.
- [ ] `compute_revision` muda quando qualquer arquivo muda de conteúdo e não
      muda quando um arquivo é reescrito igual.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente do fluxo: **nenhuma**. A cobertura de `scenario.py` é toda de
leitura via `load_scenario` (`test_scenario.py`, `test_example_scenario.py`) e
nenhum desses testes é alterado — `load_scenario` não muda. Todos os cenários
abaixo são novos, com o fixture de `scenarios_root` no padrão de `test_turn.py`
(monkeypatch de `app.scenario.scenarios_dir`).

- Feliz: cenário completo → documento com 1 start e 3 personagens, campos
  acentuados preservados.
- Feliz: `revision` igual em duas leituras seguidas.
- Borda: cenário recém-criado pelo TCK-030 (sem personagem) é lido com
  `characters: {}` e 200.
- Borda: `starts/default.yml` (extensão `.yml`) é lido com a chave `default`.
- Borda: reescrever `world.md` com o mesmo conteúdo mantém o `revision`; mudar
  um caractere muda.
- Borda: `revision` não depende do separador de caminho do sistema (calcule
  sobre uma árvore fixa e afirme o valor estável entre execuções).
- Falha: `scenario.yaml` com YAML quebrado → 422 com o caminho.
- Falha: `characters/chloe.yaml` com campo desconhecido → 422 citando o arquivo.
- Falha: `starts/` com `a.yaml` e `a.yml` → 422 de duplicata.

## Rollout e kill switch

N/A — rota de **leitura**, sem efeito no disco e sem fluxo existente afetado.
O kill switch da fase (`flags.builder` no `config.yaml`) vale para as rotas que
escrevem e é implementado no TCK-043 e no TCK-044; bloquear leitura não protege
nada e só deixaria a tela mentir.

## Observabilidade

Eventos: `builder_doc_read` — `scenario_id`, `starts`, `characters`,
`revision`; `builder_doc_invalid` — `scenario_id`, `path`, `reason`.
Métrica de sucesso: abrir o cenário exemplo pelo editor sem nenhum
`builder_doc_invalid`.

## i18n

N/A — `detail` é razão técnica em inglês; as mensagens de tela ficam no TCK-036
(`builder.editor.invalid.*`).
