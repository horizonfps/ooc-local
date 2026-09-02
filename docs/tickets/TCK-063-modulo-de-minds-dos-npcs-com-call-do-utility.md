---
id: TCK-063
title: Criar o módulo de minds dos NPCs com o call do utility e o merge determinístico
status: ready
points: 3
blockedBy: [TCK-060]
files:
  - backend/app/minds.py
  - backend/tests/test_minds.py
migration: false
ui: false
risk: low
---

## Problema

A ficha de cada personagem em cena entra no prompt com `Sentimento atual` e
`Objetivo` fixos do arquivo do cenário (`prompt.py:_format_character`,
`scenario.py:CharacterMind`). Ou seja: a Chloe continua "curiosa" no turno 40,
mesmo depois de o jogador ter mentido para ela três vezes. O jogador também não
tem como saber o que cada NPC está achando dele — nada na tela diz isso.

Falta a peça que lê o turno recém-narrado e propõe, para cada NPC em cena, uma
mente curta (`attitude`, `emoji`, `event`) que vira o bloco INFO na tela e a
linha `Estado atual` na ficha do prompt.

Este ticket entrega só a peça isolada: prompt, parsing tolerante e merge
determinístico com o mapa anterior. A fiação no `run_turn`, a persistência do
evento `minds` e o bloco INFO na UI são TCK-069 e TCK-067.

## Escopo

Dentro:
- `backend/app/minds.py` novo: `MINDS_OPTIONS`, constantes
  (`MIND_FIELD_CHARS`, `EMOJI_CHARS`, `MIND_FIELDS`, `MINDS_NARRATOR_CHARS`,
  `MINDS_RAW_LOG_CHARS`, `MIND_SHEET_CHARS`), `_PROMPT_TEMPLATES` nos dois
  locales, `build_minds_messages`, `parse_minds`, `merge_minds`, `think_minds`,
  `MindsError` e o modelo `MindRejection`.
- `backend/tests/test_minds.py`: testes **de unidade**, sem `TestClient` e sem
  banco — cenário em `tmp_path`, provider monkeypatchado, chamadas diretas.

Fora (explícito):
- `backend/app/turn.py`, `backend/app/sessions.py`, `backend/app/prompt.py`,
  `backend/app/main.py`. Evento `minds`, `read_minds(session_id)`, `hud.minds`
  no SSE, `SessionDetail.minds`, linha `Estado atual` na ficha do prompt,
  telemetria `minds_*` e flag `minds` são todos TCK-069.
- Bloco INFO / `InfoTracker.tsx`: TCK-067.
- Definir `MindView`, `MIND_EVENT_KIND` e `minds_event()`: os três nascem em
  `backend/app/cast.py` pelo TCK-060; aqui só se consome `MindView`, sem
  redefinir nada.
- Ler ou escrever no event store. `minds.py` não importa `app.sessions`, mesma
  regra do `director.py` (TCK-053).
- Decidir quem está em cena: isso é o director (`app.director`, TCK-053/055).
  Este módulo **recebe** `cast_ids` pronto.

## Comportamento esperado

Do ponto de vista do chamador (o TCK-069): passa cenário, ids em cena, o mapa de
mentes anterior, a ação do jogador e o texto do narrador; recebe a proposta
parseada ou `None` com motivo, mais o `raw` para log. Em seguida chama
`merge_minds`, síncrono e puro, e recebe **o mapa completo** para gravar mais a
lista de rejeições.

Semântica do retorno de `merge_minds`, que é a decisão central deste ticket:
**mapa completo, não delta.** O evento `minds` do brief 2.3 guarda
`{entries: {id: MindView}}` inteiro, e `read_minds` devolve só o último evento —
não existe replay somando deltas. Então `merge_minds` devolve `previous`
sobrescrito pelas entradas aceitas, incluindo NPCs que saíram de cena e não
foram propostos neste turno: a mente deles fica congelada no último valor e volta
inteira quando eles voltam. Gravar só o delta faria a Chloe perder a memória ao
sair da cena por um turno.

Quando nada é aceito, o mapa devolvido é igual ao anterior; o chamador compara
(`entries != previous`) e só grava evento quando mudou — é o brief 2.3 ("sempre
que algo mudou").

O jogador não vê nada deste ticket ainda: nada importa `minds.py` até o TCK-069.

## Detalhes técnicos

Molde a copiar: `backend/app/director.py` (TCK-053) e
`backend/tests/test_director.py`. Mesma estrutura de templates por locale, mesmo
parser tolerante, mesma 3-tupla `(dados, motivo, raw)` na função async.

### Constantes e opções

```python
MINDS_OPTIONS = GenerationOptions(max_tokens=300, temperature=0.2, timeout_s=45.0)
MIND_FIELD_CHARS = 120
EMOJI_CHARS = 4
MIND_FIELDS = ("attitude", "emoji", "event")
MINDS_NARRATOR_CHARS = 1200
MINDS_RAW_LOG_CHARS = 200
MIND_SHEET_CHARS = 160
```

`max_tokens=300` porque a saída é três campos por NPC e a cena chega a
`MAX_CAST_IN_SCENE = 6` (`cast.py:8`): 120 tokens do director não cobrem.
`temperature=0.2` é o mesmo do `COMPACT_OPTIONS` (`compact.py:19`), que é o
precedente de call do utility que produz texto e não só ids. `timeout_s=45.0`
pelo mesmo motivo do director: o default de 120s do `GenerationOptions` viraria
espera visível depois do último delta do narrador.

### Imports do contrato congelado (TCK-060)

```python
from app.cast import MindView
from app.scenario import Character, LoadedScenario
```

`MindView` (`{attitude: str, emoji: str, event: str}`) mora em `app.cast`, ao
lado de `CastMember`, `MIND_EVENT_KIND` e `minds_event()` — é onde o TCK-060 a
coloca. `cast.py` importa só `pydantic` e `app.scenario` (`cast.py:1-5`), então
importar de lá não fecha ciclo nem arrasta o event store para dentro deste
módulo, que é o que a regra do TCK-053 proíbe.

### `build_minds_messages(scenario, cast_ids, previous, message, narrator_text)`

Sistema (por locale): manda responder **só** o objeto JSON
`{"id": {"attitude": "...", "emoji": "🤨", "event": "..."}}` com ids da lista
dada, `attitude` e `event` em no máximo `MIND_FIELD_CHARS` caracteres, `emoji`
com **um** emoji, `{}` quando nada mudou, sem prosa e sem nome de personagem no
lugar do id.

Corpo (mensagem de usuário), nesta ordem:
1. `[NPCS EM CENA]` / `[NPCS IN SCENE]`, uma linha por id de `cast_ids` que
   existe em `scenario.characters`, na ordem recebida:
   `id | Nome | <ficha> | agora: ...`, onde `<ficha>` é a string
   `papel | personalidade | sentimento: X | objetivo: Y` com cada campo achatado
   pelo `_field` de `director.py:55` e **só essa string** cortada em
   `MIND_SHEET_CHARS` (`ficha[:MIND_SHEET_CHARS]`, corte duro, sem reticências);
   `id | Nome |` e o sufixo `| agora:` do item 2 ficam fora do corte. É a "ficha
   resumida" do brief 2.3, não a ficha inteira do `prompt.py`, que gastaria o
   orçamento do call. Exemplo: personalidade de 300 chars com papel `aluna` →
   a linha começa com `chloe | Chloe | aluna | ` e a ficha inteira tem exatamente
   160 chars antes do ` | agora:`;
2. na mesma linha, quando existe `previous[id]`:
   `| agora: {emoji} {attitude}` / `| now: ...`;
3. `AÇÃO DO JOGADOR` / `PLAYER ACTION` com `message`;
4. `NARRAÇÃO` / `NARRATION` com `narrator_text[:MINDS_NARRATOR_CHARS]`.

Id em `cast_ids` que não existe mais em `scenario.characters` é pulado sem erro
(o autor pode ter apagado o personagem entre sessões; `load_turn_context`
já filtra assim em `turn.py:64`).

Locale: `_PROMPT_TEMPLATES.get(scenario.meta.locale, _PROMPT_TEMPLATES["pt-br"])`,
mesmo fallback de `director.py:76`.

### `parse_minds(raw) -> tuple[dict | None, str | None]`

Cópia fiel de `parse_scene` (`director.py:101-123`): `json.loads` direto e, se
falhar, do primeiro `{` até o último `}`. Vazio, só espaço, sem `{`, JSON
quebrado ou raiz que não é objeto → `(None, "invalid_json")`. `{}` →
`({}, None)`. Nenhuma validação de conteúdo aqui: o juiz é o `merge_minds`.

### `merge_minds(previous, proposed, cast_ids) -> tuple[dict[str, MindView], list[MindRejection]]`

Puro, determinístico, sem exceção.

- `proposed` que não é `dict` → `(dict(previous), [MindRejection(id="",
  reason="not_a_map")])`.
- Para cada par, na ordem de inserção do JSON:
  - id fora de `cast_ids` → `not_in_scene` (inclui o caso do modelo devolver o
    **nome** em vez do id, que é o erro mais comum);
  - valor que não é `dict` → `invalid_shape`;
  - campo a campo, para `MIND_FIELDS`: usa o proposto quando é `str`; senão cai
    para `previous[id]` daquele campo; senão `""`. Campo ausente e campo com tipo
    errado seguem o mesmo caminho — tolerância é o ponto, e o motivo por campo
    não teria consumidor;
  - `attitude` e `event` cortados em `MIND_FIELD_CHARS`, com `_field` antes (uma
    atitude com quebra de linha estragaria a linha do INFO na UI);
  - `emoji` cortado em `EMOJI_CHARS` **por code point**, com remoção do ZWJ
    (`‍`) e do variation selector (`️`) que sobrarem no fim: cortar
    `👨‍👩‍👧` (5 code points) em 4 deixa um ZWJ pendurado, que alguns renderers
    mostram como caixa vazia;
  - entrada cujos três campos terminam vazios → `empty`, e ela não entra no mapa
    (mente vazia na tela é pior que ausência, que a UI já sabe mostrar como
    placeholder);
  - senão, entra em `entries[id] = MindView(...)`.
- Resultado: `{**previous, **aceitas}`. `previous` nunca é mutado.
- `merge_minds` **não poda** ids que sumiram do cenário: quem lê o evento é o
  TCK-069, e a poda contra `scenario.characters` é dele, no mesmo lugar em que
  `load_turn_context` já poda `cast_ids` (`turn.py:64`).

```python
class MindRejection(BaseModel):
    id: str      # "" for the root-level rejection
    reason: str
```

### `think_minds(scenario, cast_ids, previous, message, narrator_text, config)`

Igual a `decide_scene` (`director.py:125-147`):

```python
try:
    role = config.models["utility"]
except KeyError:
    raise MindsError("no utility role") from None
provider = OpenAICompatProvider(config.providers[role.provider], MINDS_OPTIONS)
```

`config.models["utility"]` ausente não é hipótese: a config de teste de
`backend/tests/test_turn.py:60` declara só `narrator`. Qualquer exceção do
`provider.complete` vira `MindsError`. Devolve `(proposed, reason, raw)` com o
`raw` inteiro, sem corte. Nome `think_minds` e não `read_minds` porque
`sessions.read_minds` (TCK-069) é outra coisa: lê o último evento do banco.

Comentários em inglês e mínimos, como o resto do backend.

### Ressalva de porte

Estimativa: ~650 linhas com testes, acima do alvo de ~400 (o molde TCK-053, também
de 3 pontos, fechou em 544). Aceito pelo coordenador porque o módulo é puro e o
volume é de casos de teste, não de lógica. Se o diff passar de ~550, corte nesta
ordem: (1) agrupe os casos de `parse_minds` malformado num único
`pytest.mark.parametrize`; (2) agrupe as rejeições nomeadas de `merge_minds` num
`parametrize` por motivo; (3) mantenha um caso feliz completo e um de clamp fora
do `parametrize`, porque são os que documentam o contrato.

## Contrato público

```python
# backend/app/minds.py
MINDS_OPTIONS: GenerationOptions        # max_tokens=300, temperature=0.2, timeout_s=45.0
MIND_FIELD_CHARS: int = 120
EMOJI_CHARS: int = 4
MIND_FIELDS: tuple[str, str, str] = ("attitude", "emoji", "event")
MINDS_NARRATOR_CHARS: int = 1200
MINDS_RAW_LOG_CHARS: int = 200
MIND_SHEET_CHARS: int = 160

class MindsError(Exception): ...

class MindRejection(BaseModel):
    id: str
    reason: str

def build_minds_messages(
    scenario: LoadedScenario,
    cast_ids: list[str],
    previous: dict[str, MindView],
    message: str,
    narrator_text: str,
) -> list[ChatMessage]

def parse_minds(raw: str) -> tuple[dict | None, str | None]
    # reasons: "invalid_json"

def merge_minds(
    previous: dict[str, MindView],
    proposed: dict,
    cast_ids: list[str],
) -> tuple[dict[str, MindView], list[MindRejection]]
    # returns the COMPLETE map to persist, never a delta
    # rejection reasons: "not_a_map" | "not_in_scene" | "invalid_shape" | "empty"

async def think_minds(
    scenario: LoadedScenario,
    cast_ids: list[str],
    previous: dict[str, MindView],
    message: str,
    narrator_text: str,
    config: Config,
) -> tuple[dict | None, str | None, str]
    # (proposed, reason, raw) — raw uncut, for the caller to log
```

Consumido pelo TCK-069, que declara este ticket em `blockedBy`. Quem persiste é
ele, com `minds_event(entries)` de `app.cast` (TCK-060): este módulo devolve o
mapa completo e não escreve evento nenhum.

## Acceptance criteria

- [ ] `think_minds` com o utility devolvendo
      `{"chloe": {"attitude": "desconfiada", "emoji": "🤨", "event": "viu você
      pegar o caderno"}}` retorna `(proposta, None, raw)` com `raw` idêntico à
      resposta crua.
- [ ] Resposta com cerca de código ou prosa em volta é aceita; `{}` retorna
      `({}, None)`.
- [ ] `parse_minds` com string vazia, prosa sem `{`, JSON quebrado ou raiz lista
      retorna `(None, "invalid_json")`.
- [ ] Config sem papel `utility` levanta `MindsError("no utility role")` sem
      tocar no provider; exceção do provider vira `MindsError`.
- [ ] `merge_minds` devolve o mapa completo: id em `previous` que não foi
      proposto neste turno continua no resultado com o valor anterior.
- [ ] Id fora de `cast_ids` é rejeitado com `not_in_scene` e não entra no mapa.
- [ ] Campo ausente é completado com o valor anterior daquele NPC; sem valor
      anterior, com `""`.
- [ ] `attitude` e `event` maiores que `MIND_FIELD_CHARS` saem cortados em
      exatamente `MIND_FIELD_CHARS`; `emoji` sai cortado em `EMOJI_CHARS` sem ZWJ
      no fim.
- [ ] Entrada cujos três campos ficam vazios é rejeitada com `empty`.
- [ ] `previous` passado à função não é mutado (comparação com uma cópia feita
      antes da chamada).
- [ ] O prompt lista uma linha por NPC em cena com id, nome e ficha resumida,
      inclui a mente atual quando existe, e termina com a narração cortada em
      `MINDS_NARRATOR_CHARS`.
- [ ] Cenário `locale: en` produz prompt sem nenhuma palavra dos templates
      pt-br, e vice-versa.
- [ ] `MINDS_OPTIONS.max_tokens == 300` e `timeout_s == 45.0`.
- [ ] `minds.py` não importa `app.sessions` nem `app.turn`.
- [ ] `npm run check:api` verde.

## Cenários de teste

**Suíte existente que muda de preparação: nenhuma.** O módulo é novo e ninguém o
importa até o TCK-069; `grep -rn "minds" backend/app` hoje devolve zero linhas,
e `grep -rni "mind" backend/app` só acha `CharacterMind` em `scenario.py`,
`character.mind` em `builder_doc.py:230-238` e
`character.mind` em `prompt.py`, que este ticket lê e não altera. `backend/tests/test_prompt.py` e
`backend/tests/test_turn.py` seguem intocados. **Nenhum teste atual cobre o
fluxo de mente dinâmica de NPC, porque ele não existe** — a cobertura nasce
inteira aqui.

Cenários novos em `backend/tests/test_minds.py` (unidade, molde de
`backend/tests/test_director.py`: cenário em `tmp_path`,
`monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)`,
`OpenAICompatProvider.stream_chat` monkeypatchado, `asyncio.run`). Fixture base:
cenário com `chloe` e `renan`, `cast_ids = ["chloe", "renan"]`.

`parse_minds`:
- Feliz: `'{"chloe": {"attitude": "curiosa", "emoji": "🙂", "event": "te viu"}}'`
  → dicionário igual, `reason is None`.
- Feliz: mesma resposta dentro de ```` ```json ... ``` ```` com prosa antes e
  depois.
- Borda: `"{}"` → `({}, None)`.
- Falha (**JSON malformado**): `""`, `"   "`, `"a Chloe ficou desconfiada"`,
  `'{"chloe": {'`, `'[{"chloe": {}}]'` → todos `(None, "invalid_json")`.

`merge_minds`:
- Feliz: `previous={}`, proposta com `chloe` completa → `entries` com uma
  `MindView` igual à proposta, zero rejeições.
- Feliz (**mapa completo**): `previous={"renan": MindView(...)}`, proposta só com
  `chloe` → resultado tem `chloe` e `renan`, com `renan` byte a byte igual ao
  anterior.
- Feliz: proposta para um id **fora** de `cast_ids` mas presente em `previous`
  não apaga a entrada anterior; só é rejeitada.
- Borda (**clamp que clampa**): `attitude` com 500 caracteres →
  `len(entries["chloe"].attitude) == MIND_FIELD_CHARS`.
- Borda (**clamp que clampa**): `emoji: "🤨🤨🤨🤨🤨"` → 4 code points;
  `emoji: "👨‍👩‍👧"` → sai sem `‍` no fim.
- Borda: proposta sem `event`, com `previous["chloe"].event == "te viu"` →
  `event` continua `"te viu"`; sem anterior → `""`.
- Borda: `{"chloe": {"attitude": 7, "emoji": [], "event": None}}` com `previous`
  vazio → todos os campos caem para `""`, a entrada fica vazia e é rejeitada com
  `empty`.
- Borda: `{"Chloe": {...}}` (nome capitalizado, não id) → `not_in_scene`.
- Borda: `{"chloe": "desconfiada"}` → `invalid_shape`.
- Borda: `merge_minds(previous, [], cast_ids)` → `(previous copiado,
  [MindRejection(id="", reason="not_a_map")])`, sem exceção.
- Borda: `merge_minds(previous, {}, cast_ids)` → resultado igual a `previous` e
  zero rejeições (o chamador vê `entries == previous` e não grava evento).
- Borda (em `parse_minds`, não em `merge_minds`): duas propostas para o mesmo id
  na mesma resposta; a última vence por construção do `json.loads` — teste
  documental que chama `parse_minds('{"chloe": {...A...}, "chloe": {...B...}}')`
  e afirma que o dict devolvido tem B, e nada quebra.

`build_minds_messages`:
- Feliz: corpo com `chloe | Chloe |` e `renan | Renan |`, ação do jogador e
  narração.
- Borda: com `previous["chloe"]`, a linha da Chloe traz o emoji e a atitude
  atuais; a do Renan não traz o rótulo de mente atual.
- Borda: `cast_ids` com id inexistente no cenário é pulado sem erro e sem
  aparecer no prompt.
- Borda: narração de 5000 caracteres sai cortada em `MINDS_NARRATOR_CHARS`.
- Borda: personalidade de 300 chars → a ficha na linha do NPC tem exatamente
  `MIND_SHEET_CHARS` chars entre o segundo ` | ` e o ` | agora:` (ou o fim da
  linha, sem mente anterior); `id | Nome | ` não entra no corte.
- Borda: `locale: en` não contém `NPCS EM CENA`; `locale: pt-br` não contém
  `NPCS IN SCENE`.

`think_minds`:
- Feliz: resposta válida → `(proposta, None, raw)` com `raw` idêntico.
- Feliz: provider construído com `MINDS_OPTIONS` (spy em
  `OpenAICompatProvider.__init__`, molde de `test_director.py`).
- Falha: config sem papel `utility` → `MindsError`, provider nunca chamado.
- Falha: provider que levanta `RuntimeError` → `MindsError`.
- Falha: resposta `"   "` → `(None, "invalid_json", "   ")`.

## Rollout e kill switch

N/A — `risk: low`. Mergear este ticket não muda comportamento de jogo nenhum:
nada importa `minds.py` até o TCK-069. A flag `minds` (default ligado, via
`config.flag`, `config.py:43`) é definida e testada no TCK-069.

## Observabilidade

Eventos: nenhum. `minds.py` não emite telemetria — devolve motivo e rejeições, e
o TCK-069 publica `minds_applied` / `minds_rejected` / `minds_failed` num único
ponto de `emit` por turno, como `turn.py:228-287` faz com o director.
`MINDS_RAW_LOG_CHARS` existe para o chamador cortar o `raw` antes de logar.
Métrica de sucesso: nos testes de unidade, as 5 formas de resposta malformada
caem em `invalid_json` e as 4 formas de entrada inválida caem em rejeição
nomeada; nenhuma delas levanta exceção nem apaga mente já guardada.

## i18n

Sem chave de `frontend/src/strings/*`. O prompt nasce nos dois locales em
`_PROMPT_TEMPLATES` dentro de `backend/app/minds.py`, no formato de
`director.py:17`, escolhido por `scenario.meta.locale` com fallback `pt-br`:

| chave | pt-br | en |
|---|---|---|
| `system` | responda só o objeto JSON com id do NPC → `attitude`, `emoji`, `event`; até 120 caracteres por campo, um emoji só, `{}` quando nada mudou, sem prosa | idem em inglês |
| `cast_label` | `NPCS EM CENA` | `NPCS IN SCENE` |
| `feeling_label` | `sentimento` | `feeling` |
| `goal_label` | `objetivo` | `goal` |
| `current_label` | `agora` | `now` |
| `action_label` | `AÇÃO DO JOGADOR` | `PLAYER ACTION` |
| `narration_label` | `NARRAÇÃO` | `NARRATION` |

`attitude`, `emoji` e `event` são texto do LLM no locale do cenário e nunca
passam por template, nem aqui nem na UI (design `game-hud-info.md`).
