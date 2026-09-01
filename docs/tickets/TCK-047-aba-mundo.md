---
id: TCK-047
title: Editar o mundo em modo guiado ou prompt custom
status: ready
points: 3
blockedBy: [TCK-029, TCK-036, TCK-037]
files:
  - frontend/src/components/builder/WorldTab.tsx
  - frontend/src/components/builder/WorldTab.test.tsx
  - frontend/src/builder/worldMarkdown.ts
  - frontend/src/builder/worldMarkdown.test.ts
  - frontend/src/builder/validate.ts
  - frontend/src/strings.ts
migration: false
ui: true
risk: medium
---

## Problema

`world.md` é o prompt do narrador: sem esta aba, o cenário criado pela UI nasce
com um cabeçalho stub e nada mais. O ponto delicado é que o modo guiado precisa
serializar cinco campos num markdown que a pessoa também pode reescrever à mão
fora do app — e reabrir sem perder nada.

`blockedBy` inclui o TCK-037 porque as duas abas editam
`frontend/src/strings.ts` e `frontend/src/builder/validate.ts`; rodar na mesma
wave seria colisão de arquivo.

## Escopo

Dentro:
- Aba Mundo: toggle guiado/custom, cinco campos guiados, textarea custom,
  painel de variáveis, avisos e erro de `{{` desbalanceado.
- `worldMarkdown.ts`: serialização e parsing dos cabeçalhos canônicos, com
  fallback.
- Regras de validação do mundo somadas a `validateDraft`.
- Chaves i18n do mundo.

Fora (explícito):
- Auto-generate por LLM (Fase 8) e plot examples (Fase 3+).
- Setup wizard e as variáveis dele (Fase 7): o painel lista apenas
  `{{player}}`, `{{start}}` e `{{scenario}}`.
- Interpolar as variáveis em tempo de jogo — nesta fase elas são texto
  documentado no editor; o engine ainda não substitui.
- Toggles de formato de turno (spec §2.2): dependem de parsers que só existem
  na Fase 3.

## Comportamento esperado

Em modo guiado, cinco campos viram um `world.md` com cabeçalhos canônicos. Em
modo custom, um textarea único é o `world.md` inteiro. Se o arquivo do disco não
bate com os cabeçalhos canônicos, a aba abre em custom com o conteúdo íntegro e
um aviso — o builder nunca joga fora texto que não entendeu.

## Detalhes técnicos

Valem os padrões de campo do TCK-037 (label explícito, hint por
`aria-describedby`, erro em `role="alert"`, validação no blur e no save,
`onChange` do `TabProps`).

Toggle `role="radiogroup"` rotulado por `builder.world.mode.label`, com
`builder.world.mode.guided` e `builder.world.mode.custom`.

### Modo guiado

Cinco textareas, cada um com hint dizendo o que o prompt-mestre faz com aquilo:
universo, tom, regras, conflito, missão. Universo é obrigatório em modo guiado;
os outros quatro são opcionais e somem do arquivo quando vazios.

```ts
export type GuidedWorld = { universe: string; tone: string; rules: string; conflict: string; mission: string }
export const WORLD_HEADINGS = ['Universe', 'Tone', 'Rules', 'Conflict', 'Mission'] as const
export function serializeGuidedWorld(w: GuidedWorld): string
export function parseGuidedWorld(md: string): GuidedWorld | null   // null = não é guiado
```

- Serialização: `## Universe\n\n<texto>\n\n## Tone\n\n<texto>…`, seção vazia
  omitida, sempre nessa ordem, cabeçalhos **em inglês** independentemente do
  locale do cenário (são marcadores de formato, não texto de UI).
- Parsing: aceita o arquivo se todos os cabeçalhos presentes pertencem à lista
  canônica, aparecem na ordem canônica e não há texto fora de seção além de
  espaço em branco; caso contrário devolve `null`.
- Round-trip: `parseGuidedWorld(serializeGuidedWorld(w))` devolve `w` com os
  textos `trim()`ados.

Atenção ao prompt-mestre: `build_master_prompt` neutraliza cabeçalhos do
`world.md` (`_neutralize_headings` rebaixa `##` para `#####`), então os
cabeçalhos canônicos não criam fronteira falsa no prompt. Nada a fazer no
backend; é só para não inventar outro formato achando que `##` quebraria o
prompt.

### Fallback de parsing

Se `meta.world_mode === 'guided'` mas `parseGuidedWorld` devolve `null`, a aba
abre em **custom**, com o conteúdo integral no textarea e o aviso não bloqueante
`builder.world.mode.fallback.title`/`.body` mais o botão
`builder.world.mode.fallback.keepCustom` (grava `world_mode: 'custom'` no
rascunho e some com o aviso). É o que faz "editar fora do app" funcionar.

### Modo custom

Textarea único monoespaçado, altura mínima de 20 linhas, obrigatório e não
vazio. Abaixo, painel `builder.world.variables.title` listando `{{player}}`,
`{{start}}` e `{{scenario}}`, cada uma com descrição e botão de inserir no
cursor (`builder.world.variables.insert` com `{name}`) — inserir preserva a
posição via `selectionStart`/`selectionEnd`.

Validação de variáveis:
- `{{nome}}` fora da lista é **aviso**, não erro:
  `builder.world.variables.unknown` com `{name}`, num bloco `role="status"`
  abaixo do textarea (chave de setup wizard chega na Fase 7 e não pode bloquear
  quem escreve adiantado);
- `{{` sem `}}` na mesma linha é erro de verdade
  (`builder.world.variables.unbalanced`), porque quebra a interpolação em
  silêncio.

### Trocar de modo

- guiado → custom: gera o markdown a partir dos campos, coloca no textarea e
  mostra `builder.world.mode.switchToCustom`;
- custom → guiado: só depois de confirmar
  `builder.world.mode.switchToGuidedTitle`/`.switchToGuidedBody`/`.switchToGuidedSubmit`,
  porque descarta o que não couber nos cinco campos; cancelar mantém custom. Ao
  confirmar, tente `parseGuidedWorld` no texto atual; `null` → os cinco campos
  nascem vazios e o texto é descartado (foi o que a confirmação avisou).

### Validação somada a `validateDraft`

`ValidationError { tab: 'world', ... }` para: `world` vazio; universo vazio
quando `world_mode === 'guided'`; `{{` desbalanceado.

## Contrato público

```ts
// frontend/src/builder/worldMarkdown.ts
export const WORLD_HEADINGS: readonly ['Universe','Tone','Rules','Conflict','Mission']
export type GuidedWorld
export function serializeGuidedWorld(w: GuidedWorld): string
export function parseGuidedWorld(md: string): GuidedWorld | null
```

Nenhum outro ticket da fase consome esta seção.

## Acceptance criteria

- [ ] Modo guiado gera `world.md` com os cabeçalhos canônicos em inglês, na
      ordem, sem seção vazia.
- [ ] `world.md` fora do formato canônico abre em custom com o texto íntegro e o
      aviso de fallback; "manter como custom" grava `world_mode: custom`.
- [ ] `{{foo}}` gera aviso; `{{foo` na mesma linha gera erro que bloqueia o
      save.
- [ ] Inserir variável escreve na posição do cursor.
- [ ] Custom → guiado só acontece depois da confirmação; cancelar mantém custom.
- [ ] Editar qualquer campo marca dirty.
- [ ] `strings.en` e `strings['pt-br']` seguem com as mesmas chaves.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente do fluxo: **nenhuma**; `i18n.test.ts` cobre a paridade de
chaves sem alteração. Nenhuma asserção existente muda.

Cenários novos:
- `worldMarkdown.test.ts` — feliz: round-trip com os cinco campos; borda: seções
  vazias omitidas e recuperadas como `''`; borda: cabeçalho fora de ordem
  devolve `null`; borda: prosa antes do primeiro cabeçalho devolve `null`;
  borda: cabeçalho desconhecido devolve `null`; borda: acento no corpo
  preservado byte a byte.
- `WorldTab.test.tsx` — feliz: preencher os guiados atualiza `world` com os
  cabeçalhos; feliz: inserir variável no cursor; borda: documento
  `world_mode: guided` com markdown à mão abre em custom com aviso; borda:
  guiado → custom mostra o aviso e mantém o texto; falha: custom → guiado sem
  confirmar não muda o modo; falha: `{{` sem fechar gera erro de validação.

## Rollout e kill switch

N/A — aba nova dentro do editor; quem gateia a gravação é o TCK-046/TCK-043.

## Observabilidade

Eventos: nenhum.
Métrica de sucesso: escrever o mundo em modo guiado, salvar, abrir o `world.md`
no editor de texto e ver os cinco blocos; reabrir a aba e encontrar os mesmos
campos.

## i18n — chaves novas

| chave | en | pt-br |
|---|---|---|
| `builder.world.heading` | `World` | `Mundo` |
| `builder.world.mode.label` | `How you write the world` | `Como você escreve o mundo` |
| `builder.world.mode.guided` | `Guided fields` | `Campos guiados` |
| `builder.world.mode.custom` | `Custom prompt` | `Prompt custom` |
| `builder.world.universe` | `Universe` | `Universo` |
| `builder.world.universe.hint` | `Where and when the story happens.` | `Onde e quando a história acontece.` |
| `builder.world.tone` | `Tone and narration style` | `Tom e estilo de narração` |
| `builder.world.tone.hint` | `How the narrator writes: pacing, register, what it avoids.` | `Como o narrador escreve: ritmo, registro, o que evita.` |
| `builder.world.rules` | `World rules` | `Regras do mundo` |
| `builder.world.rules.hint` | `What is possible here and what isn't.` | `O que é possível aqui e o que não é.` |
| `builder.world.conflict` | `Central conflict` | `Conflito central` |
| `builder.world.conflict.hint` | `The tension every scene leans on.` | `A tensão em que toda cena se apoia.` |
| `builder.world.mission` | `Player mission` | `Missão do jogador` |
| `builder.world.mission.hint` | `What the player is trying to do.` | `O que o jogador está tentando fazer.` |
| `builder.world.custom.label` | `Narrator prompt` | `Prompt do narrador` |
| `builder.world.custom.hint` | `The whole narrator prompt, in markdown. Saved as world.md.` | `O prompt do narrador inteiro, em markdown. Salvo como world.md.` |
| `builder.world.variables.title` | `Available variables` | `Variáveis disponíveis` |
| `builder.world.variables.insert` | `Insert {name}` | `Inserir {name}` |
| `builder.world.variables.player` | `The player's name.` | `O nome do jogador.` |
| `builder.world.variables.start` | `The name of the start being played.` | `O nome do start em jogo.` |
| `builder.world.variables.scenario` | `The scenario name.` | `O nome do cenário.` |
| `builder.world.variables.unknown` | `{name} isn't a known variable — it will stay as literal text.` | `{name} não é uma variável conhecida — vai ficar como texto literal.` |
| `builder.world.variables.unbalanced` | `An opening {{ has no closing }} on the same line.` | `Um {{ aberto não tem }} fechando na mesma linha.` |
| `builder.world.mode.fallback.title` | `world.md was written by hand` | `O world.md foi escrito à mão` |
| `builder.world.mode.fallback.body` | `The guided headings aren't there, so the file opened in custom mode. Nothing was lost.` | `Os cabeçalhos do modo guiado não estão lá, então o arquivo abriu em modo custom. Nada foi perdido.` |
| `builder.world.mode.fallback.keepCustom` | `Keep it custom` | `Manter como custom` |
| `builder.world.mode.switchToCustom` | `The guided fields were merged into the text below.` | `Os campos guiados foram juntados no texto abaixo.` |
| `builder.world.mode.switchToGuidedTitle` | `Go back to guided fields?` | `Voltar para os campos guiados?` |
| `builder.world.mode.switchToGuidedBody` | `Anything that doesn't fit the five fields is dropped.` | `O que não couber nos cinco campos é descartado.` |
| `builder.world.mode.switchToGuidedSubmit` | `Use guided fields` | `Usar campos guiados` |
