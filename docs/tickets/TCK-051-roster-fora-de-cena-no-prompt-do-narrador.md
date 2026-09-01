---
id: TCK-051
title: Adicionar seção de elenco fora de cena ao prompt do narrador
status: in_review
points: 3
blockedBy: []
files:
  - backend/app/prompt.py
  - backend/tests/test_prompt.py
migration: false
ui: false
risk: medium
---

## Problema

`build_master_prompt` (`backend/app/prompt.py:216`) só conhece quem está em
cena: monta ficha completa de cada um em `## PERSONAGENS EM CENA` e o resto do
elenco simplesmente não existe para o narrador. Com o Director (TCK-053)
escolhendo um subconjunto a cada turno, o narrador passaria a ignorar a
existência de metade do cenário — não poderia citar um professor ausente, nem
puxar flashback de quem saiu de cena.

O outro lado do mesmo problema é o custo: hoje todo personagem em cena entra com
ficha completa (aparência, personalidade, voz, sentimento, objetivo, opinião,
segredo). Com elenco grande, o system prompt estoura o orçamento de contexto
(`CONTEXT_BUDGET_TOKENS` em `compact.py:9`). A linha única de roster é o preço
que o resto do elenco passa a custar.

Este ticket não depende do Director e não sabe que ele existe: hoje `characters`
é o elenco estático do start, então em cenário cujo start lista todo mundo o
roster nasce vazio e o prompt é o de hoje mais o bump de versão.

## Escopo

Dentro:
- Chaves novas em `_TEMPLATES` nos **dois** locales (`pt-br` e `en`) para o
  cabeçalho, a introdução e a linha do roster.
- Função privada que monta o roster (personagens do cenário que não estão na
  lista em cena) e seção nova em `build_master_prompt`, logo depois de
  `## PERSONAGENS EM CENA`.
- `MASTER_PROMPT_VERSION` de 6 para 7.
- Confirmação, por teste, de que o vocabulário de sprites (`_tag_vocabulary`,
  `prompt.py:190`) continua derivando **só** de quem está em cena.

Fora (explícito):
- Assinatura de `build_master_prompt`. O roster é derivado dentro da função a
  partir de `scenario.characters` menos `characters`; nenhum parâmetro novo,
  nenhuma mudança em `backend/app/turn.py` (que é arquivo do TCK-053).
- Decidir quem entra em cena, ler ou escrever elenco persistido: TCK-053.
- Qualquer campo novo de personagem no YAML.
- Instrução de tag nova. O narrador não ganha um jeito de puxar personagem para
  a cena; quem faz isso é o director no turno seguinte, e o prompt diz isso com
  todas as letras.

## Comportamento esperado

Do ponto de vista do chamador: `build_master_prompt(scenario, start, hud,
characters)` com `characters` sendo um subconjunto do elenco produz, depois da
seção de fichas completas, uma seção com uma linha por personagem restante:

```
## ELENCO FORA DE CENA
Estes personagens existem no mundo e não estão na cena agora. Você pode
mencioná-los, citar o que fizeram antes ou usá-los em lembrança, mas não
escreva fala nem ação deles no presente: quem entra em cena é decidido antes
do próximo turno, fora da sua narração.
- Renan — professor de história (tier 3)
- Bia — veterana do grêmio
```

Elenco em cena igual ao elenco do cenário → a seção **não aparece** (mesmo
critério de `_tag_vocabulary`, que omite a seção quando não tem conteúdo).

## Detalhes técnicos

- Chaves novas de `_TEMPLATES`, nos dois locales:
  `roster_header`, `roster_intro`, `roster_tier` (sufixo de tier).
  `pt-br`: `"## ELENCO FORA DE CENA"`; `en`: `"## CAST OFF SCENE"`.
- Linha do roster: `f"- {character.name} — {character.role}"`, mais
  `f" ({template['roster_tier']} {character.power_tier})"` quando
  `power_tier is not None`. **Sem** `###`: o teste
  `test_build_master_prompt_world_heading_does_not_create_false_boundary`
  (`test_prompt.py:249`) conta `^### ` e exige exatamente um por personagem em
  cena; o roster usa bullet justamente para não virar ficha.
- Campo opcional ausente nunca vira `"None"` no texto — é o que o teste
  `test_build_master_prompt_character_optional_fields_omitted:181` já garante e
  o roster tem que respeitar (por isso o tier é condicional).
- Seleção do roster: itere `scenario.characters.items()` na ordem do dicionário
  e mantenha os cujo objeto **não** está em `characters`. Compare por
  identidade (`any(candidate is c for c in characters)`), mesmo critério que
  `_character_id` (`prompt.py:183`) já usa; comparar por igualdade de modelo
  pydantic uniria dois personagens de campos idênticos.
- Ordem determinística e igual à do cenário (o teste de determinismo
  `test_build_master_prompt_is_deterministic:194` cobre a repetição).
- `MASTER_PROMPT_VERSION = 7`. Ela já viaja na telemetria de turno
  (`turn.py:203`, `prompt_version`), então o bump é o que separa as amostras de
  antes e depois do roster.
- `_tag_vocabulary` **não muda**: ele já recebe só `characters` (em cena), logo
  personagem de roster não entra no vocabulário de `[SPRITE:...]` e o narrador
  não pode emitir sprite de quem não está em cena. Isso é comportamento
  desejado e passa a ter teste.

## Contrato público

N/A — nenhuma assinatura nova é exposta. `build_master_prompt` mantém a
assinatura atual e `MASTER_PROMPT_VERSION` já é importado por `turn.py:22`, que
não muda. Nenhum outro ticket consome este.

## Acceptance criteria

- [ ] Com `characters` sendo subconjunto do elenco, o prompt tem
      `## ELENCO FORA DE CENA` (pt-br) / `## CAST OFF SCENE` (en) com uma linha
      por personagem ausente, contendo nome e papel.
- [ ] Tier aparece na linha só quando `power_tier` está definido; a string
      `None` não aparece no prompt.
- [ ] Com `characters` igual ao elenco inteiro, a seção não aparece.
- [ ] Com `characters` vazio, todo o elenco vira roster e
      `Nenhum NPC em cena no momento.` continua na seção de personagens.
- [ ] A seção fica depois de `## PERSONAGENS EM CENA` e antes de
      `## ESTADO DO JOGO`.
- [ ] Personagem de roster com várias emoções **não** aparece no vocabulário de
      sprites.
- [ ] `MASTER_PROMPT_VERSION == 7`.
- [ ] Nenhuma string do roster em português aparece no prompt de locale `en` e
      vice-versa.
- [ ] `npm run check:api` verde.

## Cenários de teste

Suíte existente que muda de preparação: **nenhuma**. Todos os testes de
`backend/tests/test_prompt.py` passam `list(scenario.characters.values())` como
`characters` (roster vazio, seção ausente) ou `[]` no
`test_build_master_prompt_no_characters_in_scene:184`, cuja asserção
(`"Nenhum NPC em cena no momento." in prompt`) continua verdadeira com o roster
presente. `backend/tests/test_turn.py:396`
(`test_turn_system_prompt_contains_world_characters_and_hud`) afere presença de
`"Chloe"` e dos cabeçalhos de HUD; segue verde sem tocar no arquivo.

Cenários novos (`backend/tests/test_prompt.py`, reusando `_load` e as fixtures
`CHLOE_YAML`/`MARCO_YAML` do próprio arquivo):
- Feliz: cenário com Chloe e Marco, `characters=[chloe]` → prompt tem
  `## PERSONAGENS EM CENA` com a ficha da Chloe e `## ELENCO FORA DE CENA` com
  uma linha do Marco contendo `Marco` e `professor`; a ficha do Marco
  (`cansado`, `manter a ordem`) **não** aparece.
- Feliz (en): mesmo caso com locale `en` → `## CAST OFF SCENE` presente e
  nenhuma das palavras `ELENCO`, `PERSONAGENS` no prompt.
- Borda: `characters` = elenco inteiro → `## ELENCO FORA DE CENA` ausente.
- Borda: personagem de roster com `power_tier` definido mostra o tier; sem
  `power_tier`, a linha não contém `None`.
- Borda: ordem das seções — `index` de `## ELENCO FORA DE CENA` entre o de
  `## PERSONAGENS EM CENA` e o de `## ESTADO DO JOGO`.
- Borda: com `CHLOE_WITH_EMOTIONS_YAML` fora de cena, `## VOCABULÁRIO DE TAGS`
  não contém `chloe:`.
- Borda: `len(re.findall(r"(?m)^### ", prompt)) == len(characters_em_cena)`
  mesmo com roster não vazio.

## Rollout e kill switch

N/A. `risk: medium` porque muda o system prompt de todo turno, mas o desligamento
é trivial e não tem estado: com o flag `director` desligado (TCK-053) o elenco
em cena volta a ser o do start e, em cenário cujo start lista todo mundo, o
roster nasce vazio e o prompt volta a ser o da versão 6 exceto pelo número da
versão. Não há dado persistido por este ticket para reverter.

## Observabilidade

Eventos: nenhum evento novo. `game_turn` (`turn.py:198`) passa a reportar
`prompt_version=7`, e `context_budget` (`turn.py:227`) mede o efeito no
orçamento — é o número que diz se o roster está pagando por si.
Métrica de sucesso: com elenco em cena reduzido, `context_budget.estimated_tokens`
cai em relação ao mesmo cenário com todo mundo em cena, e o narrador consegue
citar por nome um personagem que está só no roster.

## i18n

Chaves de prompt, escritas nos dois locales de `_TEMPLATES`
(`backend/app/prompt.py:47`):

| chave | pt-br | en |
|---|---|---|
| `roster_header` | `## ELENCO FORA DE CENA` | `## CAST OFF SCENE` |
| `roster_intro` | `Estes personagens existem no mundo e não estão na cena agora. Você pode mencioná-los, citar o que fizeram antes ou usá-los em lembrança, mas não escreva fala nem ação deles no presente: quem entra em cena é decidido antes do próximo turno, fora da sua narração.` | `These characters exist in the world and are not in the scene right now. You may mention them, refer to what they did before or use them in a memory, but do not write their speech or action in the present: who enters the scene is decided before the next turn, outside your narration.` |
| `roster_tier` | `tier` | `tier` |

Nenhuma chave de UI (`frontend/src/strings.ts`) é tocada.
