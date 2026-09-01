---
id: TCK-029
title: Congelar o schema do cenario com emotions, anchor, world_mode e caminho publico
status: in_review
points: 3
blockedBy: []
files:
  - backend/app/scenario.py
  - backend/tests/test_scenario.py
  - backend/tests/test_example_scenario.py
  - scenarios/exemplo-escola/scenario.yaml
  - scenarios/exemplo-escola/characters/chloe.yaml
  - scenarios/exemplo-escola/characters/ashlee.yaml
  - scenarios/exemplo-escola/characters/mika.yaml
migration: false
ui: false
risk: medium
---

## Problema

Toda a Fase 2 depende de três campos que os schemas pydantic **não têm** e que,
com `model_config = ConfigDict(extra="forbid")`, fazem o cenário parar de
carregar se alguém escrever no YAML:

- `Character.emotions` — vocabulário de emoções do personagem. É a fonte do grid
  da aba Mídia, do nome de arquivo `media/sprites/{sprite}/{emotion}.png` e do
  fallback de `[SPRITE:char:emotion]`.
- `Character.anchor` — âncora de power level, campo da spec §2.4 que a aba
  Personagens edita.
- `ScenarioMeta.world_mode` — se o `world.md` foi escrito nos campos guiados ou
  como prompt custom. Sem ele, a aba Mundo não sabe em qual modo abrir.

Além disso, todo ticket de builder precisa resolver "id de cenário → pasta" com
o mesmo confinamento de path que o loader já faz, e essa função hoje é privada
(`_confine_scenario_path`).

Este é o **interface freeze** da fase: consumidores nomeados são TCK-030
(esqueleto de cenário novo), TCK-031 (serialização do documento), TCK-032
(mídia), TCK-034 (manifesto), TCK-037 (aba Mundo), TCK-038 (aba Personagens) e
TCK-039 (aba Mídia). Depois deste merge, o contrato de arquivo não muda mais
nesta fase.

## Escopo

Dentro:
- `Character.emotions: list[str]` com default `["default"]` e validador.
- `Character.anchor: bool = False`.
- `ScenarioMeta.world_mode: Literal["guided", "custom"] = "guided"`.
- Promover `_confine_scenario_path` a `scenario_path(scenario_id: str) -> Path`
  público, mantendo o comportamento atual e atualizando a chamada interna.
- Atualizar `scenarios/exemplo-escola/` para declarar os campos novos.
- Testes de schema e do cenário exemplo.

Fora (explícito):
- Qualquer endpoint novo (isso é TCK-030/031/032).
- Usar `emotions` no prompt-mestre (injetar as emoções disponíveis no prompt é
  Fase 5, item de geração preguiçosa).
- Validar que existe arquivo PNG para cada emoção declarada — o jogo é
  texto-first e emoção sem asset é legítima.
- Criar `stats.yaml`, `lorebook.yaml`, `endings.yaml` ou qualquer campo de fase
  posterior.

## Comportamento esperado

Um `characters/*.yaml` pode declarar:

```yaml
emotions: [default, smile, sad, angry]
anchor: false
```

e um `scenario.yaml` pode declarar `world_mode: custom`. Arquivo que **não**
declara nada continua carregando exatamente como hoje, com
`emotions == ["default"]`, `anchor == False` e `world_mode == "guided"` — nenhum
cenário existente quebra.

## Detalhes técnicos

`Character.emotions`, validador de campo (`@field_validator("emotions")`), nesta
ordem:

1. cada item passa por `strip()` e precisa casar `^[a-z0-9-]+$` — é chave de
   nome de arquivo, não texto de UI; item fora disso levanta `ValueError` com a
   mensagem `invalid emotion '<x>', expected [a-z0-9-]+` (o loader já converte
   `ValidationError` em `ScenarioError` com resumo em `_summarize`);
2. deduplica preservando a ordem de aparição;
3. garante `"default"` como **primeiro** item: se não estiver na lista,
   é inserido no começo; se estiver em outra posição, é movido para o começo;
4. máximo de 20 emoções; acima disso, `ValueError`.

O default do campo é `["default"]`. Use `Field(default_factory=lambda: ["default"])`
para não compartilhar lista mutável entre instâncias.

`ScenarioMeta.world_mode` é `Literal["guided", "custom"]` com default
`"guided"`. Ele descreve **como o arquivo foi escrito**, não altera nada no
prompt-mestre nesta fase: `build_master_prompt` continua injetando o `world.md`
inteiro em `## MUNDO`, nos dois modos.

`scenario_path`: renomeie `_confine_scenario_path` para `scenario_path`,
mantendo a assinatura, as exceções e o corpo. Requisitos que já valem e não
podem regredir: id vazio, começado por `.`, ou contendo `/`, `\` ou `\0` levanta
`ScenarioError`; o resultado precisa ter a raiz de `scenarios_dir()` entre os
`parents`. A função precisa funcionar para **pasta que ainda não existe** (é
assim que TCK-030 valida o destino antes de criar) — `Path.resolve()` de caminho
inexistente é válido e não levanta; não acrescente `strict=True`.

Cenário exemplo (`scenarios/exemplo-escola/`):

- `scenario.yaml` ganha `world_mode: custom` — o `world.md` de lá é prosa
  escrita à mão, sem os cabeçalhos canônicos do modo guiado; declarar `custom` é
  a verdade e evita que o builder abra o aviso de fallback.
- `characters/chloe.yaml`: `emotions: [default, sad, angry, smile]`
- `characters/ashlee.yaml`: `emotions: [default, mocking, angry, smile]`
- `characters/mika.yaml`: `emotions: [default, smile, sad, joy]`
- `anchor` fica omitido nos três (o default `false` é a verdade).

Migração: não há dados persistidos a migrar (o SQLite de sessões não guarda
schema de cenário). A "migração" é a atualização dos YAML do cenário exemplo,
que vai no mesmo commit dos campos — cenário e schema nunca ficam
dessincronizados.

## Contrato público

```python
# backend/app/scenario.py
class Character(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    role: str
    appearance: str
    personality: str
    voice: str
    mind: CharacterMind
    sprite: str | None = None
    anchor: bool = False
    emotions: list[str] = ["default"]   # via default_factory; normalizado

class ScenarioMeta(BaseModel):
    ...
    world_mode: Literal["guided", "custom"] = "guided"

def scenario_path(scenario_id: str) -> Path:
    """Scenario folder confined to scenarios_dir(); raises ScenarioError otherwise.
    Works for folders that do not exist yet."""
```

Ordem canônica dos campos ao serializar (usada por TCK-031): `name`, `role`,
`appearance`, `personality`, `voice`, `mind` (`feeling`, `goal`,
`opinion_of_player`, `secret_plan`), `sprite`, `anchor`, `emotions`.

## Acceptance criteria

- [ ] `characters/*.yaml` com `emotions` e `anchor` carrega sem erro.
- [ ] `scenario.yaml` com `world_mode: custom` carrega; valor fora do literal é
      `ScenarioError`.
- [ ] Personagem sem `emotions` carrega com `["default"]`; sem `anchor` carrega
      com `False`.
- [ ] `emotions: [sad, default, sad]` normaliza para `["default", "sad"]`.
- [ ] `emotions: ["Feliz "]` é `ScenarioError` (maiúscula/espaço não é slug).
- [ ] `scenario_path` é público, confina igual ao anterior e aceita pasta
      inexistente.
- [ ] `scenarios/exemplo-escola/` declara `world_mode` e `emotions` nos três
      NPCs e continua carregando.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente que muda de preparação (asserções preservadas):

- `backend/tests/test_scenario.py::test_character_unknown_field_raises_scenario_error`
  usa o campo inventado `personalidade: typo`, que continua desconhecido — o
  teste passa sem alteração. Confirme que ele não vira falso verde: `emotions` e
  `anchor` agora são conhecidos, `personalidade` não.
- `backend/tests/test_example_scenario.py::test_example_scenario_characters_have_complete_mind`
  e os demais continuam válidos; acrescente asserção nova de que cada
  personagem do exemplo declara ao menos duas emoções e que `emotions[0] == "default"`.
- Os testes que chamam `_confine_scenario_path` por nome (se houver) passam a
  chamar `scenario_path`: adaptação de preparação, mesma asserção.

Cenários novos:
- Feliz: character YAML completo com `emotions` e `anchor: true` → modelo com os
  valores lidos.
- Feliz: `world_mode: guided` explícito e ausente dão o mesmo resultado.
- Borda: `emotions: []` → normaliza para `["default"]`.
- Borda: 21 emoções → `ScenarioError` com a razão em uma linha.
- Borda: `emotions: [smile, default]` → `["default", "smile"]`.
- Falha: `world_mode: guiado` → `ScenarioError` mencionando o campo.
- Falha: `scenario_path("../fora")` e `scenario_path("")` levantam
  `ScenarioError` (paridade com `test_load_scenario_traversal_ids_raise`).

## Rollout e kill switch

N/A — sem flag. Compatibilidade é para trás por default; a incompatibilidade é
para frente e está declarada: cenário salvo com os campos novos não carrega em
backend anterior a este ticket. É justamente por isso que ele roda em wave
anterior à dos consumidores.

## Observabilidade

Eventos: nenhum novo. `scenario_invalid` (já existente em `list_scenarios`)
passa a cobrir também erro de `emotions`/`world_mode`, com a razão resumida.
Métrica de sucesso: `scenarios/exemplo-escola/` carrega com os campos novos e
nenhum `scenario_invalid` aparece no log ao abrir a lista.

## i18n

N/A — campos de arquivo. `emotions` é chave de arquivo em inglês por decisão de
formato; o rótulo traduzido é problema da UI (TCK-038), que mostra o valor cru.
