---
id: TCK-026
title: Remover bloco de HUD e eco da acao do jogador do output do narrador
status: done
points: 3
blockedBy: []
files:
  - backend/app/cleanup.py
  - backend/app/turn.py
  - backend/app/prompt.py
  - backend/tests/test_cleanup.py
  - backend/tests/test_turn.py
  - backend/tests/test_prompt.py
migration: false
ui: false
risk: medium
---

## Problema

Jogando o verde da Fase 1 apareceram dois vícios do narrador que o prompt já
proíbe e o modelo ignora:

1. o narrador escreve um bloco de HUD literal dentro da prosa (`# Turno 3`,
   `**HUD**`, linhas `Local: pátio da escola`, `Hora: 07:52`), duplicando o HUD
   determinístico que a UI já renderiza a partir do engine;
2. o narrador ecoa a ação do jogador como fala (`**Você** | vou até a Chloe`),
   o que a UI renderiza como se fosse um personagem falando.

O plano manda `bug jogando > feature da fila` (regra 4) e a regra transversal do
projeto é que tudo que é sistema é determinístico no engine. Prompt sozinho já
falhou; a correção precisa ser determinística no pipeline de limpeza, com o
reforço de prompt como segunda camada.

Sem isso, toda a Fase 2 (preview jogável, sprites) é jogada em cima de um texto
que repete estado do engine e confunde quem testa o cenário.

## Escopo

Dentro:
- Novo módulo `backend/app/cleanup.py` com `strip_engine_echo(text: str) -> tuple[str, int]`
  (texto limpo, número de linhas removidas).
- Chamada em `backend/app/turn.py`, depois de `parse_tags`, antes da checagem de
  turno vazio.
- Reforço das duas proibições no `format_body` dos dois locales em
  `backend/app/prompt.py` e bump de `MASTER_PROMPT_VERSION` de 2 para 3.
- Contagem de linhas removidas no evento `game_turn`.
- Testes novos em `backend/tests/test_cleanup.py` e um teste de ponta a ponta em
  `backend/tests/test_turn.py`.

Fora (explícito):
- Espelhar a limpeza no frontend durante o stream (é o TCK-028; até ele existir,
  o texto parcial em stream ainda pode mostrar o bloco por alguns instantes,
  mas o texto persistido já sai limpo).
- Atualizar o HUD a partir do texto do narrador (é o TCK-027).
- Qualquer mudança no parser de tags (`app/tags.py`).
- Remover fala de NPC, reformatar prosa ou normalizar markdown do narrador.

## Comportamento esperado

Do ponto de vista de quem joga: o turno que chega na tela e fica salvo na sessão
não contém mais bloco de HUD nem a fala `**Você** | ...`. O resto do texto
(narração, falas de NPC, quebras de parágrafo) é idêntico ao que o modelo
escreveu.

Se o modelo escrever **só** bloco de HUD e eco, o turno vira vazio e cai no
caminho de erro `empty turn` que já existe em `run_turn` — o mesmo tratamento de
"turno que era só uma tag" da Fase 1.

## Detalhes técnicos

`strip_engine_echo` trabalha linha a linha, sobre o texto **já limpo de tags**
por `parse_tags`, e nunca reescreve o conteúdo de uma linha: só decide manter ou
descartar a linha inteira. Linha descartada não deixa parágrafo vazio (mesma
política de `parse_tags`), e as linhas em branco das bordas são removidas no
final.

Uma linha é descartada quando (comparação case-insensitive, depois de
`strip()`):

1. **Cabeçalho de estado**: casa
   `^#{1,6}\s*(turno|turn|hud|estado do jogo|game state)\b.*$`.
   Cobre `# Turno 3`, `### HUD`, `## Estado do jogo`.
2. **Rótulo de HUD em negrito sozinho**: casa
   `^\*\*\s*(hud|estado do jogo|game state)\s*\*\*\s*:?\s*.*$`.
3. **Campo de HUD isolado**: casa
   `^\s*(?:[-*]\s*)?(?:\*\*)?\s*(turno|turn|local|location|hora|time|clima|weather)\s*(?:\*\*)?\s*[::]\s*\S.*$`.
   Cobre `Local: pátio da escola`, `- **Hora:** 07:52`, `Clima: limpo`.
4. **Eco do jogador**: casa
   `^\*\*\s*(voce|você|you|player|jogador)\s*\*\*\s*\|.*$` — a linha inteira sai,
   inclusive quando o narrador escreve `**Você** | ...` com acento ou sem.

Armadilhas conhecidas, já decididas:

- A regra 3 é de **linha inteira**. Uma fala de NPC (`**Chloe** | Local: aqui`)
  não casa porque a linha começa com o marcador de speaker. Uma narração que
  comece literalmente com `Hora: ` é sacrificada de propósito: é indistinguível
  de eco de HUD e é raríssima em prosa de segunda pessoa. Documente isso num
  comentário curto em inglês no módulo.
- Os regexes usam `re.IGNORECASE` e casam formas com e sem acento
  (`voce|você`); não normalize unicode nem remova acento do texto.
- A função é **idempotente**: rodar duas vezes dá o mesmo resultado. Há teste
  para isso, no mesmo espírito de `test_parse_tags_is_idempotent`.
- Em `turn.py` a ordem é: `clean_text, tags = parse_tags(raw_text)` →
  `clean_text, stripped = strip_engine_echo(clean_text)` → checagem de
  `clean_text.strip()` vazio → `advance(hud)` → `append_events`. Nada muda no
  que é persistido além do texto do `narrator_turn`.

Reforço de prompt (`format_body`, os dois locales, texto novo somado ao que já
existe, sem remover linha nenhuma):

- pt-br: `Nunca escreva bloco de HUD, cabeçalho de turno nem linhas como "Local:", "Hora:" ou "Clima:" — isso é estado do engine e já aparece na tela.` e
  `Nunca repita a ação do jogador como fala: a linha **Você** | ... é proibida.`
- en: `Never write a HUD block, a turn heading or lines like "Location:", "Time:" or "Weather:" — that is engine state and is already on screen.` e
  `Never repeat the player's action as speech: the line **You** | ... is forbidden.`

`MASTER_PROMPT_VERSION` vira 3 (o evento `game_turn` já carrega esse número, é
como se separa turno velho de turno novo na telemetria).

## Contrato público

```python
# backend/app/cleanup.py
def strip_engine_echo(text: str) -> tuple[str, int]:
    """Returns the text without engine-echo lines and how many lines were dropped."""
```

Consumido por TCK-027 (aplica a mesma ordem em `turn.py`) e espelhado por
TCK-028 no frontend — as quatro regras acima são o contrato que o TurnText
replica.

## Acceptance criteria

- [ ] `strip_engine_echo` remove cabeçalho de turno/HUD, rótulo `**HUD**`,
      linhas de campo de HUD isoladas e linhas de fala do jogador.
- [ ] Fala de NPC, narração comum, indentação e linhas em branco internas
      sobrevivem intactas.
- [ ] `strip_engine_echo(strip_engine_echo(x)[0])[0] == strip_engine_echo(x)[0]`.
- [ ] Um turno cujo output é só HUD + eco cai no caminho `empty turn` já
      existente e não persiste evento nenhum.
- [ ] `SessionDetail.turns` do turno salvo não contém nenhuma das linhas
      removidas.
- [ ] `format_body` dos dois locales contém as duas novas proibições e
      `MASTER_PROMPT_VERSION == 3`.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente que muda de preparação (nenhuma asserção é alterada):
`backend/tests/test_turn.py` e `backend/tests/test_prompt.py` continuam
passando como estão — as asserções atuais (`"350 palavras" in prompt`,
`"**Nome** | fala" in prompt`, textos de turno sem HUD nos fakes) não são
tocadas, porque o ticket só **acrescenta** linhas ao `format_body` e só remove
linhas que os fakes não emitem. Os cenários abaixo são cenários novos.

- Feliz: `parse_tags` + `strip_engine_echo` sobre
  `"# Turno 3\n**HUD**\nLocal: pátio\n\nVocê atravessa o pátio.\n**Chloe** | Oi."`
  devolve `"Você atravessa o pátio.\n**Chloe** | Oi."` e 3 linhas removidas.
- Feliz: `"**Você** | vou até a Chloe\nEla levanta os olhos."` devolve só
  `"Ela levanta os olhos."`.
- Borda: `"**Chloe** | Local: aqui não é lugar de conversa."` é preservada
  inteira (linha de fala de NPC, não é campo de HUD).
- Borda: `"    Ele espera.\nHora: 07:52\n    Ainda espera."` mantém as duas
  linhas indentadas com a indentação original e remove só a do meio.
- Borda: texto sem nenhuma linha de eco volta idêntico, com contagem 0.
- Borda: idempotência sobre um texto misto (tag, HUD, eco, prosa).
- Falha: turno cujo output inteiro é `"# Turno 1\n**Você** | ando"` emite
  `{"error": "empty turn"}` no stream, não persiste `player_turn` nem
  `narrator_turn` e o HUD não avança.
- Ponta a ponta (`test_turn.py`): fake stream com
  `"# Turno 1\nLocal: patio\nVoce anda ate a Chloe. [STAT:reputacao:+1]"`
  persiste `narrator_turn` com texto `"Voce anda ate a Chloe."` e um evento
  `tag`.

## Rollout e kill switch

N/A — sem flag. A limpeza é determinística e só remove linhas que o prompt já
proibia; reverter é reverter o commit. `risk: medium` vem do risco de falso
positivo na regra 3, coberto pelos testes de borda acima.

## Observabilidade

Eventos: `game_turn` ganha a propriedade `stripped_lines` (int, 0 quando nada
foi removido), emitida junto das já existentes em `emit_game_turn`.
Métrica de sucesso: `stripped_lines` cai para perto de zero ao longo das
sessões (o prompt passou a ser obedecido) e nunca dispara `empty turn` em turno
que tinha prosa de verdade.

## i18n

N/A — o texto alterado é prompt de sistema (já bilíngue por locale do cenário em
`app/prompt.py`), não string de UI.
