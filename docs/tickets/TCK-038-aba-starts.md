---
id: TCK-038
title: Editar os starts do cenario na aba Starts
status: ready
points: 3
blockedBy: [TCK-029, TCK-036, TCK-047]
files:
  - frontend/src/components/builder/StartsTab.tsx
  - frontend/src/components/builder/StartsTab.test.tsx
  - frontend/src/builder/validate.ts
  - frontend/src/strings.ts
migration: false
ui: true
risk: medium
---

## Problema

O start carrega prólogo, cena de abertura e HUD inicial — todos obrigatórios no
schema da Fase 1. Sem esta aba, o cenário criado pela UI nasce com um
`starts/default.yaml` de campos vazios e o preview não tem o que narrar.

`blockedBy` inclui o TCK-047 porque as duas abas editam
`frontend/src/strings.ts` e `frontend/src/builder/validate.ts`; rodar na mesma
wave seria colisão de arquivo.

## Escopo

Dentro:
- Aba Starts em mestre-detalhe: lista, criar, deletar, marcar padrão e todos os
  campos de `starts/*.yaml`.
- Regras de validação dos starts somadas a `validateDraft`.
- Chaves i18n dos starts.

Fora (explícito):
- Setup wizard e `opening_mode: ai` (Fase 7).
- Escopo por start de stats/lorebook/endings (Fases 3 e 4).
- Free mode (Fase 7).
- Aba Personagens (TCK-048) — aqui o elenco é só uma lista de checkboxes dos
  personagens que já existem no rascunho.

## Comportamento esperado

Mestre-detalhe: lista à esquerda (≥900px) ou `<select>` rotulado acima do form
(<900px); selecionar move o foco para o primeiro campo do detalhe e anuncia
`builder.detail.selected` com `{name}`.

Criar e deletar start são operações de **rascunho**: o arquivo só existe (ou
some) no disco depois do save, e "recarregar do disco" desfaz.

## Detalhes técnicos

Valem os padrões de campo do TCK-037. Grupos relacionados em `<fieldset>` +
`<legend>`.

### Lista

Nome, badge `builder.starts.defaultBadge` no start padrão, contagem de
sugestões. Botão `builder.starts.create` sempre visível. Botão de deletar por
item, **desabilitado** quando só existe um start, com
`builder.starts.delete.lastDisabled` no `title` — cenário sem start não carrega.

### Form do start selecionado

| campo | controle | yaml | validação |
|---|---|---|---|
| Arquivo/id | input slug (só na criação) | nome do arquivo | `[a-z0-9-]+`, único |
| Nome | input texto | `name` | obrigatório, ≤ 80 |
| Prólogo | textarea longo | `prologue` | obrigatório |
| Cena inicial | textarea | `opening_scene` | obrigatório |
| Play guide | textarea | `play_guide` | opcional (`null` quando vazio) |
| Sugestões iniciais | até 3 inputs | `suggestions` | cada uma ≤ 120; vazias descartadas |
| Local inicial | input texto | `hud.location` | obrigatório |
| Hora inicial | input `type="time"` | `hud.time` | `HH:MM` 24h |
| Clima inicial | select | `hud.weather` | os 7 códigos do backend |
| Elenco em cena | checkboxes | `characters` | ids existentes; nenhum marcado = `null` |
| Start padrão | radio | `meta.default_start` | exatamente um |

HUD inicial e elenco entram porque já são obrigatórios no schema da Fase 1
(`HudDefaults` e a validação de `characters` no loader) — sem eles o start
criado pela UI não carregaria; não é escopo de fase futura, é o mínimo para o
arquivo ser válido.

O select de clima usa as chaves `hud.weather.*` que **já existem** em
`strings.ts` (`clear`, `cloudy`, `rain`, `storm`, `snow`, `fog`, `night`);
nenhuma chave nova de clima. O valor gravado é o código em inglês.

Sugestões: cada linha com botão de remover
(`builder.starts.suggestions.remove` com o índice no `aria-label`); adicionar
desabilita no terceiro, com o hint `builder.starts.suggestions.max`.

Elenco vazio (nenhum personagem no cenário ainda): hint
`builder.starts.cast.empty` com link para a aba Personagens via `goToTab` do
`TabProps` — troca interna, não passa pelo guard de saída.

### Criar start

Diálogo com id (slug pré-preenchido `start-2`, `start-3`… conforme o que já
existe) e nome. O start nasce com prólogo e cena vazios e HUD **copiada do start
padrão**; marca dirty e fica selecionado. O diálogo usa `<dialog>` nativo com o
mesmo padrão do TCK-045 (o polyfill de teste já está no `test-setup.ts`).

### Deletar start

Confirmação `builder.starts.delete.title`/`.body`. Se o deletado era o padrão, o
primeiro restante vira padrão e a UI anuncia
`builder.starts.delete.defaultMoved` na região live.

### Validação somada a `validateDraft`

`ValidationError { tab: 'starts', ... }` para: nome/prólogo/cena/local vazios;
nome > 80; sugestão > 120; `hud.time` fora de `^([01]\d|2[0-3]):[0-5]\d$`;
`hud.weather` fora dos sete códigos; id de start duplicado ou fora do slug.
As regras estruturais (ao menos um start, `default_start` existente, ids de
elenco existentes) já vêm do TCK-036 e não são reescritas aqui.

### Responsividade

≥900px mestre-detalhe em duas colunas (`260px` + resto); <900px lista vira
`<select>` rotulado com os botões criar/deletar ao lado; <480px coluna única,
botões de largura total, alvos de 44px.

## Contrato público

N/A — a aba é consumidora: recebe `TabProps` do TCK-036 e não exporta nada para
outro ticket. As chaves `builder.starts.*` declaradas abaixo são consumidas pelo
TCK-041 (`builder.starts.defaultBadge` no seletor de start do preview), que
por isso declara `blockedBy: [TCK-038]`.

## Acceptance criteria

- [ ] Criar start pelo diálogo o adiciona ao rascunho com a HUD copiada do
      padrão e o seleciona.
- [ ] Deletar o start padrão promove o primeiro restante e anuncia a troca.
- [ ] O botão de deletar fica desabilitado quando só há um start, com o motivo.
- [ ] Marcar "usar por padrão" muda `meta.default_start`.
- [ ] Elenco sem nenhum marcado grava `characters: null`.
- [ ] Terceira sugestão desabilita o botão de adicionar.
- [ ] `hud.time` inválido bloqueia o save com mensagem no campo.
- [ ] Selecionar item da lista move o foco para o primeiro campo e anuncia
      `builder.detail.selected`.
- [ ] `strings.en` e `strings['pt-br']` seguem com as mesmas chaves.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente do fluxo: **nenhuma**; `i18n.test.ts` cobre a paridade de chaves
sem alteração. Nenhuma asserção existente muda.

Cenários novos (`StartsTab.test.tsx`):
- Feliz: preencher prólogo, cena, HUD e sugestões reflete no rascunho.
- Feliz: criar start com o id sugerido e HUD copiada.
- Feliz: trocar o start padrão pelo radio.
- Borda: terceira sugestão desabilita o botão de adicionar.
- Borda: id duplicado mostra `builder.field.slugTaken`.
- Borda: `hud.time` `25:00` gera erro de validação.
- Borda: cenário sem personagem mostra `builder.starts.cast.empty` com link que
  chama `goToTab('characters')`.
- Falha: deletar o único start é impossível (botão desabilitado com o motivo).
- Falha: deletar o start padrão promove outro e anuncia.

## Rollout e kill switch

N/A — aba nova dentro do editor; quem gateia a gravação é o TCK-046/TCK-043.

## Observabilidade

Eventos: nenhum.
Métrica de sucesso: criar 1 start pela UI, salvar e conseguir iniciar o preview
sem erro de validação do backend.

## i18n — chaves novas

| chave | en | pt-br |
|---|---|---|
| `builder.starts.heading` | `Starts` | `Starts` |
| `builder.starts.listLabel` | `Starts in this scenario` | `Starts deste cenário` |
| `builder.starts.create` | `New start` | `Novo start` |
| `builder.starts.create.title` | `New start` | `Novo start` |
| `builder.starts.create.idLabel` | `File name` | `Nome do arquivo` |
| `builder.starts.create.idHint` | `Becomes starts/{id}.yaml.` | `Vira starts/{id}.yaml.` |
| `builder.starts.create.submit` | `Create start` | `Criar start` |
| `builder.starts.defaultBadge` | `default` | `padrão` |
| `builder.starts.defaultToggle` | `Use this start by default` | `Usar este start por padrão` |
| `builder.starts.name` | `Name` | `Nome` |
| `builder.starts.prologue` | `Prologue` | `Prólogo` |
| `builder.starts.prologue.hint` | `The first text the player reads.` | `O primeiro texto que o jogador lê.` |
| `builder.starts.openingScene` | `Opening scene` | `Cena inicial` |
| `builder.starts.openingScene.hint` | `Goes to the narrator only — the player never sees it.` | `Vai só para o narrador — o jogador não vê.` |
| `builder.starts.playGuide` | `Play guide` | `Guia de jogo` |
| `builder.starts.playGuide.hint` | `Author's note shown to the player, kept out of the prompt.` | `Nota do autor mostrada ao jogador, fora do prompt.` |
| `builder.starts.suggestions.legend` | `Opening suggestions` | `Sugestões iniciais` |
| `builder.starts.suggestions.item` | `Suggestion {index}` | `Sugestão {index}` |
| `builder.starts.suggestions.add` | `Add a suggestion` | `Adicionar sugestão` |
| `builder.starts.suggestions.remove` | `Remove suggestion {index}` | `Remover a sugestão {index}` |
| `builder.starts.suggestions.max` | `Up to 3 suggestions.` | `Até 3 sugestões.` |
| `builder.starts.hud.legend` | `Opening HUD` | `HUD inicial` |
| `builder.starts.hud.location` | `Location` | `Local` |
| `builder.starts.hud.time` | `Time` | `Hora` |
| `builder.starts.hud.weather` | `Weather` | `Clima` |
| `builder.starts.cast.legend` | `Characters on scene` | `Personagens em cena` |
| `builder.starts.cast.hint` | `Leave all unchecked to bring the whole cast.` | `Deixe tudo desmarcado para trazer o elenco inteiro.` |
| `builder.starts.cast.empty` | `No characters yet — create one in the Characters tab.` | `Nenhum personagem ainda — crie um na aba Personagens.` |
| `builder.starts.delete` | `Delete start` | `Deletar start` |
| `builder.starts.delete.title` | `Delete the start {name}?` | `Deletar o start {name}?` |
| `builder.starts.delete.body` | `starts/{id}.yaml is removed when you save.` | `starts/{id}.yaml é removido quando você salvar.` |
| `builder.starts.delete.lastDisabled` | `A scenario needs at least one start.` | `Um cenário precisa de pelo menos um start.` |
| `builder.starts.delete.defaultMoved` | `{name} is the default start now.` | `{name} agora é o start padrão.` |
