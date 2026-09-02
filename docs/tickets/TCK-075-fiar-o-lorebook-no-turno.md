---
id: TCK-075
title: Selecionar lore por keyword no turno e injetar a seção no prompt
status: done
points: 3
blockedBy: [TCK-060, TCK-064, TCK-072]
files:
  - backend/app/turn.py
  - backend/app/prompt.py
  - backend/tests/test_turn_lore.py
  - backend/tests/test_prompt.py
migration: false
ui: false
risk: low
---

## Problema

`backend/app/lore.py` (TCK-064) sabe escolher quais entradas do lorebook valem
para um texto, e nada o chama. `LoadedScenario.lorebook` (TCK-060) carrega, o
builder edita (TCK-070), o `exemplo-escola` tem duas entradas (TCK-068), e nada
disso chega ao narrador: `build_master_prompt` (`prompt.py:261-317`) monta
`## MUNDO` a partir de `scenario.world` e nada mais.

O efeito prático é o motivo de o lorebook existir: o `world.md` do
`exemplo-escola` já ocupa ~350 palavras do orçamento em **todo** turno, e o
detalhe do caderno teria de morar lá dentro para o narrador conhecê-lo — pagando
o custo em todos os turnos em que ninguém menciona caderno nenhum. O lorebook é
o que troca "sempre no prompt" por "no prompt quando o assunto aparece", e sem
esta fiação ele é um editor sem consumidor.

Este é o último ticket da fase e o único da wave 5.

## Escopo

Dentro:
- `backend/app/turn.py`: `TurnContext.lore`; montagem do `scan_text`; call de
  `select_lore` sob o flag `lorebook`; telemetria `lore_injected`.
- `backend/app/prompt.py`: seção `## LORE ATIVA` / `## ACTIVE LORE` logo depois
  de `## MUNDO`; `MASTER_PROMPT_VERSION` 11 → 12.
- `backend/tests/test_turn_lore.py` novo.
- Adaptação do pino de versão em `backend/tests/test_prompt.py`.

Fora (explícito):
- `backend/app/lore.py`: vem pronto do TCK-064 e **não é editado aqui**.
  Normalização de acento, ordenação e corte por orçamento são de lá; divergência
  volta para aquele ticket.
- `backend/app/sessions.py` e `backend/app/main.py`: o lorebook não aparece em
  nenhuma resposta de API. Ele existe só dentro do prompt.
- `backend/app/compact.py`: o resumo de campanha não ganha lore. Lore é seleção
  por turno; entrar no resumo a congelaria para sempre na janela.
- Injetar lore no prompt do director, do juiz ou do minds. Os três recebem
  janela curta e trabalham sobre ids e números; lore ali seria orçamento gasto
  sem decisão dependente dele.
- Qualquer arquivo de frontend. O lorebook não tem superfície de jogo.

## Comportamento esperado

Quando o jogador (ou o narrador, no turno anterior) menciona o caderno, o prompt
do turno seguinte ganha um bloco `## LORE ATIVA` com o verbete do caderno, e o
narrador passa a saber os detalhes — capa preta, páginas numeradas, três meses
de circulação — sem que nada disso esteja no `world.md`. Quando o assunto sai de
cena, o bloco some e o orçamento volta.

Entradas com `scope: always` entram em todo turno, independentemente do texto.

Cenário sem `lorebook/`, ou com o flag `lorebook` desligado: prompt idêntico ao
de hoje, sem seção nova e sem custo nenhum.

## Detalhes técnicos

### Interface consumida (TCK-064)

```python
# backend/app/lore.py  (contrato publicado pelo TCK-064)
LORE_BUDGET_TOKENS: int   # 1200
LORE_SCAN_TURNS: int      # 2

def build_scan_text(window: list[ChatMessage], message: str) -> str
def select_lore(scenario: LoadedScenario, scan_text: str) -> list[LoreEntry]
def lore_ids(scenario: LoadedScenario, entries: list[LoreEntry]) -> list[str]
def render_lore(entries: list[LoreEntry]) -> str | None
```

Todas **puras**, sem I/O e sem exceção: entrada ruim devolve lista vazia ou
`None`. `select_lore` já aplica `enabled`, `scope`, o casamento de keyword
casefold e sem acento, a ordenação (`priority` desc, depois id asc) e o corte
pelo orçamento. `render_lore` devolve o **corpo** da seção (`### {title}` + body
por entrada), sem cabeçalho: o cabeçalho é por locale e mora no `prompt.py`
deste ticket. `lore_ids` existe para a telemetria, porque `LoreEntry` não carrega
o próprio id (a chave é o stem, contrato do TCK-060). Este ticket não repete
nenhuma dessas regras — só decide **com que texto** a seleção é chamada e
**onde** o resultado entra.

### `scan_text`: o que é varrido

Em `run_turn`, logo depois de `ctx` estar resolvido e **antes** do branch de
turno meta (TCK-072) e do bloco do director (`turn.py:228`):

```python
if config.flag("lorebook") and ctx.scenario.lorebook:
    window = events_to_messages(
        history_events(session_id, None)[-(LORE_SCAN_TURNS * 2):],
        ctx.scenario.meta.locale,
    )
    scan_text = build_scan_text(window, message)
    ctx = ctx.model_copy(update={"lore": select_lore(ctx.scenario, scan_text)})
```

`build_scan_text` recebe `list[ChatMessage]`, então a janela passa por
`events_to_messages` — a mesma conversão que o director já usa em
`turn.py:232-234`. O `locale` é o do cenário (parâmetro que o TCK-072
acrescentou); a etiqueta de modo que ele insere não atrapalha o casamento,
porque `(Ação)`/`(Action)` não é keyword de ninguém.

Três decisões que não são óbvias:

- **`message` cru, não o formatado.** O TCK-072 produz `(Ação) vou até a Chloe`
  para o modelo, mas a varredura usa o texto que o jogador digitou. O prefixo
  nunca casaria keyword nenhuma, e varrer o cru mantém o comportamento igual
  entre um cliente que manda `mode` e um que não manda.
- **`history_events`, não a janela do prompt.** `history_events`
  (`turn.py:69-74`) já filtra `player_turn`/`narrator_turn`, então turno meta
  (TCK-072) e evento de sistema ficam fora da varredura de graça. O corte é
  `LORE_SCAN_TURNS * 2` porque cada turno são dois eventos, mesmo cálculo que o
  director usa em `turn.py:233`.
- **`ctx.model_copy`, não parâmetro novo.** `_maybe_compact` chama
  `build_context` em três lugares (`turn.py:120`, `:124`, `:151`) e
  `build_context` já recebe `ctx` (`turn.py:93`). Pendurar a lore no contexto
  custa um campo e zero mudança de assinatura nos dois; passar como parâmetro
  custaria seis pontos de edição. É o mesmo movimento que o director faz com
  `cast_ids` em `turn.py:265`.

`TurnContext` (`turn.py:43-48`) ganha `lore: list[LoreEntry] = []`;
`build_context` (`turn.py:98`) passa `lore=ctx.lore` para `build_master_prompt`;
e o `build_master_prompt` do branch meta (TCK-072) recebe o mesmo `ctx.lore`,
porque o comando também merece contexto — `!fofoca` sobre o caderno precisa
saber o que é o caderno.

O `select_lore` roda **uma vez por turno**. Turno que falha depois disso não
deixa resíduo: a lore não é persistida em lugar nenhum, é só prompt.

### `backend/app/prompt.py`

Chave nova nos dois locales de `_TEMPLATES` (`prompt.py:47-181`): `lore_header`
(`"## LORE ATIVA"` / `"## ACTIVE LORE"`).

`build_master_prompt` (`prompt.py:261-267`) ganha
`lore: list[LoreEntry] | None = None` no fim da assinatura — compatível com os
21 call sites de `test_prompt.py`, que passam no máximo `compact=` e `minds=`.
A seção entra **logo depois** de `## MUNDO` (`prompt.py:273`) e antes de
`## PERSONAGENS EM CENA`, com um bloco por entrada:

```
## LORE ATIVA
### O caderno de capa preta
O caderno é um brochurão de capa preta...

### A sala do grêmio
A sala do grêmio é um cômodo apertado...
```

O corpo vem de `render_lore(lore)`; `prompt.py` só acrescenta o cabeçalho do
locale. `render_lore` neutraliza o `body` de cada entrada (`_neutralize_headings`,
`prompt.py:35-45`, ou o equivalente do TCK-064) e mantém o `### {title}` em nível
3, pelo mesmo motivo que `scenario.world` é neutralizado (`prompt.py:273`): um
`##` escrito pelo autor dentro do corpo criaria uma fronteira falsa de seção e o
narrador leria o resto do prompt como conteúdo de mundo. `render_lore`
devolvendo `None` (lista vazia) → **nenhuma** seção, nem cabeçalho vazio.

Depois do `## MUNDO` e não no fim porque a lore é ampliação do mundo, e o
narrador lê o prompt de cima para baixo: separar as duas coisas por seis seções
faria o verbete parecer um adendo desconexo da premissa.

`MASTER_PROMPT_VERSION` sobe para **12**.

## Contrato público

```python
# backend/app/turn.py
# TurnContext ganha lore: list[LoreEntry] = []

# backend/app/prompt.py
def build_master_prompt(
    scenario: LoadedScenario,
    start: StartConfig,
    hud: HudState,
    characters: list[Character],
    compact: str | None = None,
    minds: dict[str, MindView] | None = None,
    lore: list[LoreEntry] | None = None,
) -> str
```

Nenhum ticket consome esta seção: este é o último ticket da fase e não há
consumidor a jusante. A assinatura está publicada porque `build_master_prompt` é
função pública do módulo e três tickets desta fase já a estenderam.

## Acceptance criteria

- [ ] Cenário com entrada de keyword `caderno` e mensagem do jogador citando
      "caderno": o system prompt tem `## LORE ATIVA`, `### <title>` e o corpo da
      entrada, depois de `## MUNDO` e antes de `## PERSONAGENS EM CENA`.
- [ ] A mesma sessão, com mensagem sem a palavra: nenhuma seção `## LORE ATIVA`.
- [ ] Keyword mencionada com acento diferente ou caixa diferente
      (`Diário`, `DIARIO`) casa a mesma entrada (regra do TCK-064, aferida aqui
      ponta a ponta).
- [ ] Keyword mencionada **no turno anterior** (player ou narrador) ainda casa no
      turno seguinte; mencionada três turnos atrás, não casa mais
      (`LORE_SCAN_TURNS == 2`).
- [ ] Entrada com `scope: always` entra em todo turno, sem keyword nenhuma;
      entrada com `enabled: false` nunca entra.
- [ ] Duas entradas casando saem na ordem de `priority` desc.
- [ ] Um `##` dentro do corpo de uma entrada sai neutralizado no prompt.
- [ ] Turno meta (`!fofoca`) também recebe a seção quando o comando casa keyword.
- [ ] Com `flags: {lorebook: false}`, `select_lore` nunca é chamado, o prompt não
      tem a seção e nenhum `lore_injected` é emitido.
- [ ] Cenário sem `lorebook/`: nenhuma seção, nenhuma telemetria, nenhum custo.
- [ ] `lore_injected` traz `ids` (de `lore_ids`) e `tokens`, e é emitido também
      quando nada casou (com `ids: []`).
- [ ] `MASTER_PROMPT_VERSION == 12`.
- [ ] `npm run check` verde, com as asserções dos testes existentes inalteradas.

## Cenários de teste

Suíte existente que muda **de preparação** (asserções preservadas):

- `backend/tests/test_prompt.py` — o pino de versão passa a `12`. **Única edição
  de asserção autorizada**, pela mesma razão dos TCK-061/069/072: o teste afere
  que alguém lembrou de subir o número, não comportamento. Os 34 outros testes do
  arquivo chamam `build_master_prompt` sem `lore=`, então a seção não aparece e
  todas as asserções de conteúdo e de ordem relativa
  (`:112-147`, `:486-499`, `:611-622`) seguem verdes.
- `backend/tests/test_turn.py`, `test_turn_director.py`, `test_compact.py` —
  verificados, **não** entram em `files`: nenhum dos cenários sintéticos desses
  arquivos tem pasta `lorebook/`, então `ctx.scenario.lorebook` é vazio, o bloco
  inteiro é pulado pela guarda `and ctx.scenario.lorebook`, e nem
  `select_lore` nem `lore_injected` acontecem.
  `test_compact.py:1080` chama `turn.build_context(session.id, "mensagem nova",
  compact_seq=999, history=full)` sem `ctx`, então `load_turn_context` monta um
  `TurnContext` com `lore=[]` e a chamada segue idêntica.
  `test_turn_window_truncated_at_18_pairs:262` idem.
- Nenhum teste existente constrói `TurnContext` à mão (busca confirma: as únicas
  ocorrências fora de `turn.py` são `main.py:27,146` e o nome de um teste em
  `test_turn_director.py:373`), então o campo novo com default não quebra nada.

Cenários novos (`backend/tests/test_turn_lore.py`, no padrão de
`backend/tests/test_turn.py`: `TestClient`, cenário em `tmp_path` com
`lorebook/`, `_config()` sem papel `utility`, `stream_chat` monkeypatchado
capturando as mensagens):
- Feliz: mensagem com `caderno` → `## LORE ATIVA` no system prompt capturado,
  com o `### title` e o corpo, na posição certa entre `## MUNDO` e
  `## PERSONAGENS EM CENA`.
- Feliz: `scope: always` entra num turno cuja mensagem não cita nada.
- Feliz: duas entradas casando saem por `priority` desc.
- Borda: mensagem sem keyword → nenhuma seção.
- Borda: `Diário` com acento e caixa diferentes casa a entrada de keyword
  `diario`.
- Borda: keyword citada no turno 1 ainda casa no turno 2 (vem da janela) e não
  casa mais no turno 4.
- Borda: `enabled: false` nunca entra, mesmo com a keyword na mensagem.
- Borda: corpo com `## Subtítulo` sai neutralizado (`##### Subtítulo`) no
  prompt, e o `### {title}` da entrada continua em nível 3.
- Borda: turno meta `!fofoca` (TCK-072) com keyword no nome recebe a seção.
- Borda: `flags: {lorebook: false}` → nenhuma seção e nenhum `lore_injected`;
  garantido monkeypatchando `turn.select_lore` para uma função que registra
  chamada e afirmando que a lista de chamadas ficou vazia.
- Borda: cenário sem `lorebook/` → nenhuma seção e nenhum `lore_injected`.
- Feliz (telemetria): turno com uma entrada casada emite `lore_injected` com
  `ids == ["caderno"]` e `tokens` maior que zero; turno sem casamento, num
  cenário **com** lorebook, emite `lore_injected` com `ids == []`.

## Rollout e kill switch

Flag de runtime **`lorebook`**, no padrão do projeto (`Config.flag`,
`backend/app/config.py:43`): ausente = ligado. Desligar sem deploy e sem
reiniciar é acrescentar em `~/.ooc-local/config.yaml`:

```yaml
flags:
  lorebook: false
```

Desligado: `select_lore` não é chamado, `ctx.lore` fica vazio, a seção some do
prompt e nenhuma telemetria é emitida. Nada é rebobinado porque nada é
persistido — a lore vive só no prompt do turno, então desligar o flag no meio de
uma sessão é seguro e reversível a qualquer momento.

Segundo desligamento, por dado e por entrada: `enabled: false` numa entrada do
`lorebook/` a tira de circulação sem tocar em config, e apagar a pasta
`lorebook/` do cenário devolve o comportamento pré-fase. É o caminho certo
quando o problema é **uma** entrada, e não o subsistema.

`risk: low` e não `high`: nenhum call novo ao provider, nenhuma escrita nova
no banco, nenhuma rota nova. O risco real é orçamento de contexto — até
`LORE_BUDGET_TOKENS = 1200` a mais no system prompt, num orçamento de entrada de
23.200 tokens (`compact.py:9-13`). O `_maybe_compact` roda **depois** da seleção
e o `fits`/`select_window` (`turn.py:128`, `:154`) já medem o system prompt
inteiro, então uma lore gorda encurta a janela de histórico em vez de estourar o
contexto. O evento `context_budget` (`turn.py:294-299`), que já existe, é o sinal
para vigiar isso.

## Observabilidade

Eventos (via `emit` de `backend/app/observability.py`):
- `lore_injected`: `session_id`, `turn`, `ids` (ids das entradas escolhidas, na
  ordem em que entram no prompt), `tokens` (`estimate_tokens` de `compact.py`,
  já importado em `turn.py:14`, aplicado sobre `render_lore(ctx.lore)`; `0`
  quando `render_lore` devolve `None`, isto é, quando nada casou),
  `candidates` (quantas entradas `enabled` o cenário tem). Emitido sempre que o
  flag está ligado e o cenário tem lorebook, **inclusive com `ids: []`** — um
  lorebook que nunca casa é exatamente a falha que precisa aparecer, e ela é
  invisível se só emitirmos no caso de sucesso.
- `context_budget` (`turn.py:294-299`) não muda de forma: `estimated_tokens` já
  inclui o system prompt e passa a refletir a lore automaticamente. É o número
  que diz se o orçamento aguentou.

Métrica de sucesso: numa partida de 20 turnos no `exemplo-escola`, pelo menos
três `lore_injected` trazem `ids` não vazio, nenhum traz `tokens` acima de
`LORE_BUDGET_TOKENS`, e `context_budget.estimated_tokens` fica abaixo de
`INPUT_BUDGET_TOKENS` (`compact.py:13`) em todos os 20 — a lore entra quando o
assunto aparece e nunca custa a janela de histórico.

## i18n

Uma chave de template em `backend/app/prompt.py`, nos dois locales já existentes:

| chave | pt-br | en |
| --- | --- | --- |
| `lore_header` | `## LORE ATIVA` | `## ACTIVE LORE` |

Nenhuma string de UI. `LoreEntry.title` e `LoreEntry.body` vêm do YAML do
cenário, já no locale do cenário, e nunca passam por `t()` nem por tradução no
prompt.
