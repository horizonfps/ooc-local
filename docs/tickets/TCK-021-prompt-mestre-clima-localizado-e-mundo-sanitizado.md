---
id: TCK-021
title: Localizar o clima no prompt e neutralizar headings do texto do autor
status: done
points: 3
blockedBy: []
files:
  - backend/app/prompt.py
  - backend/tests/test_prompt.py
migration: false
ui: false
risk: low
---

## Problema

`build_master_prompt` (`backend/app/prompt.py:103`) monta o bloco de estado do
jogo interpolando o HUD cru:

```python
f"{template['hud_weather']}: {hud.weather}"
```

`hud.weather` é um **código** do engine (`WEATHER_CODES` em
`backend/app/hud.py:10`: `clear`, `cloudy`, `rain`, `storm`, `snow`, `fog`,
`night`). Num cenário `pt-br`, o narrador recebe `"Clima: cloudy"` — rótulo em
português, valor em inglês, dentro de um prompt que termina com "Responda em
português do Brasil". O modelo tende a espelhar o vocabulário do prompt, e um
modelo local de 24B faz exatamente isso: escreve "o céu cloudy". O frontend já
resolveu o mesmo problema no HUD, com `WEATHER_KEYS`
(`frontend/src/components/Hud.tsx:13`) mapeando código → chave i18n; o prompt
ficou para trás.

Segundo problema, mais grave: `scenario.world` entra **cru** no prompt
(`backend/app/prompt.py:114`), logo abaixo do cabeçalho `## MUNDO`. O prompt usa
`##` como fronteira de seção (`## NARRADOR`, `## MUNDO`, `## PERSONAGENS EM
CENA`, `## ESTADO DO JOGO`, `## CENA DE ABERTURA`, `## RESUMO DA CAMPANHA`,
`## FORMATO DO TURNO`) e `###` para cada personagem
(`_format_character`, `:88`). O `world.md` é markdown escrito por autor de
cenário — o do repositório, `scenarios/exemplo-escola/world.md`, começa com um
heading. Um `## ESTADO DO JOGO` escrito por engano (ou de propósito) dentro do
`world.md` cria uma fronteira de seção falsa: o narrador passa a ler o resto do
mundo como se fosse estado do engine, que o prompt manda tratar como "verdade
absoluta". `start.opening_scene` (`:133`) tem o mesmo problema e a mesma origem.

## Escopo

Dentro:
- Tabela `WEATHER_LABELS` por locale em `backend/app/prompt.py`, usada na linha
  de clima do bloco de estado.
- `_neutralize_headings(text)` aplicada a `scenario.world` e a
  `start.opening_scene` antes de entrarem nas seções.
- Bump de `MASTER_PROMPT_VERSION`.
- Testes em `backend/tests/test_prompt.py`.

Fora (explícito):
- Localizar `hud.location` ou `hud.time`: são conteúdo do autor
  (`starts/*.yaml`), já escritos no idioma do cenário, e não têm vocabulário
  fechado como o clima.
- Mudar `WEATHER_CODES`, o HUD, o event store, ou a API: o código continua sendo
  o valor canônico em todo lugar; a localização acontece **só** na montagem do
  prompt.
- Sanitizar os campos curtos de personagem (`role`, `personality`, `voice`,
  `mind.*`): são uma linha cada, entram como `Rótulo: valor` e não têm heading.
  Se um autor escrever `##` ali, o valor aparece no meio de uma linha rotulada e
  não cria fronteira.
- Sanitizar o texto do compact: ele é gerado pelo utility com prompt que pede
  prosa, não markdown. Se isso virar problema, é ticket próprio com evidência.
- Escapar outras construções markdown (`---`, blocos de código, tabelas): só
  heading cria fronteira falsa neste prompt.
- Mexer no `prologue`: ele não entra no prompt (grep em `backend/app/prompt.py`
  confirma; o prólogo é da UI, via `SessionDetail.prologue`).

### Testes existentes que este ticket invalida

Grep em `backend/tests/test_prompt.py` (7 testes) e nos demais arquivos que
constroem prompt:

- `test_build_master_prompt_ptbr_happy_path` (`:86`) tem duas asserções que
  descrevem o comportamento antigo:
  - `assert "Clima: cloudy" in prompt` — a saída passa a ser `"Clima: Nublado"`.
  - `assert WORLD_MD in prompt`, com `WORLD_MD = "# Mundo\n\nUma escola nas
    montanhas.\n"` — o heading passa a sair rebaixado.
  Isso **não é adaptação de preparação**: são as asserções que o ticket muda de
  propósito. As duas são **substituídas** pelos cenários novos deste ticket
  (`"Clima: Nublado"` e `"#### Mundo"` + `"Uma escola nas montanhas."`), e essa
  substituição está declarada aqui para não virar `spec_drift`.
- `test_build_master_prompt_en_locale` (`:120`) afere headers e ausência de
  palavras pt-br; não afere clima nem o corpo do mundo. Continua válido, e ganha
  a asserção nova de `"Weather: Cloudy"` como cenário novo.
- `test_build_master_prompt_is_deterministic` (`:175`),
  `test_build_master_prompt_compact_present_and_absent` (`:140`),
  `test_build_master_prompt_character_optional_fields_omitted` (`:155`),
  `test_build_master_prompt_no_characters_in_scene` (`:165`),
  `test_build_master_prompt_trusts_hud_state` (`:186`): continuam válidos sem
  adaptação — nenhum deles afere clima nem o texto cru do mundo.
- `backend/tests/test_turn.py` e `test_compact.py` chamam `build_master_prompt`
  indiretamente por `build_context`, mas nenhuma asserção olha o conteúdo do
  system prompt hoje (é justamente a lacuna que o TCK-018 fecha). Nenhuma
  adaptação, e este ticket **não** edita esses arquivos.
- `MASTER_PROMPT_VERSION` aparece em `backend/app/turn.py:166` só como
  propriedade de telemetria; nenhum teste afere o valor. Bump seguro.

## Comportamento esperado

Do ponto de vista do narrador (chamador de `build_master_prompt`):

- Cenário `pt-br` com `weather="cloudy"` → `"Clima: Nublado"`.
- Cenário `en` com `weather="cloudy"` → `"Weather: Cloudy"`.
- Código fora de `WEATHER_CODES` (impossível hoje, mas o prompt não pode
  quebrar) → o código cru é usado como rótulo.
- `world.md` começando com `# Mundo` → aparece como `#### Mundo` sob o
  cabeçalho `## MUNDO`; nenhum heading do autor pode produzir `##` ou `###`.
- Nível relativo preservado: `#` e `##` do autor continuam distintos entre si
  depois do rebaixamento.

## Detalhes técnicos

- `WEATHER_LABELS: dict[str, dict[str, str]]` em `backend/app/prompt.py`, com
  uma entrada por locale (`pt-br`, `en`) e uma por código de `WEATHER_CODES`.
  Os textos são os mesmos já usados na UI (`frontend/src/strings.ts`,
  `hud.weather.*`): Limpo/Nublado/Chuva/Tempestade/Neve/Neblina/Noite e
  Clear/Cloudy/Rain/Storm/Snow/Fog/Night. Manter as duas listas iguais é
  deliberado: o jogador lê o HUD e o narrador lê o prompt, e divergir aí produz
  contradição visível na tela.
  Fallback: `WEATHER_LABELS[locale].get(hud.weather, hud.weather)`.
  **Não** importe as strings do frontend nem crie dependência entre as duas
  camadas; são tabelas independentes com o mesmo conteúdo, e há teste aferindo
  que a tabela do prompt cobre `WEATHER_CODES` inteiro.
- `_neutralize_headings(text: str) -> str`: para cada linha que casar
  `^(#{1,6})[ \t]+(.*)$`, o nível vira `min(level + 3, 6)`. `#` → `####`,
  `##` → `#####`, `###` → `######`, e daí em diante satura em `######`.
  Nunca produz `##` nem `###`, que são os dois níveis reservados pelo prompt.
  Linha que não é heading sai intocada; nada de `strip`, nada de normalizar
  espaço (o texto do autor é conteúdo).
  **Armadilha**: `#hashtag` sem espaço não é heading em markdown e o regex
  exige o espaço — não rebaixe.
- `MASTER_PROMPT_VERSION` passa de `1` para `2`
  (`backend/app/prompt.py:6`). O valor é emitido em `game_turn.prompt_version`
  (`backend/app/turn.py:166`) e é o que permite atribuir mudança de qualidade de
  narração à mudança de prompt.
- Ordem de aplicação: sanitize primeiro, interpole depois. Sanitizar a seção já
  montada rebaixaria os cabeçalhos do próprio prompt.

## Contrato público

```python
# backend/app/prompt.py
MASTER_PROMPT_VERSION = 2
WEATHER_LABELS: dict[str, dict[str, str]]   # locale -> codigo -> rotulo

def build_master_prompt(
    scenario: LoadedScenario,
    start: StartConfig,
    hud: HudState,
    characters: list[Character],
    compact: str | None = None,
) -> str: ...     # assinatura inalterada
```

## Acceptance criteria

- [ ] Cenário `pt-br` com `weather="cloudy"` produz `"Clima: Nublado"` e não
      contém `"Clima: cloudy"`.
- [ ] Cenário `en` com `weather="cloudy"` produz `"Weather: Cloudy"`.
- [ ] `WEATHER_LABELS["pt-br"]` e `WEATHER_LABELS["en"]` têm exatamente as
      chaves de `WEATHER_CODES`.
- [ ] Clima desconhecido cai no código cru sem levantar exceção.
- [ ] `world.md` com `# Mundo` produz `#### Mundo` no prompt.
- [ ] `world.md` contendo `## ESTADO DO JOGO` não produz uma segunda fronteira:
      `len(re.findall(r"(?m)^## ESTADO DO JOGO$", prompt)) == 1`. Aferição por
      substring não vale — `#####` contém `##` como prefixo.
- [ ] `opening_scene` com heading recebe o mesmo tratamento.
- [ ] Para qualquer entrada, nenhuma linha devolvida por `_neutralize_headings`
      casa `^(##|###)[ \t]` (regex multiline sobre a saída da função).
- [ ] `MASTER_PROMPT_VERSION == 2`.
- [ ] `npm run check` verde.

## Cenários de teste

- Feliz (pt-br): prompt com `"Clima: Nublado"`, `"#### Mundo"` e o corpo
  `"Uma escola nas montanhas."` presentes; `"Clima: cloudy"` ausente.
- Feliz (en): cenário `locale: en` com o mesmo HUD → `"Weather: Cloudy"`.
- Feliz (tabela): `set(WEATHER_LABELS[locale]) == set(WEATHER_CODES)` para os
  dois locales.
- Borda: `world.md` com `## ESTADO DO JOGO` e `### Chloe` →
  `re.findall(r"(?m)^## ESTADO DO JOGO$", prompt)` tem 1 ocorrência e
  `re.findall(r"(?m)^### ", prompt)` tem exatamente o número de personagens em
  cena.
- Borda: `world.md` com `###### Nota` → satura em `######`, sem virar `#########`.
- Borda: `world.md` com `#semespaco` e com `código # dentro da linha` → saem
  intocados.
- Borda: `weather="chuvisco"` (fora de `WEATHER_CODES`) → `"Clima: chuvisco"`,
  sem exceção.
- Borda: `opening_scene` de uma linha só, sem heading → byte a byte igual.
- Falha: `build_master_prompt` continua determinístico (duas chamadas com a
  mesma entrada devolvem string idêntica) depois da sanitização.

## Rollout e kill switch

N/A. Não há flag: o prompt-mestre é montado a cada turno e não tem estado
intermediário desligável — a alternativa a este ticket é o prompt de hoje, que é
o próprio defeito. Rollback é `git revert` do PR, e a regressão é imediatamente
visível em `game_turn.prompt_version` voltando a `1`.

## Observabilidade

Eventos: `game_turn` (já existente) — `prompt_version` passa a valer `2`, o que
permite comparar sessões antes e depois no log.
Métrica de sucesso: em sessões com `prompt_version: 2` e cenário `pt-br`,
nenhuma ocorrência de código de clima em inglês no texto narrado gravado.

## i18n

N/A para a UI: nenhuma chave nova em `frontend/src/strings.ts`. Os rótulos de
clima do prompt são conteúdo de backend, existem nos dois locales suportados
(`pt-br` e `en`, os mesmos de `ScenarioMeta.locale` em
`backend/app/scenario.py:86`), e replicam o texto já traduzido de
`hud.weather.*`.
