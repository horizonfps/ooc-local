---
id: TCK-003
title: Montar o prompt-mestre guiado a partir do cenário, personagens e HUD
status: ready
points: 3
blockedBy: [TCK-001]
files:
  - backend/app/prompt.py
  - backend/tests/test_prompt.py
migration: false
ui: false
risk: low
---

## Problema

O único prompt de sistema do repo é a constante de fumaça
`SMOKE_SYSTEM_PROMPT` em `backend/app/main.py:13` ("You are the narrator of an
interactive story. Reply briefly, in character."). Ela não conhece mundo,
personagem, HUD nem formato de turno. Sem um montador de prompt-mestre o turno
da Fase 1 não tem como produzir o formato que a UI espera (narração em itálico,
falas `**Nome** | fala`, tags inline) nem respeitar o orçamento de contexto de
24K com turno curto (~350 palavras) definido no plano.

## Escopo

Dentro:
- `backend/app/prompt.py` com `build_master_prompt(...)` (assinatura no contrato
  público) e a constante `MASTER_PROMPT_VERSION`.
- Seções fixas e ordenadas: papel do narrador, mundo, personagens em cena,
  estado do jogo (HUD), cena de abertura, resumo da campanha (opcional),
  formato do turno.
- Templates por idioma do cenário (`en` e `pt-br`), escolhidos por
  `scenario.meta.locale`.
- `backend/tests/test_prompt.py` com cenário montado em `tmp_path` (não depende
  do TCK-002).

Fora (explícito):
- Chamar o LLM, montar histórico ou janela de contexto — isso é o TCK-006. Este
  ticket produz **uma string**, função pura, sem I/O e sem async.
- Compact (o parâmetro `compact` existe e é interpolado, mas quem o produz é o
  TCK-007).
- Modo custom de prompt, plot examples/few-shot, `{{variáveis}}` de setup wizard
  — Fases 2 e 7 (spec §2.2).
- Bloco INFO, stats e sugestões de ação no formato do turno — Fase 3. O
  prompt-mestre da Fase 1 **não** pede sugestões nem INFO.

## Comportamento esperado

Do ponto de vista do chamador: dado um `LoadedScenario`, um `StartConfig`, um
`HudState` e a lista de personagens em cena, a função devolve o texto do
`system` message do turno. A mesma entrada devolve sempre a mesma saída
(determinístico, sem timestamp, sem random) — testável por asserção direta.

O texto instrui o narrador a:
1. narrar em prosa na 2ª pessoa, sem falar ou decidir pelo jogador;
2. escrever fala de personagem como `**Nome** | fala`, uma por linha;
3. manter o turno em torno de 350 palavras (teto duro: nunca passar de 500);
4. tratar o HUD como verdade absoluta e **nunca** reescrever HUD, relógio ou
   ficha de status dentro do texto — isso é estado do engine;
5. poder emitir as tags inline `[STAT:nome:±N]`, `[SPRITE:personagem:emocao]`,
   `[BG:local]`, sempre coladas ao trecho a que se referem;
6. responder no idioma do cenário.

## Detalhes técnicos

- Função pura em módulo próprio; nenhuma importação de `main.py` ou de provider.
  Importa só `app.scenario` e `app.hud`.
- Ordem das seções é contrato (o TCK-006 e a Fase 7 dependem dela para cachear
  prefixo de prompt). Cabeçalhos de seção em maiúsculas com `##`, para o modelo
  achar as fronteiras.
- Orçamento (plano, "Orçamento de contexto"): prompt-mestre ~3.000 tokens e
  personagens ~1.000. Não truncar `world.md` nem descrição de personagem neste
  ticket — a responsabilidade de caber é do conteúdo (TCK-002 limita palavras).
  Expor `estimated_tokens(prompt)` não é deste ticket.
- Personagens entram com `name`, `role`, `appearance`, `personality`, `voice` e
  os campos de `mind` que não forem `None`. `secret_plan` entra marcado como
  segredo do personagem que o jogador não conhece.
- Idioma: dois dicionários de template no próprio módulo (`_TEMPLATES["pt-br"]`,
  `_TEMPLATES["en"]`). `locale` desconhecido é impossível (o schema do TCK-001 é
  `Literal["en","pt-br"]`), então nada de fallback silencioso: `KeyError` é
  aceitável e sinaliza schema fora de sincronia.
- `MASTER_PROMPT_VERSION` é um inteiro incrementado quando o texto muda; vai na
  telemetria do turno (TCK-006) para correlacionar qualidade de narração com
  versão de prompt.

Testes existentes que este ticket invalida: **nenhum**. `SMOKE_SYSTEM_PROMPT` e
`/api/chat` continuam intactos, e `backend/tests/test_chat.py` segue valendo —
a rota de fumaça não passa a usar este montador.

## Contrato público

```python
# backend/app/prompt.py
MASTER_PROMPT_VERSION: int

def build_master_prompt(
    scenario: LoadedScenario,
    start: StartConfig,
    hud: HudState,
    characters: list[Character],
    compact: str | None = None,
) -> str: ...
```

Ordem das seções na saída (títulos no idioma do cenário):
`NARRADOR` → `MUNDO` → `PERSONAGENS EM CENA` → `ESTADO DO JOGO` →
`CENA DE ABERTURA` → `RESUMO DA CAMPANHA` (omitida quando `compact is None`) →
`FORMATO DO TURNO`.

## Acceptance criteria

- [ ] A saída contém, na ordem, os sete cabeçalhos de seção (seis quando
      `compact is None`).
- [ ] O texto de `world.md` aparece íntegro na seção `MUNDO`.
- [ ] Cada personagem recebido aparece com nome, papel e traço de personalidade;
      personagem fora da lista **não** aparece.
- [ ] Os quatro valores do HUD (turno, local, hora, clima) aparecem na seção de
      estado.
- [ ] A instrução de tamanho (~350 palavras) e o formato `**Nome** | fala`
      aparecem literalmente na seção de formato.
- [ ] `locale: en` produz cabeçalhos e instruções em inglês; `pt-br`, em
      português.
- [ ] Duas chamadas com a mesma entrada produzem strings idênticas.
- [ ] `npm run check` verde.

## Cenários de teste

- Feliz: cenário pt-br com 2 personagens → seções na ordem, ambos os nomes
  presentes, instruções de formato presentes.
- Feliz: mesmo cenário com `locale: en` → cabeçalhos em inglês e nenhuma palavra
  do template pt-br na saída.
- Borda: `compact="resumo..."` → seção de resumo presente com o texto;
  `compact=None` → seção ausente por completo (nem cabeçalho vazio).
- Borda: personagem com `secret_plan=None` e `opinion_of_player=None` → nenhuma
  linha "None" na saída.
- Borda: `characters=[]` → seção de personagens presente com uma linha dizendo
  que não há NPC em cena (não some, para o modelo não achar que perdeu contexto).
- Falha: `hud.weather` inválido não é caso deste ticket (o schema já barrou);
  o teste documenta que a função confia no `HudState` recebido.

## Rollout e kill switch

N/A — módulo puro sem consumidor até o TCK-006; reverter é apagar o arquivo.

## Observabilidade

Eventos: nenhum próprio (função pura). `MASTER_PROMPT_VERSION` é exportado para
o evento `game_turn` do TCK-006.
Métrica de sucesso: turnos gerados com este prompt saem no formato esperado
(narração + `**Nome** | fala`) sem HUD escrito dentro do texto, verificado no
critério de verde da fase.

## i18n

Não há string de UI. Há **texto de prompt por idioma**, que é o equivalente
aqui: os dois templates (`en`, `pt-br`) nascem juntos neste ticket, escolhidos
por `scenario.meta.locale`. Adicionar idioma no futuro é adicionar entrada em
`_TEMPLATES` e ampliar o `Literal` do TCK-001.
