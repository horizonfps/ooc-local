---
id: TCK-020
title: Limitar a limpeza de tags às linhas que tinham tag e corrigir o recorte
status: in_review
points: 3
blockedBy: []
files:
  - backend/app/tags.py
  - backend/tests/test_tags.py
  - frontend/src/components/TurnText.tsx
  - frontend/src/components/TurnText.test.tsx
migration: false
ui: true
risk: low
---

## Problema

`parse_tags` (`backend/app/tags.py:28`) remove as tags e depois roda a limpeza
de espaços em **todas** as linhas do turno, tenha ou não havido tag:

```python
for original, line in zip(original_lines, lines):
    line = _TRAILING_WHITESPACE_RE.sub(" ", line)   # [ \t]+ -> " "
    line = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", line)
    line = line.strip()
```

`_TRAILING_WHITESPACE_RE` é `[ \t]+`: qualquer sequência de espaço ou tab vira
um espaço só. Isso reescreve narração que o modelo escreveu de propósito —
indentação de verso, tabulação de lista, alinhamento de fala — e o `.strip()`
mata recuo de parágrafo. O texto limpo é o que vai para o event store e é o que
o frontend renderiza com `white-space: pre-wrap`
(`frontend/src/components/turnText.css:9`, `frontend/src/screens/game.css:92`),
ou seja, o espaço em branco **é significativo na tela** e está sendo destruído
antes de chegar lá. `_SPACE_BEFORE_PUNCT_RE` inclui `…`, então "Ele parou …" (com
espaço deliberado antes das reticências) vira "Ele parou…" em linha que nem tinha
tag. A limpeza é consequência da remoção de tag e deve valer só onde houve
remoção.

Três defeitos de recorte no mesmo módulo:

1. **Tag colada perde o separador.** `TAG_RE.sub` substitui por string vazia:
   `"palavra[BG:sala]outra"` vira `"palavraoutra"`. Duas palavras viram uma, e
   nenhuma limpeza posterior recupera.
2. **Colchete aninhado deixa `]` órfão.** `TAG_RE` é
   `\[([A-Z][A-Z0-9_]*):([^\]\n]*)\]`: o grupo de argumentos aceita `[`. Em
   `"[BG:sala [interna]]"` a regex casa `"[BG:sala [interna]"` e sobra um `]`
   solto no meio da narração.
3. **`\d` aceita dígito não-ASCII.** `_validate` (`:20`) usa
   `re.match(r"^[+-]?\d+$", args[1])`; em Python, `\d` casa dígito Unicode
   (`"١٢"`, `"１２"`). Um `[STAT:coragem:١٢]` é marcado `valid=True` e o
   consumidor de stat da Fase 2 vai receber algo que `int()` até converte, mas
   que ninguém escreveu de propósito. O mirror no frontend
   (`frontend/src/components/TurnText.tsx:6`) usa `\d` do JavaScript, que é
   ASCII-only: as duas implementações discordam.

O frontend reimplementa a mesma limpeza em `cleanLine`
(`frontend/src/components/TurnText.tsx:16`) com os mesmos três regex. Corrigir só
o backend não resolve nada: o texto salvo passa pelo `TurnText` outra vez na
renderização, e a normalização volta a acontecer. `TAG_RE` é declarada mirror
explícito do backend (comentário em `TurnText.tsx:5`) e há teste aferindo a
paridade (`frontend/src/components/TurnText.test.tsx:116`).

## Escopo

Dentro:
- `backend/app/tags.py`: limpeza por linha, aplicada só a linha que teve tag;
  separador ao remover tag colada entre dois caracteres de palavra; `TAG_RE`
  rejeitando `[` nos argumentos; validação de `STAT` em ASCII.
- `frontend/src/components/TurnText.tsx`: as mesmas quatro regras, mantendo a
  paridade declarada.
- Testes nos dois lados.

Fora (explícito):
- Mudar o conjunto de tags conhecidas (`STAT`, `SPRITE`, `BG`) ou a regra de
  validade de cada uma além do dígito ASCII.
- Aplicar efeito de tag no engine (mexer em stat, trocar sprite/BG): Fase 2.
- Mudar a renderização de fala (`**Nome** | fala`), o `SPEAKER_RE` ou o
  tratamento de colchete não fechado durante streaming
  (`findUnclosedBracket`, `frontend/src/components/TurnText.tsx:23`).
- Reprocessar turnos já gravados no banco com a limpeza antiga: o texto já
  normalizado fica como está. Sem migração.
- Mexer em `frontend/src/screens/GameScreen.tsx` ou nos CSS de `pre-wrap`.

### Testes existentes que este ticket invalida

Grep em `backend/tests/test_tags.py` (18 testes) e
`frontend/src/components/TurnText.test.tsx` (18 testes):

- `test_whitespace_only_string_returns_empty_text_and_no_tags`
  (`test_tags.py:95`) espera `parse_tags("   ") == ("", [])`. Com a limpeza
  restrita, a linha `"   "` não tem tag e seria preservada verbatim. Continua
  válido **porque** a regra do recorte final descarta as linhas em branco das
  bordas (ver "Detalhes técnicos"). Sem adaptação — mas é o teste que prova a
  regra, e ele **não pode** ser afrouxado.
- `test_empty_string_returns_empty_text_and_no_tags` (`:91`): `""` vira uma
  única linha em branco, descartada como borda. Válido sem adaptação.
- `test_bracketed_prose_is_not_a_tag` (30), `test_lowercase_bracket_is_not_a_tag`
  (36), `test_sic_and_number_in_brackets_are_not_tags` (42),
  `test_unclosed_bracket_leaves_text_untouched` (85),
  `test_speaker_line_is_untouched_by_parser` (101): todos usam linhas sem espaço
  redundante, e continuam válidos verbatim.
- `test_removes_stat_tag_and_returns_valid_tag` (4),
  `test_no_double_space_or_space_before_punctuation_after_removal` (70),
  `test_three_tags_same_paragraph_no_double_space` (76),
  `test_line_with_only_tag_disappears_without_blank_paragraph` (13),
  `test_sprite_tag_between_paragraphs_preserves_blank_line_separator` (24),
  `test_parse_tags_is_idempotent` (107): linhas **com** tag, onde a limpeza
  continua acontecendo. Válidos sem adaptação.
- `TurnText.test.tsx` "removes an inline tag without leaving a double space
  before punctuation" (31), "drops a line that becomes empty after tag removal"
  (36), "preserves prose brackets that are not tags" (41), "exports a TAG_RE
  mirroring the backend tag pattern" (116): o último afere a paridade do
  `source` da regex. **Adaptação de preparação**: o literal esperado passa a ser
  o padrão novo (`[^\[\]\n]*`). O que o teste afere — que os dois lados usam o
  mesmo padrão — não muda.
- Nenhum teste existente afere que linha **sem** tag é normalizada; ou seja,
  nenhuma asserção descreve o comportamento antigo que este ticket remove.

## Comportamento esperado

Do ponto de vista do jogador: a narração aparece exatamente como o narrador
escreveu, incluindo indentação e espaçamento deliberado, exceto nas linhas onde
uma tag foi retirada — ali o buraco da tag é fechado sem deixar espaço duplo,
espaço antes de pontuação, nem palavras coladas.

Do ponto de vista do chamador de `parse_tags`:

| Entrada | Saída |
|---|---|
| `"    Ele espera."` | `"    Ele espera."` (verbatim) |
| `"O sino  toca ."` | `"O sino  toca ."` (verbatim, sem tag) |
| `"O sino [STAT:rep:+1] toca ."` | `"O sino toca."` |
| `"palavra[BG:sala]outra"` | `"palavra outra"` |
| `"sorri[SPRITE:chloe:happy]."` | `"sorri."` |
| `"[BG:sala [interna]]"` | verbatim, nenhuma tag |
| `"[STAT:coragem:١٢]"` | tag removida, `valid=False` |

## Detalhes técnicos

- `TAG_RE = re.compile(r"\[([A-Z][A-Z0-9_]*):([^\[\]\n]*)\]")`. Com `[`
  excluído dos argumentos, `"[BG:sala [interna]]"` não casa em lugar nenhum e o
  texto fica intocado — consistente com a regra já existente de colchete não
  fechado (`test_unclosed_bracket_leaves_text_untouched`).
- Substituição com separador: no callback de `sub`, olhe o caractere
  imediatamente antes e depois do `match` no texto **original da linha**. Se os
  dois existirem e ambos casarem `[^\W_]` (letra ou dígito, sem underscore),
  devolva `" "`; caso contrário, `""`. `"sorri[SPRITE:a:b]."` cai no segundo
  caso (`.` não é palavra) e continua `"sorri."`.
- **Regra do recorte final.** Um `.strip()` sobre o texto inteiro apagaria a
  indentação da primeira linha, que é justamente o que este ticket promete
  preservar; não usá-lo quebraria
  `parse_tags("   ") == ("", [])` (`backend/tests/test_tags.py:95`). A regra que
  concilia os dois é **remover apenas as linhas em branco das bordas**: depois
  do processamento linha a linha, descarte, do início e do fim da lista, as
  linhas cujo conteúdo é só espaço em branco. Linha interna em branco é
  preservada (é separador de parágrafo, e
  `test_blank_line_between_paragraphs_is_preserved` afere isso); linha com
  conteúdo mantém a indentação, inclusive a primeira.
  `parse_tags("   ")` vira uma lista de uma linha em branco, que é borda dos
  dois lados, descartada, resultado `""`. E o contrato de "turno só com tag é
  turno vazio", que `run_turn` usa (`backend/app/turn.py:138`), continua valendo.
- Processamento:

  ```python
  out: list[str] = []
  for line in text.split("\n"):
      if not TAG_RE.search(line):
          out.append(line)               # verbatim, indentação inclusive
          continue
      cleaned = TAG_RE.sub(_replace, line)
      cleaned = _TRAILING_WHITESPACE_RE.sub(" ", cleaned)
      cleaned = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", cleaned)
      cleaned = cleaned.strip()
      if cleaned == "":
          continue                       # a linha era só tag
      out.append(cleaned)

  while out and not out[0].strip():
      out.pop(0)
  while out and not out[-1].strip():
      out.pop()
  return "\n".join(out), tags
  ```

  **Armadilha**: as tags precisam ser coletadas na ordem de aparição no texto
  inteiro (`test_tags_returned_in_order_of_appearance`,
  `backend/tests/test_tags.py:114`); processar linha a linha em ordem preserva
  isso, desde que a lista `tags` seja a mesma entre as iterações.
- Validação ASCII: `re.match(r"^[+-]?[0-9]+$", args[1])`. Não use
  `re.ASCII` como flag global do módulo — `[A-Z0-9_]` do `TAG_RE` já é ASCII
  literal e a flag mudaria `\W` do separador, que **deve** continuar Unicode
  (senão `"olá[BG:x]mundo"` não recebe separador).
- Frontend, em `frontend/src/components/TurnText.tsx`:
  - `TAG_RE = /\[([A-Z][A-Z0-9_]*):([^\[\]\n]*)\]/g` (mirror);
  - `cleanLine` vira `cleanLineIfTagged(line)`: sem tag, devolve a linha como
    veio; com tag, aplica remoção com separador + normalização + `trim`;
  - `buildBlocks` (`:29`) passa a seguir uma regra única e afirmativa: **uma
    linha vira bloco quando, depois do tratamento (verbatim se não tinha tag,
    limpa se tinha), ela contém pelo menos um caractere que não é espaço em
    branco.** O bloco leva a linha tratada inteira, indentação inclusive. Isso
    mantém o comportamento de hoje para linha em branco (nunca vira `<p>`) e
    para linha só de tag (some), e passa a preservar o recuo das linhas com
    conteúdo, que hoje o `trim` de `cleanLine` (`:20`) apaga.
  - `TAG_RE` é `/g`: `TAG_RE.test()` avança `lastIndex` entre chamadas. Use
    `line.search(TAG_RE)` ou zere `TAG_RE.lastIndex` antes de cada uso — este é
    o erro clássico e ele produz falha intermitente linha sim, linha não.

## Contrato público

```python
# backend/app/tags.py
TAG_RE: re.Pattern           # r"\[([A-Z][A-Z0-9_]*):([^\[\]\n]*)\]"
def parse_tags(text: str) -> tuple[str, list[Tag]]: ...   # assinatura inalterada
```

```ts
// frontend/src/components/TurnText.tsx
export const TAG_RE: RegExp   // mesmo padrão, flag /g
```

`Tag` (`kind`, `args`, `raw`, `valid`) inalterada.

## Acceptance criteria

- [ ] Linha sem nenhuma tag e com pelo menos um caractere não-espaço sai de
      `parse_tags` byte a byte igual à entrada, incluindo indentação, tabs e
      espaço antes de `…` — inclusive quando é a primeira ou a última linha.
- [ ] Linhas em branco nas bordas do resultado são descartadas; linha em branco
      entre parágrafos é preservada.
- [ ] Linha com tag continua sendo normalizada como hoje (sem espaço duplo, sem
      espaço antes de pontuação).
- [ ] `parse_tags("palavra[BG:sala]outra")` devolve `"palavra outra"`.
- [ ] `parse_tags("sorri[SPRITE:chloe:happy].")` devolve `"sorri."`.
- [ ] `"[BG:sala [interna]]"` sai verbatim, com `tags == []`, sem `]` órfão.
- [ ] `[STAT:coragem:١٢]` é removida com `valid=False`.
- [ ] `TAG_RE` do frontend e do backend têm o mesmo padrão, aferido pelo teste
      de paridade existente.
- [ ] `TurnText` renderiza `"    Ele espera."` preservando os quatro espaços.
- [ ] `npm run check` verde (pytest + tsc + vitest).

## Cenários de teste

Backend (`backend/tests/test_tags.py`):
- Feliz: linha só de narração com indentação de 4 espaços e tab interno → saída
  idêntica.
- Feliz: texto de 3 linhas cuja **primeira** e cuja **última** são indentadas →
  as duas mantêm o recuo (o caso que um `strip()` global quebraria).
- Borda: `"\n\n    Ele espera.\n\n"` → as linhas em branco das bordas somem e a
  indentação sobrevive.
- Feliz: linha com tag no meio → normalizada, como hoje.
- Borda: tag colada entre duas letras acentuadas (`"olá[BG:x]mundo"`) → separador
  inserido.
- Borda: tag colada antes de pontuação → sem separador.
- Borda: tag no começo da linha e no fim da linha → sem separador espúrio nas
  bordas.
- Borda: `"[BG:sala [interna]]"` e `"[BG:[x]]"` → verbatim, `tags == []`.
- Borda: `"[STAT:rep:١٢]"`, `"[STAT:rep:１２]"` → `valid=False`;
  `"[STAT:rep:-3]"` → `valid=True`.
- Borda: texto misto de 3 linhas (uma sem tag e indentada, uma só com tag, uma
  com tag no meio) → indentação preservada, linha-tag some, terceira limpa.
- Falha: `parse_tags` continua idempotente sobre a própria saída no texto misto
  acima.

Frontend (`frontend/src/components/TurnText.test.tsx`):
- Feliz: narração indentada renderiza com os espaços no `textContent`.
- Borda: tag colada entre palavras → separador na tela.
- Borda: colchete aninhado renderiza cru, sem `]` sobrando.
- Borda: teste de paridade do `TAG_RE` com o padrão novo.
- Borda: duas linhas com tag em sequência não perdem a segunda por causa do
  `lastIndex` do regex global.

## Rollout e kill switch

N/A. Não há flag: a limpeza de tag é o contrato do texto que entra no event
store e ela não tem estado intermediário seguro — meia limpeza produz turno com
`]` órfão gravado. Rollback é `git revert` do PR; o texto já gravado com a
limpeza antiga não é afetado nem pelo PR nem pelo revert.

## Observabilidade

Eventos: `game_turn` (já existente, `backend/app/turn.py:161`) já reporta `tags`
e `invalid_tags` por turno. Nenhum evento novo — a limpeza é uma transformação
pura, coberta por teste, não por telemetria.
Métrica de sucesso: `invalid_tags` continua zero numa sessão jogada, e nenhum
turno gravado contém `"] "` órfão nem duas palavras coladas.

## i18n

N/A — nenhuma chave nova. As chaves de `TurnText`
(`turnText.speakerLabel`, `turnText.narrationLabel`, `turnText.rawFallback`)
já existem em `en` e `pt-br` em `frontend/src/strings.ts` e não mudam de texto
nem de uso.

**`ui: true` porque o ticket edita um componente React e altera o que aparece na
tela.** `contentGates` do projeto está vazio em `.claude/pipeline.json`, logo não
há gate de conteúdo aplicável; a paridade de locales é verificada pelo teste já
existente `frontend/src/i18n.test.ts`, que não muda.
