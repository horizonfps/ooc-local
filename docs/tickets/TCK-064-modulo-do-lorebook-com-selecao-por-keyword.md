---
id: TCK-064
title: Criar o módulo do lorebook com seleção por keyword, orçamento e render da seção
status: in_review
points: 3
blockedBy: [TCK-060]
files:
  - backend/app/lore.py
  - backend/tests/test_lore.py
migration: false
ui: false
risk: low
---

## Problema

Depois do TCK-060 o cenário tem `lorebook/<id>.yaml` carregado em
`LoadedScenario.lorebook`, mas nada lê essas entradas: elas ficam no disco sem
chegar ao narrador. Hoje todo o conhecimento de mundo mora em `world.md`, que
entra inteiro no prompt a cada turno (`prompt.py:_neutralize_headings` sobre
`scenario.world`) — quanto mais o autor escreve, mais caro fica cada turno, e o
detalhe que importava naquela cena se perde no meio de 4000 tokens de mundo.

Falta a peça que escolhe, por turno, só as entradas relevantes: as `always` mais
as cujas keywords aparecem nos últimos turnos, ordenadas por prioridade e
cortadas por orçamento de tokens.

Este ticket entrega só a peça pura. A fiação no `run_turn`, a seção no prompt, a
telemetria `lore_injected` e a flag `lorebook` são o TCK-075.

## Escopo

Dentro:
- `backend/app/lore.py` novo: `LORE_BUDGET_TOKENS`, `LORE_SCAN_TURNS`,
  `normalize_text`, `keyword_matches`, `build_scan_text`, `select_lore`,
  `lore_ids`, `render_lore`.
- `backend/tests/test_lore.py`: testes de unidade, sem `TestClient` e sem banco.

Fora (explícito):
- `backend/app/turn.py` e `backend/app/prompt.py`: montar o `scan_text` a partir
  dos eventos, encaixar a seção `## LORE ATIVA` / `## ACTIVE LORE` depois de
  `## MUNDO`, subir `MASTER_PROMPT_VERSION`, emitir `lore_injected` e respeitar a
  flag `lorebook` são todos TCK-075.
- Carregar `lorebook/<id>.yaml`, validar `keywords` obrigatória quando
  `scope == keyword`, e o modelo `LoreEntry`: tudo TCK-060.
- Aba Lorebook do builder e o botão de quebrar o mundo em entradas: TCK-070.
- Chamar o LLM. **Este módulo não tem função async**: é 100% puro, sem I/O de
  rede, sem leitura de disco e sem `emit`. É o único dos quatro módulos da wave
  nessa situação, e é de propósito — seleção de lore é regra, não opinião de
  modelo.

## Comportamento esperado

Do ponto de vista do chamador (o TCK-075): monta o texto de varredura com
`build_scan_text(window, message)`, chama `select_lore(scenario, scan_text)` e
recebe as entradas já filtradas, ordenadas e cortadas pelo orçamento; chama
`render_lore(entries)` e recebe o corpo pronto da seção (ou `None` quando não há
nada), que ele encaixa sob o cabeçalho do locale que vive em `prompt.py`; e
chama `lore_ids(scenario, entries)` para a telemetria.

Determinismo total: mesma entrada, mesma saída, sempre — inclusive a ordem.
Duas entradas com a mesma prioridade saem em ordem de id, nunca na ordem em que o
`glob` do loader as encontrou.

Nada muda para o jogador neste ticket: ninguém importa `lore.py` até o TCK-075.

## Detalhes técnicos

### Constantes

```python
LORE_BUDGET_TOKENS = 1200
LORE_SCAN_TURNS = 2
```

`LORE_BUDGET_TOKENS` é medido com `estimate_tokens` de `app.compact`
(`compact.py:49`, `ceil(len(text)/4)`) — a mesma régua que `fits`
(`compact.py:53`) e o `emit("context_budget", ...)` de `turn.py:294-299` usam. Não invente
um contador de tokens novo: dois contadores discordando é bug garantido no dia
em que o `compact` cortar a janela e o lore não.

### Imports do contrato congelado (TCK-060)

`LoreEntry` e `LoadedScenario` de `app.scenario`; `ChatMessage` de
`app.llm.base` (mesmo import de `turn.py:21`); `estimate_tokens` de
`app.compact`. Nada de `app.prompt`, `app.turn`, `app.sessions`.

### `normalize_text(text) -> str`

```python
unicodedata.normalize("NFKD", text.casefold())
```
com os caracteres combinantes descartados (`unicodedata.combining(ch)`), sem
normalizar de volta. `casefold` antes do `NFKD` porque é o que trata `ß` e
maiúsculas acentuadas; o resultado é a forma comparável de keyword e de
`scan_text`. `Diário` e `DIARIO` viram `diario`.

### `keyword_matches(keyword, text) -> bool`

Normaliza os dois lados e procura com fronteira de palavra:

```python
re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack)
```

Lookarounds em vez de `\b` porque a keyword pode começar ou terminar com
caractere não-word (`"caderno-preto"`, `"§7"`), e aí `\b` inverte o sentido.
`\w` do Python é unicode-aware, o que basta depois da normalização. Keyword que
normaliza para vazio (`"   "`, `"—"`) devolve `False` sempre: entrada com
keyword vazia não pode virar entrada `always` por acidente.

Substring com fronteira, e não igualdade de token: `"sala do grêmio"` casa dentro
de `"passei na sala do gremio ontem"`, mas `"caderno"` **não** casa em
`"cadernos"` — o `(?!\w)` barra. É a leitura literal do brief 2.4 ("match por
substring em fronteira de palavra").

### `build_scan_text(window, message) -> str`

Recebe a janela de `ChatMessage` já lida pelo chamador (o mesmo
`events_to_messages(history_events(...))` que `turn.py:232` usa para o director),
pega as últimas `LORE_SCAN_TURNS * 2` mensagens, e devolve os conteúdos mais a
mensagem atual juntos por `"\n"`. Existe para que o TCK-075 não improvise a
janela: o número de turnos varreidos é regra do lorebook, não do turno.

### `select_lore(scenario, scan_text) -> list[LoreEntry]`

O id da entrada **não está dentro do `LoreEntry`**: o brief 1.1 fixa o modelo com
`extra="forbid"` e sem campo `id`, e o loader (TCK-060) usa o stem do arquivo
como chave de `LoadedScenario.lorebook: dict[str, LoreEntry]`. Então o id vem de
`scenario.lorebook.items()`, e é por isso que a ordenação percorre os pares
`(entry_id, entry)` e não a lista de entradas.

1. candidatas = pares com `entry.enabled`;
2. selecionadas = `scope == "always"` mais `scope == "keyword"` com pelo menos
   uma keyword casando em `scan_text` (`any(keyword_matches(k, scan_text) ...)`);
3. ordenação: `sorted(key=lambda pair: (-pair[1].priority, pair[0]))` —
   prioridade desc, id asc;
4. orçamento: percorre na ordem somando `estimate_tokens(_render_one(entry))` e
   **para na primeira que estouraria** `LORE_BUDGET_TOKENS`, descartando ela e
   todas as seguintes (o brief diz "descartando as últimas"; parar é o único
   corte que preserva a ordem de prioridade — pular a que estourou e continuar
   deixaria a seção variar com o tamanho do corpo, não com a prioridade);
5. devolve `list[LoreEntry]`, sem cópia: são as mesmas instâncias que estão em
   `scenario.lorebook`, o que é o que faz `lore_ids` funcionar.

O custo de cada entrada é medido sobre o **texto renderizado**
(`### {title}\n{body}`), o mesmo que `render_lore` produz, e não sobre o body
cru: o orçamento tem que valer para o que entra no prompt.

Entrada única maior que o orçamento inteiro não entra, nem sendo `always`. O
orçamento é guarda de contexto; abrir exceção para a primeira faria uma entrada
de 4000 tokens estourar a janela justamente no cenário em que o autor exagerou.

### `lore_ids(scenario, entries) -> list[str]`

Mapeia as entradas de volta para os ids por **identidade** (`is`), varrendo
`scenario.lorebook.items()` — exatamente a técnica de `_character_id` em
`prompt.py:228-232`, que resolve o mesmo problema com `Character`. Existe porque
`select_lore` devolve `list[LoreEntry]` por contrato do brief e o TCK-075 precisa
de `ids` para a telemetria `lore_injected`. Entrada que não veio de
`scenario.lorebook` (cópia, `model_copy`) é ignorada — documente na docstring de
uma linha que a função depende de identidade, não de igualdade.

### `render_lore(entries) -> str | None`

`None` quando a lista é vazia. Senão, `"\n\n".join(f"### {title}\n{body}")`, com
`title` achatado (`" ".join(title.split())`) e `body` com `.strip()` e cabeçalhos
rebaixados.

Rebaixamento: copie `_neutralize_headings` de `prompt.py:35-45` literalmente
(laço por linha sobre `_HEADING_RE = re.compile(r"^(#{1,6})([ \t].*)$")`, nível
novo `min(len(hashes) + 3, 6)`; `##Regras` sem espaço **não** é heading, como lá)
numa função local, em vez de importar o símbolo privado de `app.prompt`. Motivo: o TCK-075 é dono do
`prompt.py` e pode acabar importando `lore.py` de lá para montar a seção; se
`lore.py` importar `prompt.py`, isso vira import circular em runtime. Duplicar
quatro linhas é o preço de manter `lore.py` sem dependência de módulo de prompt.
Sem o rebaixamento, um corpo de entrada que comece com `## Regras` cria uma
seção falsa no meio do prompt do narrador — que é o mesmo motivo pelo qual
`world.md` e `opening_scene` já passam pelo neutralizador.

`render_lore` devolve **só o corpo da seção**, sem o `## LORE ATIVA`: o cabeçalho
é string de locale e mora em `_TEMPLATES` de `prompt.py`, que este ticket não
toca.

Comentários em inglês e mínimos, como o resto do backend.

## Contrato público

```python
# backend/app/lore.py
LORE_BUDGET_TOKENS: int = 1200
LORE_SCAN_TURNS: int = 2

def normalize_text(text: str) -> str
def keyword_matches(keyword: str, text: str) -> bool
def build_scan_text(window: list[ChatMessage], message: str) -> str
def select_lore(scenario: LoadedScenario, scan_text: str) -> list[LoreEntry]
def lore_ids(scenario: LoadedScenario, entries: list[LoreEntry]) -> list[str]
def render_lore(entries: list[LoreEntry]) -> str | None
```

Consumido pelo TCK-075, que declara este ticket em `blockedBy`. `render_lore`
devolve o corpo da seção; o cabeçalho por locale é do `prompt.py` (TCK-075).

## Acceptance criteria

- [ ] `normalize_text("Diário DO Grêmio")` devolve `"diario do gremio"`.
- [ ] `keyword_matches("caderno", "o Caderno preto")` é `True`;
      `keyword_matches("caderno", "os cadernos")` é `False`;
      `keyword_matches("diário", "abriu o diario")` é `True`;
      `keyword_matches("   ", "qualquer coisa")` é `False`.
- [ ] `select_lore` devolve as entradas `always` mesmo com `scan_text` vazio.
- [ ] Entrada `enabled: false` nunca é devolvida, nem com `scope: always`, nem
      com keyword casando.
- [ ] Duas entradas com a mesma `priority` saem em ordem de id asc; prioridade
      maior vem antes de prioridade menor.
- [ ] O orçamento corta: três entradas `always` com corpo de 1600 caracteres
      cada (`### t\n` + corpo = 1606 chars = 402 tokens por entrada) → a lista
      devolvida tem exatamente as duas primeiras (804 tokens); a terceira
      (1206 > 1200) não aparece.
- [ ] `lore_ids(scenario, select_lore(...))` devolve os ids na mesma ordem das
      entradas.
- [ ] `render_lore([])` é `None`; com entradas, o texto tem uma linha
      `### {title}` por entrada e **não** contém `## LORE ATIVA`.
- [ ] Corpo de entrada que começa com `## Regras` sai rebaixado para `##### Regras`.
- [ ] `build_scan_text` usa só as últimas `LORE_SCAN_TURNS * 2` mensagens da
      janela mais a mensagem atual.
- [ ] `lore.py` não importa `app.sessions`, `app.turn` nem `app.prompt`, e não
      tem nenhuma função `async`.
- [ ] `npm run check:api` verde.

## Cenários de teste

**Suíte existente que muda de preparação: nenhuma.** O módulo é novo e ninguém o
importa até o TCK-075; `grep -rn "lorebook" backend/app` hoje não acha nada fora
do que o TCK-060 acrescenta. `backend/tests/test_prompt.py`,
`backend/tests/test_turn.py` e `backend/tests/test_scenario.py` seguem intocados.
**Nenhum teste atual cobre seleção de lore, porque ela não existe** — a cobertura
nasce inteira aqui.

Cenários novos em `backend/tests/test_lore.py` (unidade, cenário escrito em
`tmp_path` com `monkeypatch.setattr("app.scenario.scenarios_dir", lambda:
tmp_path)` e `load_scenario`, molde de `backend/tests/test_director.py`). Fixture
base: `lorebook/caderno.yaml` (keywords `[caderno, diário]`, priority 0),
`lorebook/gremio.yaml` (keywords `[sala do grêmio]`, priority 5),
`lorebook/regras.yaml` (`scope: always`, priority 0),
`lorebook/antigo.yaml` (`enabled: false`, `scope: always`).

`normalize_text` / `keyword_matches`:
- Feliz: acento e caixa (`"Diário"` vs `"diario"`), keyword multi-palavra
  (`"sala do grêmio"` dentro de `"fui até a Sala do Gremio"`).
- Borda: fronteira à direita (`"cadernos"` não casa `"caderno"`), à esquerda
  (`"macaderno"` não casa) e pontuação colada (`"o caderno."` casa).
- Borda: hífen é fronteira — a keyword `"preto"` **casa** em `"caderno-preto"`,
  porque `-` não é `\w`. O teste existe para fixar essa regra por escrito.
- Borda: keyword só com espaço, string vazia e travessão → `False`.
- Borda: `scan_text` vazio → só `always` sobrevive.

`select_lore`:
- Feliz: `scan_text="peguei o caderno na mesa"` → `[caderno, regras]` (por id
  asc, mesma prioridade) — e o teste afirma a ordem, não só o conjunto.
- Feliz: `scan_text="fui à sala do grêmio"` → `gremio` primeiro (priority 5),
  depois `regras`.
- Borda: `scan_text=""` → só `regras`.
- Borda: entrada `enabled: false` com `scope: always` e keyword casando não
  aparece em nenhum dos casos.
- Borda: entrada `scope: keyword` com lista de keywords em que só a segunda casa
  aparece.
- Borda (**corte que corta**): três entradas `always` com título `t` e corpo
  de 1600 caracteres cada (402 tokens por entrada renderizada) → só as duas
  primeiras da ordem entram (804 tokens), a terceira levaria a 1206 > 1200, e
  `estimate_tokens(render_lore(resultado))` é `<= LORE_BUDGET_TOKENS`.
- Borda: uma única entrada `always` de 8000 caracteres → `[]`.
- Borda: cenário sem `lorebook` (dict vazio) → `[]`, sem exceção.
- Borda: duas chamadas com o mesmo `scan_text` devolvem listas iguais (prova de
  determinismo, incluindo ordem).

`lore_ids`:
- Feliz: ids na ordem das entradas selecionadas.
- Borda: `lore_ids(scenario, [])` → `[]`.
- Borda: entrada que não pertence ao cenário (construída à mão) é ignorada.

`render_lore`:
- Feliz: duas entradas → `"### O caderno\n<body>\n\n### Regras\n<body>"`.
- Borda: `[]` → `None`.
- Borda: título com quebra de linha sai numa linha só; corpo com espaço em volta
  sai `strip`ado.
- Borda (**entrada malformada, análogo do JSON quebrado dos outros módulos**):
  corpo que começa com `## Regras da casa` sai como `##### Regras da casa`, e
  corpo com `###### já no nível 6` continua em 6 (o `min(level+3, 6)` satura).
- Borda: corpo vazio → sai só a linha do título, sem linha em branco extra no
  fim.

`build_scan_text`:
- Feliz: janela de 10 mensagens + mensagem atual → só as 4 últimas da janela
  entram, e a mensagem atual é a última linha.
- Borda: janela vazia → devolve só a mensagem atual.

## Rollout e kill switch

N/A — `risk: low`. Nada importa `lore.py` até o TCK-075, então o merge não muda
comportamento de jogo. A flag `lorebook` (default ligado, via `config.flag`,
`config.py:43`) é definida e testada no TCK-075.

## Observabilidade

Eventos: nenhum. `lore.py` não importa `app.observability`. A telemetria
`lore_injected {session_id, turn, ids, tokens}` é emitida pelo TCK-075, que tem o
`session_id` e o turno na mão; `lore_ids` e `estimate_tokens` são o que ele usa
para preencher `ids` e `tokens`.
Métrica de sucesso: nos testes, o custo em tokens de qualquer seleção é sempre
`<= LORE_BUDGET_TOKENS`, e as 6 formas de quase-match (plural, prefixo colado,
acento, caixa, keyword vazia, entrada desabilitada) resolvem do jeito
documentado, sem exceção.

## i18n

N/A no sentido de string de usuário: `lore.py` não tem texto próprio. O título e
o corpo de cada entrada vêm do cenário, já no locale dele, e passam íntegros. O
cabeçalho da seção (`## LORE ATIVA` / `## ACTIVE LORE`) é chave de locale e mora
em `_TEMPLATES` de `backend/app/prompt.py`, que o TCK-075 acrescenta — este
ticket não cria nem consome chave de locale nenhuma.
