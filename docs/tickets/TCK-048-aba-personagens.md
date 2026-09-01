---
id: TCK-048
title: Editar os personagens do cenario na aba Personagens
status: done
points: 3
blockedBy: [TCK-029, TCK-036, TCK-038]
files:
  - frontend/src/components/builder/CharactersTab.tsx
  - frontend/src/components/builder/CharactersTab.test.tsx
  - frontend/src/builder/validate.ts
  - frontend/src/strings.ts
migration: false
ui: true
risk: medium
---

## Problema

O personagem é a entidade que o prompt-mestre injeta em `## PERSONAGENS EM CENA`
e de quem saem as emoções que viram espaços de sprite. Sem esta aba, o cenário
criado pela UI não tem elenco, o loader recusa carregá-lo e o preview não abre.

O critério de verde da fase pede "2 NPCs" — é aqui.

`blockedBy` inclui o TCK-038 porque as duas abas editam
`frontend/src/strings.ts` e `frontend/src/builder/validate.ts`; rodar na mesma
wave seria colisão de arquivo.

## Escopo

Dentro:
- Aba Personagens em mestre-detalhe: lista, criar, deletar e o form espelho 1:1
  do `characters/*.yaml`, incluindo `anchor` e o editor de emoções.
- Limpeza da citação do personagem nos starts ao deletar.
- Regras de validação dos personagens somadas a `validateDraft`.
- Chaves i18n dos personagens.

Fora (explícito):
- Gerar personagem ou elenco por LLM (Fase 8).
- Estúdio de personagem e âncora de imagem (Fase 5) — o campo `anchor` daqui é o
  de **power level** da spec §2.4, e o hint diz isso justamente para não
  confundir.
- Upload de sprite (TCK-039); esta aba só **declara** as emoções.
- Miniatura do sprite `default` na lista: exigiria o índice de mídia, que é
  estado do TCK-039; aqui a lista usa sempre o placeholder com a inicial. É
  ausência deliberada, para a aba não depender de um carregamento que não é
  dela.

## Comportamento esperado

Mestre-detalhe igual ao dos Starts: lista à esquerda (≥900px) ou `<select>`
(<900px); selecionar move o foco para o primeiro campo e anuncia
`builder.detail.selected`.

Criar e deletar personagem são operações de **rascunho**. Deletar avisa que os
sprites em `media/sprites/{sprite}/` **não** são removidos e que os starts que
citavam o personagem perdem a referência.

## Detalhes técnicos

Valem os padrões de campo do TCK-037.

### Lista

Item: nome, papel em `--fg-muted`, inicial em placeholder, badge
`builder.characters.anchorBadge` quando `anchor: true`. Botões
`builder.characters.create` e `builder.characters.delete`.

Vazio: `EmptyState` com `builder.characters.empty.title`/`.body` e ação de
criar. Cenário sem personagem é rascunho legítimo; quem exige ao menos um é o
loader — por isso o **save** é bloqueado por
`builder.characters.error.atLeastOne` (regra somada a `validateDraft`), e não a
aba.

### Form — espelho 1:1 do YAML

| campo | controle | yaml | validação |
|---|---|---|---|
| Arquivo/id | input slug (só na criação) | nome do arquivo | `[a-z0-9-]+`, único |
| Nome | input texto | `name` | obrigatório, ≤ 80 |
| Papel | input texto | `role` | obrigatório, ≤ 140 |
| Aparência | textarea | `appearance` | obrigatório |
| Personalidade | textarea | `personality` | obrigatório |
| Voz | textarea | `voice` | obrigatório |
| Sentimento | textarea curto | `mind.feeling` | obrigatório |
| Objetivo | textarea curto | `mind.goal` | obrigatório |
| Opinião sobre o jogador | textarea curto | `mind.opinion_of_player` | opcional (`null` quando vazio) |
| Plano secreto | textarea curto | `mind.secret_plan` | opcional (`null` quando vazio) |
| Pasta de sprites | input slug | `sprite` | opcional; placeholder = id; `[a-z0-9-]+` |
| Âncora de power level | checkbox | `anchor` | — |
| Emoções | chips com sugestões | `emotions` | `default` sempre presente e não removível |

Os quatro campos de `mind` num `<fieldset>` com legend
`builder.characters.mind.legend` e a nota `builder.characters.mind.hint` (é o
estado inicial da mente; o jogo evolui a partir daí).

`anchor` leva o hint `builder.characters.anchor.hint`.

### Emoções

Chips com menu de sugestões do vocabulário base (`default`, `smile`, `sad`,
`angry`, `shy`, `despair`, `joy`, `crying`, `hit`, `attacking`, `mocking`),
rotulado por `builder.characters.emotions.suggest`. Só o valor cru em inglês vai
para o YAML — é chave de arquivo, não texto de UI. A validação é a mesma do
backend (`^[a-z0-9-]+$`, TCK-029); valor fora disso mostra
`builder.field.slugInvalid` e não vira chip. Duplicata é ignorada em silêncio.

O chip `default` mostra `builder.characters.emotions.defaultLocked` no `title` e
não tem botão de remover; ele fica sempre em primeiro (o backend normaliza
assim, e a UI faz igual para não parecer que o campo "pulou" depois de salvar).

Remover qualquer outra emoção mostra o aviso
`builder.characters.emotions.hasAsset` numa região polite: o arquivo daquele
espaço, se existir, continua no disco e apenas sai do grid da aba Mídia. O aviso
é incondicional (esta aba não carrega o índice de mídia) e é escrito para ser
verdadeiro nos dois casos.

### Criar e deletar

Criar: diálogo com id e nome (`<dialog>` nativo, padrão do TCK-045); nasce com
`emotions: ['default']`, `anchor: false` e textos vazios.

Deletar: confirmação `builder.characters.delete.title`/`.body`. Ao confirmar, a
UI remove o id da lista `characters` de cada start que o citava e anuncia
`builder.characters.delete.castUpdated` com `{starts}` — sem isso o save cairia
em 422, porque o backend valida que todo id citado existe (TCK-043).

### Validação somada a `validateDraft`

`ValidationError { tab: 'characters', ... }` para: cada campo obrigatório vazio;
nome > 80; papel > 140; `sprite` fora do slug; emoção fora do slug; id duplicado
ou fora do slug; e `builder.characters.error.atLeastOne` quando `characters`
está vazio.

### Responsividade

Igual à aba Starts: ≥900px duas colunas; <900px `<select>`; <480px coluna única,
chips quebrando linha, alvos de 44px.

## Contrato público

N/A — aba consumidora do `TabProps` (TCK-036). As emoções que ela grava são
lidas pelo TCK-039 a partir do rascunho, não de uma constante exportada daqui.

## Acceptance criteria

- [ ] Criar personagem nasce com `emotions: ['default']` e `anchor: false`.
- [ ] O chip `default` não oferece botão de remover e fica em primeiro.
- [ ] Adicionar emoção pelo menu e por digitação funciona; valor fora de
      `[a-z0-9-]+` é recusado com `builder.field.slugInvalid`.
- [ ] Remover emoção mostra o aviso de que o arquivo continua no disco.
- [ ] Os quatro campos de `mind` gravam em `mind.*`, com `null` nos opcionais
      vazios.
- [ ] Deletar personagem citado por um start remove a citação e anuncia quais
      starts mudaram.
- [ ] Rascunho sem personagem bloqueia o save com
      `builder.characters.error.atLeastOne`.
- [ ] Selecionar item move o foco para o primeiro campo e anuncia
      `builder.detail.selected`.
- [ ] `strings.en` e `strings['pt-br']` seguem com as mesmas chaves.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente do fluxo: **nenhuma**; `i18n.test.ts` cobre a paridade de chaves
sem alteração. Nenhuma asserção existente muda.

Cenários novos (`CharactersTab.test.tsx`):
- Feliz: criar personagem e preencher os dez campos de texto.
- Feliz: chip de emoção adicionado pelo menu e por Enter.
- Feliz: marcar `anchor` mostra o badge na lista.
- Borda: remover `default` não é oferecido.
- Borda: emoção duplicada é ignorada; emoção `Feliz` é recusada.
- Borda: opcionais vazios viram `null` no rascunho.
- Borda: deletar personagem atualiza os starts e anuncia.
- Falha: rascunho sem personagem gera o erro que bloqueia o save.
- Falha: id duplicado no diálogo de criação mostra `builder.field.slugTaken`.

## Rollout e kill switch

N/A — aba nova dentro do editor; quem gateia a gravação é o TCK-046/TCK-043.

## Observabilidade

Eventos: nenhum.
Métrica de sucesso: criar 2 NPCs pela UI, salvar e ver os dois no prompt do
preview (aparecem na narração do primeiro turno).

## i18n — chaves novas

| chave | en | pt-br |
|---|---|---|
| `builder.characters.heading` | `Characters` | `Personagens` |
| `builder.characters.listLabel` | `Characters in this scenario` | `Personagens deste cenário` |
| `builder.characters.create` | `New character` | `Novo personagem` |
| `builder.characters.create.title` | `New character` | `Novo personagem` |
| `builder.characters.create.idLabel` | `File name` | `Nome do arquivo` |
| `builder.characters.create.idHint` | `Becomes characters/{id}.yaml.` | `Vira characters/{id}.yaml.` |
| `builder.characters.create.submit` | `Create character` | `Criar personagem` |
| `builder.characters.empty.title` | `No characters yet` | `Nenhum personagem ainda` |
| `builder.characters.empty.body` | `A scenario needs at least one character to be playable. Create the first one.` | `Um cenário precisa de pelo menos um personagem para ser jogável. Crie o primeiro.` |
| `builder.characters.error.atLeastOne` | `Create at least one character before saving.` | `Crie pelo menos um personagem antes de salvar.` |
| `builder.characters.name` | `Name` | `Nome` |
| `builder.characters.role` | `Role` | `Papel` |
| `builder.characters.role.hint` | `One line: who they are in this story.` | `Uma linha: quem essa pessoa é nesta história.` |
| `builder.characters.appearance` | `Appearance` | `Aparência` |
| `builder.characters.appearance.hint` | `Also the base for the sprite art.` | `Também é a base da arte do sprite.` |
| `builder.characters.personality` | `Personality` | `Personalidade` |
| `builder.characters.voice` | `Voice` | `Voz` |
| `builder.characters.voice.hint` | `How they speak: length, register, tics.` | `Como fala: tamanho, registro, vícios.` |
| `builder.characters.mind.legend` | `Starting mind` | `Mente inicial` |
| `builder.characters.mind.hint` | `Where this character starts. The game moves it from here.` | `De onde este personagem parte. O jogo move a partir daqui.` |
| `builder.characters.mind.feeling` | `Feeling` | `Sentimento` |
| `builder.characters.mind.goal` | `Goal` | `Objetivo` |
| `builder.characters.mind.opinion` | `Opinion of the player` | `Opinião sobre o jogador` |
| `builder.characters.mind.secretPlan` | `Secret plan` | `Plano secreto` |
| `builder.characters.sprite` | `Sprite folder` | `Pasta de sprites` |
| `builder.characters.sprite.hint` | `Folder under media/sprites/. Defaults to the file name.` | `Pasta dentro de media/sprites/. O padrão é o nome do arquivo.` |
| `builder.characters.anchor` | `Power level anchor` | `Âncora de power level` |
| `builder.characters.anchor.hint` | `Marks this character as the strength reference for the scenario.` | `Marca este personagem como a referência de força do cenário.` |
| `builder.characters.anchorBadge` | `anchor` | `âncora` |
| `builder.characters.emotions.legend` | `Emotions` | `Emoções` |
| `builder.characters.emotions.hint` | `Each emotion becomes a sprite slot in the Media tab.` | `Cada emoção vira um espaço de sprite na aba Mídia.` |
| `builder.characters.emotions.add` | `Add emotion` | `Adicionar emoção` |
| `builder.characters.emotions.remove` | `Remove the emotion {emotion}` | `Remover a emoção {emotion}` |
| `builder.characters.emotions.suggest` | `Suggested emotions` | `Emoções sugeridas` |
| `builder.characters.emotions.defaultLocked` | `default always exists — it's the fallback sprite.` | `default sempre existe — é o sprite de fallback.` |
| `builder.characters.emotions.hasAsset` | `If {emotion} has an uploaded sprite, the file stays on disk — it just leaves the grid.` | `Se {emotion} tiver sprite enviado, o arquivo fica no disco — só sai do grid.` |
| `builder.characters.delete` | `Delete character` | `Deletar personagem` |
| `builder.characters.delete.title` | `Delete {name}?` | `Deletar {name}?` |
| `builder.characters.delete.body` | `characters/{id}.yaml is removed when you save. The sprites in media/sprites/{sprite}/ stay on disk.` | `characters/{id}.yaml é removido quando você salvar. Os sprites em media/sprites/{sprite}/ ficam no disco.` |
| `builder.characters.delete.castUpdated` | `{name} was also removed from these starts: {starts}` | `{name} também saiu destes starts: {starts}` |

## Ressalva registrada na wave 12

- Regra de "pelo menos um personagem" foi removida na correcao da wave: contradizia o contrato do TCK-043 (`characters: {}` e payload valido). O empty state da aba convida a criar; o save nao bloqueia.
