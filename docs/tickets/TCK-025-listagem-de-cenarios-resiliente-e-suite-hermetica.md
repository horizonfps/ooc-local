---
id: TCK-025
title: Tornar a listagem de cenários resiliente e a suíte do cenário exemplo hermética
status: done
points: 3
blockedBy: [TCK-019]
files:
  - backend/app/scenario.py
  - backend/tests/test_scenario.py
  - backend/tests/test_example_scenario.py
migration: false
ui: false
risk: low
---

## Problema

Quatro defeitos de robustez em `backend/app/scenario.py`, todos no caminho de
listagem e de mensagem de erro:

1. **Glob só pega `*.yaml`.** `_load_starts` (`backend/app/scenario.py:145`) e
   `_load_characters` (`:172`) usam `glob("*.yaml")`. Um autor que salva
   `chloe.yml` vê o personagem sumir sem nenhuma mensagem: o cenário carrega, só
   que incompleto, e a `starts/` fica com um start a menos. Falha silenciosa é
   pior que erro.
2. **Listagem frágil.** `list_scenarios` (`backend/app/scenario.py:210`) só
   captura `ScenarioError` (`:223`). Um `UnicodeDecodeError` num `world.md` mal
   salvo, um `PermissionError`, ou um `RecursionError` do yaml derrubam a rota
   `GET /api/scenarios` inteira com 500 — todos os cenários somem da tela por
   causa de um.
3. **Log poluído.** `_load_yaml` (`:127`) usa `str(ValidationError)` como
   `reason`; o pydantic v2 formata isso em várias linhas, com URL de
   documentação. `emit("scenario_invalid", ..., error=exc.reason)` (`:224`)
   escreve um JSON com um valor de várias linhas dentro de um log
   line-oriented (`backend/app/observability.py:23`), e a linha vira ilegível.
4. **Suíte não-hermética.** `backend/tests/test_example_scenario.py` tem 10
   testes e todos chamam `load_scenario("exemplo-escola")` (ou a rota
   `GET /api/scenarios`) **sem** fixar `scenarios_dir`. Quem tiver
   `OOC_SCENARIOS_DIR` exportado no ambiente — variável que o próprio código
   oferece (`backend/app/scenario.py:109`) — roda a suíte contra outro diretório
   e vê os 10 falharem por motivo errado. A suíte que afere tamanho de mundo
   (`:45`) e de prólogo (`:51`) depende do conteúdo do repositório, e precisa
   apontar para o conteúdo do repositório explicitamente.

## Escopo

Dentro:
- Glob de `*.yaml` **e** `*.yml` em `starts/` e `characters/`, com erro
  explícito para stem duplicado.
- `list_scenarios` resiliente a qualquer exceção por entrada.
- `ScenarioError.reason` em uma linha; texto completo do erro de validação em
  `ScenarioError.details`.
- Fixture hermética em `backend/tests/test_example_scenario.py`.

Fora (explícito):
- Confinamento de path, validadores de `HudState`, validação de
  `default_start`: são o **TCK-019**, que chega mergeado antes deste.
- Aceitar `scenario.yml` no lugar de `scenario.yaml`: o arquivo de metadados
  continua com nome único e canônico, e o erro "scenario.yaml is missing"
  (`backend/app/scenario.py:185`) já diz o que fazer. A tolerância de extensão
  vale só para os diretórios onde o autor cria muitos arquivos.
- Cache de cenário carregado entre requisições.
- Validar semântica de conteúdo (tamanho de `world.md`, número de sugestões):
  os testes que fazem isso continuam existindo e continuam aferindo o mesmo;
  este ticket só muda de onde eles leem.
- Mudar o formato do log (`backend/app/observability.py`): o `emit` continua
  como está; o que muda é o valor que ele recebe.

### Testes existentes que este ticket invalida

Grep em `backend/tests/`:

- `test_character_unknown_field_raises_scenario_error`
  (`backend/tests/test_scenario.py:132`) só afere o **tipo** `ScenarioError`,
  não o texto. Continua válido depois do resumo do erro de validação.
- `test_start_characters_unknown_id_raises` (`:109`) afere `"ghost" in
  exc.reason`, sobre um `reason` construído à mão
  (`backend/app/scenario.py:196`), que não passa pelo resumo. Válido.
- `test_list_scenarios_skips_invalid_between_valid_and_emits` (`:165`) afere
  `events[0][0] == "scenario_invalid"` e a lista de ids devolvida. Continua
  válido: o `props` do evento ganha uma chave e o teste não afere o dicionário
  inteiro.
- `test_list_scenarios_ignores_file_and_folder_without_scenario_yaml` (`:121`),
  `test_list_scenarios_empty_root_returns_empty_list` (`:180`) e
  `test_list_scenarios_missing_root_returns_empty_without_log` (`:185`):
  válidos sem adaptação.
- `test_missing_world_md_raises` (`:144`) e `test_load_scenario_not_found_raises`
  (`:155`): `reason` construído à mão, uma linha só. Válidos.
- `backend/tests/test_example_scenario.py` (10 testes): **adaptação de
  preparação** — entra uma fixture `autouse` function-scoped que neutraliza a
  variável de ambiente e fixa a raiz no diretório do repositório. Nenhuma
  asserção muda; os mesmos 10 testes continuam aferindo exatamente o que
  aferiam.
- `backend/tests/test_prompt.py`, `test_compact.py`, `test_turn.py` e
  `test_sessions.py` já fixam `scenarios_dir` por monkeypatch
  (`test_turn.py:72` e equivalentes) e não são tocados.

## Comportamento esperado

Do ponto de vista do chamador da API:

- `GET /api/scenarios` nunca responde 500 por causa de um cenário quebrado: o
  quebrado some da lista e vira **uma** linha de log legível.
- `starts/rota-vilao.yml` e `characters/chloe.yml` carregam igual aos `.yaml`.
- Dois arquivos com o mesmo stem e extensões diferentes viram erro explícito, em
  vez de um vencer por ordem alfabética.

Do ponto de vista de quem roda a suíte: `uv run pytest -q` dá o mesmo resultado
com e sem `OOC_SCENARIOS_DIR` no ambiente.

## Detalhes técnicos

- Glob duplo: `sorted([*d.glob("*.yaml"), *d.glob("*.yml")])` em `_load_starts`
  e `_load_characters`. Se dois arquivos compartilham o stem,
  `ScenarioError(d, f"duplicate id '{stem}' in .yaml and .yml")`. Sem isso a
  ordem do `sorted` decide silenciosamente qual vence.
  `sorted` sobre `Path` compara o caminho inteiro, então `a.yaml` vem antes de
  `a.yml`; detecte a duplicata pelo stem, não pela posição.
- `list_scenarios`: o `except ScenarioError` continua emitindo
  `scenario_invalid` com `path`/`error`; um `except Exception` adicional emite o
  mesmo evento com `path=str(entry)`, `error=str(exc)` truncado em uma linha e
  `error_type=type(exc).__name__`, e a entrada é pulada. Nenhuma exceção sobe.
  **Não** capture `BaseException`: `KeyboardInterrupt` durante uma listagem tem
  que continuar interrompendo.
- `_summarize(exc: ValidationError) -> str` produz
  `"N erro(s): loc1: msg1; loc2: msg2"` a partir de `exc.errors()`, com `loc`
  juntado por ponto, sem quebra de linha, truncado em 300 caracteres. Usada nos
  três pontos que hoje fazem `str(exc)` de `ValidationError`:
  `backend/app/scenario.py:127`, `:161` e o caminho de `_load_characters` que
  passa por `_load_yaml`.
- `ScenarioError.__init__(self, path, reason, details=None)`: `details` é
  atributo novo com default `None`, carregando o texto integral do
  `ValidationError`. **Não** é emitido no log — quem quiser o detalhe roda o
  loader na mão. Os chamadores existentes que passam dois argumentos continuam
  válidos.
- Fixture hermética, em `backend/tests/test_example_scenario.py`:

  ```python
  REPO_SCENARIOS = Path(__file__).resolve().parents[2] / "scenarios"

  @pytest.fixture(autouse=True)
  def _repo_scenarios(monkeypatch):
      monkeypatch.delenv("OOC_SCENARIOS_DIR", raising=False)
      monkeypatch.setattr("app.scenario.scenarios_dir", lambda: REPO_SCENARIOS)
  ```

  `parents[2]` a partir de `backend/tests/test_example_scenario.py` é a raiz do
  repositório, a mesma que `scenarios_dir` calcula com `parents[2]` a partir de
  `backend/app/scenario.py:112`. A fixture é function-scoped porque
  `monkeypatch` é function-scoped; `autouse` cobre os 10 testes sem editar
  nenhum deles. O `delenv` é o que torna o teste **prova** de hermeticidade: sem
  ele, o `setattr` bastaria e a suíte continuaria silenciosa sobre a variável.

## Contrato público

```python
# backend/app/scenario.py
class ScenarioError(Exception):
    path: Path
    reason: str            # sempre uma única linha
    details: str | None    # texto integral do erro de validação, quando houver

    def __init__(self, path: Path, reason: str, details: str | None = None) -> None: ...
```

`load_scenario(scenario_id)` e `list_scenarios()` mantêm assinatura e tipo de
retorno.

## Acceptance criteria

- [ ] `starts/x.yml` e `characters/y.yml` são carregados com os mesmos ids que
      as versões `.yaml`.
- [ ] Stem duplicado entre `.yaml` e `.yml` levanta `ScenarioError` citando o
      stem.
- [ ] Um cenário que levanta exceção não-`ScenarioError` é pulado por
      `list_scenarios`, que devolve os demais e emite `scenario_invalid` com
      `error_type`.
- [ ] `KeyboardInterrupt` levantado dentro do load de um cenário **não** é
      capturado por `list_scenarios`.
- [ ] `ScenarioError.reason` de um YAML inválido não contém `"\n"` e tem no
      máximo 300 caracteres; `ScenarioError.details` contém o texto integral.
- [ ] Um teste dentro de `backend/tests/test_example_scenario.py` que faz
      `monkeypatch.setenv("OOC_SCENARIOS_DIR", str(tmp_path))` com `tmp_path`
      vazio continua carregando `exemplo-escola` e passando — prova de que a
      fixture neutraliza a variável.
- [ ] A fixture `autouse` cobre os 10 testes do módulo sem que nenhum deles
      declare fixture nova no corpo.
- [ ] `npm run check` verde.

## Cenários de teste

- Feliz: cenário com um start `.yml` e um personagem `.yml` carrega com os
  mesmos ids que a versão `.yaml`.
- Feliz: cenário misto (`default.yaml` + `rota-vilao.yml`) → dois starts.
- Feliz: `list_scenarios` com um cenário válido e um que levanta `RuntimeError`
  no parse (monkeypatch em `yaml.safe_load` que levanta só naquele path) →
  devolve o válido e emite `scenario_invalid` com `error_type="RuntimeError"`.
- Borda: `starts/default.yaml` e `starts/default.yml` no mesmo diretório →
  `ScenarioError` de id duplicado; idem em `characters/`.
- Borda: `ValidationError` com 3 campos errados → `reason` de uma linha, com
  `"3 erro(s)"`, e `details` com o texto integral do pydantic.
- Borda: `reason` de um erro com mais de 300 caracteres → truncado, ainda em uma
  linha.
- Borda: `list_scenarios` onde o load levanta `KeyboardInterrupt` → a exceção
  sobe.
- Falha: com `OOC_SCENARIOS_DIR` apontando para `tmp_path` vazio, os testes de
  `test_example_scenario.py` continuam verdes.

## Rollout e kill switch

N/A. Não há flag: tornar a listagem resiliente e o log legível não tem estado
intermediário desligável, e a única mudança que pode reprovar conteúdo existente
(stem duplicado) foi verificada contra o único cenário do repositório,
`scenarios/exemplo-escola/`, que não tem duplicata. Rollback é `git revert` do
PR.

## Observabilidade

Eventos: `scenario_invalid` (`backend/app/scenario.py:224`) — já existente, com
`path` e `error` (agora garantidamente uma linha) e, no caminho novo,
`error_type`.
Métrica de sucesso: `GET /api/scenarios` responde 200 mesmo com um cenário
propositalmente corrompido no diretório, e o log tem exatamente uma linha
`scenario_invalid` por cenário quebrado.

## i18n

N/A. As mensagens de `ScenarioError` são log e detalhe de API para o
desenvolvedor, não texto de jogador; a UI já traduz os erros de carregamento com
`sessions.new.scenariosError` e a família `error.*` em
`frontend/src/strings.ts`. Nenhuma chave nova.
