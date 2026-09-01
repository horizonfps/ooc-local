---
id: TCK-030
title: Expor a API do builder para listar, criar, duplicar e deletar cenario
status: ready
points: 5
blockedBy: [TCK-029]
files:
  - backend/app/builder.py
  - backend/app/main.py
  - backend/tests/test_builder.py
migration: false
ui: false
risk: medium
---

## Problema

O app só sabe **ler** cenários: `list_scenarios()` devolve os válidos e
`load_scenario()` carrega um. Não existe nenhuma forma de criar a pasta de um
cenário novo, copiar uma existente ou apagar — hoje isso é `mkdir` na mão.
A Fase 2 inteira começa por aqui: sem criar cenário pela UI, não há o que
editar, nem o que jogar no preview.

Um detalhe que o `GET /api/scenarios` atual não resolve: ele **esconde** pasta
quebrada (o `except ScenarioError` só emite log). Para o builder isso é o pior
comportamento possível — pasta quebrada é justamente a que a pessoa precisa
achar para consertar.

## Escopo

Dentro:
- Novo módulo `backend/app/builder.py` com um `APIRouter` (prefixo
  `/api/builder`) e as quatro operações de pasta.
- Varredura tolerante (`scan_scenarios`) que lista também pasta inválida, com a
  razão.
- Registro do router em `backend/app/main.py` (uma linha,
  `app.include_router(builder.router)`).
- Suíte nova `backend/tests/test_builder.py`.

Fora (explícito):
- Ler/salvar o conteúdo dos arquivos do cenário (é o TCK-031).
- Upload de mídia (é o TCK-032).
- Alterar `GET /api/scenarios`, que continua listando só cenário jogável —
  as duas rotas têm públicos diferentes e ambas continuam existindo.
- Import/export `.zip` (Fase 8).
- Renomear pasta de cenário (duplicar + deletar cobre; renomear direto quebraria
  as sessões salvas que apontam para o id antigo).

## Comportamento esperado

Do ponto de vista do chamador (a tela de lista do builder):

- Pede a lista e recebe **toda** pasta de `scenarios/` que tenha um
  `scenario.yaml`, válida ou não, com contagem de starts e personagens.
- Cria um cenário informando nome, pasta e idioma; recebe o item já criado e
  pode ir direto editar. A pasta nasce com o esqueleto mínimo no disco.
- Duplica informando a pasta nova; a cópia inclui `media/`.
- Deleta; a pasta some inteira.

Erro de pasta já existente é 409 e não escreve nada. Id fora da raiz de
`scenarios/` é 422 e nunca toca o disco.

## Detalhes técnicos

Todo caminho passa por `scenario_path(scenario_id)` de `app/scenario.py`
(público desde TCK-029), que confina na raiz de `scenarios_dir()` e levanta
`ScenarioError`. Nenhuma rota monta path concatenando string.

Slug de pasta: `FOLDER_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")`. Validado
antes de qualquer I/O; falha → 422 `{"detail": "invalid folder"}`.

### Varredura tolerante

```python
class BuilderScenarioItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    name: str
    tagline: str | None = None
    locale: str = "pt-br"
    start_count: int = Field(0, alias="startCount")
    character_count: int = Field(0, alias="characterCount")
    has_cover: bool = Field(False, alias="hasCover")
    updated_at: str = Field(alias="updatedAt")
    status: Literal["ok", "invalid"] = "ok"
    reason: str | None = None
```

`scan_scenarios()` percorre `sorted(scenarios_dir().iterdir())`, ignora arquivo
e pasta sem `scenario.yaml`, e para cada pasta:

- lê e valida `scenario.yaml` com `ScenarioMeta`; falhar aqui é
  `status: "invalid"` com `reason` = razão do `ScenarioError`, `name` = id da
  pasta e contagens em 0;
- conta `starts/*.yaml|*.yml` e `characters/*.yaml|*.yml` **sem** validar
  conteúdo de cada arquivo (contagem é de arquivo, não de start válido);
- `has_cover` = existe `media/cover.png|.jpg|.webp`;
- `updated_at` = maior `mtime` dos arquivos do cenário (fora de `media/`), em
  ISO 8601 UTC com `Z`, no mesmo formato de `sessions._now_iso()`.

**Decisão deliberada**: cenário sem nenhum personagem, ou com prólogo vazio, é
`status: "ok"` aqui, mesmo que `load_scenario()` o recuse. O builder edita
rascunho; quem exige elenco é o jogo. Só erro de leitura/parse de
`scenario.yaml` produz `invalid`. Ordenação: por `name.casefold()`, com os
inválidos ordenados pelo id, mantendo tudo numa lista só.

Qualquer exceção inesperada numa pasta vira item `invalid` com o tipo do erro na
razão e emissão de `scenario_invalid` — a listagem nunca morre por causa de uma
pasta (mesma regra do TCK-025).

### Rotas

| método | rota | corpo | resposta |
|---|---|---|---|
| GET | `/api/builder/scenarios` | — | 200 `BuilderScenarioItem[]` |
| POST | `/api/builder/scenarios` | `{folder, name, locale}` | 201 `BuilderScenarioItem` |
| POST | `/api/builder/scenarios/{id}/duplicate` | `{folder}` | 201 `BuilderScenarioItem` |
| DELETE | `/api/builder/scenarios/{id}` | — | 204 |

Códigos de erro, com `detail` em inglês (o frontend traduz por chave própria,
como já faz):

- 422 `invalid folder` — slug fora do `FOLDER_RE`, id fora da raiz, `name` vazio
  ou maior que 80, `locale` fora de `en|pt-br`.
- 409 `folder exists` — destino já existe (criar e duplicar).
- 404 `scenario not found` — pasta de origem não existe (duplicar e deletar).
- 500 `write failed` / `delete failed` — `OSError` no disco, com `emit` do erro.

### Esqueleto criado

`POST` cria, com `yaml.safe_dump(..., allow_unicode=True, sort_keys=False)`:

```
scenarios/{folder}/
  scenario.yaml     # name, tagline: null, description: null, locale,
                    # world_mode: guided, tags: [], default_start: default
  world.md          # "## Universe\n\n"
  starts/default.yaml
  characters/       # vazia
  media/sprites/    # vazia
  media/backgrounds/# vazia
```

`starts/default.yaml`:

```yaml
name: default
prologue: ""
opening_scene: ""
play_guide: null
suggestions: []
hud:
  location: ""
  time: "08:00"
  weather: clear
characters: null
```

O `id` do start vem do nome do arquivo (o loader já injeta), então o arquivo não
carrega `id`. `hud.location: ""` é aceito pelo schema (`str`) e a UI cobra o
preenchimento na validação de save.

Criação é atômica no nível da pasta: monte tudo em
`scenarios/.{folder}.tmp-{uuid4().hex}` e faça `os.replace` para o destino
final; se o destino já existir, 409 antes de montar. Falhou no meio: remova o
temporário no `finally`. O prefixo `.` garante que a pasta temporária não
apareça em `scan_scenarios` (que ignora quem não tem `scenario.yaml`) nem em
`list_scenarios`.

Duplicar: `shutil.copytree(origem, destino_tmp)` + `os.replace`, mesma
estratégia. `dirs_exist_ok=False`. O `name` dentro do `scenario.yaml` é copiado
tal qual, sem sufixo — quem renomeia é a pessoa, na aba Identidade.

Deletar: `shutil.rmtree`. Em Windows, arquivo aberto por outro programa levanta
`PermissionError`: capture `OSError` e devolva 500 `delete failed` com `emit`,
nunca deixe a pasta pela metade sem avisar.

## Contrato público

```
GET    /api/builder/scenarios                     -> 200 BuilderScenarioItem[]
POST   /api/builder/scenarios                     -> 201 BuilderScenarioItem
       body: { folder: string, name: string, locale: "en" | "pt-br" }
POST   /api/builder/scenarios/{id}/duplicate      -> 201 BuilderScenarioItem
       body: { folder: string }
DELETE /api/builder/scenarios/{id}                -> 204

BuilderScenarioItem (JSON, camelCase):
{ id, name, tagline, locale, startCount, characterCount, hasCover,
  updatedAt, status: "ok" | "invalid", reason?: string }
```

```python
# backend/app/builder.py
router: APIRouter                    # prefix="/api/builder"
FOLDER_RE: re.Pattern[str]
def scan_scenarios() -> list[BuilderScenarioItem]: ...
def scan_one(scenario_id: str) -> BuilderScenarioItem: ...
```

Consumidores: TCK-031 (reusa `FOLDER_RE` e o padrão de erro), TCK-035 (tela de
lista consome as quatro rotas).

## Acceptance criteria

- [ ] `GET /api/builder/scenarios` lista pasta válida e pasta com
      `scenario.yaml` quebrado, esta com `status: "invalid"` e `reason` não
      vazia.
- [ ] Pasta sem `scenario.yaml` e arquivo solto na raiz não aparecem.
- [ ] `POST` cria a pasta com o esqueleto completo e devolve 201 com o item;
      a pasta criada aparece na listagem seguinte com `startCount: 1` e
      `characterCount: 0`.
- [ ] `POST` com pasta existente é 409 e não altera a pasta existente.
- [ ] `POST` com slug inválido ou id de traversal (`../x`, `a/b`) é 422 e não
      cria nada.
- [ ] `duplicate` copia todos os arquivos, inclusive `media/`, e a cópia carrega
      pelo loader se a origem carregava.
- [ ] `DELETE` remove a pasta inteira e devolve 204; em pasta inexistente, 404.
- [ ] Nenhuma pasta temporária sobra em `scenarios/` depois de sucesso ou falha.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente do fluxo: `backend/tests/test_scenario.py` cobre
`list_scenarios`/`load_scenario` e continua intacta — este ticket não altera
nenhuma dessas funções. Nenhum teste existente cobre escrita de cenário: **hoje
não há nenhum teste de criação, duplicação ou remoção de pasta de cenário**, a
suíte inteira é de leitura. Todos os cenários abaixo são novos, em
`backend/tests/test_builder.py`, usando o fixture de `scenarios_root` no mesmo
padrão de `test_turn.py` (monkeypatch de `app.scenario.scenarios_dir`).

- Feliz: criar → listar → o item aparece com `status: "ok"`; `load_scenario` do
  novo cenário falha por falta de personagem (comportamento esperado, o builder
  ainda lista como ok).
- Feliz: duplicar um cenário com `media/backgrounds/patio.png` — o arquivo
  existe no destino com os mesmos bytes.
- Feliz: deletar → some da listagem e a pasta não existe mais no disco.
- Borda: pasta com `scenario.yaml` inválido (YAML quebrado) aparece na listagem
  com razão de uma linha e não derruba as outras.
- Borda: pasta com `scenario.yaml` válido e `characters/` vazia é `status: "ok"`.
- Borda: `updatedAt` muda depois de reescrever `world.md`.
- Falha: `POST` com `{"folder": "Pasta Com Espaço"}` é 422.
- Falha: `POST /api/builder/scenarios/../etc/duplicate` é 404/422 e não escreve
  fora de `scenarios/` (paridade com
  `test_scenario.py::test_post_sessions_route_traversal_id_is_404`).
- Falha: `shutil.rmtree` monkeypatchado para levantar `OSError` → 500
  `delete failed`, com a pasta ainda presente.

## Rollout e kill switch

N/A — rotas novas, nada existente muda de comportamento. Desligar é não navegar
para `#/builder`. `risk: medium` porque as operações apagam e copiam pasta:
mitigado pelo confinamento via `scenario_path`, pelo `FOLDER_RE` e pela criação
em pasta temporária.

## Observabilidade

Eventos:
- `builder_scenario_created` — `scenario_id`, `locale`
- `builder_scenario_duplicated` — `source_id`, `scenario_id`
- `builder_scenario_deleted` — `scenario_id`
- `builder_scenario_write_failed` — `op`, `scenario_id`, `error`
- `scenario_invalid` (já existente) para pasta que não parseia.

Métrica de sucesso: criar um cenário pela API e ele aparecer na listagem
seguinte, com zero `builder_scenario_write_failed` no verde da fase.

## i18n

N/A — `detail` de erro é código em inglês, e a UI escolhe a mensagem traduzida
por status (padrão do `errors.ts` já existente). As chaves de tela ficam no
TCK-035.
