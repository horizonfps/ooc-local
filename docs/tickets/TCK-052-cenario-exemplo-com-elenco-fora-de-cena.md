---
id: TCK-052
title: Acrescentar dois personagens fora de cena ao cenário exemplo
status: in_review
points: 2
blockedBy: []
files:
  - scenarios/exemplo-escola/characters/renan.yaml
  - scenarios/exemplo-escola/characters/bia.yaml
  - backend/tests/test_example_scenario.py
migration: false
ui: false
risk: low
---

## Problema

O `exemplo-escola` tem exatamente três personagens (`chloe`, `ashlee`, `mika`) e
o start `default` lista os três em `characters:`
(`scenarios/exemplo-escola/starts/default.yaml`). Elenco em cena == elenco do
cenário: o roster do TCK-051 nasce vazio e o Director do TCK-053 não tem nada
para trocar. Nenhuma das duas features aparece no cenário exemplo, e a regra do
plano é que feature que não aparece no exemplo não existe — nem dá para jogar o
verde da fase.

## Escopo

Dentro:
- Dois personagens novos em `scenarios/exemplo-escola/characters/`: `renan`
  (professor) e `bia` (veterana do grêmio), completos no mesmo padrão dos três
  atuais.
- Atualizar `EXPECTED_CHARACTER_IDS` em `backend/tests/test_example_scenario.py`.

Fora (explícito):
- `starts/default.yaml` **não muda**. O start continua com
  `characters: [chloe, ashlee, mika]`, que é o que o prólogo descreve; os dois
  novos entram fora de cena de propósito, que é justamente o caso que o roster e
  o director exercitam.
- `world.md` não muda: o teste
  `test_example_scenario_world_word_count_within_budget` prende a contagem entre
  300 e 600 palavras e o mundo já explica a escola. Os personagens novos se
  apresentam pelas próprias fichas.
- Nenhum sprite ou background novo em `media/` — personagem de roster não é
  desenhado, e sprite ausente já é tratado (a tag é ignorada, TCK-042).
- Qualquer código de backend ou frontend.

## Comportamento esperado

`load_scenario("exemplo-escola")` passa a devolver cinco personagens; o start
`default` continua colocando três em cena. Jogando o exemplo, o narrador vê a
ficha completa dos três e uma linha de `renan` e `bia` no roster; com o Director
ligado, os dois são candidatos legítimos a entrar em cena.

## Detalhes técnicos

- Schema: `backend/app/scenario.py:43` (`Character`, `extra="forbid"`). Campos
  obrigatórios: `name`, `role`, `appearance`, `personality`, `voice`,
  `mind.feeling`, `mind.goal`. Opcionais usados aqui: `mind.opinion_of_player`,
  `mind.secret_plan`, `power_tier` (`ge=1`), `emotions` (`[a-z0-9-]+`,
  `default` sempre primeiro, no máximo 20).
- O id é o **stem do arquivo** (`_load_characters`, `scenario.py:203`): grave
  `renan.yaml` e `bia.yaml`, sem campo de id dentro.
- Testes do arquivo que já vigiam a qualidade das fichas e que os dois novos
  precisam satisfazer sem alteração:
  `test_example_scenario_characters_have_complete_mind` (itera
  `EXPECTED_CHARACTER_IDS` e exige `feeling`, `goal`, `opinion_of_player`,
  `secret_plan`, ao menos 2 emoções e `emotions[0] == "default"`) e
  `test_example_scenario_files_are_utf8_and_accented` (todo `characters/*.yaml`
  precisa de pelo menos um caractere acentuado).
- Conteúdo: mantenha o tom e o tamanho de bloco dos YAMLs existentes (blocos
  `>` de 2–4 linhas por campo) e amarre os dois na trama do caderno preto que
  Chloe e Ashlee já disputam, para que entrar em cena faça sentido narrativo.
  `renan` leva `power_tier: 2` (autoridade adulta na escola) — é o que faz a
  linha de tier do roster aparecer no exemplo; `bia` fica sem `power_tier`, para
  o exemplo cobrir os dois formatos de linha.
- Emoções: dê 3 a 4 emoções a cada um (`default` incluso), no mesmo estilo de
  `mika.yaml` (`[default, smile, sad, joy]`), mesmo sem arte.

## Contrato público

N/A — o cenário exemplo é conteúdo, não interface. Nenhum ticket depende deste
para compilar; TCK-051 e TCK-053 apenas ficam demonstráveis no exemplo depois
que ele entra.

## Acceptance criteria

- [ ] `load_scenario("exemplo-escola")` devolve
      `{chloe, ashlee, mika, renan, bia}`.
- [ ] `scenario.starts["default"].characters == ["chloe", "ashlee", "mika"]`
      (inalterado).
- [ ] `renan` tem `power_tier: 2`; `bia` não declara `power_tier`.
- [ ] Ambos passam nas exigências de `mind` completo e ≥2 emoções com
      `default` primeiro.
- [ ] Ambos os arquivos têm caractere acentuado e são UTF-8.
- [ ] `GET /api/scenarios` continua listando `exemplo-escola` (cenário inválido
      seria silenciosamente omitido por `list_scenarios`).
- [ ] `npm run check:api` verde.

## Cenários de teste

Suíte existente que muda: `backend/tests/test_example_scenario.py`. A constante
`EXPECTED_CHARACTER_IDS:10` passa a incluir `renan` e `bia`. É **declaração da
fixture**, não o que os testes aferem: `test_example_scenario_loads_without_exception`
continua aferindo "o cenário do repo carrega e seus ids são exatamente os
declarados", e `test_example_scenario_characters_have_complete_mind` continua
aferindo "toda ficha do exemplo é completa" — agora sobre cinco personagens.
Nenhuma outra asserção muda.

Cenários novos (mesmo arquivo):
- Feliz: o elenco do cenário é estritamente maior que o elenco em cena do start
  (`set(scenario.characters) > set(start.characters)`) — é a condição que faz o
  roster e o director existirem no exemplo, e prende contra alguém "consertar" o
  start listando todo mundo.
- Borda: `renan.power_tier == 2` e `bia.power_tier is None`, cobrindo os dois
  formatos de linha de roster no exemplo.

## Rollout e kill switch

N/A — `risk: low`. Reverter é apagar dois arquivos YAML e a linha da constante.
Sessões existentes não são afetadas: elas guardam `scenario_id` e leem o cenário
do disco, e o start delas continua com os mesmos três ids.

## Observabilidade

Eventos: nenhum novo. `scenario_invalid` (`scenario.py:278`) já denuncia no log
se algum dos YAMLs novos não validar, e `session_assets` continua reportando
zero sprites para os dois.
Métrica de sucesso: começar uma sessão do exemplo e ver, no prompt do turno, a
ficha completa de três personagens e duas linhas de roster.

## i18n

N/A — o cenário exemplo é `locale: pt-br` e todo o conteúdo novo é escrito em
português, como os três personagens existentes. Nenhuma chave de UI ou de
prompt.
