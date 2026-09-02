---
id: TCK-056
title: Adicionar conflito e missão opcionais ao start e injetá-los no prompt do narrador
status: done
points: 3
blockedBy: []
files:
  - backend/app/scenario.py
  - backend/app/builder_doc.py
  - backend/app/prompt.py
  - backend/tests/test_scenario.py
  - backend/tests/test_builder_doc.py
  - backend/tests/test_builder_doc_write.py
  - backend/tests/test_prompt.py
  - backend/tests/test_example_scenario.py
  - scenarios/exemplo-escola/world.md
  - scenarios/exemplo-escola/starts/default.yaml
migration: false
ui: false
risk: medium
---

## Problema

Hoje o conflito central e a missão do jogador vivem no `world.md`, como seções
livres de texto: no cenário exemplo são `## Conflito central`
(`scenarios/exemplo-escola/world.md:34`) e `## Papel do jogador`
(`scenarios/exemplo-escola/world.md:44`). O `world.md` inteiro entra no prompt
do narrador em `## MUNDO` (`backend/app/prompt.py:269`), então funciona — para
um cenário de um start só.

Um mundo grande tem N starts. "Primeiro dia de aula" e "última semana antes do
vestibular" acontecem na mesma escola, com as mesmas regras e o mesmo tom, e
têm conflito e missão diferentes. Com os dois campos presos ao `world.md`, ou o
autor duplica o mundo inteiro por start, ou o narrador recebe, em todo turno, um
conflito que não é o daquela partida. O `world.md` tem que ficar só com o que
vale em qualquer história do universo; o que muda por partida desce para o
start.

O `StartConfig` é `extra="forbid"` (`backend/app/scenario.py:93`), então hoje um
YAML de start com `conflict:` ou `mission:` é rejeitado com `ScenarioError` na
carga — o autor não tem nem como escrever o campo à mão.

## Escopo

Dentro:
- `backend/app/scenario.py`: `StartConfig` (`scenario.py:92`) ganha
  `conflict: str | None = None` e `mission: str | None = None`, mais um
  `field_validator` que faz `strip()` e converte string em branco em `None`.
- `backend/app/builder_doc.py`: `_serialize_start` (`builder_doc.py:199`) emite
  `conflict` e `mission` quando não são `None`, logo depois de `opening_scene` e
  antes de `play_guide`.
- `backend/app/prompt.py`: rótulos novos em `_TEMPLATES` (`prompt.py:47`) nos
  dois locales e linhas rotuladas dentro da seção `opening_header`, só quando os
  campos estão definidos. `MASTER_PROMPT_VERSION` de 7 para 8 (`prompt.py:9`).
- Cenário exemplo: mover o texto das seções `## Conflito central` e
  `## Papel do jogador` do `world.md` para `conflict` e `mission` de
  `scenarios/exemplo-escola/starts/default.yaml`.
- Testes novos e a adaptação do piso de contagem de palavras do `world.md` do
  exemplo (ver "Cenários de teste").

Fora (explícito):
- **Qualquer arquivo em `frontend/`.** `frontend/src/api.ts:116` (`StartDoc`) e
  a aba Starts (`frontend/src/components/builder/StartsTab.tsx`) ganham os dois
  campos no TCK-057; a aba Mundo (`frontend/src/builder/worldMarkdown.ts`,
  `WorldTab.tsx`), que hoje tem `Conflict` e `Mission` entre os
  `WORLD_HEADINGS` (`worldMarkdown.ts:3`), é assunto do TCK-058. Este ticket
  não edita, não renomeia e não deprecia nada lá.
- `backend/app/builder.py` `_write_skeleton` (`builder.py:137`): os campos são
  opcionais e o esqueleto continua válido sem eles. Não acrescente
  `conflict: null`/`mission: null` ao skeleton.
- `backend/app/director.py` e `backend/app/compact.py`: nenhum dos dois lê
  conflito ou missão nesta rodada.
- `backend/app/sessions.py`: conflito e missão **não** vão para o cliente do
  jogo. `SessionDetail` (`sessions.py:83`) continua expondo só `prologue` e
  `play_guide` do start.
- Qualquer campo novo além desses dois (nada de `stakes`, `theme`, `tone`).
- Validação de tamanho, obrigatoriedade ou formato dos dois campos: são texto
  livre opcional.

## Comportamento esperado

Do ponto de vista do autor de cenário: um start pode declarar dois campos novos.

```yaml
name: Primeiro dia
prologue: >
  ...
opening_scene: >
  Pátio da escola, poucos minutos antes do sinal.
conflict: >
  Chloe guarda o caderno original e não decidiu o que fazer com ele.
mission: >
  O jogador é o aluno novo do 3º B e precisa decidir se investiga ou se ignora.
play_guide: >
  ...
```

Do ponto de vista do narrador, a seção de cena de abertura passa a carregar as
duas linhas rotuladas, depois do texto da cena:

```
## CENA DE ABERTURA
Pátio da escola, poucos minutos antes do sinal.

Conflito deste início: Chloe guarda o caderno original e não decidiu o que fazer com ele.

Missão do jogador: O jogador é o aluno novo do 3º B e precisa decidir se investiga ou se ignora.
```

Start sem os campos (o caso de todo cenário existente) produz exatamente o
prompt de hoje, com a seção `## CENA DE ABERTURA` contendo só
`opening_scene` — nenhuma linha rotulada, nenhuma linha vazia, e a string
`None` em lugar nenhum.

Do ponto de vista do chamador da API do builder: `GET
/api/builder/scenarios/{id}` passa a devolver `conflict` e `mission` em cada
`starts[id]` (`null` quando ausentes), e `PUT` os grava de volta no YAML.

## Detalhes técnicos

**1. `backend/app/scenario.py`**

Em `StartConfig` (`scenario.py:92`), declare os dois campos entre
`opening_scene` e `play_guide`, para que a ordem do modelo espelhe a ordem da
serialização:

```python
    opening_scene: str
    conflict: str | None = None
    mission: str | None = None
    play_guide: str | None = None
```

Validator no mesmo estilo dos que já existem no arquivo
(`_validate_emotions:56`, `_validate_time:81`):

```python
    @field_validator("conflict", "mission")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None
```

Armadilha que motiva o validator: YAML escrito à mão com `conflict: ""` ou
`conflict: "   "` viraria uma linha `Conflito deste início: ` vazia no prompt.
E `conflict: >` (bloco folded, que é como o cenário exemplo escreve texto
longo) sempre termina em `\n`; sem o `strip()` a linha rotulada arrastaria uma
quebra a mais para dentro da seção. Campo ausente não passa pelo validator
(pydantic não valida default), o que é correto: já nasce `None`.

Não toque em `play_guide`: ele não tem strip hoje e mudar isso não é deste
ticket.

**2. `backend/app/builder_doc.py`**

Em `_serialize_start` (`builder_doc.py:199`), entre o dict inicial e o bloco de
`play_guide` (`builder_doc.py:205`):

```python
    if start.conflict is not None:
        data["conflict"] = start.conflict
    if start.mission is not None:
        data["mission"] = start.mission
```

`_dump_yaml` usa `sort_keys=False` (`builder_doc.py:173`), então a ordem de
inserção é a ordem do arquivo. `read_document` (`builder_doc.py:104`) já
constrói os starts via `StartConfig`, então nada mais é preciso para o
documento JSON carregar os campos.

**3. `backend/app/prompt.py`**

Chaves novas nos **dois** blocos de `_TEMPLATES`, ao lado de `opening_header`
(pt-br em `prompt.py:80`, en em `prompt.py:145`): `conflict_label` e
`mission_label` (textos na seção i18n).

Na montagem da seção (`prompt.py:293-295`), troque a linha única por um corpo
montado em partes:

```python
    opening_parts = [_neutralize_headings(start.opening_scene)]
    if start.conflict is not None:
        opening_parts.append(
            f"{template['conflict_label']}: {_neutralize_headings(start.conflict)}"
        )
    if start.mission is not None:
        opening_parts.append(
            f"{template['mission_label']}: {_neutralize_headings(start.mission)}"
        )
    sections.append(f"{template['opening_header']}\n" + "\n\n".join(opening_parts))
```

- Junção com `"\n\n"`: o texto de `opening_scene` pode ter mais de um
  parágrafo, e a linha rotulada não pode colar no último deles.
- `_neutralize_headings` (`prompt.py:35`) nos dois campos pelo mesmo motivo do
  `world` e do `opening_scene`: texto de autor com `## ...` no meio criaria uma
  fronteira falsa de seção. Ele rebaixa em 3 níveis e satura em 6, então nada
  do que sai dele casa com `^### ` — o teste
  `test_build_master_prompt_world_heading_does_not_create_false_boundary`
  (`test_prompt.py:248`), que conta `^### ` e exige um por personagem em cena,
  continua válido.
- A string `None` nunca aparece: os dois `if` são a única porta de entrada, e o
  validator já garante que `None` é o único valor "vazio" possível.
- `MASTER_PROMPT_VERSION = 8` (`prompt.py:9`). Ela viaja na telemetria em
  `turn.py:206` (`prompt_version`), e é o que separa as amostras de antes e
  depois. **Nenhum teste afere o número 7** — a busca por
  `MASTER_PROMPT_VERSION`/`prompt_version` em `backend/` acha só `prompt.py:9`,
  `turn.py:24` e `turn.py:206`, e nenhum teste em `backend/tests/` cita
  `version`. O bump não quebra nada e não precisa de adaptação.

**4. Cenário exemplo (`scenarios/exemplo-escola/`)**

`world.md` fica com as linhas 1–32 do arquivo atual (introdução,
`## Tom de narração`, `## Regras do mundo`) e perde da linha 33 em diante
(`## Conflito central` e `## Papel do jogador`). Termine o arquivo com uma única
quebra de linha depois de `...nunca como protagonistas da tensão.`

Em `starts/default.yaml`, entre `opening_scene` (`default.yaml:22`) e
`play_guide` (`default.yaml:26`), com blocos `>` no mesmo estilo do resto do
arquivo. Textos finais (o conflito é literal do `world.md`; o "papel do
jogador" foi reescrito como missão — o que o jogador está tentando fazer):

```yaml
conflict: >
  Chloe guarda o caderno original e não decidiu o que fazer com ele: expor
  tudo, usar como proteção, ou simplesmente sumir com ele. Ashlee lidera a
  turma socialmente e teme — com razão — que seu nome apareça em páginas que
  ela preferia esquecer. Entre as duas, sem escolher lado, está Mika, que
  cresceu com o jogador e por isso vira o fio que costura os dois grupos.
mission: >
  O jogador é o aluno novo do 3º B, chegando no primeiro dia de aula depois de
  uma mudança de cidade, sem história prévia com ninguém dali. Ele chega sem
  saber nada do caderno e precisa decidir, aos poucos, se investiga, se ignora,
  ou se vira peça no jogo de alguém. Ser o único ponto de vista de fora é o que
  permite que outros personagens confiem a ele informações que não confiariam
  entre si, e é também o que o torna alvo de desconfiança: gente nova pode ser
  usada por qualquer lado.
```

O `exemplo-escola` é `world_mode: custom` (`scenario.yaml`) e usa cabeçalhos em
português, então `parseGuidedWorld` (`worldMarkdown.ts:20`) já devolvia `null`
para ele: encurtar o `world.md` não muda nada na aba Mundo hoje.

**5. Round trip pelo builder, antes do TCK-057**

`updateStart` em `StartsTab.tsx:105` faz `{ ...draft.starts[id], ...patch }`
sobre o objeto vindo do `GET`, então as chaves novas sobrevivem ao `PUT` mesmo
sem existirem no tipo `StartDoc`. Start criado do zero pela aba
(`StartsTab.tsx:156`) sai sem as chaves e o backend as trata como `None`. Ou
seja: não há perda de dado entre este ticket e o TCK-057.

## Contrato público

Consumido pelo **TCK-057** (aba Starts). Rotas `GET` e `PUT
/api/builder/scenarios/{scenario_id}` (`builder_doc.py:313` e
`builder_doc.py:339`): cada valor de `starts` passa a ter dois campos novos,
opcionais e anuláveis, entre `opening_scene` e `play_guide`.

```json
"starts": {
  "default": {
    "id": "default",
    "name": "Primeiro dia",
    "prologue": "...",
    "opening_scene": "...",
    "conflict": "Chloe guarda o caderno original...",
    "mission": "O jogador é o aluno novo do 3º B...",
    "play_guide": null,
    "suggestions": [],
    "hud": { "location": "pátio da escola", "time": "07:50", "weather": "clear" },
    "characters": ["chloe", "ashlee", "mika"]
  }
}
```

Equivalente TypeScript a acrescentar em `StartDoc` (`frontend/src/api.ts:116`)
pelo TCK-057, **não** por este ticket:

```ts
  conflict: string | null
  mission: string | null
```

Regras que o consumidor pode assumir:
- `GET` devolve `null` quando o YAML não tem a chave.
- `PUT` com `""` ou só espaços grava como ausente; o `GET` seguinte devolve
  `null`. Um campo apagado na UI volta como `null`, nunca como `""`.
- `PUT` sem as chaves é aceito (`extra="forbid"` só rejeita chave desconhecida,
  não chave ausente com default) e equivale a `null`.
- Ordem no YAML gravado: `name`, `prologue`, `opening_scene`, `conflict`,
  `mission`, `play_guide`, `suggestions`, `hud`, `characters`.

## Acceptance criteria

- [ ] Start YAML com `conflict` e `mission` carrega sem `ScenarioError`, e
      `scenario.starts[id].conflict/.mission` trazem o texto sem espaço nas
      pontas.
- [ ] Start YAML sem os campos carrega com os dois em `None`.
- [ ] `conflict: ""` e `mission: "   "` carregam como `None`.
- [ ] `GET /api/builder/scenarios/{id}` traz `conflict` e `mission` em cada
      start (`null` quando ausentes).
- [ ] `PUT` com os dois campos preenchidos, num start que tem `play_guide`,
      grava o YAML com as chaves na ordem `opening_scene`, `conflict`,
      `mission`, `play_guide`; com os dois `null` ou `""`, as chaves não
      aparecem no arquivo.
- [ ] Prompt pt-br com os dois campos contém `Conflito deste início: ` e
      `Missão do jogador: `, nessa ordem, dentro da seção `## CENA DE ABERTURA`
      e depois do texto de `opening_scene`.
- [ ] Prompt `en` com os dois campos contém `Conflict of this start: ` e
      `Player mission: `, e nenhuma das palavras `Conflito` ou `Missão`.
- [ ] Prompt de start sem os campos não contém nenhum dos quatro rótulos nem a
      string `None`.
- [ ] `MASTER_PROMPT_VERSION == 8`.
- [ ] `scenarios/exemplo-escola/world.md` não contém mais `## Conflito central`
      nem `## Papel do jogador`, e `starts/default.yaml` carrega com
      `conflict` e `mission` não vazios.
- [ ] `test_example_scenario_world_word_count_within_budget` passa a exigir
      `250 <= word_count <= 600` (piso 300 → 250, teto intacto) e fica verde
      com o `world.md` migrado (292 palavras).
- [ ] Teste novo em `test_example_scenario.py` afere que `conflict` + `mission`
      do start `default`, somados, têm entre 100 e 300 palavras (o texto
      migrado soma 161).
- [ ] `npm run check` verde (inclui `tsc -b` e vitest do frontend; ver
      inventário).

## Cenários de teste

**Inventário da suíte existente** (lido antes de escrever o escopo):

Continuam verdes **sem tocar no arquivo**, porque os dois campos são opcionais e
os fixtures são dicts/YAML literais que simplesmente não os declaram:
- `backend/tests/test_scenario.py`: `DEFAULT_START:17` e `VILLAIN_START:25` não
  têm os campos; `test_start_characters_none_means_all:104` e todo o resto do
  arquivo seguem iguais. (Ganha cenários novos, ver abaixo — o arquivo é tocado
  só para *acrescentar*.)
- `backend/tests/test_builder_doc_write.py`: `DEFAULT_START:21` está escrito na
  forma canônica pós-`write_document`; como `conflict`/`mission` são `None`, a
  serialização não emite as chaves e
  `test_get_put_get_roundtrip_without_changes_keeps_revision:208` e
  `test_put_identical_document_does_not_change_revision_or_mtime:137` continuam
  byte-idênticos, sem editar o fixture. O arquivo é tocado só para *acrescentar*
  os dois cenários de escrita listados abaixo. **`DEFAULT_START:21` não tem
  `play_guide`**, e `_serialize_start` só emite a chave quando ela não é
  `None`; por isso os dois cenários novos de escrita usam um start local
  (`DEFAULT_START + "play_guide: guia do start\n"`, passado via
  `starts={"default.yaml": ...}` de `_write_scenario:46`), nunca o fixture
  compartilhado.
- Fixtures de start que passam por `StartConfig` sem os campos novos e
  **continuam verdes sem edição**, porque os campos são opcionais com default
  `None`: `test_cast.py:60`, `test_director.py:35`, `test_sessions.py:21,30`,
  `test_media_manifest.py:19`, `test_builder.py:22`, `test_compact.py:26`,
  `test_turn_director.py:21`. Nenhum deles afere o conjunto de chaves do start
  nem o corpo da seção de abertura.
- Testes que capturam o system prompt do narrador e **continuam verdes**
  (todos usam fixtures de start sem os campos novos, então o prompt sai
  byte-idêntico ao de hoje exceto pela versão, que nenhum afere):
  `test_turn_director.py:169-171` (afere `### Renan` presente e `### Dara`
  ausente), `:213` (mesma família) e `:264` (`Nenhum NPC em cena no momento.`
  presente); `test_compact.py:573-579` (afere `RESUMO DA CAMPANHA` e o teto
  `all_content_tokens <= INPUT_BUDGET_TOKENS`, único teste de teto do master
  prompt: o fixture `:26` não declara os campos, logo o tamanho não muda),
  `:839-846` e `:899-909` (textos de turno presentes/ausentes no prompt do
  narrador), `:1123-1127` (`Resumo legado.` presente); `:159-162` e `:667`
  (prompt do utility, que não passa por `build_master_prompt`). Nenhum afere a
  seção `## CENA DE ABERTURA` nem a ausência de linhas nela.
- Frontend (`npm run check` roda `tsc -b` + vitest): os 8 arquivos de teste que
  citam `opening_scene` (`validate.test.ts`, `StartsTab.test.tsx`,
  `BuilderEditorScreen.test.tsx`, `BuilderPreview.test.tsx`,
  `CharactersTab.test.tsx`, `IdentityTab.test.tsx`, `MediaTab.test.tsx`,
  `WorldTab.test.tsx`) usam fixtures locais de `StartDoc` e mocks de `fetch`;
  nenhum bate no backend real, então nenhum vê as chaves novas e nenhum muda.
  `StartDoc` (`api.ts:116`) segue sem os campos até o TCK-057, e `tsc` não
  reclama de chave a mais vinda do JSON em runtime. **Nenhum arquivo de
  `frontend/` é editado.**
- `backend/tests/test_prompt.py`: `DEFAULT_START:23` não tem os campos, então
  `test_build_master_prompt_ptbr_happy_path:112`,
  `test_build_master_prompt_en_locale:149`,
  `test_build_master_prompt_character_optional_fields_omitted:186` (o
  `assert "None" not in prompt`) e todos os testes de roster seguem verdes.
- `backend/tests/test_turn.py`: `DEFAULT_START:18` sem os campos;
  `test_turn_system_prompt_contains_world_characters_and_hud:396` afere
  `"Uma escola"`, `"Chloe"`, `## ESTADO DO JOGO` e `Turno: 0`, tudo intacto.
  Nenhum teste do arquivo afere `prompt_version`. **Arquivo não é editado.**
- `backend/tests/test_chat.py`: não toca cenário nem prompt. **Não é editado.**
- `backend/tests/test_builder_doc.py`: `DEFAULT_START:15` sem os campos;
  `test_full_scenario_returns_document_with_starts_and_characters:96` afere
  chaves específicas, não o conjunto de chaves. Ganha cenário novo.
- `backend/tests/test_example_scenario.py`: `..._explicit_characters:36`,
  `..._has_three_suggestions:41`, `..._prologue_word_count_within_budget:65` e
  `..._files_are_utf8_and_accented:71` continuam verdes (o `world.md` que
  sobra, linhas 1–32, tem acentuação de sobra).

**Única asserção que muda, e por quê**:
`test_example_scenario_world_word_count_within_budget`
(`test_example_scenario.py:59`) exige `300 <= word_count <= 600`. O `world.md`
atual tem 472 palavras; tirando as duas seções sobram **292**, abaixo do piso.
O piso foi calibrado para um `world.md` que carregava conflito e missão, e é
exatamente esse conteúdo que este ticket move de lugar — o orçamento total do
cenário não mudou, a distribuição sim. Troque o piso para `250` e acrescente,
no mesmo arquivo, um teste que afere o orçamento do lado que recebeu o texto
(`conflict` e `mission` do start `default`, somados, entre 100 e 300 palavras),
para que nenhum dos dois lados fique sem cobertura de tamanho. Não mexa no teto
de 600.

**Cenários novos**:

- Feliz (`test_scenario.py`, reusando `_write_scenario:53` e `DEFAULT_START:17`
  com `+ "conflict: um caderno circula\nmission: descobrir de quem é\n"`):
  carrega e os dois campos trazem o texto.
- Borda (`test_scenario.py`): `DEFAULT_START + 'conflict: "  "\nmission: ""\n'`
  → os dois viram `None`.
- Borda (`test_scenario.py`): `DEFAULT_START + "conflict: '  texto  '\n"` →
  `conflict == "texto"`.
- Borda (`test_scenario.py`): `DEFAULT_START` puro → `conflict is None` e
  `mission is None`.
- Feliz (`test_builder_doc.py`): `GET` de cenário cujo start tem os dois campos
  → `body["starts"]["default"]["conflict"]` e `["mission"]` com o texto; `GET`
  do `DEFAULT_START` puro → os dois `null` (use `is None`, não `not in`).
- Feliz (`test_builder_doc_write.py`, reusando `_write_scenario:46` com
  `starts={"default.yaml": DEFAULT_START + "play_guide: guia do start\n"}` e o
  `client`/`scenarios_root` do arquivo): `GET`, preencher
  `doc["starts"]["default"]["conflict"]` e `["mission"]`, `PUT` → nas linhas do
  YAML gravado (`splitlines()`), os índices das linhas que começam com
  `opening_scene:`, `conflict:`, `mission:` e `play_guide:` são estritamente
  crescentes, nessa ordem (mesmo estilo de
  `test_put_adding_character_writes_file_with_canonical_order_and_accents:110`).
- Borda (`test_builder_doc_write.py`, mesmo start local com `play_guide`):
  `PUT` com os dois campos em `""` → o arquivo gravado não contém linha que
  comece com `conflict:` nem `mission:`, e o `GET` seguinte devolve `null` nos
  dois.
- Feliz (`test_prompt.py`, com um `DEFAULT_START` local acrescido dos campos):
  pt-br → `"Conflito deste início: "` e `"Missão do jogador: "` presentes;
  `prompt.index(conflito) < prompt.index(missão)`; ambos depois de
  `prompt.index("Você acorda no dormitório.")` e antes de
  `prompt.index("## FORMATO DO TURNO")`.
- Feliz (`test_prompt.py`, locale `en`): `"Conflict of this start: "` e
  `"Player mission: "` presentes; `"Conflito"` e `"Missão"` ausentes.
- Borda (`test_prompt.py`): só `conflict` definido → rótulo de conflito
  presente, rótulo de missão ausente. E o simétrico com só `mission`.
- Borda (`test_prompt.py`): `DEFAULT_START` sem os campos → nenhum dos quatro
  rótulos no prompt e `"None" not in prompt`.
- Borda (`test_prompt.py`): `conflict` com `"## ESTADO DO JOGO"` no meio do
  texto → `len(re.findall(r"(?m)^## ESTADO DO JOGO$", prompt)) == 1` (mesma
  garantia de `test_prompt.py:248`, agora pelo campo novo).
- Borda (`test_prompt.py`): `from app.prompt import MASTER_PROMPT_VERSION;
  assert MASTER_PROMPT_VERSION == 8`.
- Feliz (`test_example_scenario.py`): `scenario.starts["default"].conflict` e
  `.mission` não são `None` e têm mais de 40 palavras cada; `"Conflito central"`
  e `"Papel do jogador"` não aparecem em `scenario.world`; `"Tom de narração"` e
  `"Regras do mundo"` continuam aparecendo.

Falha: não há caminho de erro novo. YAML com chave desconhecida continua sendo
`ScenarioError` pelo `extra="forbid"` já existente, coberto por
`test_character_unknown_field_raises_scenario_error` (`test_scenario.py:135`).

## Rollout e kill switch

N/A. Não há flag: os dois campos são opcionais, cenário que não os declara
produz o prompt de hoje, e o único cenário do repositório que passa a usá-los é
migrado no mesmo PR. Não há dado persistido de sessão envolvido — conflito e
missão são lidos do disco a cada turno, então reverter o commit reverte o
comportamento por inteiro.

`risk: medium` (não `low`) por dois motivos somados: o system prompt de **todo**
turno muda, e o conteúdo do cenário exemplo — o único cenário jogável do repo —
é reorganizado no mesmo PR. Um erro aqui aparece na qualidade da narração, não
em exceção.

## Observabilidade

Eventos: nenhum evento novo. `game_turn` (`turn.py:201`) passa a reportar
`prompt_version=8`, o que separa as amostras antes/depois desta mudança. O
`context_budget` de `turn.py` continua medindo o efeito no orçamento; conflito e
missão são texto curto que **sai** do `world.md` e **entra** na cena de
abertura, então o total estimado deve ficar praticamente igual.
Métrica de sucesso: com `prompt_version=8`, `estimated_tokens` do mesmo cenário
não sobe de forma perceptível, e um segundo start do mesmo mundo com conflito
diferente produz narração alinhada ao conflito daquele start, não ao do outro.

## i18n

Chaves novas de prompt, escritas nos dois locales de `_TEMPLATES`
(`backend/app/prompt.py:47` para `pt-br`, `prompt.py:113` para `en`), ao lado de
`opening_header`:

| chave | pt-br | en |
|---|---|---|
| `conflict_label` | `Conflito deste início` | `Conflict of this start` |
| `mission_label` | `Missão do jogador` | `Player mission` |

Nenhuma chave de UI (`frontend/src/strings.ts`) é tocada por este ticket; os
rótulos da tela do builder são do TCK-057.
