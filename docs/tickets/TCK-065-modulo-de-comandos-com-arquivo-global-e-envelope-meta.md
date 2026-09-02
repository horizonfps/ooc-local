---
id: TCK-065
title: Criar o módulo de comandos com arquivo global, resolução por sinal e envelope meta
status: done
points: 3
blockedBy: [TCK-060]
files:
  - backend/app/commands.py
  - backend/tests/test_commands.py
migration: false
ui: false
risk: low
---

## Problema

Depois do TCK-060 o cenário tem `commands.yaml` carregado em
`LoadedScenario.commands`, mas nada resolve o que o jogador digita. E não existe
nenhum comando global: hoje, se o jogador quiser um diário, um resumo da história
ou o pensamento dos NPCs, tem que pedir dentro da narrativa e torcer para o
narrador não avançar a cena — que é exatamente o que ele não quer.

Falta a peça que transforma `!fofoca` ou `/diary` num prompt pronto para o turno
meta: onde moram os comandos globais, como o arquivo do usuário nasce, como se
decide entre cenário e global, e qual envelope garante que o modelo responda
fora da narrativa.

Este ticket entrega só essa peça. A rota, o turno meta, os eventos
`meta_player_turn`/`meta_narrator_turn`, o 422 `unknown_command` e
`SessionDetail.commands` são o TCK-072; a paleta e o Play Guide são o TCK-074.

## Escopo

Dentro:
- `backend/app/commands.py` novo: `GLOBAL_COMMANDS_PATH`,
  `DEFAULT_GLOBAL_COMMANDS`, `GlobalCommandDef`, `load_global_commands`,
  `ResolvedCommand`, `resolve_command`, `UnknownCommand`,
  `META_PROMPT_TEMPLATES`, `build_meta_user_message`, `command_views`,
  `SCENARIO_SIGIL`, `GLOBAL_SIGIL`, `COMMAND_NAME_RE`, `COMMAND_ARG_CHARS`,
  `GLOBAL_COMMANDS_ENV`, `global_commands_path`.
- `backend/tests/test_commands.py`: testes de unidade, sem `TestClient` e sem
  banco; **todo** teste que toca disco passa `path=tmp_path / "commands.yaml"`.

Fora (explícito):
- `backend/app/main.py`, `backend/app/turn.py`, `backend/app/sessions.py`: rota,
  turno meta, janela de histórico do meta, gravação dos eventos meta, 422
  `unknown_command`, `TurnView.meta/command` e `SessionDetail.commands`
  preenchido são todos TCK-072.
- Paleta de comandos, Play Guide e estilo do turno meta na UI: TCK-074
  (spec pronta em `fase3/design/game-commands.md`).
- Aba Comandos do builder: TCK-073.
- Carregar `commands.yaml` do **cenário** e o modelo `CommandDef`: TCK-060.
  Aqui só se lê `scenario.commands`.
- Chamar o LLM. **Este módulo não tem função async**: quem streama o turno meta é
  o `run_turn` do TCK-072, com o provider do papel `narrator` — comando meta é
  narração fora da história, não é call de utility.
- Escrever no event store ou emitir telemetria de turno. O único `emit` daqui é
  `commands_file_invalid`, que é sobre o arquivo do próprio módulo.

## Comportamento esperado

Do ponto de vista do chamador (o TCK-072): chama `load_global_commands()` uma vez
por requisição, passa a mensagem crua do jogador para `resolve_command`. Se vier
`None`, é turno normal e nada muda. Se vier um `ResolvedCommand`, é turno meta:
`build_meta_user_message` devolve o texto que entra como `user`. Se vier
`UnknownCommand`, é 422 antes de abrir o stream.

Do ponto de vista do jogador (quando o TCK-072/074 entrarem): `!nome` roda um
comando do cenário, `/nome` roda um global, e o arquivo `~/.ooc-local/commands.yaml`
nasce sozinho no primeiro uso com `diary`, `inner` e `recap` — igual ao
`config.yaml` (`config.py:55-58`). Se ele editar esse arquivo e quebrar o YAML, o
jogo **não cai**: o turno roda com os defaults em memória e a falha vai para o
log.

### Decisão: o resto da linha vira `arg`

`!fofoca sobre a Chloe` resolve o comando `fofoca` com `arg="sobre a Chloe"`, e
o `arg` entra no fim da mensagem meta sob um rótulo próprio. Ignorar o resto
seria descartar em silêncio o que o jogador digitou de propósito — e "digitei e
sumiu" é o pior contrato possível num campo de texto. O `arg` é cortado em
`COMMAND_ARG_CHARS`; sem resto, `arg is None` e o rótulo não aparece.

## Detalhes técnicos

### Constantes e caminho

```python
GLOBAL_COMMANDS_PATH = CONFIG_DIR / "commands.yaml"   # from app.config
GLOBAL_COMMANDS_ENV = "OOC_COMMANDS_FILE"
SCENARIO_SIGIL = "!"
GLOBAL_SIGIL = "/"
COMMAND_NAME_RE = re.compile(r"^[a-z0-9_-]+$")
COMMAND_ARG_CHARS = 200
```

`CONFIG_DIR` vem de `app.config` (`config.py:7`), o mesmo lugar de onde
`sessions.py:14` e `observability.py:7` já tiram os deles.

`global_commands_path() -> Path` resolve o caminho de forma preguiçosa, no
molde de `db_path()` (`sessions.py:112-116`): se `OOC_COMMANDS_FILE` estiver
no ambiente, devolve `Path(os.environ["OOC_COMMANDS_FILE"])`; senão,
`GLOBAL_COMMANDS_PATH`. É o que permite à suíte inteira (o `get_session` do
TCK-072 chama `load_global_commands()` sem argumento em dezenas de testes)
apontar o arquivo para um `tmp_path` via `conftest.py`, sem nunca tocar
`~/.ooc-local/commands.yaml` na máquina de quem roda o pre-commit.

### `DEFAULT_GLOBAL_COMMANDS`

Texto YAML literal, no molde de `DEFAULT_CONFIG` (`config.py:10-20`): uma
constante `str` escrita à mão, comentada em inglês se precisar, que é gravada tal
e qual no primeiro uso. Três comandos, `description` e `prompt` por locale
(`pt-br` e `en`), prompts curtos e específicos:

```yaml
- name: diary
  description:
    pt-br: Diário do jogador sobre o dia
    en: Player diary of the day
  prompt:
    pt-br: >
      Escreva a entrada de diário que o jogador escreveria sobre o que
      aconteceu até aqui: primeira pessoa, no máximo 200 palavras, só o que
      ele viu, sentiu e decidiu.
    en: >
      Write the diary entry the player would write about what happened so
      far: first person, at most 200 words, only what they saw, felt and
      decided.
- name: inner
  description:
    pt-br: Pensamentos de cada NPC em cena
    en: Thoughts of each NPC in scene
  prompt:
    pt-br: >
      Liste, uma linha por NPC em cena, o que ele pensa agora sobre o jogador
      e sobre a situação, no formato "Nome: pensamento". Sem diálogo e sem
      ação.
    en: >
      List, one line per NPC in scene, what they think right now about the
      player and the situation, in the format "Name: thought". No dialogue,
      no action.
- name: recap
  description:
    pt-br: Recapitulação da história até aqui
    en: Recap of the story so far
  prompt:
    pt-br: >
      Recapitule a história até aqui em no máximo 150 palavras: o que o
      jogador fez, o que ficou pendente e quem quer o quê. Não invente fato
      novo.
    en: >
      Recap the story so far in at most 150 words: what the player did, what
      is pending and who wants what. Do not invent new facts.
```

### `GlobalCommandDef`

```python
class GlobalCommandDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: dict[str, str]
    prompt: dict[str, str]
```

`extra="forbid"` como todo modelo de arquivo do projeto (`scenario.py:32,44`).
Validadores: `name` casa `COMMAND_NAME_RE`; `description` e `prompt` não podem
ser dicts vazios. Locale não é restrito a `en`/`pt-br` — o `_pick_locale` já lida
com qualquer chave, e travar aqui impediria o usuário de acrescentar um idioma
no arquivo dele.

### `load_global_commands(path: Path | None = None) -> list[GlobalCommandDef]`

`path is None` → `global_commands_path()`. Cria o arquivo com `DEFAULT_GLOBAL_COMMANDS` quando ele não existe, exatamente
como `load_config` (`config.py:55-58`: `mkdir(parents=True, exist_ok=True)` +
`write_text(..., encoding="utf-8")`), e então lê.

- `yaml.safe_load` devolvendo `None` (arquivo vazio) → `[]`. Arquivo esvaziado é
  escolha do usuário: zero comandos globais, sem erro. É o estado que a UI já
  espera (`design/game-commands.md`, estado 3 da paleta).
- Raiz que não é lista, `yaml.YAMLError`, `ValidationError` em qualquer item, ou
  nome repetido → `emit("commands_file_invalid", path=str(path), error=<motivo
  cortado em 300 chars>)` e devolve os defaults **parseados em memória**. O
  arquivo do usuário **não** é reescrito: sobrescrever o que ele digitou errado
  apagaria o trabalho dele.
- O corte de 300 chars do motivo copia `_summarize` de `scenario.py:22-28`, que
  existe pelo mesmo motivo (erro de pydantic inteiro no log é ilegível).
- Ordem do resultado: a do arquivo.

Esta é a única função do módulo que toca disco e a única que emite. Todo teste a
chama com `path` explícito em `tmp_path`, **ou** sem argumento com
`OOC_COMMANDS_FILE` apontando para `tmp_path` via `monkeypatch.setenv`; nunca
sem nenhum dos dois, porque escrever em `~/.ooc-local/commands.yaml` durante a
suíte contaminaria a máquina do dev (o repo já cuida disso para o banco, com
`OOC_SESSIONS_DB`, `sessions.py:113`).

### `resolve_command(text, scenario, global_commands) -> ResolvedCommand | None`

```python
class ResolvedCommand(BaseModel):
    name: str
    scope: Literal["scenario", "global"]
    prompt: str
    arg: str | None

class UnknownCommand(Exception):
    def __init__(self, prefix: str, name: str) -> None: ...
```

Algoritmo:
1. `stripped = text.strip()`; vazio ou primeiro caractere fora de
   `{SCENARIO_SIGIL, GLOBAL_SIGIL}` → `None`. O sinal precisa ser o primeiro
   caractere do texto, como na paleta do TCK-074 — `"vou ver /diary"` é turno
   normal;
2. `head = stripped[1:]`; o nome vai até o primeiro espaço em branco (inclui
   `\n`), o resto é o `arg`;
3. `name = name_part.casefold()`; `arg = resto.strip()[:COMMAND_ARG_CHARS]` ou
   `None` quando vazio;
4. nome vazio ou fora de `COMMAND_NAME_RE` → `UnknownCommand(prefix, name)`.
   Prefixo reconhecido é promessa de comando: devolver `None` aqui mandaria
   `"!!!"` para o narrador como se fosse fala;
5. `!` procura em `scenario.commands` por `name`; `/` procura em
   `global_commands`. Não achou → `UnknownCommand(prefix, name)`;
6. prompt: `CommandDef.prompt` é `str` (o comando do cenário é escrito no locale
   do cenário, brief 1.1); `GlobalCommandDef.prompt` é mapa por locale e passa
   por `_pick_locale`.

`_pick_locale(mapping, locale) -> str`: `mapping.get(locale)`, senão
`mapping[sorted(mapping)[0]]`, senão `""`. O `sorted` é o que torna o fallback
determinístico — "qualquer locale presente" (brief 2.5) não pode depender da
ordem de iteração do YAML.

### `META_PROMPT_TEMPLATES` e `build_meta_user_message(resolved, locale)`

```python
META_PROMPT_TEMPLATES = {"pt-br": {"envelope": ..., "arg_label": ...}, "en": {...}}
```

`build_meta_user_message` devolve
`f"{envelope}\n\n{resolved.prompt}"`, mais `f"\n\n{arg_label}: {resolved.arg}"`
quando há `arg`. Locale desconhecido cai em `pt-br`, mesmo fallback de
`director.py:76`.

O envelope é o que segura o modelo fora da história: manda responder fora da
narrativa, sem avançar a cena, sem tag e sem fala de personagem em cena, e diz
que o pedido não é ação do jogador. "Sem tag" é literal e importa: o turno meta
do TCK-072 não passa por `parse_tags`, então um `[LOC:...]` cuspido ali ficaria
visível no texto, cru, para o jogador.

### `command_views(scenario, global_commands, locale) -> list[CommandView]`

`CommandView` (`{name, description, scope}`) vem congelado do TCK-060, importado
de `app.scenario` — mesmo módulo de `CommandDef`, e é a única casa possível:
`sessions.py` vai importar `commands.py` (TCK-072, para preencher
`SessionDetail.commands`), então `CommandView` morar em `sessions.py` faria
import circular.

Ordem: comandos do cenário na ordem de `scenario.commands`, depois os globais na
ordem do arquivo. Descrição do cenário é `str` direto; a global passa por
`_pick_locale`. Nome sai sem sinal — quem põe o `!`/`/` é a UI (`SCENARIO_SIGIL`
e `GLOBAL_SIGIL` também existem em `frontend`, por `design/game-commands.md`), e
o `scope` é o que diz qual sinal usar.

Comentários em inglês e mínimos, como o resto do backend.

### Ressalva de porte

Estimativa: ~650 linhas com testes, acima do alvo de ~400 (o molde TCK-053, também
de 3 pontos, fechou em 544). Aceito pelo coordenador porque o módulo é puro e o
volume é de casos de teste, não de lógica. Se o diff passar de ~550, corte nesta
ordem: (1) agrupe os casos de `load_global_commands (arquivo inválido)` malformado num único
`pytest.mark.parametrize`; (2) agrupe as rejeições nomeadas de `resolve_command` num
`parametrize` por motivo; (3) mantenha um caso feliz completo e um de clamp fora
do `parametrize`, porque são os que documentam o contrato.

## Contrato público

```python
# backend/app/commands.py
GLOBAL_COMMANDS_PATH: Path            # CONFIG_DIR / "commands.yaml"
GLOBAL_COMMANDS_ENV: str = "OOC_COMMANDS_FILE"
DEFAULT_GLOBAL_COMMANDS: str          # YAML text written on first use
SCENARIO_SIGIL: str = "!"
GLOBAL_SIGIL: str = "/"
COMMAND_NAME_RE: re.Pattern
COMMAND_ARG_CHARS: int = 200
META_PROMPT_TEMPLATES: dict[str, dict[str, str]]

class GlobalCommandDef(BaseModel):    # extra="forbid"
    name: str
    description: dict[str, str]
    prompt: dict[str, str]

class ResolvedCommand(BaseModel):
    name: str
    scope: Literal["scenario", "global"]
    prompt: str
    arg: str | None

class UnknownCommand(Exception):
    prefix: str
    name: str

def global_commands_path() -> Path      # OOC_COMMANDS_FILE or GLOBAL_COMMANDS_PATH, resolved lazily
def load_global_commands(path: Path | None = None) -> list[GlobalCommandDef]
def resolve_command(
    text: str,
    scenario: LoadedScenario,
    global_commands: list[GlobalCommandDef],
) -> ResolvedCommand | None                    # raises UnknownCommand
def build_meta_user_message(resolved: ResolvedCommand, locale: str) -> str
def command_views(
    scenario: LoadedScenario,
    global_commands: list[GlobalCommandDef],
    locale: str,
) -> list[CommandView]
```

Consumido pelo TCK-072 (turno meta, 422, `SessionDetail.commands`), que declara
este ticket em `blockedBy`.

## Acceptance criteria

- [ ] `global_commands_path()` devolve `Path(os.environ["OOC_COMMANDS_FILE"])`
      quando a variável existe (via `monkeypatch.setenv`) e `GLOBAL_COMMANDS_PATH`
      quando não existe; `load_global_commands()` sem argumento usa esse caminho.
- [ ] `load_global_commands(tmp_path / "commands.yaml")` cria o arquivo com
      `DEFAULT_GLOBAL_COMMANDS` byte a byte e devolve os três comandos `diary`,
      `inner` e `recap`, nessa ordem.
- [ ] Segunda chamada não reescreve o arquivo (conteúdo editado pelo usuário
      sobrevive).
- [ ] Arquivo com YAML quebrado, raiz que não é lista, item inválido ou nome
      repetido devolve os defaults em memória, **emite `commands_file_invalid`**
      e deixa o arquivo do usuário intacto.
- [ ] Arquivo vazio devolve `[]` sem emitir nada.
- [ ] `resolve_command("olá", ...)` e `resolve_command("", ...)` devolvem `None`.
- [ ] `resolve_command("!fofoca", ...)` devolve
      `ResolvedCommand(name="fofoca", scope="scenario", prompt=<prompt do
      cenário>, arg=None)`.
- [ ] `resolve_command("/diary", ...)` devolve o global com o prompt no locale do
      cenário; cenário `locale: en` traz o prompt em inglês.
- [ ] `resolve_command("!fofoca sobre a Chloe", ...)` traz
      `arg="sobre a Chloe"`; um `arg` de 500 caracteres sai cortado em
      `COMMAND_ARG_CHARS`.
- [ ] `!FOFOCA` resolve; `!Fofoca!` levanta `UnknownCommand`; `!` sozinho
      levanta `UnknownCommand`; `/fofoca` (nome que só existe no cenário)
      levanta `UnknownCommand`.
- [ ] `build_meta_user_message` põe o envelope antes do prompt do comando e
      acrescenta o rótulo do `arg` só quando há `arg`.
- [ ] `command_views` devolve cenário antes de globais, com `scope` correto e
      descrição no locale pedido, com fallback determinístico para outro locale
      presente.
- [ ] `commands.py` não importa `app.sessions`, `app.turn` nem `app.main`.
- [ ] Todo teste de `test_commands.py` chama `load_global_commands` com `path`
      explícito em `tmp_path` ou com `OOC_COMMANDS_FILE` apontando para
      `tmp_path`; nenhum caminho sob `Path.home()` é criado pela suíte.
- [ ] `npm run check:api` verde.

## Cenários de teste

**Suíte existente que muda de preparação: nenhuma.** O módulo é novo e ninguém o
importa até o TCK-072; `grep -rn "resolve_command\|commands.yaml" backend/app`
hoje não acha nada fora do que o TCK-060 acrescenta ao loader.
`backend/tests/test_config.py`, `backend/tests/test_scenario.py` e
`backend/tests/test_turn.py` seguem intocados. **Nenhum teste atual cobre
resolução de comando nem arquivo global, porque nada disso existe** — a cobertura
nasce inteira aqui.

Cenários novos em `backend/tests/test_commands.py` (unidade; cenário escrito em
`tmp_path` com `monkeypatch.setattr("app.scenario.scenarios_dir", lambda:
tmp_path)` e `load_scenario`, molde de `backend/tests/test_director.py`; arquivo
global sempre em `tmp_path`, molde de `backend/tests/test_config.py:7-12`).
Fixture base: cenário com `commands.yaml` contendo `fofoca` e `inventario`.

`load_global_commands`:
- Feliz: arquivo ausente → é criado com `DEFAULT_GLOBAL_COMMANDS` e devolve
  `["diary", "inner", "recap"]`, cada um com `pt-br` e `en` em `description` e
  `prompt` (molde de `test_config.py:7`).
- Feliz: arquivo editado com um comando só → devolve esse comando, sem tocar no
  disco.
- Feliz (`global_commands_path`): `monkeypatch.setenv("OOC_COMMANDS_FILE",
  str(tmp_path / "g.yaml"))` → `global_commands_path() == tmp_path / "g.yaml"` e
  `load_global_commands()` sem argumento cria **esse** arquivo com os defaults.
- Borda (`global_commands_path`): `monkeypatch.delenv("OOC_COMMANDS_FILE",
  raising=False)` → `global_commands_path() == GLOBAL_COMMANDS_PATH`, sem tocar
  disco (não chame `load_global_commands` neste caso).
- Borda: arquivo vazio (`""`) → `[]`, sem `emit`.
- Borda: lista com um item válido e outro inválido → defaults, e o item válido
  **não** aparece (o arquivo é aceito ou rejeitado inteiro; meio arquivo valendo
  seria estado que o usuário não consegue prever).
- Falha (**arquivo malformado, análogo do JSON quebrado dos outros módulos**):
  `"- name: [\n"` (YAML quebrado) → defaults + `commands_file_invalid`, capturado
  com `monkeypatch.setattr("app.commands.emit", fake)` que guarda `(event, props)`
  (molde de `backend/tests/test_scenario.py:227` e
  `backend/tests/test_builder_doc_write.py:368`), afirmando `props["path"]` e que
  `props["error"]` tem no máximo 300 chars.
- Falha: raiz que é mapa (`"diary: {}"`) → defaults + `commands_file_invalid`.
- Falha: `extra="forbid"` violado (`"- name: diary\n  extra: x\n"`) → defaults +
  `commands_file_invalid`.
- Falha: dois comandos com o mesmo `name` → defaults + `commands_file_invalid`.
- Falha: `name: "Diary!"` → defaults + `commands_file_invalid`.
- Falha: o arquivo do usuário continua com o conteúdo original depois de qualquer
  um dos casos de falha.

`resolve_command`:
- Feliz: `"!fofoca"` → escopo `scenario`, prompt do cenário, `arg is None`.
- Feliz: `"/diary"` → escopo `global`, prompt `pt-br` num cenário `pt-br` e `en`
  num cenário `locale: en`.
- Feliz: `"!fofoca sobre a Chloe"` → `arg="sobre a Chloe"`.
- Borda (**clamp que clampa**): `"!fofoca " + "x" * 500` →
  `len(arg) == COMMAND_ARG_CHARS`.
- Borda: `"  !fofoca  "` (espaço em volta) resolve igual; `"!fofoca\nlinha 2"` →
  `arg="linha 2"`.
- Borda: `"!FOFOCA"` resolve (casefold); `"!Fofoca!"` → `UnknownCommand` com
  `prefix="!"`.
- Borda: `"texto normal"`, `""`, `"   "`, `"vou ver /diary"` → `None`.
- Borda: `"!"` e `"/ "` → `UnknownCommand` com `name=""`.
- Borda: `"!diary"` (nome só existe nos globais) → `UnknownCommand`; `"/fofoca"`
  (nome só existe no cenário) → `UnknownCommand`. Prova que o sinal escolhe a
  lista, sem fallback cruzado.
- Borda: cenário sem `commands.yaml` (`scenario.commands == []`) → qualquer `!`
  levanta `UnknownCommand`.
- Borda: global cujo `prompt` só tem `de` (locale ausente) num cenário `pt-br` →
  cai no único presente, sem exceção.

`build_meta_user_message`:
- Feliz: contém o envelope, depois o prompt do comando, nessa ordem.
- Borda: com `arg`, termina com o rótulo do `arg` e o texto; sem `arg`, o rótulo
  não aparece em lugar nenhum.
- Borda: `locale="en"` não contém nenhuma palavra do envelope pt-br; locale
  desconhecido (`"de"`) cai no pt-br.

`command_views`:
- Feliz: dois do cenário e três globais → 5 views, cenário primeiro, `scope`
  correto, nome sem sinal.
- Borda: descrição global no locale pedido; com locale ausente, no primeiro em
  ordem alfabética (determinismo).
- Borda: cenário sem comandos e lista global vazia → `[]`.

## Rollout e kill switch

N/A — `risk: low`. Nada importa `commands.py` até o TCK-072, então mergear não
muda comportamento de jogo. O único efeito
colateral do módulo quando ele for chamado: criar `~/.ooc-local/commands.yaml` na
máquina do usuário. É recuperável (apagar o arquivo o recria com os defaults) e
nunca é destrutivo, porque arquivo existente jamais é reescrito, nem quando
inválido. Kill switch da feature de comandos, se houver, é do TCK-072.

## Observabilidade

Eventos: `commands_file_invalid` `{path, error}`, emitido por
`load_global_commands` via `app.observability.emit` (`observability.py:22`),
no molde de `scenario_invalid` (`scenario.py:288`) — mesmo par de propriedades,
mesmo corte de 300 caracteres na mensagem. É a única telemetria do módulo, e
existe porque ninguém mais consegue explicar por que os comandos globais do
usuário sumiram: o chamador recebe os defaults e não tem como saber que houve
troca.
Métrica de sucesso: zero `commands_file_invalid` em uso normal; quando aparece, o
turno seguinte ainda roda (o teste afirma que a lista devolvida é a dos defaults,
não vazia nem exceção).

## i18n

Sem chave de `frontend/src/strings/*` — as chaves de UI de comando são do TCK-074
(`design/game-commands.md`).

Locales dentro do backend, todos em `backend/app/commands.py`:

| onde | chave | pt-br | en |
|---|---|---|---|
| `META_PROMPT_TEMPLATES` | `envelope` | Responda fora da narrativa, sem avançar a história, sem tag e sem fala de personagem em cena. Este pedido não é uma ação do jogador. | Answer outside the narrative, without advancing the story, without tags and without in-scene character speech. This request is not a player action. |
| `META_PROMPT_TEMPLATES` | `arg_label` | `Complemento do jogador` | `Player note` |
| `DEFAULT_GLOBAL_COMMANDS` | `diary.description` | Diário do jogador sobre o dia | Player diary of the day |
| `DEFAULT_GLOBAL_COMMANDS` | `inner.description` | Pensamentos de cada NPC em cena | Thoughts of each NPC in scene |
| `DEFAULT_GLOBAL_COMMANDS` | `recap.description` | Recapitulação da história até aqui | Recap of the story so far |
| `DEFAULT_GLOBAL_COMMANDS` | `*.prompt` | textos do bloco YAML em Detalhes técnicos | idem |

Nome de comando (`diary`, `fofoca`) é identificador e **não** é traduzido: é o
que o jogador digita depois do sinal e o que o `COMMAND_NAME_RE` valida. Nome,
descrição e prompt de comando de cenário vêm do arquivo do autor, já no locale
dele, e nunca passam por template.
