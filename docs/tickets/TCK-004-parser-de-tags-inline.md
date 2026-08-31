---
id: TCK-004
title: Extrair e remover tags inline do texto do narrador
status: ready
points: 3
blockedBy: []
files:
  - backend/app/tags.py
  - backend/tests/test_tags.py
migration: false
ui: false
risk: low
---

## Problema

O plano coloca o parser de tags na Fase 1 justamente porque "todas as fases
seguintes penduram nele": stats (Fase 3), sprites e backgrounds (Fases 2 e 5),
cenas (Fase 7). Hoje o texto do modelo vai cru para a tela
(`frontend/src/App.tsx:69`). Se o narrador emitir `[SPRITE:chloe:sad]`, o
jogador lê a tag — o defeito mais visível possível. E sem um extrator, o engine
não tem como registrar o que o modelo pediu.

## Escopo

Dentro:
- `backend/app/tags.py`: modelo `Tag` e função `parse_tags(text)` devolvendo
  `(texto_limpo, tags)`.
- Regra de reconhecimento única para todo o projeto (a UI replica a mesma no
  TCK-010 como filtro de defesa durante o streaming).
- Normalização de espaço após a remoção: espaço duplo colapsado, espaço antes de
  pontuação removido, linha que ficou vazia descartada sem virar parágrafo vazio.
- Validação leve dos três tipos conhecidos (`STAT`, `SPRITE`, `BG`): aridade dos
  argumentos, com tag malformada marcada como inválida em vez de derrubar.
- `backend/tests/test_tags.py`.

Fora (explícito):
- **Aplicar** o efeito das tags: `[STAT]` não altera stat (Fase 3), `[SPRITE]` e
  `[BG]` não carregam imagem (Fases 2 e 5). Na Fase 1 as tags são logadas e
  removidas, nada mais.
- Persistir as tags no event store — quem grava é o TCK-006.
- Parsing de `**Nome** | fala` — isso é renderização, mora na UI (TCK-010).
- `[SCENE:...]` e `[ITEM_*]` — Fase 7 / não portados.

## Comportamento esperado

Do ponto de vista do chamador: entra o texto bruto de um turno, sai o texto que
o jogador vê (sem tag alguma, sem cicatriz de espaçamento) e a lista ordenada
das tags encontradas, na ordem em que apareceram.

Reconhecimento: um trecho entre colchetes é tag quando casa
`\[([A-Z][A-Z0-9_]*):([^\]\n]*)\]`. Ou seja: nome em maiúsculas, dois-pontos,
argumentos sem quebra de linha. `[risos]`, `[sic]` e `[3]` **não** são tags e
ficam no texto — prosa entre colchetes é legítima em narração.

## Detalhes técnicos

- Um único `re.compile` no topo do módulo, exportado como `TAG_RE`, para o
  TCK-010 documentar a mesma regra na UI sem divergir por reescrita.
- `args` = `raw_args.split(":")` com `strip()` em cada parte; string vazia vira
  lista vazia.
- Validação por tipo (não levanta exceção; marca `valid=False`):
  - `STAT`: exatamente 2 args e o segundo casa `^[+-]?\d+$`;
  - `SPRITE`: exatamente 2 args, ambos não vazios;
  - `BG`: exatamente 1 arg não vazio;
  - qualquer outro nome: `valid=True` (desconhecida, mas bem formada) — é
    removida do texto do mesmo jeito, porque tag futura vazando na tela é pior
    que tag futura ignorada.
- Limpeza, nesta ordem: remove as tags → colapsa runs de espaço/tab em um espaço
  → remove espaço antes de `.,;:!?…` → faz `strip()` por linha → remove linhas
  que ficaram vazias **e** que não eram vazias antes (linha em branco original,
  que separa parágrafo, é preservada).
- Idempotência: `parse_tags(parse_tags(t)[0])[0] == parse_tags(t)[0]`.
- Função pura, síncrona, sem I/O e sem log (quem loga é o TCK-006, que tem o
  `session_id`).

Testes existentes que este ticket invalida: **nenhum**. Módulo novo, sem
consumidor até o TCK-006; `/api/chat` continua entregando texto sem filtro.

## Contrato público

```python
# backend/app/tags.py
TAG_RE: re.Pattern[str]   # \[([A-Z][A-Z0-9_]*):([^\]\n]*)\]

class Tag(BaseModel):
    kind: str          # "STAT" | "SPRITE" | "BG" | outro nome em maiúsculas
    args: list[str]
    raw: str           # o trecho original, com colchetes
    valid: bool        # aridade/formato do tipo conhecido conferem

def parse_tags(text: str) -> tuple[str, list[Tag]]: ...
```

## Acceptance criteria

- [ ] `parse_tags("O sino toca. [STAT:reputacao:+1]")` devolve
      `"O sino toca."` e uma `Tag(kind="STAT", args=["reputacao","+1"],
      valid=True)`.
- [ ] Linha que só continha tag desaparece sem deixar parágrafo vazio.
- [ ] Linha em branco entre parágrafos é preservada.
- [ ] `"Ele ri [risos] e sai."` volta idêntico, com lista de tags vazia.
- [ ] `[STAT:reputacao]` (aridade errada) é removida do texto e volta com
      `valid=False`.
- [ ] Tag desconhecida bem formada (`[FOO:bar]`) é removida e volta com
      `kind="FOO"`, `valid=True`.
- [ ] Espaço antes de pontuação não sobra após remoção.
- [ ] `parse_tags` é idempotente sobre o próprio resultado.
- [ ] `npm run check` verde.

## Cenários de teste

- Feliz: texto com narração, uma fala `**Chloe** | ...` e duas tags → texto limpo
  preserva a fala intacta (o parser não toca em `**`), tags na ordem de
  aparição.
- Feliz: três tags de tipos diferentes no mesmo parágrafo → três `Tag`, texto sem
  espaço duplo.
- Borda: `[SPRITE:chloe:sad]` sozinho numa linha, entre dois parágrafos → linha
  some, os dois parágrafos continuam separados por uma linha em branco.
- Borda: colchete aberto sem fechar (`"...e então [SPR"`) → texto volta inteiro,
  nenhuma tag (o tratamento de tag parcial em streaming é da UI, TCK-010).
- Borda: `[stat:reputacao:+1]` em minúsculas → não é tag, fica no texto.
- Borda: string vazia e string só com espaços → `("", [])` e `("", [])`.
- Falha: `[STAT:reputacao:muito]` → removida, `valid=False`; o chamador decide o
  que fazer (o TCK-006 loga).

## Rollout e kill switch

N/A — função pura sem consumidor até o TCK-006. Reverter é apagar o arquivo.

## Observabilidade

Eventos: nenhum próprio, por decisão (o módulo não conhece sessão). O TCK-006
emite a contagem de tags e as inválidas no evento `game_turn`.
Métrica de sucesso: zero tag visível na tela durante o critério de verde da
fase.

## i18n

N/A — não produz texto de usuário; só remove marcação do texto do modelo.
