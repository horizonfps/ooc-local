---
id: TCK-068
title: Dar stats, lorebook e comando ao cenário exemplo da escola
status: in_review
points: 2
blockedBy: [TCK-060]
files:
  - scenarios/exemplo-escola/stats.yaml
  - scenarios/exemplo-escola/lorebook/caderno.yaml
  - scenarios/exemplo-escola/lorebook/sala-do-gremio.yaml
  - scenarios/exemplo-escola/commands.yaml
  - backend/tests/test_example_scenario.py
migration: false
ui: false
risk: low
---

## Problema

`scenarios/exemplo-escola` é o único cenário do repositório e o que todo mundo
usa para jogar de verdade e fechar fase. Depois do TCK-060 ele continua sem
`stats.yaml`, sem `lorebook/` e sem `commands.yaml`, então a fase inteira ficaria
sem um caminho jogável: nenhuma barra no HUD, nenhuma entrada de lore para o
TCK-075 injetar, nenhum comando para a paleta do TCK-074 listar. Os testes de
engine rodam contra cenários sintéticos em `tmp_path`; nada garante que o cenário
real exercite as três features.

Os arquivos novos também não podem ser encheção: o cenário tem um gancho
declarado — o caderno de capa preta que circula pelo 3º B (`world.md`, parágrafo
2) — e stats, lore e comando que ignorassem esse gancho fariam o exemplo
contradizer a própria premissa.

## Escopo

Dentro:
- `scenarios/exemplo-escola/stats.yaml`: `reputacao` (0..100, default 40, 3
  levels) e `energia` (0..100, default 80, sem levels).
- `scenarios/exemplo-escola/lorebook/caderno.yaml` e
  `scenarios/exemplo-escola/lorebook/sala-do-gremio.yaml`.
- `scenarios/exemplo-escola/commands.yaml` com `!fofoca`.
- `backend/tests/test_example_scenario.py`: asserções sobre os três, mais
  coerência entre keyword de lore e o texto do cenário.

Fora (explícito):
- `scenario.yaml`, `world.md`, `starts/default.yaml` e os cinco arquivos de
  `characters/`: **nenhum é editado**. Os testes de orçamento de palavras
  (`test_example_scenario.py:59-91`) fixam esse conteúdo, e mexer nele aqui
  arrastaria o ticket para uma reescrita de cenário.
- `allow_dynamic_stats`: fica **ausente** (default `False`). O exemplo mostra o
  caminho declarado; stat dinâmico é uma saída do TCK-062 e não precisa de vitrine
  para a fase fechar.
- Qualquer código de `backend/app/`. Este ticket só produz conteúdo e teste.
- Media (sprite ou background) para os stats ou para a lore.
- Um segundo cenário exemplo.

## Comportamento esperado

Quem abre o `exemplo-escola` depois desta wave vê duas barras no HUD
(Reputação em 40/100, com o texto de nível "aluno novo", e Energia em 80/100),
tem `!fofoca` disponível na paleta de comandos, e vê o bloco de lore do caderno
entrar no prompt quando a conversa do turno menciona o caderno.

Quem só carrega o cenário (`GET /api/scenarios`, `list_scenarios`) não vê
diferença: os arquivos novos são aditivos e o cenário continua válido.

## Detalhes técnicos

Todo o conteúdo abaixo é normativo: escreva exatamente isto, sem improvisar tom
nem inventar personagem novo. É português do Brasil, no registro do `world.md`
("realista e contida, no registro de drama adolescente brasileiro").

### `scenarios/exemplo-escola/stats.yaml`

```yaml
- id: reputacao
  name: Reputação
  icon: "⭐"
  color: "#f5c542"
  min: 0
  max: 100
  default: 40
  description: >
    O quanto o 3º B te leva a sério. Sobe quando você banca uma posição e desce
    quando te pegam em contradição ou de fofoca.
  levels:
    - from: 0
      text: >
        Ninguém do 3º B te leva a sério; conversa morre quando você chega perto
        e ninguém te conta nada de verdade.
    - from: 40
      text: >
        Você é o aluno novo: tolerado, observado, e ninguém se compromete com
        você antes de saber de que lado você está.
    - from: 75
      text: >
        Você virou referência na turma; gente que nunca falou com você procura
        sua opinião antes de decidir alguma coisa.
- id: energia
  name: Energia
  icon: "⚡"
  color: "#4fa3f5"
  min: 0
  max: 100
  default: 80
  description: >
    Quanto fôlego sobrou para o resto da manhã. Cai com confronto, corrida e
    noite mal dormida; sobe no intervalo e na cantina.
```

Por que estes dois: `reputacao` é o stat que o `world.md` pede (a moeda social do
caderno) e traz os três levels que o TCK-061 precisa exercitar; `energia` existe
justamente **sem** `levels` e **sem** ficar cheio de regra, para o exemplo cobrir
o caminho "stat sem nível" no prompt e no HUD.

### `scenarios/exemplo-escola/lorebook/caderno.yaml`

```yaml
title: O caderno de capa preta
keywords: [caderno, diário, capa preta]
scope: keyword
priority: 10
enabled: true
body: >
  O caderno é um brochurão de capa preta, sem nome na etiqueta, com as páginas
  numeradas à mão. Circula escondido entre alguns alunos do 3º B há uns três
  meses e registra, com data e detalhe, episódios de bullying dos últimos dois
  anos: quem fez, quem sofreu, quem assistiu calado. Parte do conteúdo já vazou
  em prints de celular, mas a maior parte só existe ali. Hoje ele está com a
  Chloe, que não decidiu o que fazer com ele. Ninguém admite ter lido; quase
  todo mundo já ouviu falar.
```

### `scenarios/exemplo-escola/lorebook/sala-do-gremio.yaml`

```yaml
title: A sala do grêmio
keywords: [grêmio, sala do grêmio, mural]
scope: keyword
priority: 0
enabled: true
body: >
  A sala do grêmio é um cômodo apertado ao lado da quadra, com armário de aço,
  um mural de avisos desatualizado e caixas de atas de gestões antigas
  empilhadas no canto. Fica destrancada na maior parte da manhã porque a chave
  vive perdida, o que a transformou no lugar onde a turma vai conversar sem
  professor por perto. A Bia é da gestão passada e entra ali como se fosse
  dela; é nas caixas de atas que está registrado o episódio do ano passado que
  ela guarda para si.
```

Consistente com `characters/bia.yaml` ("veterana do grêmio estudantil", segredo
sobre um episódio do ano passado) e com as regras de `world.md` ("os espaços
centrais são o portão de entrada, o pátio, a sala do 3º B, a biblioteca e a
quadra" — a sala do grêmio é declarada como anexo da quadra, não como espaço
central novo).

### `scenarios/exemplo-escola/commands.yaml`

```yaml
- name: fofoca
  description: O que andam dizendo de você pelas costas
  prompt: >
    Fora da narrativa, e sem avançar a história, liste o que cada personagem em
    cena andaria dizendo de você pelas costas neste momento. Uma linha por
    personagem, no tom de conversa de corredor, coerente com o que já aconteceu
    até aqui. Não invente personagem que não está em cena e não escreva nenhuma
    ação nova.
```

### Cuidado com nome de arquivo

O stem do arquivo de lore casa `^[a-z0-9-]+$`, então `sala-do-gremio.yaml` vai
**sem acento no nome do arquivo** — o acento vive no `title` e nas `keywords`,
que são texto livre. É a mesma regra que `characters/` e `starts/` já seguem.

## Contrato público

N/A — este ticket não expõe assinatura, tipo nem rota. Ele consome o schema
congelado no TCK-060 (`StatDef`, `LoreEntry`, `CommandDef`) e produz só conteúdo
de cenário e teste.

## Acceptance criteria

- [ ] `load_scenario("exemplo-escola")` carrega sem exceção com
      `[s.id for s in scenario.stats] == ["reputacao", "energia"]`.
- [ ] `reputacao` tem `min=0`, `max=100`, `default=40` e 3 levels com `from`
      estritamente crescente começando em 0; `energia` tem `default=80` e
      `levels == []`.
- [ ] Os dois stats têm `description`, `icon` e `color` preenchidos, e as cores
      casam `^#[0-9a-fA-F]{6}$`.
- [ ] `scenario.meta.allow_dynamic_stats is False`.
- [ ] `set(scenario.lorebook) == {"caderno", "sala-do-gremio"}`, ambas com
      `scope == "keyword"`, `enabled is True` e pelo menos uma keyword.
- [ ] `caderno` tem `priority` maior que `sala-do-gremio` (o gancho do cenário
      entra primeiro quando os dois casam).
- [ ] Para cada entrada de lore com `scope == "keyword"`, pelo menos uma keyword
      aparece (casefold) no texto do cenário (`world.md` + `starts/*.yaml` +
      `characters/*.yaml`) — a lore está ancorada em algo que o cenário já diz.
- [ ] `[c.name for c in scenario.commands] == ["fofoca"]`, com `description` e
      `prompt` não vazios, e o `prompt` dizendo explicitamente que é fora da
      narrativa.
- [ ] Cada `body` de lore tem entre 40 e 200 palavras (cabe no orçamento de
      injeção sem estourar).
- [ ] Os quatro arquivos novos são UTF-8 e têm caractere acentuado.
- [ ] `GET /api/scenarios` continua devolvendo `exemplo-escola` e o teste
      existente de `:127-135` passa sem alteração.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente que muda **de preparação** (asserções preservadas):

- `backend/tests/test_example_scenario.py:93-104`
  (`test_example_scenario_files_are_utf8_and_accented`): a lista `files`
  (`:97-99`) ganha `stats.yaml`, `commands.yaml` e o glob de `lorebook/*.yaml`.
  O corpo do laço e a asserção (`assert any(char in accented_chars ...)`) ficam
  **idênticos** — o que muda é a entrada do teste, não o que ele afere. É a única
  entrada existente tocada, e é preparação: a intenção declarada do teste é
  "todo arquivo do cenário exemplo é UTF-8 e acentuado", e os arquivos novos
  passam a pertencer a esse conjunto.
- Verificados e **não** afetados, portanto sem edição:
  `test_example_scenario_loads_without_exception:21`,
  `..._world_word_count_within_budget:59`, `..._prologue_word_count:65`,
  `..._conflict_and_mission_word_count:71` e `..._present:80` — todos aferem
  `world.md`, `scenario.yaml`, `starts/` e `characters/`, e nenhum desses
  arquivos é tocado. `test_get_scenarios_route_includes_exemplo_escola:127`
  afere `id` e `locale`, que não mudam.
- Nenhum teste de backend fora deste arquivo lê `scenarios/exemplo-escola`: os
  demais montam cenário em `tmp_path` com `monkeypatch` de
  `app.scenario.scenarios_dir`. Confirmado por busca de `exemplo-escola` fora de
  `test_example_scenario.py` — as ocorrências são todas de cenários sintéticos
  com o mesmo nome, criados em `tmp_path`.

Cenários novos (no próprio `backend/tests/test_example_scenario.py`, com a
fixture `_repo_scenarios` que já aponta `scenarios_dir` para o repositório,
`:15-18`):
- Feliz: ids e ordem dos stats; faixa, default e levels de `reputacao`;
  `energia` sem levels.
- Feliz: os dois stats têm `description`, `icon` e `color` válidos.
- Feliz: `allow_dynamic_stats` é `False`.
- Feliz: ids do lorebook, `scope`, `enabled`, keywords não vazias, e
  `priority` de `caderno` maior que a de `sala-do-gremio`.
- Feliz: um comando `fofoca`, com `description` e `prompt` não vazios.
- Borda: `from` dos levels de `reputacao` é estritamente crescente e cada um cai
  dentro de `[min, max]` (regra do modelo, aferida no dado real).
- Borda: cada `body` de lore fica entre 40 e 200 palavras.
- Borda: **coerência** — para cada entrada de `scope == "keyword"`, alguma
  keyword aparece casefold no texto concatenado de `world.md`, `starts/*.yaml` e
  `characters/*.yaml`. É o teste que impede lore órfã (`caderno` casa com
  `world.md`; `grêmio` casa com `characters/bia.yaml`). Comparação casefold
  simples, **sem** normalização de acento: a normalização é do `lore.py`
  (TCK-064) e duplicá-la aqui esconderia divergência entre keyword e texto.
- Borda: nenhum stem de `lorebook/` tem acento ou maiúscula.

## Rollout e kill switch

N/A — `risk: low`. O ticket só acrescenta arquivos de conteúdo a um cenário. O
desligamento é apagar o arquivo: sem `stats.yaml` o cenário volta a não ter
stats, sem `lorebook/` volta a não ter lore, sem `commands.yaml` volta a não ter
comando, e o loader do TCK-060 trata cada ausência como lista vazia, nunca como
erro. Nenhuma sessão em andamento quebra: `stat_views` (TCK-060) ignora id que
não existe mais no cenário.

## Observabilidade

Eventos: nenhum novo. O único sinal que este ticket move é `scenario_invalid`
(`scenario.py:288`), que **não** pode aparecer para `exemplo-escola` depois do
merge — é exatamente o que o teste de carga afere.

Métrica de sucesso: uma partida de 10 turnos no `exemplo-escola` termina com
`hud.stats` mostrando `reputacao` diferente de 40 (o valor se moveu de verdade) e
com pelo menos um `lore_injected` (telemetria do TCK-075) citando `caderno`.

## i18n

N/A — o cenário é `locale: pt-br` (`scenario.yaml:5`) e todo texto novo nasce em
português, como o resto do cenário. Conteúdo de cenário não passa por `t()` nem
tem contraparte em `en`: quem quiser um exemplo em inglês cria outro cenário.
