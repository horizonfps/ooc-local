---
id: TCK-010
title: Renderizar o texto do turno com narração, falas e filtro de tags
status: done
points: 3
blockedBy: [TCK-008]
files:
  - frontend/src/components/TurnText.tsx
  - frontend/src/components/TurnText.test.tsx
  - frontend/src/components/turnText.css
migration: false
ui: true
risk: low
---

## Problema

Hoje o texto do modelo é jogado num `<p>` com `font-style: italic` no CSS
(`frontend/src/index.css:51`) e nada mais: fala de personagem não se distingue
de narração, e qualquer tag inline que escape aparece crua para o jogador. O
plano exige o formato "narração itálico + `**Nome** | fala`" já na Fase 1, e as
Fases 2–5 penduram sprite e background exatamente neste ponto de renderização.

## Escopo

Dentro:
- `frontend/src/components/TurnText.tsx`: componente puro que recebe uma string e
  devolve o turno formatado. Usado pelo prólogo e por todo turno do narrador,
  em histórico e em streaming (o consumidor é o TCK-012).
- Parsing de linha: narração vs fala `**Nome** | fala`.
- Filtro de defesa de tags inline, com retenção de tag parcial durante o
  streaming.
- `turnText.css` com a tipografia do turno.
- `TurnText.test.tsx` cobrindo os cenários listados abaixo (as seções
  "Acceptance criteria" e "Cenários de teste" deste ticket são a lista
  completa).

Fora (explícito):
- Markdown geral (`#`, listas, links, código): na Fase 1 aparecem como texto
  literal. Só `**` de nome de fala tem significado.
- Sprite e background: as tags são removidas, não renderizadas (Fases 2 e 5).
- Cor por personagem: sem paleta antes do builder da Fase 2.
- Remover a tag no servidor — isso é o TCK-004/TCK-006. Aqui é **defesa**, não
  a limpeza canônica.
- Cursor de digitação animado (opcional e não implementado).

## Comportamento esperado

Adaptado do tema 04 da spec de UI.

### Formato de entrada

Por linha: **narração** (prosa comum) renderiza em itálico; **fala**
(`**Nome** | fala do personagem`) renderiza nome em negrito, separador visual e
fala em texto normal (não itálico — a fala é a voz literal, a narração é a
moldura); linha em branco separa parágrafos.

Regras de parsing:
- Uma linha só é fala se casar `^\*\*(.+?)\*\*\s*\|\s*(.*)$`. Qualquer outra
  coisa é narração.
- `|` dentro da fala não quebra o parsing (só o primeiro separa nome de fala).
- Nome vazio (`** ** | ...`) cai em narração — melhor mostrar cru do que
  inventar personagem.
- Renderização é por nós React, **não** por `dangerouslySetInnerHTML`. Texto do
  modelo é entrada não confiável.

### Limpeza de tags inline

Tags são removidas pelo engine; a UI recebe texto já limpo. Ainda assim
`TurnText` aplica um filtro de defesa, porque durante o streaming a UI renderiza
texto que ainda não passou pelo fechamento do turno, e tag vazando na tela é o
defeito mais visível possível.

- Remove a tag e colapsa espaço duplicado / espaço antes de pontuação que sobrar.
- Linha que fica vazia depois da remoção não vira parágrafo vazio.
- **Tag parcial no streaming**: enquanto um `[` aberto não tiver `]`
  correspondente, o trecho a partir do `[` fica **retido** (não renderizado) até
  fechar ou até o fim do turno (`streaming={false}`). Isso impede o efeito de
  `[SPR` aparecer e sumir. Se o turno acabar com colchete aberto, o trecho
  retido é exibido cru — melhor texto estranho do que texto sumido.
- O filtro nunca engole colchete de prosa normal (`[risos]`, `[sic]`): só remove
  quando o conteúdo casa `^[A-Z][A-Z0-9_]*:` — a mesma regra do `TAG_RE` do
  backend (TCK-004).

### Streaming

- Renderiza incrementalmente sem reprocessar o histórico inteiro a cada delta.
- `**` ainda não fechado no fim do buffer não pode alternar o layout da linha:
  enquanto a linha estiver incompleta ela renderiza como narração e só vira fala
  quando o padrão fechar. A transição acontece uma vez, no fim da linha.

### Tipografia

Narração em itálico, cor primária, `line-height` ~1.6. Nome do falante em
negrito, cor de destaque, não itálico. Separador entre nome e fala gerado por
CSS (`::before`/`::after`), não o caractere `|` literal na tela. Parágrafos com
espaçamento; `white-space: pre-wrap`.

### Estados

| Estado | Comportamento |
|---|---|
| **Vazio** | String vazia ou só espaços → nada renderizado; o bloco não ocupa altura. Quem mostra `game.turn.thinking` é a tela de jogo (TCK-012). |
| **Carregando** | Não se aplica; o componente é puro sobre a string que recebe. |
| **Erro** | Nenhuma entrada faz o componente lançar. Entrada malformada degrada para narração crua, com `turnText.rawFallback` no `title` do bloco. Nunca "algo deu errado". |
| **Sucesso** | Narração em itálico, falas com nome em negrito, nenhuma tag visível. |

### Acessibilidade

Nome do falante em `<strong>` semântico; narração em `<em>` — o leitor de tela
recebe a mesma distinção que o olho. Separador visual é CSS, portanto não é
lido. Texto respeita zoom até 200% sem cortar conteúdo.

### Responsividade (360px)

`overflow-wrap: anywhere`; nome do falante e fala quebram na mesma linha lógica;
fonte mínima 15px no menor breakpoint.

## Detalhes técnicos

- Assinatura: `TurnText({ text, streaming = false })`. `streaming` controla só a
  retenção de colchete aberto e de `**` não fechado.
- A regex de tag fica numa constante exportada do módulo, com comentário de uma
  linha apontando que ela espelha `TAG_RE` de `backend/app/tags.py` (TCK-004).
  Divergência entre as duas é bug de contrato.
- Parsing é `useMemo` sobre `text`: o custo é O(tamanho do turno), aceitável a
  ~500 tokens por turno; nada de estado interno acumulado.
- Sem dependência nova (nada de `react-markdown`).
- Testes com Testing Library, disponível desde o TCK-008.

Testes existentes que este ticket invalida: **nenhum**. Componente novo, arquivo
novo, sem consumidor até o TCK-012. O estilo itálico de `.messages p.assistant`
em `index.css` continua onde está e é o TCK-012 que deixa de usá-lo.

## Contrato público

```ts
// frontend/src/components/TurnText.tsx  (consumido pelo TCK-012)
export const TAG_RE: RegExp                       // espelha backend/app/tags.py
export function TurnText(props: { text: string; streaming?: boolean }): JSX.Element
```

## Acceptance criteria

- [ ] `"Ela abre a porta devagar."` → um parágrafo em `<em>`.
- [ ] `"**Yuna** | Você veio."` → `<strong>Yuna</strong>` + fala em texto normal,
      sem `|` na tela.
- [ ] `"**Yuna** | Vem — agora | rápido."` → tudo depois do primeiro `|` é fala.
- [ ] `"** ** | oi"` → narração crua, sem falante.
- [ ] `"O sino toca. [STAT:reputacao:+1]"` → tag removida, sem espaço duplo
      antes do ponto.
- [ ] `"[SPRITE:yuna:feliz]"` sozinho numa linha → linha some, sem parágrafo
      vazio.
- [ ] `"Ele ri [risos] e sai."` → colchete de prosa preservado.
- [ ] Com `streaming`, buffer terminando em `"...e então [SPR"` → o trecho retido
      não aparece; ao completar, aparece só `" ela sorri"`.
- [ ] Com `streaming={false}` e colchete aberto → trecho retido exibido cru.
- [ ] Com `streaming`, `"**Yu"` renderiza como narração e vira fala uma única vez
      ao completar.
- [ ] `"# Título"` → texto literal; `<script>` → texto, nenhum HTML executado.
- [ ] String vazia → nada renderizado, altura zero.
- [ ] `npm run check` verde.

## Cenários de teste

- Feliz: mistura de narração e duas falas em linhas seguidas → três blocos, ordem
  preservada.
- Feliz: três tags de tipos diferentes num parágrafo → texto limpo.
- Borda: `\r\n` no texto do modelo → quebras normalizadas, sem linha fantasma.
- Falha: entrada com `**` desbalanceado e colchete aberto ao mesmo tempo, sem
  `streaming` → texto cru visível, componente não lança.
- Falha: `text` com 20.000 caracteres → renderiza sem travar (sanity de
  performance, sem asserção de tempo).

Verificação manual (fora do `verify`; anotar no PR): nome de 40 caracteres sem
espaço em 360px quebra sem scroll horizontal; zoom 200% não corta texto.

## Rollout e kill switch

N/A — componente puro sem consumidor até o TCK-012. Rollback é reverter o PR.

## Observabilidade

Eventos: nenhum. A contagem de tags e as tags inválidas são observadas no
backend (`game_turn`, TCK-006); duplicar isso no cliente não acrescenta sinal.
Métrica de sucesso: zero tag visível na tela durante os 5 turnos do critério de
verde.

## i18n

Nenhuma chave nova. O texto do turno é conteúdo do cenário/modelo e **não** é
traduzido pela UI. Consome apenas `turnText.rawFallback`, `turnText.speakerLabel`
e `turnText.narrationLabel` (rótulos de apoio para leitor de tela), criadas no
TCK-008.
