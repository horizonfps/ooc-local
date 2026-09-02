---
id: TCK-057
title: Editar conflito e missão do start na aba Starts
status: in_review
points: 3
blockedBy: [TCK-056]
files:
  - frontend/src/api.ts
  - frontend/src/components/builder/StartsTab.tsx
  - frontend/src/components/builder/StartsTab.test.tsx
  - frontend/src/strings.ts
  - frontend/src/builder/validate.test.ts
  - frontend/src/components/builder/BuilderPreview.test.tsx
  - frontend/src/components/builder/CharactersTab.test.tsx
  - frontend/src/components/builder/IdentityTab.test.tsx
  - frontend/src/components/builder/MediaTab.test.tsx
  - frontend/src/components/builder/WorldTab.test.tsx
migration: false
ui: true
risk: low
---

## Problema

O TCK-056 fez o backend aceitar `conflict` e `mission` em cada start, e o
narrador já recebe os dois no prompt. Do lado do editor, não existe caminho: o
tipo `StartDoc` (`frontend/src/api.ts:116`) não conhece os campos e a aba Starts
(`frontend/src/components/builder/StartsTab.tsx`) não os desenha. Quem quiser
usar o recurso hoje tem que abrir `scenarios/<id>/starts/<id>.yaml` num editor de
texto — exatamente o que o builder existe para evitar.

Os dois campos sobrevivem ao round trip por acidente: `updateStart`
(`StartsTab.tsx:105`) faz `{ ...draft.starts[id], ...patch }` sobre o objeto
vindo do `GET`, então as chaves desconhecidas voltam intactas no `PUT`. Acidente
não é recurso: start criado pelo diálogo "Novo start" (`StartsTab.tsx:156-166`)
nasce sem as chaves, e nenhuma superfície mostra ou edita o que já está no
arquivo.

## Escopo

Dentro:
- `StartDoc` (`api.ts:116`) ganha `conflict: string | null` e
  `mission: string | null`.
- Dois `textarea` novos no painel de detalhe da aba Starts, entre "Cena inicial"
  e "Guia de jogo", no padrão do `play_guide`.
- `newStart` (`StartsTab.tsx:156`) passa a nascer com os dois campos em `null`.
- Quatro chaves novas em `frontend/src/strings.ts`, nos dois dicionários.
- Testes novos em `StartsTab.test.tsx`.
- Completar os literais de `StartDoc` nos fixtures de teste que o tipo novo
  passa a exigir (inventário na seção de testes).

Fora (explícito):
- Qualquer arquivo em `backend/`. O contrato já existe: é o TCK-056.
- Validação dos dois campos. Nenhuma regra nova em
  `frontend/src/builder/validate.ts` — os campos são opcionais e sem limite de
  tamanho nesta rodada. `validate.test.ts` é tocado só para completar o fixture
  e para acrescentar os dois testes de "não valida" pedidos pelo design.
- A aba Mundo (`WorldTab.tsx`, `worldMarkdown.ts`) e as chaves
  `builder.world.conflict`/`builder.world.mission`: quem remove é o TCK-058.
  Este ticket **não** apaga chave nenhuma; durante a janela entre os dois
  tickets, `builder.world.conflict` e `builder.starts.conflict` coexistem, e
  isso é esperado.
- Preview (`BuilderPreview.tsx`) e qualquer superfície de jogo. Os dois campos
  vão só para o narrador; o jogador não vê. `BuilderPreview.test.tsx` é tocado
  só para completar o fixture.
- CSS novo. O design fecha: nenhuma regra nova é necessária.

## Comportamento esperado

*(Seção fechada pelo design-specialist, copiada literalmente de
`design/tema-1-starts-conflict-mission.md`.)*

### Onde e o quê

Dois campos novos no painel de detalhe do start selecionado, **depois de "Cena
inicial" (`opening_scene`) e antes de "Guia de jogo" (`play_guide`)**, nesta
ordem:

1. **Conflito** — `textarea`, `rows={4}`.
2. **Missão do jogador** — `textarea`, `rows={4}`.

Ambos são opcionais e seguem exatamente o padrão do campo `play_guide` já
existente na aba:

- `label htmlFor={'builder-field-starts.' + selectedId + '.conflict'}` com o
  sufixo `<span className="field-hint">({t('common.optional')})</span>`;
- `textarea` com `className="builder-field-textarea"`;
- `aria-describedby` apontando para o `<p className="field-hint">` de id
  `builder-field-starts.<id>.conflict-hint` (idem `.mission-hint`);
- `value={selectedStart.conflict ?? ''}`;
- `onChange` grava `null` quando `value.trim() === ''`, senão grava o texto como
  digitado (sem trim), igual ao `play_guide`.

Ids seguem a convenção da aba, para que o "Ir para {campo}" do painel de
validação (`jumpToValidationError` → `getElementById('builder-field-' + field)`)
continue funcionando caso algum dia esses campos ganhem validação:

| Elemento | id |
|---|---|
| textarea conflito | `builder-field-starts.<startId>.conflict` |
| hint conflito | `builder-field-starts.<startId>.conflict-hint` |
| textarea missão | `builder-field-starts.<startId>.mission` |
| hint missão | `builder-field-starts.<startId>.mission-hint` |

### Contrato de dados

- `StartDoc` ganha `conflict: string | null` e `mission: string | null`.
- Start criado pelo diálogo "Novo start" nasce com `conflict: null` e
  `mission: null` (o objeto `newStart` em `handleCreateSubmit` passa a incluir
  os dois campos; nada é herdado do start padrão, ao contrário do HUD).
- Vazio = `null` = chave omitida no `starts/<id>.yaml`. Nunca gravar `""`.
- Ambos vão **só para o narrador**; o jogador não vê, mesma natureza da
  `opening_scene`. Nenhuma superfície de jogo (prólogo, HUD, sugestões, guia de
  jogo) exibe esse texto.

### Estados

| Estado | Comportamento |
|---|---|
| **Vazio** | Sem nenhum start, o painel de detalhe inteiro não renderiza (comportamento atual, inalterado). Com start selecionado e campo vazio: `textarea` vazio, sem placeholder, com o hint sempre visível abaixo dizendo que é deste start, opcional e que vai só para o narrador. Nenhum texto de "nada aqui" extra: o hint já é a saída. |
| **Carregando** | Nenhum estado de carregamento próprio. O rascunho já está em memória (`BuilderEditorScreen`) e a edição é síncrona; o skeleton do painel (`.builder-skeleton-block` + `Loading visuallyHidden`) da tela cobre o carregamento do documento. Spinner por campo seria ruído. |
| **Erro** | Não há validação de campo: os dois são opcionais e sem limite de tamanho, então nenhum `role="alert"` novo. O único caminho de erro é o de salvar, já coberto pela tela (`builder.editor.save.error.*`, com "Tentar de novo"). Se o backend rejeitar o documento (422), o texto do usuário continua na tela e o `ErrorState` existente explica e oferece recuperação. |
| **Sucesso** | Feedback já existente e explícito: o indicador `role="status"` do topo vira "tem mudanças não salvas" ao digitar, a aba Starts ganha o marcador `is-dirty` (com texto acessível `builder.editor.tab.dirty`), e ao salvar a live region anuncia `builder.editor.saved`. Nenhuma chave nova. |

### Foco, teclado e acessibilidade

- Ordem de tabulação dentro do detalhe: nome → padrão → prólogo → cena inicial →
  **conflito → missão** → guia de jogo → sugestões → HUD → elenco.
- Trocar de start (lista ou `select`) continua movendo o foco para o campo Nome
  e anunciando `builder.detail.selected`; os dois campos novos recarregam com o
  valor do start recém-selecionado.
- Foco visível: os `textarea` herdam `.builder-field-textarea:focus-visible` do
  CSS do builder; nenhum estilo novo.
- Rótulo programático via `label htmlFor`/`id`; hint ligado por
  `aria-describedby`, lido junto do rótulo. O "(opcional)" está dentro do
  `<label>`, então entra no nome acessível, como já acontece no guia de jogo.
- Contraste: hint usa `var(--fg-muted)` já em uso na aba; nada novo.

### Responsividade

- Menor breakpoint suportado no CSS do builder: `max-width: 479.98px`.
- Os dois campos ficam dentro de `.builder-field`, que já é coluna com
  `width: 100%`; em ≤479.98px o `textarea` ocupa a largura toda e o rótulo com o
  "(opcional)" quebra em duas linhas sem cortar texto.
- Em ≤899.98px a aba está no layout de coluna única (`select` de starts no topo,
  detalhe abaixo): os campos aparecem na mesma ordem, sem scroll horizontal.
- Nenhuma regra de CSS nova é necessária. Se a implementação precisar de alguma,
  ela mora junto das regras de `.builder-starts-*`.

## Detalhes técnicos

**1. `frontend/src/api.ts:116`** — `StartDoc` ganha os dois campos entre
`opening_scene` e `play_guide`, espelhando a ordem do modelo do backend:

```ts
export type StartDoc = {
  id: string
  name: string
  prologue: string
  opening_scene: string
  conflict: string | null
  mission: string | null
  play_guide: string | null
  suggestions: string[]
  hud: HudDefaults
  characters: string[] | null
}
```

Campos **não** opcionais (`| null`, não `?`): é o que força o `tsc -b` a apontar
todo literal de `StartDoc` que ficou incompleto, incluindo o `newStart` da aba.
Essa é a rede de segurança do ticket; não use `?`.

**2. `frontend/src/components/builder/StartsTab.tsx`**

- O bloco do `play_guide` (`StartsTab.tsx:370-385`) é o molde. Copie-o duas
  vezes e insira **entre** o fim do bloco de `opening_scene`
  (`</div>` em `StartsTab.tsx:368`) e o início do bloco de `play_guide`
  (`StartsTab.tsx:370`), na ordem conflito → missão.
- `onChange` idêntico ao do guia de jogo (`StartsTab.tsx:379`):
  `updateStart(selectedId, { conflict: e.target.value.trim() === '' ? null : e.target.value })`.
  O valor gravado é o texto **como digitado**; só o teste de vazio usa `trim`.
- `aria-describedby` só com o hint (não há erro possível), como em
  `StartsTab.tsx:380`.
- `newStart` (`StartsTab.tsx:156-165`) ganha `conflict: null, mission: null`
  logo depois de `opening_scene: ''`.
- Nada de string literal no JSX: rótulo e hint via `t(...)`.

**3. `frontend/src/strings.ts`** — o dicionário `en` começa em `strings.ts:1`,
`ptBr` em `strings.ts:455` (`Record<StringKey, string>`), e
`export type StringKey = keyof typeof en` (`strings.ts:453`). As quatro chaves
entram depois de `builder.starts.openingScene.hint` (`strings.ts:279` em `en`,
`strings.ts:732` em `pt-br`) e antes de `builder.starts.playGuide`
(`strings.ts:280` / `strings.ts:733`). Chave só em `en` quebra o `tsc -b` pelo
`Record<StringKey, string>`; chave só em `pt-br` quebra o teste de paridade
`strings > has the same keys in en and pt-br` (`frontend/src/i18n.test.ts:78`).

**4. Armadilha do fixture** — `BuilderDraft` é
`Omit<ScenarioDocument, 'revision'>` (`screens/BuilderEditorScreen.tsx:20`),
logo `draft.starts` é `Record<string, StartDoc>`. Todo objeto literal tipado
como `BuilderDraft` (direta ou indiretamente, via retorno anotado de função)
passa a precisar dos dois campos. O `tsc -b` do `npm run check:web` lista todos;
o inventário abaixo já antecipa quais são.

## Contrato público

N/A — este ticket **consome** contrato, não expõe. O contrato consumido é o da
seção "Contrato público" do **TCK-056** (`GET`/`PUT
/api/builder/scenarios/{scenario_id}`), que garante:

- `starts[id].conflict` e `starts[id].mission` presentes no `GET`, `null` quando
  ausentes no YAML;
- `PUT` com `""` ou só espaços grava como ausente e o `GET` seguinte devolve
  `null` (por isso a UI já manda `null`, e não `""`: os dois caminhos convergem,
  mas o rascunho na tela fica igual ao que volta do disco);
- `PUT` sem as chaves é aceito e equivale a `null`.

Nenhum outro ticket depende deste.

## Acceptance criteria

- [ ] `StartDoc` tem `conflict: string | null` e `mission: string | null`, nessa
      ordem, entre `opening_scene` e `play_guide`.
- [ ] O detalhe do start mostra, nesta ordem: Cena inicial → Conflito → Missão
      do jogador → Guia de jogo.
- [ ] Os dois campos são `textarea` `rows={4}`, com `(opcional)` no rótulo e
      hint ligado por `aria-describedby` nos ids
      `builder-field-starts.<id>.conflict-hint` / `.mission-hint`.
- [ ] Digitar grava o texto no rascunho; apagar até sobrar só espaço grava
      `null`.
- [ ] Start criado pelo diálogo "Novo start" nasce com os dois campos `null`.
- [ ] Trocar de start troca o conteúdo dos dois campos.
- [ ] Nenhum `role="alert"` novo e nenhuma entrada nova no painel de validação:
      `validateDraft` não produz erro com `field` terminando em `.conflict` ou
      `.mission`.
- [ ] As quatro chaves existem em `en` e em `pt-br`, com os textos da tabela de
      i18n.
- [ ] `npm run check` verde (inclui `tsc -b` e `vitest run`).

## Cenários de teste

*(Lista fechada pelo design-specialist, copiada literalmente.)*

Testes em `frontend/src/components/builder/StartsTab.test.tsx` (mesmo `Harness`
já usado no arquivo). O `baseDraft()` do teste precisa ganhar
`conflict: null, mission: null`, assim como os starts inline dos casos
existentes.

1. **Digitar grava no rascunho** — renderiza com um start; `fireEvent.change` no
   campo rotulado por `builder.starts.conflict` com "Duas facções, um poço"; o
   `starts-debug` mostra `starts.default.conflict === 'Duas facções, um poço'`.
   Idem para `builder.starts.mission`.
2. **Apagar até só espaço vira `null`** — start com `conflict: 'Algo'`; muda o
   valor para `'   '`; `starts.default.conflict` é `null` (espelha o teste já
   existente do `play_guide`).
3. **Start sem os campos abre com os textarea vazios** — start com
   `conflict: null, mission: null`; ambos os campos têm `value === ''` e nenhum
   `role="alert"` na aba.
4. **Trocar de start troca os valores** — dois starts com conflitos diferentes;
   clicar no segundo item da lista; o campo Conflito passa a mostrar o texto do
   segundo start (e o foco vai para o Nome, comportamento já testado).
5. **Ordem no DOM** — dentro do detalhe, a posição do campo Conflito é depois de
   Cena inicial e antes de Guia de jogo, e Missão fica entre Conflito e Guia de
   jogo (comparar por `compareDocumentPosition` ou pela ordem de
   `container.querySelectorAll('.builder-field textarea')`).
6. **Ligação acessível** — o `textarea` de Conflito tem `aria-describedby`
   contendo `builder-field-starts.default.conflict-hint`, e esse elemento existe
   com o texto de `builder.starts.conflict.hint`. Idem Missão.
7. **Start novo nasce com os dois `null`** — abrir "Novo start", criar
   `start-2`; `starts['start-2'].conflict` e `.mission` são `null`, e os campos
   aparecem vazios já com o novo start selecionado.
8. **Nada de obrigatório** — `validateDraft` de um rascunho com
   `conflict: null, mission: null` não produz nenhum erro com `tab === 'starts'`
   e `field` terminando em `.conflict`/`.mission` (`validate.test.ts`).
9. **Texto longo não quebra o salvar** — start com 5 000 caracteres em
   `conflict`: `validateDraft` segue sem erros (decisão: sem limite nesta
   rodada).
10. **i18n completo** — o teste `strings` de `i18n.test.ts` (mesmas chaves em
    `en` e `pt-br`) cobre automaticamente as quatro chaves novas; não é preciso
    teste extra, mas o PR não passa sem as duas traduções.
11. **Backend** — `starts/<id>.yaml` gravado sem `conflict`/`mission` quando os
    dois são `null`; com valor, o round trip GET → PUT → GET devolve o mesmo
    texto (teste do lado do backend, no ticket de contrato).

**Nota de escopo sobre o item 11**: já está coberto pelo TCK-056
(`backend/tests/test_builder_doc_write.py`). Não reimplemente do lado do
frontend.

### Inventário da suíte existente

Nenhum teste existente muda de asserção. O que muda é **preparação**: com
`conflict`/`mission` não-opcionais, todo literal de `StartDoc` dentro de um
objeto tipado `BuilderDraft` precisa dos dois campos, senão o `tsc -b` falha.
Acrescente `conflict: null, mission: null` (nada mais) em:

| Arquivo | Literal |
|---|---|
| `frontend/src/components/builder/StartsTab.test.tsx` | `baseDraft():23`, e os starts inline em `:113`, `:175`, `:255` |
| `frontend/src/builder/validate.test.ts` | `draft():6`, literal do start em `:19` (retorno anotado `BuilderDraft`) |
| `frontend/src/components/builder/BuilderPreview.test.tsx` | os dois starts do `draft()` em `:41` e `:51` |
| `frontend/src/components/builder/CharactersTab.test.tsx` | `baseDraft():27` |
| `frontend/src/components/builder/IdentityTab.test.tsx` | `baseDraft():27` |
| `frontend/src/components/builder/MediaTab.test.tsx` | o start literal em `:47` |
| `frontend/src/components/builder/WorldTab.test.tsx` | `baseDraft():27` |

Verificado por Grep de `opening_scene:` em `frontend/src`: essa é a lista
completa de literais de start. Dois casos que **não** entram:

- `frontend/src/screens/BuilderEditorScreen.test.tsx:24` — o `DOCUMENT` é um
  literal sem anotação de tipo, servido como corpo `unknown` de
  `jsonResponse`, então o `tsc -b` não exige os campos. Não toque no arquivo (e
  ele não está em `files`). Se algum dia ganhar anotação, entra na lista.
- `frontend/src/components/builder/StartsTab.tsx:156` — não é fixture, é o
  `newStart` de produção, e está no escopo do item 7.

Testes existentes que continuam verdes sem edição de asserção, e por quê:
- `StartsTab.test.tsx:195` (`blanking play_guide down to whitespace saves it as
  null`) usa `getByLabelText(new RegExp(t('builder.starts.playGuide')))` — o
  rótulo do guia de jogo não é prefixo dos rótulos novos (`Conflict` /
  `Player mission` em `en`), então a regex continua casando um elemento só.
  **Ao consultar os campos novos nos testes**: os rótulos carregam o sufixo
  `(optional)` / `(opcional)`, então `getByLabelText` com string exata **não**
  casa. Use `new RegExp(t('builder.starts.conflict'))` e
  `new RegExp(t('builder.starts.mission'))`, pelo mesmo motivo do `play_guide`
  em `StartsTab.test.tsx:200`; nenhuma dessas regex casa dois campos.
  Duplicação consciente e temporária: `builder.starts.mission` tem o mesmo
  texto visível de `builder.world.mission` (`strings.ts:247` / `:700`) até o
  TCK-058 remover o par da aba Mundo; as abas nunca renderizam juntas.
- `StartsTab.test.tsx:89` (`creating a start ... copies the default HUD`)
  continua valendo: o HUD é herdado, os dois campos novos não.
- `validate.test.ts:47` (`returns no errors for a coherent document`) continua
  em `[]` porque nenhuma regra nova é adicionada.
- Todos os testes de `BuilderPreview.test.tsx`, `CharactersTab.test.tsx`,
  `IdentityTab.test.tsx`, `MediaTab.test.tsx` e `WorldTab.test.tsx`: só o
  fixture muda; nenhuma asserção toca os campos novos.

Falha: não há caminho de erro novo nesta aba.

## Rollout e kill switch

N/A. Sem flag: são dois campos opcionais de formulário, sem estado persistido
próprio e sem chamada de rede nova. Reverter o commit devolve a aba ao estado
anterior; o texto já gravado em `starts/*.yaml` continua válido para o backend
(TCK-056) e volta a sobreviver por `updateStart` sem aparecer na tela.

`risk: low`: superfície pequena, sem rede, sem migração, e o `tsc -b` prova que
nenhum literal de start ficou para trás.

## Observabilidade

Eventos: nenhum evento novo. O salvar já emite `builder_doc_saved`
(`backend/app/builder_doc.py:302`) com `files_written`, e o efeito no jogo
aparece em `game_turn` com `prompt_version=8` (TCK-056).
Métrica de sucesso: cenário editado só pelo builder passa a ter `conflict` e
`mission` no `starts/<id>.yaml` — ou seja, `files_written` de um save que só
mexeu nesses campos é 1 (o arquivo do start), sem nenhum `builder_doc_invalid`
depois.

## i18n

*(Tabela fechada pelo design-specialist, copiada literalmente.)*

Todas as chaves ficam no bloco `builder.starts.*` de `frontend/src/strings.ts`,
inseridas logo depois de `builder.starts.openingScene.hint` e antes de
`builder.starts.playGuide`, nos **dois** dicionários (`en` e `pt-br`).

### Chaves novas

| Chave | en | pt-br |
|---|---|---|
| `builder.starts.conflict` | `Conflict` | `Conflito` |
| `builder.starts.conflict.hint` | `The conflict of this start. Optional, and it goes to the narrator only — the player never sees it.` | `O conflito deste start. Opcional, e vai só para o narrador — o jogador não vê.` |
| `builder.starts.mission` | `Player mission` | `Missão do jogador` |
| `builder.starts.mission.hint` | `What the player is chasing in this start. Optional, and it goes to the narrator only — the player never sees it.` | `O que o jogador persegue neste start. Opcional, e vai só para o narrador — o jogador não vê.` |

### Chaves reaproveitadas (nenhuma mudança)

`common.optional`, `builder.detail.selected`, `builder.editor.tab.dirty`,
`builder.editor.saved`, `builder.editor.save.error.*`.

### Chaves removidas

Nenhuma neste tema. As remoções (`builder.world.conflict`,
`builder.world.mission` e hints) são do TEMA 2 (TCK-058).

### Regra

Nenhuma string literal no componente: rótulo, hint e qualquer texto novo passam
por `t(...)`. Chave que entrar em `en` e faltar em `pt-br` quebra o `tsc -b`
(`Record<StringKey, string>`) e o teste de paridade de chaves — é defeito do PR,
não pendência.
