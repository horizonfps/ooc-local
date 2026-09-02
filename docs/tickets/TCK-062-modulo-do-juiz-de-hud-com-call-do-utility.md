---
id: TCK-062
title: Criar o módulo do juiz de HUD com o call do utility e o aplicador determinístico
status: done
points: 3
blockedBy: [TCK-060]
files:
  - backend/app/judge.py
  - backend/tests/test_judge.py
migration: false
ui: false
risk: low
---

## Problema

Depois do TCK-060 o cenário declara stats (`StatDef`) e a sessão guarda valores
(`HudState.stats`), e o TCK-061 faz a tag `[STAT:id:±N]` do narrador mexer neles.
Só que a tag é o único caminho: se o narrador esquecer de emitir a tag — e
modelo local esquece —, uma humilhação pública não mexe em `reputacao` e o HUD
fica congelado enquanto a história anda. Falta o segundo par de olhos: um call
curto ao papel `utility`, depois do turno, que olha o que aconteceu e propõe
ajustes em JSON.

Este ticket entrega só a peça isolada: montar o prompt, transformar a resposta
(texto livre de modelo local, quase sempre com cerca de código em volta) numa
proposta, e aplicar essa proposta ao HUD com regras determinísticas. A fiação no
`run_turn` é o TCK-069, que depende deste.

Sem este módulo, o TCK-069 não tem o que fiar; com ele mergeado antes, o TCK-069
vira só cola e telemetria.

## Escopo

Dentro:
- `backend/app/judge.py` novo: `JUDGE_OPTIONS`, constantes (`JUDGE_MAX_DELTA`,
  `MAX_DYNAMIC_STATS`, `JUDGE_NARRATOR_CHARS`, `JUDGE_RAW_LOG_CHARS`,
  `DYNAMIC_STAT_NAME_CHARS`, `STAT_ID_RE`), `_PROMPT_TEMPLATES` nos dois
  locales, `build_judge_messages`, `parse_judgement`, `apply_judgement`,
  `judge_turn`, `JudgeError`, e os modelos `StatChange` e `StatRejection`.
- `backend/tests/test_judge.py`: testes **de unidade**, sem `TestClient` e sem
  banco — cenário escrito em `tmp_path`, provider monkeypatchado, chamadas
  diretas às funções do módulo.

Fora (explícito):
- `backend/app/turn.py`, `backend/app/prompt.py`, `backend/app/sessions.py`,
  `backend/app/main.py`: nada deste ticket os toca. Telemetria `judge_applied` /
  `judge_rejected` / `judge_failed`, flag `hud_judge`, gravação do evento `stat`
  e `hud.stats` no SSE são todos TCK-069.
- Aplicar a tag `[STAT:id:±N]` (TCK-061, mesma wave, dono de `tags.py`,
  `hud.py`, `prompt.py`, `sessions.py` e `turn.py`). Este módulo só **recebe** a
  lista de ids que a tag já mexeu, em `touched_ids`, e não opina sobre eles.
- Definir a constante do kind do evento (`"stat"`) ou escrever qualquer evento.
  `STAT_EVENT_KIND`, `stat_event()`, `ensure_stats()`, `stat_ids()` e
  `apply_stat()` nascem em `hud.py` pelo TCK-061, que está **na mesma wave** e
  portanto não pode ser importado daqui. `judge.py` também não importa
  `app.sessions` — é módulo de prompt, parsing e regra pura, como `director.py`.
- Seção `## STATUS DO JOGADOR` do prompt do narrador: é TCK-061.
- Criar `StatDef`, `StatView`, `DynamicStat` ou `HudState.stats`: tudo vem
  congelado do TCK-060 e é consumido aqui sem redefinição.

## Comportamento esperado

Do ponto de vista do chamador (o TCK-069): passa cenário, HUD do turno, ação do
jogador, texto do narrador já limpo, os ids que a tag mexeu e a config; recebe a
proposta do utility já parseada, ou `None` com um motivo publicável em
telemetria, mais a resposta crua para log. Em seguida chama `apply_judgement`,
que é síncrono e puro, e recebe o HUD novo, a lista de mudanças efetivas e a
lista de rejeições com motivo.

Nada aqui levanta exceção crua: falha de provider, timeout e papel `utility`
ausente na config viram `JudgeError`. Resposta lixo vira motivo, nunca stack
trace. E `apply_judgement` nunca levanta: qualquer forma esquisita dentro do
JSON vira rejeição com motivo.

O jogador não vê nada deste ticket ainda — o módulo não é chamado por ninguém
até o TCK-069 entrar.

## Detalhes técnicos

Molde a copiar, linha a linha: `backend/app/director.py` (TCK-053) e seu teste
`backend/tests/test_director.py`. Mesma estrutura de templates por locale, mesmo
parser tolerante, mesma 3-tupla `(dados, motivo, raw)` na função async.

### Constantes e opções

```python
JUDGE_OPTIONS = GenerationOptions(max_tokens=200, temperature=0.1, timeout_s=45.0)
JUDGE_MAX_DELTA = 10
MAX_DYNAMIC_STATS = 6
JUDGE_NARRATOR_CHARS = 1200
JUDGE_RAW_LOG_CHARS = 200
DYNAMIC_STAT_NAME_CHARS = 40
STAT_ID_RE = re.compile(r"^[a-z0-9_-]+$")
```

`max_tokens=200` e `temperature=0.1` vêm do brief. `timeout_s=45.0` é o mesmo do
`DIRECTOR_OPTIONS` (`director.py:12`) e existe pelo mesmo motivo: o default de
120s do `GenerationOptions` (`llm/base.py`) faria o jogador esperar dois minutos
depois do último delta do narrador. `JUDGE_NARRATOR_CHARS` corta o texto do
narrador no prompt (o `format_body` pede ~350 palavras, mas o modelo estoura) e
`JUDGE_RAW_LOG_CHARS` existe para o TCK-069 cortar o `raw` antes de logar, como
`DIRECTOR_RAW_LOG_CHARS` já faz em `turn.py:284`.

### Imports do contrato congelado (TCK-060)

```python
from app.hud import DynamicStat, HudState
from app.scenario import LoadedScenario, StatDef
```

`StatDef` e `LoadedScenario.stats` / `ScenarioMeta.allow_dynamic_stats` vêm de
`app.scenario`; `DynamicStat` e `HudState.stats` / `HudState.dynamic_stats` vêm
de `app.hud`. É onde o TCK-060 os coloca: `hud.py` hoje não importa nada do
projeto além de `app.scenario` sob `TYPE_CHECKING` (`hud.py:8-9`), então importar
de lá não fecha ciclo com `judge.py`.

### Modelos deste ticket

```python
class StatChange(BaseModel):
    id: str
    delta: int
    value: int
    source: Literal["tag", "judge"]

class StatRejection(BaseModel):
    id: str
    reason: str
```

`StatChange` carrega exatamente os quatro campos do evento `stat` do brief 2.1.
Quem grava é o TCK-069, convertendo cada mudança com o helper do TCK-061:
`stat_event(change.id, change.delta, change.value, change.source)`, de `hud.py`.
Por isso `source` já nasce com `"tag"` no `Literal`: o mesmo modelo descreve a
mudança vinda da tag e a vinda do juiz, e o TCK-069 fica com um caminho só de
persistência.

`delta` é sempre a mudança **efetiva**: `value == valor_antes + delta`. Um stat
em 98/100 com proposta `+5` vira `StatChange(value=100, delta=2)`.

### `build_judge_messages(scenario, hud, message, narrator_text, touched_ids)`

Sistema (por locale): manda responder **só** o objeto JSON
`{"stats": {"id": -5}, "new": [...]}`, usando só ids da lista dada, delta inteiro
entre `-JUDGE_MAX_DELTA` e `+JUDGE_MAX_DELTA`, `{}` quando nada mudou, e proibindo
prosa. A parte de `new` só entra no texto do sistema quando
`scenario.meta.allow_dynamic_stats` é `True` — pedir stat novo a um cenário que
não aceita é convidar rejeição.

Corpo (mensagem de usuário), nesta ordem:
1. `[ATRIBUTOS]` / `[STATS]`, uma linha por stat declarado, na ordem de
   `scenario.stats`:
   `id | Nome | 55/0..100 | descrição`, com a descrição omitida quando `None`;
2. os dinâmicos de `hud.dynamic_stats` na mesma forma, sem descrição, em ordem de
   inserção do dict;
3. cada stat cujo id está em `touched_ids` recebe no fim da linha o marcador
   `(já ajustado neste turno)` / `(already adjusted this turn)`;
4. `AÇÃO DO JOGADOR` / `PLAYER ACTION` com `message`;
5. `NARRAÇÃO` / `NARRATION` com `narrator_text[:JUDGE_NARRATOR_CHARS]`.

Valor atual de um stat declarado: `hud.stats.get(stat.id, stat.default)`. Não
depende do `ensure_stats` do TCK-061 — sessão antiga sem a chave rende o default
aqui também, e o módulo continua puro.

Achatamento de campo com `|` e quebra de linha: copie o `_field` de
`director.py:55` (`" ".join(value.split()).replace("|", "/")`) para nome e
descrição, senão um nome com pipe quebra a tabela do prompt.

Locale: `_PROMPT_TEMPLATES.get(scenario.meta.locale, _PROMPT_TEMPLATES["pt-br"])`,
mesmo fallback de `director.py:76`.

### `parse_judgement(raw) -> tuple[dict | None, str | None]`

Cópia fiel de `parse_scene` (`director.py:101-122`): `json.loads` direto e, se
falhar, do primeiro `{` até o último `}`. Vazio, só espaço, sem `{`, JSON
quebrado ou raiz que não é objeto → `(None, "invalid_json")`. Objeto vazio `{}`
→ `({}, None)`: nada mudou é resposta legítima, não erro. Chaves fora de
`stats`/`new` são ignoradas sem reclamação. **Nenhuma validação de conteúdo
aqui**: o juiz é um só, e é o `apply_judgement`.

### `apply_judgement(scenario, hud, judgement, touched_ids) -> tuple[HudState, list[StatChange], list[StatRejection]]`

Puro, determinístico e sem exceção. Ordem fixa: primeiro `stats`, depois `new`.
Consequência documentada: delta para um id que a mesma resposta cria em `new`
cai em `unknown_id` — o stat só existe a partir do turno seguinte.

Conjunto judgeável = ids de `scenario.stats` mais as chaves de
`hud.dynamic_stats`, cada um com `(value, min, max)`. É a mesma regra que o
brief 2.1 dá para a tag.

`judgement.get("stats")`:
- não é `dict` (e não é ausente/`None`) → uma rejeição
  `StatRejection(id="stats", reason="not_a_map")`, e segue para `new`;
- para cada par, na ordem de inserção do JSON:
  - id fora do conjunto judgeável → `unknown_id`;
  - id em `touched_ids` → `touched_by_tag` (a tag tem precedência);
  - delta que não é `int`, **ou é `bool`** → `not_an_int`. `isinstance(True, int)`
    é `True` em Python; sem o `type(delta) is not bool` explícito, `{"vida": true}`
    viraria `+1`;
  - delta clampado em `[-JUDGE_MAX_DELTA, +JUDGE_MAX_DELTA]`, valor novo clampado
    em `[min, max]`;
  - valor novo igual ao atual → `no_change`, sem `StatChange` (regra "sem
    mudança, sem evento" do brief 2.1);
  - senão, `StatChange(id, delta=novo-atual, value=novo, source="judge")`.

`judgement.get("new")`:
- `scenario.meta.allow_dynamic_stats` falso e a lista não é vazia → uma rejeição
  `StatRejection(id="new", reason="dynamic_disabled")`, sem olhar item por item;
- não é `list` → `StatRejection(id="new", reason="not_a_list")`;
- por item, na ordem da lista:
  - `min` ausente → `0` (resolvido **antes** de qualquer comparação);
  - não é `dict`, ou `id`/`name` não são `str`, ou `value`/`max`/`min` não são
    `int` (com a mesma exclusão de `bool`), ou `max <= min` → `invalid_shape`
    (`id` da rejeição = o id proposto quando for `str`, senão `""`); a checagem
    de tipo roda antes de `max <= min`, então `min: "x"` nunca chega à
    comparação e nunca levanta `TypeError`;
  - id que não casa com `STAT_ID_RE` → `invalid_id`;
  - id que já é stat declarado, já está em `hud.dynamic_stats`, ou já foi criado
    nesta mesma chamada → `duplicate_id`;
  - contagem de `hud.dynamic_stats` mais os criados nesta chamada chegando a
    `MAX_DYNAMIC_STATS` → `over_cap` para este e para todos os seguintes;
  - aceito: `name` cortado em `DYNAMIC_STAT_NAME_CHARS` depois do `_field`,
    `value` clampado em `[min, max]`, entra em `dynamic_stats` como
    `DynamicStat(name=..., value=..., min=..., max=...)` e rende
    `StatChange(id, delta=0, value=<inicial>, source="judge")`.
    `delta=0` numa criação é intencional e é a única `StatChange` com delta zero:
    a mudança é o stat passar a existir, e o TCK-069 precisa do evento para o
    HUD do frontend acordar com a barra nova.

Retorno do HUD: `hud.model_copy(update={"stats": ..., "dynamic_stats": ...})`,
como `advance` e `apply_location` já fazem (`hud.py:65,79`). Sempre que não
houver nenhuma `StatChange` (nem stat dinâmico criado), devolva o **mesmo objeto**
`hud` recebido, independentemente de quantas rejeições houve; `changes` vem vazia
e `rejected` traz o que foi rejeitado. O chamador usa `hud_novo is hud` /
`changes == []` para decidir se grava.

`stats` do HUD novo carrega **todos** os ids declarados (valor atual ou default)
mais os que já estavam lá, para que a sessão pare de depender de default depois
do primeiro julgamento.

**Clamp duplicado, de propósito.** O TCK-061 põe `apply_stat` em `hud.py` com a
mesma aritmética de clamp, e está na mesma wave: importar de lá aqui quebraria a
independência dos dois PRs. Escreva o clamp num `_apply_one` privado de dez
linhas. Não é dívida escondida — o juiz tem duas regras que `apply_stat` não tem
(teto de `JUDGE_MAX_DELTA` no delta e criação de dinâmico), e o TCK-069, que vê
os dois módulos já mergeados, é quem decide se vale unificar.

### `judge_turn(scenario, hud, message, narrator_text, touched_ids, config)`

Igual a `decide_scene` (`director.py:125-147`):

```python
try:
    role = config.models["utility"]
except KeyError:
    raise JudgeError("no utility role") from None
provider = OpenAICompatProvider(config.providers[role.provider], JUDGE_OPTIONS)
```

`config.models["utility"]` ausente não é hipótese: a config de teste de
`backend/tests/test_turn.py:60` declara só `narrator`. Qualquer exceção do
`provider.complete` vira `JudgeError`. Devolve `(judgement, reason, raw)` com o
`raw` inteiro, sem corte.

Comentários em inglês e mínimos, como o resto do backend.

### Ressalva de porte

Estimativa: ~800 linhas com testes, acima do alvo de ~400 (o molde TCK-053, também
de 3 pontos, fechou em 544). Aceito pelo coordenador porque o módulo é puro e o
volume é de casos de teste, não de lógica. Se o diff passar de ~600, corte nesta
ordem: (1) agrupe os casos de `parse_judgement` malformado num único
`pytest.mark.parametrize`; (2) agrupe as rejeições nomeadas de `apply_judgement` num
`parametrize` por motivo; (3) mantenha um caso feliz completo e um de clamp fora
do `parametrize`, porque são os que documentam o contrato.

## Contrato público

```python
# backend/app/judge.py
JUDGE_OPTIONS: GenerationOptions          # max_tokens=200, temperature=0.1, timeout_s=45.0
STAT_ID_RE: re.Pattern                    # ^[a-z0-9_-]+$, id de stat dinamico proposto
JUDGE_MAX_DELTA: int = 10
MAX_DYNAMIC_STATS: int = 6
JUDGE_NARRATOR_CHARS: int = 1200
JUDGE_RAW_LOG_CHARS: int = 200
DYNAMIC_STAT_NAME_CHARS: int = 40

class JudgeError(Exception): ...

class StatChange(BaseModel):
    id: str
    delta: int          # effective change; value == previous + delta
    value: int
    source: Literal["tag", "judge"]

class StatRejection(BaseModel):
    id: str             # "stats" / "new" for section-level rejections
    reason: str

def build_judge_messages(
    scenario: LoadedScenario,
    hud: HudState,
    message: str,
    narrator_text: str,
    touched_ids: list[str],
) -> list[ChatMessage]

def parse_judgement(raw: str) -> tuple[dict | None, str | None]
    # reasons: "invalid_json"

def apply_judgement(
    scenario: LoadedScenario,
    hud: HudState,
    judgement: dict,
    touched_ids: list[str],
) -> tuple[HudState, list[StatChange], list[StatRejection]]
    # rejection reasons: "unknown_id" | "touched_by_tag" | "not_an_int" |
    #                    "no_change" | "not_a_map" | "not_a_list" |
    #                    "dynamic_disabled" | "invalid_shape" | "invalid_id" |
    #                    "duplicate_id" | "over_cap"

async def judge_turn(
    scenario: LoadedScenario,
    hud: HudState,
    message: str,
    narrator_text: str,
    touched_ids: list[str],
    config: Config,
) -> tuple[dict | None, str | None, str]
    # (judgement, reason, raw) — raw uncut, for the caller to log
```

Consumido pelo TCK-069, que declara este ticket em `blockedBy`. Ele grava cada
`StatChange` com `stat_event(...)` de `app.hud` (TCK-061); `judge.py` não escreve
evento nenhum.

## Acceptance criteria

- [ ] `judge_turn` com o utility devolvendo `{"stats": {"reputacao": -5}}`
      retorna `({"stats": {"reputacao": -5}}, None, raw)`, com `raw` idêntico à
      resposta crua do provider.
- [ ] Resposta embrulhada em cerca de código ou com prosa antes e depois do
      objeto é aceita; `{}` retorna `({}, None)`.
- [ ] `parse_judgement` com string vazia, só espaço, prosa sem `{`, JSON
      quebrado ou raiz lista retorna `(None, "invalid_json")`.
- [ ] Config sem o papel `utility` levanta `JudgeError("no utility role")` sem
      tocar no provider; exceção do provider vira `JudgeError`.
- [ ] `apply_judgement` com `{"stats": {"reputacao": -5}}` sobre `reputacao=50`
      devolve HUD com 45 e uma `StatChange(id="reputacao", delta=-5, value=45,
      source="judge")`.
- [ ] Delta `+40` vira `+JUDGE_MAX_DELTA`; stat em 98/100 com delta `+5` fecha em
      100 com `delta=2`; stat já no máximo com delta `+5` não gera `StatChange` e
      gera rejeição `no_change`.
- [ ] Id desconhecido gera rejeição `unknown_id`, id em `touched_ids` gera
      `touched_by_tag`, e nenhum dos dois muda o HUD.
- [ ] Com `allow_dynamic_stats: false`, qualquer `new` gera uma única rejeição
      `dynamic_disabled` e `hud.dynamic_stats` fica intacto.
- [ ] Com `allow_dynamic_stats: true`, `new` válido cria o `DynamicStat` com
      `min` 0 por default, valor clampado em `[min, max]`, e uma `StatChange` com
      `delta=0`.
- [ ] `new` com id `"Vida!"` gera `invalid_id`; id igual a um stat declarado gera
      `duplicate_id`; o sétimo dinâmico da sessão gera `over_cap`.
- [ ] `{"stats": {"vida": true}}` gera `not_an_int` e não muda o HUD.
- [ ] `apply_judgement` com `{}` devolve o mesmo HUD e duas listas vazias.
- [ ] O prompt lista todos os stats declarados com valor/min/max, marca os de
      `touched_ids`, termina com a narração cortada em `JUDGE_NARRATOR_CHARS`, e
      só menciona criação de stat quando `allow_dynamic_stats` é `True`.
- [ ] Cenário `locale: en` produz prompt sem nenhuma palavra dos templates
      pt-br, e vice-versa.
- [ ] `JUDGE_OPTIONS.max_tokens == 200`, `temperature == 0.1`,
      `timeout_s == 45.0`.
- [ ] `judge.py` não importa `app.sessions` nem `app.turn`.
- [ ] `npm run check:api` verde.

## Cenários de teste

**Suíte existente que muda de preparação: nenhuma.** O módulo é novo, ninguém o
importa até o TCK-069, e `grep` por `judge` em `backend/` hoje só acha o
docstring de `cast.py:35`. `backend/tests/test_turn.py`,
`backend/tests/test_turn_director.py` e `backend/tests/test_director.py` seguem
intocados. **Nenhum teste atual cobre o fluxo de juiz de HUD, porque ele não
existe** — a cobertura nasce inteira aqui.

Cenários novos em `backend/tests/test_judge.py` (unidade, no molde de
`backend/tests/test_director.py`: cenário escrito em `tmp_path`,
`monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)`,
`OpenAICompatProvider.stream_chat` monkeypatchado, `asyncio.run` para as
corrotinas). Fixture base: cenário com `stats.yaml` de dois stats —
`reputacao` (0..100, default 50, com descrição) e `energia` (0..100, default 80,
sem descrição) — e `allow_dynamic_stats` ligado ou desligado conforme o teste.
HUD base: `HudState(turn=3, location="patio", time="09:30", weather="cloudy",
stats={"reputacao": 50, "energia": 80})`.

`parse_judgement`:
- Feliz: `'{"stats": {"reputacao": -5}}'` → `({"stats": {"reputacao": -5}}, None)`.
- Feliz: `'claro:\n```json\n{"stats": {}}\n```\npronto'` → `({"stats": {}}, None)`.
- Borda: `"{}"` → `({}, None)`.
- Borda: chave extra (`{"stats": {}, "comentario": "..."}`) é aceita e ignorada.
- Falha (**JSON malformado**): `""`, `"   "`, `"a reputação cai"`,
  `'{"stats": {'`, `'[{"stats": {}}]'` → todos `(None, "invalid_json")`.

`apply_judgement` — stats existentes:
- Feliz: `{"stats": {"reputacao": -5}}` → HUD com `reputacao=45`, uma
  `StatChange(id="reputacao", delta=-5, value=45, source="judge")`, zero
  rejeições.
- Feliz: dois ids na mesma resposta produzem duas `StatChange` na ordem do JSON.
- Borda (**clamp que clampa**): `{"stats": {"reputacao": 40}}` → `delta=10`,
  `value=60`; `{"stats": {"reputacao": -999}}` → `delta=-10`, `value=40`.
- Borda (**clamp que clampa**): HUD com `reputacao=98` e delta `+5` → `value=100`,
  `delta=2`.
- Borda: HUD com `reputacao=100` e delta `+5` → nenhuma `StatChange`, rejeição
  `no_change`, HUD devolvido é o mesmo objeto recebido.
- Borda: `{"stats": {"fantasma": -3}}` → rejeição `unknown_id`.
- Borda: `touched_ids=["reputacao"]` com `{"stats": {"reputacao": -5}}` →
  rejeição `touched_by_tag`, HUD intacto.
- Borda: stat dinâmico já em `hud.dynamic_stats` aceita delta como qualquer
  outro.
- Borda: `{"stats": {"reputacao": true}}` e `{"stats": {"reputacao": "muito"}}` →
  `not_an_int` nos dois.
- Borda: `{"stats": []}` → rejeição `StatRejection(id="stats",
  reason="not_a_map")`, sem exceção.
- Borda: `{}` → `(hud, [], [])`.

`apply_judgement` — stats novos:
- Feliz (`allow_dynamic_stats: true`): `{"new": [{"id": "vida", "name": "Vida",
  "value": 110, "max": 110}]}` → `dynamic_stats["vida"] == DynamicStat(name="Vida",
  value=110, min=0, max=110)` e `StatChange(id="vida", delta=0, value=110)`.
- Borda (**clamp que clampa**): `value: 999` com `max: 110` entra como 110;
  `name` de 90 caracteres entra cortado em `DYNAMIC_STAT_NAME_CHARS`.
- Borda: `allow_dynamic_stats: false` → uma única rejeição
  `StatRejection(id="new", reason="dynamic_disabled")`, `dynamic_stats` vazio.
- Borda: `{"new": "vida"}` → `StatRejection(id="new", reason="not_a_list")`.
- Borda: item sem `max`, com `max <= min`, ou com `value` string → `invalid_shape`.
- Borda: `id: "Vida!"` → `invalid_id`; `id: "reputacao"` → `duplicate_id`; dois
  itens com o mesmo id → o segundo é `duplicate_id`.
- Borda: HUD já com 6 dinâmicos e um `new` válido → `over_cap` e HUD intacto;
  lista de 3 itens com 5 dinâmicos existentes → o primeiro entra, os outros dois
  saem `over_cap`.
- Borda: delta em `stats` para um id que a mesma resposta cria em `new` →
  `unknown_id` no delta e criação aceita (prova da ordem `stats` antes de `new`).

`build_judge_messages`:
- Feliz: o corpo traz `reputacao | Reputação | 50/0..100 | Quanto a escola te
  respeita.` e `energia | Energia | 80/0..100` sem cauda de descrição.
- Borda: `touched_ids=["energia"]` marca só a linha de `energia`.
- Borda: narração de 5000 caracteres aparece cortada em `JUDGE_NARRATOR_CHARS`.
- Borda: `hud.stats` vazio usa o `default` de cada `StatDef`.
- Borda: `allow_dynamic_stats: false` → o texto do sistema não fala em criar
  stat; `true` → fala.
- Borda: nome com `|` e quebra de linha sai achatado (`aluna do / clube`, molde
  de `test_director.py`).
- Borda: `locale: en` não contém `AÇÃO DO JOGADOR`; `locale: pt-br` não contém
  `PLAYER ACTION`.

`judge_turn`:
- Feliz: resposta `{"stats": {"reputacao": -5}}` → `(judgement, None, raw)` com
  `raw` idêntico.
- Feliz: provider construído com `JUDGE_OPTIONS` (spy em
  `OpenAICompatProvider.__init__`, molde de `test_director.py`).
- Falha: config sem papel `utility` → `JudgeError`, e o provider nunca é chamado.
- Falha: provider que levanta `RuntimeError` → `JudgeError`.
- Falha: resposta `"   "` → `(None, "invalid_json", "   ")`.

## Rollout e kill switch

N/A — `risk: low`. Mergear este ticket não muda comportamento de jogo nenhum:
nada importa `judge.py` até o TCK-069. A flag `hud_judge` (default ligado, via
`config.flag`, `config.py:43`) é definida e testada no TCK-069, que é quem liga
o módulo ao turno.

## Observabilidade

Eventos: nenhum. `judge.py` não emite telemetria — devolve motivo e rejeições, e
o TCK-069 publica `judge_applied` / `judge_rejected` / `judge_failed` num único
ponto de `emit` por turno, como `turn.py:228-287` já faz com o director.
`JUDGE_RAW_LOG_CHARS` existe para o chamador cortar o `raw` antes de logar.
Métrica de sucesso: nos testes de unidade, cerca de código e prosa em volta do
objeto são **aceitas** por `parse_judgement`, as 5 formas que de fato falham
(`""`, `"   "`, prosa sem `{`, `'{"stats": {'`, `'[{"stats": {}}]'`) caem em
`invalid_json`, e as 11 formas de
proposta inválida caem em rejeição nomeada — nenhuma delas levanta exceção nem
altera o HUD.

## i18n

Sem chave de `frontend/src/strings/*`. O prompt do juiz nasce nos dois locales em
`_PROMPT_TEMPLATES` dentro de `backend/app/judge.py`, no formato de
`director.py:17` (`system` mais rótulos do corpo), escolhido por
`scenario.meta.locale` com fallback `pt-br`:

| chave | pt-br | en |
|---|---|---|
| `system` | responda só `{"stats": {...}}`, delta inteiro entre -10 e +10, `{}` quando nada mudou, sem prosa | idem em inglês |
| `system_dynamic` | trecho extra, só com `allow_dynamic_stats`: pode propor `"new"` com id, nome, valor e máximo | idem em inglês |
| `stats_label` | `ATRIBUTOS` | `STATS` |
| `touched_label` | `(já ajustado neste turno)` | `(already adjusted this turn)` |
| `action_label` | `AÇÃO DO JOGADOR` | `PLAYER ACTION` |
| `narration_label` | `NARRAÇÃO` | `NARRATION` |

Nome, descrição e level de stat vêm do cenário e não passam por template: já
estão no locale do cenário.
