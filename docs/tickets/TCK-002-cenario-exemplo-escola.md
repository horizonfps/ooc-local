---
id: TCK-002
title: Criar o cenário exemplo-escola com escola e 3 NPCs
status: ready
points: 2
blockedBy: [TCK-001]
files:
  - scenarios/exemplo-escola/scenario.yaml
  - scenarios/exemplo-escola/world.md
  - scenarios/exemplo-escola/starts/default.yaml
  - scenarios/exemplo-escola/characters/chloe.yaml
  - scenarios/exemplo-escola/characters/ashlee.yaml
  - scenarios/exemplo-escola/characters/mika.yaml
  - backend/tests/test_example_scenario.py
migration: false
ui: false
risk: low
---

## Problema

O repositório não tem nenhum cenário (`ls scenarios` → não existe). A regra 3 do
plano (`dev/implementation-plan.md`, "Regras do loop") diz que
`scenarios/exemplo-escola/` acompanha toda feature nova: é o fixture de todas as
fases e o cenário do critério de verde da Fase 1 ("jogo 5 turnos, fecho o app,
reabro, continuo"). Sem ele não há o que jogar, e cada ticket seguinte teria que
inventar conteúdo próprio para testar.

## Escopo

Dentro:
- `scenarios/exemplo-escola/scenario.yaml` conforme `ScenarioMeta` do TCK-001,
  `locale: pt-br`.
- `world.md`: mundo da escola em 300–600 palavras — universo, tom de narração,
  regras do mundo, conflito central, papel do jogador (os campos do modo guiado
  da spec §2.2).
- `starts/default.yaml` conforme `StartConfig`: prólogo jogável (150–300
  palavras), `opening_scene`, `play_guide`, 3 `suggestions`, `hud` com
  `location`, `time`, `weather` (código do vocabulário do TCK-001).
- Três personagens em `characters/` (`chloe`, `ashlee`, `mika`), cada um com
  `name`, `role`, `appearance`, `personality`, `voice` e `mind` completo
  (`feeling`, `goal`, `opinion_of_player`, `secret_plan`), no formato da spec
  §2.4.
- `backend/tests/test_example_scenario.py`: teste que carrega a pasta real do
  repositório com `load_scenario("exemplo-escola")` e afere o contrato.

Fora (explícito):
- `media/` (sprites, backgrounds, capa) — Fases 2 e 5. Nenhum PNG entra aqui.
- `stats.yaml`, `lorebook.yaml`, `commands.yaml`, `endings.yaml` — Fases 3 e 4.
- Segundo start (`rota-vilao.yaml`) — não é preciso na Fase 1.
- Qualquer alteração no loader: se o schema não couber no conteúdo, o conteúdo
  cede; mudar o schema é ticket de foundation numa wave anterior (interface
  freeze do TCK-001).

## Comportamento esperado

Quem roda o app vê `Escola` no seletor de cenários da lista de sessões (TCK-009)
e, ao criar sessão, lê um prólogo que já situa a cena e sugere o que fazer.
Quem lê a pasta no editor entende o formato de cenário sem abrir o código: o
exemplo é a documentação executável do schema.

Conteúdo (decidido, não reabrir): escola de ensino médio brasileira, turma do 3º
ano, conflito central = um caderno com provas de bullying que circula na escola.
Personagens, inspirados no formato The Outcast:

| id | papel |
|---|---|
| `chloe` | a aluna excluída que guarda o caderno |
| `ashlee` | a popular que lidera a turma e teme o conteúdo do caderno |
| `mika` | o(a) amigo(a) de infância do jogador, no meio do fogo cruzado |

O jogador é aluno novo, entra no primeiro dia, no portão, 07:50, tempo `clear`.

## Detalhes técnicos

- Texto em pt-br, com acentuação correta, arquivos em utf-8 sem BOM.
- YAML com blocos `>`/`|` para textos longos (como no exemplo da spec §2.4);
  nada de linha única gigante.
- `default_start: default`; `starts/default.yaml` tem `characters: [chloe,
  ashlee, mika]` explícito, para exercitar o caminho da lista explícita do
  loader.
- Nada de conteúdo sexual ou de violência gráfica: o cenário aparece em teste,
  screenshot e README.
- O prólogo termina com o jogador em condição de agir (não fecha a cena) — é o
  que a tela de jogo mostra antes do primeiro input.
- O teste usa `load_scenario` (contrato do TCK-001), não `yaml.safe_load` direto:
  se o schema mudar numa fase futura, o teste falha aqui e não em produção.

Testes existentes que este ticket invalida: **nenhum**. Só acrescenta arquivos
de conteúdo e um teste novo.

## Contrato público

`scenarios/exemplo-escola/` é o fixture oficial do repositório. Outros tickets
podem depender de que ele exista, seja válido e tenha exatamente os ids
`chloe`, `ashlee`, `mika` e o start `default`. Renomear qualquer um desses ids é
mudança de contrato.

## Acceptance criteria

- [ ] `load_scenario("exemplo-escola")` carrega sem exceção.
- [ ] `GET /api/scenarios` inclui `{"id": "exemplo-escola", "locale": "pt-br"}`.
- [ ] Os três personagens têm todos os campos obrigatórios e `mind` com os
      quatro campos preenchidos (nenhum `null` em `opinion_of_player` ou
      `secret_plan`).
- [ ] `world.md` tem entre 300 e 600 palavras; o prólogo, entre 150 e 300 —
      aferido no teste (o orçamento de contexto da Fase 1 é 24K e o
      prompt-mestre inteiro tem que caber em ~3.000 tokens).
- [ ] `starts/default.yaml` traz 3 sugestões e `hud` com `weather` do
      vocabulário fechado.
- [ ] `npm run check` verde.

## Cenários de teste

- Feliz: `load_scenario("exemplo-escola").characters.keys() == {chloe, ashlee,
  mika}` e `starts["default"].hud.weather in WEATHER_CODES`.
- Feliz: `scenario.start()` devolve o start `default` sem argumento.
- Borda: contagem de palavras de `world.md` e do prólogo dentro das faixas.
- Borda: todos os arquivos decodificam em utf-8 e contêm acento (garante que não
  entrou texto sem acentuação nem arquivo em cp1252).
- Falha: não há caminho de falha próprio; se o loader recusar o conteúdo, o
  teste falha e o conteúdo é corrigido (nunca o schema).

## Rollout e kill switch

N/A — conteúdo estático versionado. Reverter é apagar a pasta.

## Observabilidade

Eventos: nenhum próprio.
Métrica de sucesso: o cenário aparece no seletor da UI e uma sessão criada nele
gera prólogo legível na tela de jogo (critério de verde da fase).

## i18n

O cenário é conteúdo, não UI: nasce só em pt-br, com `locale: pt-br` declarado.
A tradução de cenário não existe na Fase 1 (a i18n do projeto cobre strings do
app; prompts de sistema seguem o `locale` do cenário). Nenhuma chave nova.
