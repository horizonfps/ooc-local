---
id: TCK-072
title: Aplicar modo de input no contexto e rodar o turno meta dos comandos
status: done
points: 5
blockedBy: [TCK-060, TCK-065, TCK-069]
files:
  - backend/app/turn.py
  - backend/app/main.py
  - backend/app/prompt.py
  - backend/app/sessions.py
  - backend/tests/conftest.py
  - backend/tests/test_turn_commands.py
  - backend/tests/test_turn_modes.py
  - backend/tests/test_prompt.py
migration: false
ui: false
risk: low
---

## Problema

`ChatRequest.mode` existe desde o TCK-060 e é ignorado: `run_turn` recebe a
mensagem crua e `events_to_messages` (`turn.py:77-83`) devolve
`payload["text"]` sem etiqueta nenhuma. O narrador não tem como distinguir "vou
até a Chloe" (tentativa, ele decide o resultado) de "Chloe, você viu o caderno?"
(fala literal, que ele não pode transformar em ação) e de "o sinal toca e a
turma se levanta" (fato narrado pelo jogador, que ele deve incorporar). Hoje as
três chegam idênticas e ele adivinha — normalmente errado na do meio, virando a
fala do jogador em ação inventada.

`backend/app/commands.py` (TCK-065) sabe resolver `!fofoca` e `/diary`, e nada o
chama. `SessionDetail.commands` (congelado no TCK-060) responde `[]` para sempre,
a paleta do TCK-074 não tem o que listar, e mandar `!fofoca` no campo de texto
hoje faz o narrador tratar isso como fala do personagem.

## Escopo

Dentro:
- `backend/app/prompt.py`: `MODE_LABELS` e `format_player_message()`; explicação
  dos três rótulos no `format_body`; `MASTER_PROMPT_VERSION` 10 → 11.
- `backend/app/turn.py`: `mode` e `command` em `run_turn`; formatação em
  `events_to_messages` e na mensagem atual; `mode` gravado no `player_turn`;
  branch do turno meta com os eventos `meta_player_turn`/`meta_narrator_turn`.
- `backend/app/main.py`: resolução do comando na rota, com 422 `unknown_command`
  antes de abrir o stream; `mode` e `command` repassados a `run_turn`.
- `backend/app/sessions.py`: `SessionDetail.commands`; `_build_turns` lendo os
  dois kinds meta com `meta`, `command` e `mode`.
- `backend/tests/conftest.py` novo: fixture autouse que mantém a suíte fora de
  `~/.ooc-local`.
- `backend/tests/test_turn_commands.py` e `backend/tests/test_turn_modes.py`
  novos, no molde de `backend/tests/test_turn.py`.
- Adaptação do pino de versão em `backend/tests/test_prompt.py`.

Fora (explícito):
- `backend/app/commands.py`: vem pronto do TCK-065 e **não é editado aqui**.
  Divergência com a seção "Interface consumida" volta para aquele ticket.
- Paleta, rótulo de modo na bolha, estilo do turno meta e comandos no Play
  Guide: TCK-074, contra o contrato congelado no TCK-060.
- `history_events` (`turn.py:69-74`) e `_maybe_compact`: continuam lendo só
  `player_turn`/`narrator_turn`, então o turno meta fica fora da memória do
  narrador e do resumo **por construção**, sem filtro novo. Isto é uma decisão,
  não um esquecimento.
- `list_sessions` (`sessions.py:232-238`): o `COUNT(*)` já filtra
  `kind = 'player_turn'`, então meta não infla a contagem de turnos. Sem
  alteração.
- Tag, director, juiz, minds, sugestão, compact e `advance` no turno meta:
  nenhum roda. O HUD não avança.
- Lorebook: TCK-075.

## Comportamento esperado

O jogador escolhe um modo antes de escrever. Em `say`, o que ele digitou chega ao
narrador como fala literal entre aspas e não pode virar ação. Em `story`, chega
como fato narrado a ser incorporado. Em `do`, chega como tentativa cujo
resultado o narrador decide. O texto guardado no histórico é sempre o cru: a
etiqueta é do prompt, não do banco.

Mandando `!fofoca`, o jogador recebe uma resposta fora da narrativa: o narrador
lista o que cada NPC anda dizendo pelas costas, o relógio não anda, o turno não
conta, e nada disso entra na memória do próximo turno. Mandando `!naoexiste`, ele
recebe 422 imediatamente, sem stream e sem turno gasto.

Turno normal, sem modo e sem comando (o que o `BuilderPreview` manda hoje),
comporta-se exatamente como antes.

## Detalhes técnicos

### Interface consumida (TCK-065)

```python
# backend/app/commands.py  (contrato publicado pelo TCK-065)
GLOBAL_COMMANDS_PATH: Path            # CONFIG_DIR / "commands.yaml"
SCENARIO_SIGIL: str                   # "!"
GLOBAL_SIGIL: str                     # "/"

class GlobalCommandDef(BaseModel):    # extra="forbid"
    name: str
    description: dict[str, str]       # por locale
    prompt: dict[str, str]            # por locale

class ResolvedCommand(BaseModel):
    name: str
    scope: Literal["scenario", "global"]
    prompt: str                       # ja resolvido no locale do cenario
    arg: str | None                   # texto depois do nome, quando houver

class UnknownCommand(Exception):
    prefix: str
    name: str

def global_commands_path() -> Path
def load_global_commands(path: Path | None = None) -> list[GlobalCommandDef]
def resolve_command(text, scenario, global_commands) -> ResolvedCommand | None   # raises UnknownCommand
def build_meta_user_message(resolved: ResolvedCommand, locale: str) -> str
def command_views(scenario, global_commands, locale) -> list[CommandView]
```

**Consumido do TCK-065, já disponível no contrato dele (nada a editar em
`commands.py` aqui):** `load_global_commands` resolve o caminho de forma
preguiçosa e honra a variável de ambiente `OOC_COMMANDS_FILE`, no molde de
`db_path()` (`sessions.py:112-116`) e `scenarios_dir()` (`scenario.py:142-148`):

```python
GLOBAL_COMMANDS_ENV = "OOC_COMMANDS_FILE"
def global_commands_path() -> Path
def load_global_commands(path: Path | None = None) -> list[GlobalCommandDef]
```

É disso que o `conftest.py` deste ticket depende. Se o default estivesse ligado
ao valor de `GLOBAL_COMMANDS_PATH` no momento do `def`, a suite inteira passaria a criar e ler `~/.ooc-local/commands.yaml` na maquina de
quem roda o pre-commit, porque `get_session` — chamado por dezenas de testes —
vai chamar a funcao sem argumento. Nao ha como um `monkeypatch` de atributo de
modulo corrigir um default ja avaliado. Este e o motivo do `conftest.py` deste
ticket; o TCK-065 ja chega mergeado com essa assinatura.

`sessions.py` e `main.py` importam os símbolos direto
(`from app.commands import load_global_commands, resolve_command`), para que um
teste possa `monkeypatch.setattr(main, "load_global_commands", ...)` — mesmo
recurso que `test_turn.py:105` já usa com `load_config`.

### Modos: onde a etiqueta é colada

Rótulos ficam em `prompt.py`, ao lado de `WEATHER_LABELS` (`prompt.py:11-30`),
que é onde toda tabela por locale já mora:

```python
MODE_LABELS: dict[str, dict[str, str]] = {
    "pt-br": {"do": "Ação", "say": "Fala", "story": "Narração"},
    "en":    {"do": "Action", "say": "Speech", "story": "Narration"},
}

def format_player_message(text: str, mode: str | None, locale: str) -> str
```
- `mode is None` ou desconhecido → devolve `text` **cru**. Evento antigo não tem
  `mode`, e inventar `do` para ele reescreveria história.
- `do` → `(Ação) {text}`; `story` → `(Narração) {text}`;
  `say` → `(Fala) "{text}"` (só o `say` leva aspas, porque é o único que é
  citação literal).

`events_to_messages` (`turn.py:77-83`) ganha `locale: str = "pt-br"` e passa
`event.payload.get("mode")` pelo formatador. Default no parâmetro porque
`test_compact.py:393` chama a função com um argumento só — e continua chamando.

A **mensagem atual** é formatada uma vez em `run_turn`, antes de qualquer coisa:

```python
prompt_message = format_player_message(message, mode, ctx.scenario.meta.locale)
```

e é `prompt_message` que vai para `_maybe_compact`/`build_context`
(`turn.py:289-291`), enquanto o evento gravado leva o cru:

```python
("player_turn", {"text": message, "mode": mode} if mode else {"text": message}),
```

A chave `mode` só é escrita quando existe: um `mode: null` no payload de todo
turno sem modo seria ruído em todas as sessões que o `BuilderPreview` cria.

Formatar antes de `_maybe_compact` também é o que faz o orçamento de contexto
(`select_window`, `turn.py:128`) medir o texto que realmente vai ao modelo.

### Turno meta

Branch próprio em `run_turn`, logo depois de resolver `config`/`ctx` e **antes**
do director (`turn.py:228`):

```python
if command is not None:
    compact, _ = get_compact(session_id)
    system = build_master_prompt(
        ctx.scenario, ctx.start, ctx.row.hud, ctx.characters, compact, minds=ctx.minds
    )
    window = events_to_messages(
        history_events(session_id, None)[-(WINDOW_TURNS * 2):], ctx.scenario.meta.locale
    )
    messages = [
        ChatMessage(role="system", content=system),
        *window,
        ChatMessage(role="user", content=build_meta_user_message(command, ctx.scenario.meta.locale)),
    ]
    # stream identico ao do turno normal
    clean_text, _ = parse_tags(raw_text)
    clean_text, stripped_lines = strip_engine_echo(clean_text)
    if not clean_text.strip():
        emit_game_turn("empty turn"); yield {"error": "empty turn"}; return
    append_events(session_id, [
        ("meta_player_turn", {"text": message, "command": command.name}),
        ("meta_narrator_turn", {"text": clean_text}),
    ])
    yield {"hud": hud_payload(ctx, ctx.row.hud)}
    emit("meta_turn", session_id=session_id, command=command.name, scope=command.scope,
         chars=len(raw_text), duration_ms=int((time.monotonic() - started) * 1000), model=role.model)
    return
```

O resumo da campanha entra de propósito: `/recap` e `/diary` são justamente os
comandos que precisam do que já saiu da janela. `get_compact` já é importado em
`turn.py:31`.

`hud_payload(ctx, hud)` é o dicionário que o turno normal manda no `yield` final
(`{**hud.model_dump(exclude={"stats", "dynamic_stats"}), "cast": ..., "stats":
[...stat_views...], "minds": {...}}`, montado pelos TCK-061/069). Se ainda for um
literal inline no `yield` do turno normal, extraia-o para uma função de módulo
`hud_payload(ctx: TurnContext, hud: HudState) -> dict` e use nos dois branches:
meta manda o HUD atual sem `advance`, sem evento, sem mudança.

O turno meta **não** emite `game_turn`: `emit_game_turn` fica só no caminho
normal e no `except` do topo (falha antes do branch). Sucesso do meta emite só
`meta_turn`; falha do provider dentro do branch propaga a exceção e cai no
`except` do topo, que emite `game_turn` com `error` como hoje (`turn.py:331-333`),
e isso é aceitável: erro é raro e vale contar.

Pontos que não são óbvios:
- `parse_tags` roda e o resultado das tags é **descartado**: o objetivo é limpar
  o texto de tag que o narrador emitiu por hábito, não persistir nem aplicar.
  Nenhum evento `tag`, nenhum `apply_location`, nenhum `apply_stat`.
- `append_events` é chamado **sem** `hud=`, e por isso só atualiza `updated_at`
  (`sessions.py:408-409`). É assim que "o relógio não anda" acontece: não existe
  `advance` no caminho.
- O `yield {"hud": ...}` manda o HUD **atual**, com `cast`, `stats` e `minds`
  como em turno normal. O contrato do TCK-060 diz que a UI espera o `hud` no fim
  de qualquer turno; um meta que não mandasse nada deixaria o painel em estado
  de "streaming" pela ausência do evento de fechamento.
- Turno meta vazio falha como turno normal falha: erro no SSE e **nada**
  persistido.
- `compact` não roda: o branch nunca chega em `_maybe_compact`. E como
  `history_events` filtra por `player_turn`/`narrator_turn`, o par meta não
  entra na janela do turno seguinte nem no resumo.

### `backend/app/main.py`

Na `turn_route`, depois da checagem de mensagem vazia (`main.py:153-155`) e antes
de abrir o `StreamingResponse`:

```python
try:
    command = resolve_command(req.message, ctx.scenario, load_global_commands())
except UnknownCommand as exc:
    emit("turn_rejected", session_id=session_id, reason="unknown_command",
         command=exc.name, prefix=exc.prefix)
    raise HTTPException(status_code=422, detail="unknown_command") from None
```

Antes do stream porque um 422 depois do `StreamingResponse` viraria um evento
`error` dentro de um 200, e o TCK-074 depende do status para distinguir "comando
inexistente" de "turno falhou". `ctx` já está carregado na rota (`main.py:146`),
então nada é lido duas vezes. `run_turn` passa a receber
`mode=req.mode, command=command`, os dois com default `None` na assinatura para
não quebrar chamador direto.

### `backend/app/sessions.py`

- `get_session` (`:282-311`) e `create_session` (`:163-225`):
  `commands=command_views(scenario, load_global_commands(), scenario.meta.locale)`.
- `get_session` (`:290`) passa a ler os quatro kinds:
  `("player_turn", "narrator_turn", "meta_player_turn", "meta_narrator_turn")`.
- `_build_turns` (`:473-481`):
  - `index` só incrementa em `player_turn` — o meta compartilha o índice do
    turno corrente, como o design do TCK-074 espera;
  - `role` é `"player"` para `player_turn`/`meta_player_turn` e `"narrator"`
    para os outros dois;
  - `meta=True` para os dois kinds meta;
  - `command` vem de `meta_player_turn.payload["command"]` e é **carregado
    adiante** para o `meta_narrator_turn` seguinte, que não tem a chave no
    payload (contrato do TCK-060). Um `meta_narrator_turn` órfão (sem par antes)
    sai com `command=None` em vez de estourar;
  - `mode` vem de `player_turn.payload.get("mode")`;
  - `suggestions` continua vindo do `narrator_turn` (TCK-069).

### `backend/app/prompt.py`

`format_body` dos dois locales ganha três frases, uma por rótulo, explicando o
que cada prefixo significa: `(Fala)` é o que o jogador diz em voz alta e não pode
virar ação; `(Narração)` é texto do jogador que entra como fato narrado e deve
ser incorporado; `(Ação)` é a tentativa do jogador, e o resultado é decisão do
narrador. `MASTER_PROMPT_VERSION` sobe para **11**.

### Ressalva de porte

A estimativa é ~430 linhas. Se passar disso, funda em `test_turn_modes.py` os
três cenários de formatação num único `pytest.mark.parametrize` sobre
`(mode, locale, esperado)`. Não corte o cenário de "meta não entra na janela do
turno seguinte": é o que prova a decisão central do desenho.

## Contrato público

```python
# backend/app/prompt.py
MODE_LABELS: dict[str, dict[str, str]]
def format_player_message(text: str, mode: str | None, locale: str) -> str

# backend/app/turn.py
async def run_turn(
    session_id: str, message: str, *,
    ctx: TurnContext | None = None,
    config: Config | None = None,
    mode: str | None = None,
    command: "ResolvedCommand | None" = None,
) -> AsyncIterator[dict]
def events_to_messages(events: list[Event], locale: str = "pt-br") -> list[ChatMessage]
```

Rota: `POST /api/sessions/{id}/turn` passa a responder **422 com
`{"detail": "unknown_command"}`** quando a mensagem começa por `!` ou `/` e o
nome não existe. É o único status novo; mensagem vazia continua 422 com
`"message must not be empty"`, e o TCK-074 distingue os dois pelo `detail`.

Os formatos de `SessionDetail.commands`, `TurnView.meta/command/mode`,
`ChatRequest.mode` e dos eventos `meta_player_turn`/`meta_narrator_turn` já estão
congelados no TCK-060; este ticket só os preenche.

## Acceptance criteria

- [ ] `POST .../turn` com `{"message": "vou até a Chloe", "mode": "do"}` manda
      `(Ação) vou até a Chloe` como user ao narrador e grava
      `player_turn.payload == {"text": "vou até a Chloe", "mode": "do"}`.
- [ ] `mode: "say"` produz `(Fala) "..."`; `mode: "story"` produz `(Narração) ...`;
      locale `en` produz `(Action)`, `(Speech) "..."` e `(Narration)`.
- [ ] Sem `mode` no corpo, o user é o texto cru e o payload não tem a chave
      `mode` — igual ao comportamento de hoje.
- [ ] No turno seguinte, o turno anterior reaparece na janela **com** a etiqueta
      (o evento guarda o modo), e um evento gravado antes deste ticket reaparece
      cru.
- [ ] `!fofoca` num cenário que declara esse comando: o SSE devolve deltas e o
      `hud` com `turn` **inalterado**, o banco ganha exatamente
      `meta_player_turn` + `meta_narrator_turn`, e nenhum evento `tag`, `cast`,
      `stat`, `minds` ou `compact`.
- [ ] O par meta **não** aparece na janela de contexto do turno normal seguinte.
- [ ] `GET /api/sessions/{id}` traz os dois turnos meta com `meta: true`,
      `command: "fofoca"` nos dois, e o mesmo `index` do turno normal anterior;
      `turnCount` em `GET /api/sessions` não conta o meta.
- [ ] `/diary` resolve pelo arquivo global e grava `command: "diary"`.
- [ ] `!naoexiste` responde **422** com `detail == "unknown_command"`, sem abrir
      stream e sem gravar evento nenhum; `/naoexiste` idem.
- [ ] Texto que não começa por `!` nem `/` nunca é tratado como comando, mesmo
      contendo `/` no meio.
- [ ] Turno meta cujo narrador devolve texto vazio responde erro e não grava
      nada.
- [ ] `SessionDetail.commands` traz os comandos do cenário com
      `scope: "scenario"` seguidos dos globais com `scope: "global"`, com a
      descrição no locale do cenário.
- [ ] `MASTER_PROMPT_VERSION == 11` e o `format_body` explica os três rótulos nos
      dois locales.
- [ ] A suíte inteira roda sem criar nem ler `~/.ooc-local/commands.yaml`.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente que muda **de preparação** (asserções preservadas):

- `backend/tests/test_prompt.py` — o pino de versão passa a `11`. **Única edição
  de asserção autorizada**, pela mesma razão dos TCK-061/069: o teste afere que
  alguém lembrou de subir o número, não comportamento.
- `backend/tests/conftest.py` **novo**: fixture autouse de escopo `session` que
  faz `os.environ["OOC_COMMANDS_FILE"] = str(tmp_path_factory.mktemp("cfg") /
  "commands.yaml")` (usa o `global_commands_path()` do TCK-065). Não altera
  nenhum teste existente e é o que impede que
  `get_session` — chamado por dezenas de testes — passe a criar
  `~/.ooc-local/commands.yaml` na máquina de quem roda o pre-commit.
- `backend/tests/test_compact.py` — verificado, **não** entra em `files`:
  `test_events_to_messages_is_order_preserving_and_one_to_one:380` chama
  `turn.events_to_messages(events)` com um argumento e os eventos não têm `mode`,
  então as três asserções (`:396-398`) seguem idênticas graças ao default
  `locale="pt-br"` e à regra "sem `mode`, texto cru".
- `backend/tests/test_turn.py` — verificado, **não** entra em `files`:
  `test_turn_second_turn_includes_previous_pair_in_context:202` afere
  `("user", "primeira mensagem") in roles_contents`, e nenhum teste do arquivo
  manda `mode` nem mensagem começando por `!`/`/`;
  `test_turn_window_truncated_at_18_pairs:262` chama
  `turn.build_context(session["id"], "nova mensagem")`, cuja assinatura não muda.
- `backend/tests/test_sessions.py` — verificado, **não** entra em `files`: os
  testes aferem campo a campo e `commands` é aditivo; o `conftest.py` cobre o
  efeito colateral de FS.

Cenários novos (`backend/tests/test_turn_modes.py`, padrão de `test_turn.py`):
- Feliz: os três modes em `pt-br` produzem `(Ação)`, `(Fala) "..."` e
  `(Narração)` na mensagem user capturada.
- Feliz: os três em `en` produzem `(Action)`, `(Speech) "..."` e `(Narration)`.
- Feliz: o `mode` fica no `player_turn.payload` e o `text` continua cru.
- Feliz: turno 2 vê o turno 1 já etiquetado na janela.
- Borda: sem `mode`, user cru e payload sem a chave.
- Borda: evento antigo (gravado direto com `append_events`, sem `mode`) volta
  cru na janela mesmo com o turno atual usando `say`.
- Borda: `TurnView.mode` chega em `GET /api/sessions/{id}` e é `None` para turno
  antigo.
- Falha: `mode: "gritar"` responde 422 (validação do `Literal`, TCK-060) e não
  grava nada.

Cenários novos (`backend/tests/test_turn_commands.py`; cenário em `tmp_path` com
`commands.yaml`, e o arquivo global apontado por `OOC_COMMANDS_FILE` para um
`tmp_path` do próprio teste):
- Feliz: `!fofoca` grava `meta_player_turn` + `meta_narrator_turn` e nada mais;
  o `hud` do SSE tem o mesmo `turn` de antes.
- Feliz: o system prompt do meta é o mesmo do turno normal (contém
  `## PERSONAGENS EM CENA`) e o último user é o `build_meta_user_message` do comando.
- Feliz: `/diary` resolve pelo global e grava `command: "diary"`.
- Feliz: `GET /api/sessions/{id}` traz os dois turnos meta com `meta: true`,
  `command` preenchido nos dois e o índice do turno corrente.
- Feliz: `SessionDetail.commands` traz cenário antes de global, com o `scope`
  certo.
- Borda: um turno normal, depois um meta, depois outro normal → a janela do
  terceiro tem só o par do primeiro.
- Borda: `turnCount` de `GET /api/sessions` não conta o meta.
- Borda: dois metas seguidos → quatro `TurnView` meta com o mesmo `index`.
- Borda: mensagem `"vou ver /diary depois"` roda como turno normal.
- Falha: `!naoexiste` → 422 `unknown_command`, nenhum evento gravado,
  `turn_rejected` emitido com `reason == "unknown_command"`.
- Falha: `/naoexiste` → mesmo 422.
- Falha: narrador devolve só espaço no meta → evento `error` no SSE e
  `read_events(...)` sem par meta.

## Rollout e kill switch

N/A como flag própria — e é deliberado. `risk: low`, não `high`, porque
nenhum dos dois caminhos acrescenta call ao provider: o modo só muda o texto do
user, e o turno meta **substitui** o turno normal em vez de somar a ele. Não há
latência nova, não há subsistema que possa alucinar, e a falha máxima é um turno
meta ruim, que o jogador descarta lendo.

O desligamento efetivo existe e é por dado, sem deploy:
- comandos de cenário: apagar (ou esvaziar) o `commands.yaml` do cenário faz
  `!qualquercoisa` voltar a ser 422, e nenhum comando aparece na paleta;
- comandos globais: esvaziar `~/.ooc-local/commands.yaml` (a lista vazia é
  válida) desliga o `/`;
- modos: um cliente que pare de mandar `mode` volta ao comportamento anterior no
  turno seguinte, porque a formatação é condicionada ao campo existir.

Os eventos meta já gravados continuam no histórico e continuam fora da memória do
narrador, então desligar não corrompe nenhuma sessão em andamento.

## Observabilidade

Eventos (via `emit` de `backend/app/observability.py`):
- `turn_rejected` (`main.py:143`, `:148`, `:151`, `:154`) ganha o motivo
  `"unknown_command"`, com a propriedade `command` (o nome digitado).
- `game_turn` (`turn.py:200-215`) ganha duas propriedades: `mode` (o modo do
  turno, `None` quando ausente) e `command` (o nome do comando, `None` em turno
  normal). São o que permite medir adoção sem evento novo.
- `meta_turn`: evento novo, emitido no fim de um turno meta bem-sucedido, com
  `session_id`, `command`, `scope`, `chars`, `duration_ms`, `model`. Separado do
  `game_turn` porque um meta não é um turno de jogo: contá-lo junto estragaria a
  média de duração e a contagem de turnos da telemetria existente.

Métrica de sucesso: numa partida de 20 turnos no `exemplo-escola`, `game_turn`
traz `mode` preenchido em todos, pelo menos um `meta_turn` é registrado com
`command == "fofoca"`, e nenhum `turn_rejected` com `reason == "unknown_command"`
aparece para comando que a paleta ofereceu.

## i18n

`MODE_LABELS` em `backend/app/prompt.py`, nos dois locales:

| modo | pt-br | en |
| --- | --- | --- |
| `do` | `Ação` | `Action` |
| `say` | `Fala` | `Speech` |
| `story` | `Narração` | `Narration` |

Mais as três frases de explicação acrescentadas ao `format_body` de `pt-br`
(`prompt.py:95-113`) e de `en` (`prompt.py:161-179`).

Nenhuma string de UI: os rótulos do seletor e da bolha são chaves
`game.mode.*` do TCK-071/074, e nascem lá. `CommandView.description` vem do
`commands.yaml` do cenário (locale do cenário) ou do mapa por locale do arquivo
global, resolvido por `command_views` no TCK-065 — nunca passa por `t()`.
