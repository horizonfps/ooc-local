---
id: TCK-027
title: Atualizar o local do HUD pela tag [LOC:] emitida no turno
status: ready
points: 3
blockedBy: [TCK-026]
files:
  - backend/app/tags.py
  - backend/app/hud.py
  - backend/app/turn.py
  - backend/app/prompt.py
  - backend/tests/test_tags.py
  - backend/tests/test_turn.py
  - backend/tests/test_prompt.py
migration: false
ui: false
risk: medium
---

## Problema

No verde da Fase 1 a cena mudou do pátio para a sala de aula e o HUD continuou
mostrando `Local: pátio da escola` até o fim da sessão. `hud.advance()` só mexe
em `turn` e `time`; `location` nasce do start e nunca mais muda. Como o
prompt-mestre injeta o HUD no contexto, o narrador passa a ler um local errado e
a narração começa a brigar com o próprio estado do engine.

Não existe hoje nenhum mecanismo pelo qual o modelo informe mudança de local: as
tags conhecidas são `[STAT:]`, `[SPRITE:]` e `[BG:]`, e nenhuma delas carrega
texto de local exibível.

## Escopo

Dentro:
- Nova tag `[LOC:texto do local]`, validada em `app/tags.py`.
- `apply_location(hud, raw)` em `app/hud.py`, determinística e defensiva.
- `app/turn.py` aplica a última `[LOC:]` válida do turno ao HUD novo, depois de
  `advance`.
- Instrução da tag no `format_body` dos dois locales em `app/prompt.py` e bump
  de `MASTER_PROMPT_VERSION` para 4.
- Testes em `test_tags.py`, `test_turn.py`, `test_prompt.py`.

Fora (explícito):
- Renderizar background a partir de `[BG:]` (é o TCK-042) — este ticket **não**
  deriva local de `[BG:]`.
- Alterar `time`, `weather` ou `turn` do HUD.
- Editor de locais, lista canônica de locais do cenário ou validação do local
  contra o cenário (não existe tabela de locais na Fase 2).
- Qualquer mudança no frontend: o HUD já renderiza `location` como vem do
  evento `hud` do stream.

## Comportamento esperado

Quando a cena muda de lugar, o narrador emite `[LOC:sala de aula do 3º B]`
colada ao trecho. O parser remove a tag do texto (comportamento que já existe
para toda tag) e o engine grava o novo local no HUD do turno. A UI mostra o
local novo no mesmo evento `hud` do fim do turno, e o turno seguinte injeta o
local novo no prompt-mestre.

Sem tag `[LOC:]`, o local continua exatamente como estava — o engine nunca
adivinha local a partir da prosa.

## Detalhes técnicos

**Por que uma tag nova e não `[BG:]`**: `[BG:]` é chave de arquivo
(`media/backgrounds/{slug}.png`, slug sem acento e sem espaço) e o HUD mostra
texto humano com acento (`pátio da escola`). Reaproveitar `[BG:]` obrigaria a
"deshumanizar" o HUD ou a inventar um mapa slug→rótulo que a Fase 2 não tem.
As duas tags convivem: `[BG:]` troca a arte, `[LOC:]` troca o estado.

`app/tags.py`, dentro de `_validate`:

```python
if kind == "LOC":
    return len(args) == 1 and bool(args[0])
```

`args` já vem de `raw_args.split(":")`, então `[LOC:sala 3: fundo]` produz dois
args e é **inválida** — removida do texto e registrada como evento `tag` com
`valid: False`, igual às demais tags inválidas de hoje. Não mude o `TAG_RE`.

`app/hud.py`:

```python
LOCATION_MAX_CHARS = 60

def apply_location(hud: HudState, raw: str) -> HudState:
    """Engine-owned HUD move: normalizes and applies a narrator location tag."""
```

- `strip()`, colapsa qualquer sequência de espaço/tab em um espaço único.
- Vazio depois da normalização → devolve o HUD sem alteração.
- Maior que `LOCATION_MAX_CHARS` → trunca em 60 caracteres pelo limite de
  palavra mais próximo à esquerda (sem cortar palavra no meio; se não houver
  espaço, corta em 60 direto).
- Igual ao local atual → devolve o mesmo HUD (sem cópia, sem evento extra).
- Caso contrário devolve `hud.model_copy(update={"location": normalizado})`.

`app/turn.py`, dentro de `run_turn`, depois de `strip_engine_echo` (TCK-026) e
antes de `append_events`:

```python
new_hud = advance(hud)
for tag in tags:
    if tag.kind == "LOC" and tag.valid:
        new_hud = apply_location(new_hud, tag.args[0])
```

Última `[LOC:]` válida do turno vence, porque o laço aplica em ordem de
aparição. Tag inválida é ignorada aqui e continua sendo persistida como evento
`tag` com `valid: False` pelo caminho que já existe.

Instrução nova no `format_body` (somada, sem remover linha):

- pt-br: `Quando a cena mudar de lugar, emita [LOC:nome do local] com o nome do lugar em português, curto, no máximo 60 caracteres. O HUD só muda de local por essa tag.`
- en: `When the scene moves to another place, emit [LOC:place name] with a short name, at most 60 characters. The HUD only changes location through this tag.`

A linha existente que lista as tags permitidas (`[STAT:...]`, `[SPRITE:...]`,
`[BG:...]`) passa a listar `[LOC:local]` junto.

## Contrato público

```python
# backend/app/hud.py
LOCATION_MAX_CHARS: int  # 60
def apply_location(hud: HudState, raw: str) -> HudState: ...
```

Tag `[LOC:texto]`: exatamente um argumento não vazio; texto livre com acento e
espaço; sem dois-pontos internos. Nenhum outro ticket da Fase 2 consome esta
seção — TCK-042 usa `[BG:]` e `[SPRITE:]`, não `[LOC:]`.

## Acceptance criteria

- [ ] `[LOC:sala de aula]` é reconhecida como tag válida, removida do texto e
      registrada como evento `tag`.
- [ ] Depois de um turno com `[LOC:sala de aula]`, `GET /api/sessions/{id}`
      devolve `hud.location == "sala de aula"` e o evento `hud` do stream traz o
      mesmo valor.
- [ ] Turno sem `[LOC:]` preserva o local anterior.
- [ ] `[LOC:]` vazia ou com dois-pontos interno é inválida: não muda o HUD e é
      persistida com `valid: False`.
- [ ] Local com mais de 60 caracteres é truncado sem cortar palavra no meio.
- [ ] `turn` e `time` do HUD continuam se comportando exatamente como hoje.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente que muda: nenhuma asserção é alterada.
`test_turn.py::test_turn_happy_path_emits_deltas_hud_then_done` e
`test_turn.py::test_turn_records_tags_as_events` continuam válidos porque os
fakes não emitem `[LOC:]` e o local segue vindo do start. Em `test_prompt.py`,
as asserções de `format_body` existentes (`"350 palavras"`, `"**Nome** | fala"`)
continuam verdadeiras; acrescente uma asserção nova de que `[LOC:` aparece no
prompt dos dois locales.

- Feliz (`test_tags.py`): `parse_tags("Voce entra. [LOC:sala de aula]")` devolve
  texto `"Voce entra."` e uma tag `LOC` válida com `args == ["sala de aula"]`.
- Feliz (`test_turn.py`): fake stream com
  `"Voce sobe a escada. [LOC:sala do 3 B]"` → `hud.location == "sala do 3 B"` na
  sessão relida.
- Borda: dois `[LOC:]` no mesmo turno — o último vence.
- Borda: `[LOC:  pátio   da   escola  ]` vira `"pátio da escola"`.
- Borda: `[LOC:]` com o local igual ao atual não altera nada.
- Borda: texto de 200 caracteres é truncado em ≤ 60 e não termina no meio de uma
  palavra.
- Falha: `[LOC:sala 3: fundo]` é `valid: False`, sai do texto, não altera o HUD,
  e o evento `tag` guarda os dois args.

## Rollout e kill switch

N/A — sem flag. Não há migração de dados: sessões antigas simplesmente não têm
tag `[LOC:]` e mantêm o local do start.

## Observabilidade

Eventos: `game_turn` ganha `location_changed` (bool) — se o turno moveu o local
do HUD.
Métrica de sucesso: em uma sessão de 5 turnos com mudança de cena, o HUD
acompanha; `location_changed` é `true` nos turnos em que a narração muda de
lugar, e a proporção de tags `LOC` inválidas fica em zero.

## i18n

N/A — prompt de sistema, já bilíngue por locale do cenário. O texto do local vem
do cenário/narrador, não do dicionário de UI.
