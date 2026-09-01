---
id: TCK-028
title: Espelhar no TurnText a limpeza de eco do engine durante o stream
status: done
points: 2
blockedBy: [TCK-026]
files:
  - frontend/src/components/turnCleanup.ts
  - frontend/src/components/turnCleanup.test.ts
  - frontend/src/components/TurnText.tsx
  - frontend/src/components/TurnText.test.tsx
migration: false
ui: false
risk: low
---

## Problema

A limpeza do TCK-026 acontece no backend, depois que o stream termina: o texto
que é persistido sai sem bloco de HUD e sem o eco `**Você** | ...`. Só que a UI
renderiza o **texto parcial** enquanto o turno está chegando, direto dos deltas
do SSE (`pending.text` no `GameScreen`). Resultado: durante o turno inteiro a
pessoa vê o bloco de HUD e a fala do jogador na tela, e eles somem de repente no
fim — pisca, parece bug, e é exatamente o que a Fase 1 já resolveu para tags
espelhando `TAG_RE` no `TurnText`.

## Escopo

Dentro:
- Novo módulo `frontend/src/components/turnCleanup.ts` com
  `isEngineEchoLine(line: string): boolean`, espelho das quatro regras do
  TCK-026.
- `TurnText` descarta linhas de eco em `buildBlocks`, no mesmo ponto em que já
  descarta linha vazia.
- Testes unitários do predicado e de render.

Fora (explícito):
- Qualquer mudança de comportamento no backend.
- Filtrar tags (já feito), reformatar prosa, ou mexer no fallback de colchete
  não fechado.
- Mostrar aviso de que algo foi filtrado — a remoção é silenciosa, igual à de
  tags.

## Comportamento esperado

Durante o stream e depois dele, o `TurnText` não renderiza bloco de HUD nem a
fala do jogador. O que aparece na tela durante o stream é idêntico, linha a
linha, ao que fica salvo quando o turno termina.

## Detalhes técnicos

O módulo novo carrega, no topo, um comentário curto em inglês no mesmo espírito
do que já existe sobre `TAG_RE`: "Mirrors strip_engine_echo in
backend/app/cleanup.py (TCK-026); divergence is a contract bug."

Os quatro regexes, em JS, com a flag `i` (e sem `g`, para não carregar
`lastIndex`):

```ts
const HEADING_RE = /^#{1,6}\s*(turno|turn|hud|estado do jogo|game state)\b/i
const HUD_LABEL_RE = /^\*\*\s*(hud|estado do jogo|game state)\s*\*\*\s*:?/i
const HUD_FIELD_RE = /^\s*(?:[-*]\s*)?(?:\*\*)?\s*(turno|turn|local|location|hora|time|clima|weather)\s*(?:\*\*)?\s*[::]\s*\S/i
const PLAYER_ECHO_RE = /^\*\*\s*(voce|você|you|player|jogador)\s*\*\*\s*\|/i
```

`isEngineEchoLine` roda sobre a linha **já limpa de tag** — ou seja, dentro de
`buildBlocks`, logo depois de `cleanLineIfTagged(line)` e da checagem de linha
vazia, antes de tentar o `SPEAKER_RE`. A ordem importa: uma linha
`[BG:sala]Local: pátio` só é reconhecida como eco depois que a tag saiu.

Ponto de atenção no caminho de streaming: `parseTurnText` monta um bloco a
partir do `prefix` da linha com colchete não fechado. Esse prefixo também passa
pelo predicado — extraia a decisão para uma função local usada nos dois pontos
(`buildBlocks` e o ramo `streaming`), para não duplicar a regra.

O ramo de fallback `raw: true` (colchete não fechado, turno finalizado) **não**
filtra: ali o objetivo declarado é mostrar exatamente o que o narrador escreveu.

## Contrato público

```ts
// frontend/src/components/turnCleanup.ts
export function isEngineEchoLine(line: string): boolean
```

Consumido só pelo `TurnText`. As regras são as do TCK-026; qualquer divergência
entre os dois é bug de contrato.

## Acceptance criteria

- [ ] `isEngineEchoLine` devolve `true` para `# Turno 3`, `**HUD**`,
      `Local: pátio`, `- **Hora:** 07:52`, `**Você** | vou até a Chloe` e
      `**You** | I walk`.
- [ ] Devolve `false` para `**Chloe** | Local: aqui não`, narração comum, linha
      indentada e linha vazia.
- [ ] `TurnText` com `text` contendo bloco de HUD + eco renderiza só a prosa
      restante, tanto com `streaming` quanto sem.
- [ ] Texto sem eco renderiza exatamente como hoje (nenhum teste existente de
      `TurnText.test.tsx` muda de asserção).
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente do fluxo: `frontend/src/components/TurnText.test.tsx` cobre
tags, speaker, streaming e fallback. Nenhuma asserção existente muda — os textos
de fixture não contêm eco de HUD. As asserções abaixo são cenários novos, no
mesmo arquivo (render) e no arquivo novo (predicado).

- Feliz: `<TurnText text={"# Turno 3\n**HUD**\nLocal: pátio\n\nVocê atravessa o pátio."} />`
  renderiza uma única linha de narração.
- Feliz: `<TurnText text={"**Você** | vou até a Chloe\n**Chloe** | Oi."} />`
  renderiza só a fala da Chloe, com o nome dela.
- Borda: streaming com `"Local: pátio\nEla ergue os olhos [SPR"` — a linha de
  HUD some, a prosa aparece, e o pedaço com colchete aberto não vira bloco.
- Borda: linha `**Chloe** | Hora: de ir embora.` é renderizada inteira como
  fala.
- Falha: texto que é só eco renderiza `null` (o componente já devolve `null`
  quando não sobra bloco).

## Rollout e kill switch

N/A — `risk: low`, mudança de render puro, revertível pelo commit.

## Observabilidade

Eventos: nenhum (não há telemetria de frontend no projeto).
Métrica de sucesso: o texto na tela durante o stream é igual ao texto salvo
depois do turno — verificável jogando um turno em que o modelo emite HUD.

## i18n

N/A — nenhuma string nova; a filtragem é silenciosa por decisão de produto.
