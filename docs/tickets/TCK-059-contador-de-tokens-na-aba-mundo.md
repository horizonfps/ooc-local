---
id: TCK-059
title: Mostrar contador de tokens estimados na aba Mundo
status: done
points: 2
blockedBy: [TCK-058]
files:
  - frontend/src/components/builder/WorldTab.tsx
  - frontend/src/components/builder/WorldTab.test.tsx
  - frontend/src/strings.ts
  - frontend/src/screens/builderEditor.css
migration: false
ui: true
risk: low
---

## Problema

O `world.md` inteiro entra no system prompt em **todo** turno
(`backend/app/prompt.py:269`, seção `## MUNDO`) e divide um orçamento fixo com a
cena, o elenco e o histórico: `CONTEXT_BUDGET_TOKENS = 24_000`
(`backend/app/compact.py:9`), menos a reserva de saída
(`compact.py:13`). Quanto maior o mundo, menos sobra para o resumo da campanha e
para o histórico recente — e o autor não tem como saber disso enquanto escreve.

Hoje a aba Mundo não mostra nenhum número. O autor descobre que passou do ponto
quando a narração começa a esquecer o que aconteceu há dez turnos, o que é o
sintoma mais caro e mais difícil de atribuir à causa. Um contador de caracteres
dividido por 4, na tela, transforma isso em informação de escrita.

## Escopo

Dentro:
- Bloco do contador em `WorldTab.tsx`, visível nos **dois** modos (guiado e
  custom), com o total do `world.md` inteiro.
- Constante `WORLD_TOKEN_WARN = 2000` e o aviso brando acima desse limite, numa
  live region.
- Três chaves novas em `strings.ts`, nos dois dicionários.
- CSS do bloco, se necessário para o comportamento responsivo do §9.
- Dois testes em `WorldTab.test.tsx`.

Fora (explícito):
- Bloquear o salvar, marcar a aba como inválida ou produzir qualquer
  `ValidationError`. O aviso é informativo; `frontend/src/builder/validate.ts`
  **não** é tocado (e não está em `files`).
- Contar tokens de qualquer outra coisa: prólogo, cena de abertura, fichas de
  personagem, prompt final. Só `draft.world`.
- Chamar o backend para contar. A fórmula é local, sem rede, sem debounce.
- Blocos de lore, campos guiados, parse/serialização: tudo isso é o TCK-058.
  Este ticket não muda uma linha de `worldMarkdown.ts`.
- Alinhar a estimativa com o tokenizer real do modelo. `Math.ceil(len / 4)` é
  deliberadamente grosseiro e a string diz isso ao usuário.

## Comportamento esperado

*(Seção fechada pelo design-specialist, copiada literalmente do §5 de
`design/tema-2-world-lore-blocks.md`.)*

### 5. Contador de tokens estimados

- Fórmula: `Math.ceil(draft.world.length / 4)`, espelhando `estimate_tokens` de
  `backend/app/compact.py`. Comentário curto no código apontando a origem, como
  já se faz com `MAX_EMOTIONS` em `validate.ts`.
- Constante `WORLD_TOKEN_WARN = 2000` no `WorldTab.tsx`.
- Sempre visível, nos dois modos, com o total do `world.md` inteiro (não só dos
  campos guiados).
- Estrutura:
  - `<p className="field-hint">` com `builder.world.tokens` (`{count}`) e, em
    outro `<p className="field-hint">`, `builder.world.tokens.hint`. Nada de
    concatenar strings traduzidas em JSX.
  - `<p role="status" aria-live="polite">` **sempre presente no DOM**, vazio
    abaixo do limite e com `builder.world.tokens.over` (`{max}`) acima dele.
    Assim o aviso é anunciado uma vez, quando cruza o limite, e o número que
    muda a cada tecla não vira spam de leitor de tela.
- O aviso é brando: texto informativo, sem `role="alert"`, sem
  `aria-invalid`, **não bloqueia o salvar** e não marca a aba como inválida.
- Sem debounce: contar caracteres é barato.

### Posição na tela (§3 do design, item 3)

O bloco é renderizado **uma única vez, fora do `if (mode === 'guided')`**, entre
o banner de fallback e os campos guiados / o textarea custom. Ordem final da
aba: radiogroup de modo → banner de fallback → **contador** → campos guiados
(ou textarea custom).

### Responsividade (§9 do design)

O bloco do contador quebra em duas linhas em telas estreitas; nada de scroll
horizontal em 320px de largura. Menor breakpoint do CSS do builder:
`max-width: 479.98px`.

## Detalhes técnicos

- **Onde encaixar**: no `WorldTab.tsx` **já reestruturado pelo TCK-058**, o
  ponto é entre o bloco `isFallback ? (...) : null` e o ternário
  `mode === 'guided' ? (...) : (...)` — no código de hoje, entre
  `WorldTab.tsx:136` e `WorldTab.tsx:138`. O TCK-058 deixa esse ponto livre de
  propósito, sem placeholder.
- **Fórmula e comentário**: espelha `estimate_tokens`
  (`backend/app/compact.py:49-50`, `math.ceil(len(text) / 4)`). Comentário de
  uma linha, em inglês, apontando a origem — mesmo padrão de `MAX_EMOTIONS`
  (`frontend/src/builder/validate.ts:9-10`, `// Mirrors backend/app/scenario.py
  ...`). Nada além de uma linha.
- **`WORLD_TOKEN_WARN = 2000`** fica no topo do `WorldTab.tsx`, junto de
  `KNOWN_VARIABLES` (`WorldTab.tsx:9`). Não exporte: nada mais consome.
- **Live region sempre no DOM**: renderize
  `<p role="status" aria-live="polite">{over ? t('builder.world.tokens.over', { max: WORLD_TOKEN_WARN }) : ''}</p>`,
  nunca `{over ? <p .../> : null}`. Região que entra e sai do DOM não é
  anunciada de forma confiável; é o motivo de o design pedir "sempre presente".
- **Não confunda com a live region do TCK-058**: aquela é a `visually-hidden` de
  anúncio de bloco de lore adicionado/removido. Esta é visível e tem texto
  próprio. São dois elementos distintos.
- **Sem `useMemo`, sem debounce**: `draft.world.length` é O(1) e o componente já
  re-renderiza a cada tecla.
- **CSS** (`frontend/src/screens/builderEditor.css`, importado por
  `WorldTab.tsx:5`): se precisar de regra, uma classe
  `.builder-world-tokens` junto do bloco `.builder-world-*`
  (`builderEditor.css:535-600`), com `display: flex; flex-wrap: wrap; gap` e a
  variante no `@media (max-width: 479.98px)` já existente
  (`builderEditor.css:523`). Se dois `<p className="field-hint">` empilhados já
  resolverem, **não** crie classe nova e tire `builderEditor.css` do PR.
- **`strings.ts`**: `en` em `strings.ts:1`, `ptBr`
  (`Record<StringKey, string>`) em `strings.ts:455`,
  `StringKey = keyof typeof en` em `strings.ts:453`. As três chaves entram logo
  antes de `builder.world.variables.title` (`strings.ts:251` em `en`,
  `strings.ts:704` em `pt-br`), na mesma ordem nos dois dicionários.

### Por que `blockedBy: [TCK-058]`

Não é dependência de contrato: o contador não importa nada do
`worldMarkdown.ts` e a fórmula só depende de `draft.world`. É dependência de
**estrutura do arquivo**. O TCK-058 reescreve o corpo do `WorldTab.tsx` (remove
dois campos de `GUIDED_FIELDS`, acrescenta o `fieldset` de lore, a nota do §6, a
live region e os handlers), e a posição de inserção do contador — item 3 do §3
do design — fica no meio dessa reescrita. Implementar sobre o `WorldTab.tsx`
antigo produz conflito de merge garantido no mesmo hunk, e um contador colocado
numa árvore que vai ser reorganizada. Os dois também colidem em `strings.ts`,
`WorldTab.test.tsx` e `builderEditor.css`: a ordem resolve todos de uma vez.

## Contrato público

N/A — nada é exportado para outro ticket. `WORLD_TOKEN_WARN` é constante de
módulo, não exportada, e as três chaves de i18n são consumidas só pelo próprio
`WorldTab.tsx`.

O que este ticket **consome** é a seção "Contrato público" do TCK-058, na parte
que descreve a estrutura do `WorldTab.tsx` reestruturado: o bloco entra depois
do banner de fallback e antes do ramo `mode === 'guided' ? ... : ...`, com
`draft.world` disponível no escopo do componente.

## Acceptance criteria

- [ ] O contador aparece em modo guiado **e** em modo custom, com
      `Math.ceil(draft.world.length / 4)` interpolado em
      `builder.world.tokens`.
- [ ] O hint `builder.world.tokens.hint` aparece num `<p>` próprio, sem
      concatenação de strings traduzidas.
- [ ] O elemento `role="status" aria-live="polite"` existe no DOM mesmo abaixo
      do limite, com texto vazio.
- [ ] Acima de 2 000 tokens estimados, esse elemento passa a conter
      `builder.world.tokens.over` com `{max}` = 2000.
- [ ] O aviso não tem `role="alert"` nem `aria-invalid`, o botão Salvar continua
      habilitado e `validateDraft` não ganha nenhum erro novo.
- [ ] As três chaves existem em `en` e em `pt-br`, com os textos da tabela.
- [ ] `npm run check` verde (`tsc -b` + `vitest run` + pytest).

## Cenários de teste

*(Casos 27 e 28 da lista fechada pelo design-specialist, copiados
literalmente. A numeração original do design foi preservada.)*

### `frontend/src/components/builder/WorldTab.test.tsx`

27. **Contador aparece nos dois modos** — em guiado e em custom, o texto `builder.world.tokens` com o número certo (`Math.ceil(len/4)`) está na tela.
28. **Aviso de orçamento cruza o limite** — `world.md` com 7 000 caracteres (≈1 750 tokens): a live region do contador está vazia. Digitar até passar de 2 000 tokens: o texto `builder.world.tokens.over` aparece dentro de um elemento com `aria-live="polite"`, e o botão Salvar **não** fica desabilitado por causa disso.

Notas de implementação dos dois casos, para não improvisar:
- O `Harness` do arquivo (`WorldTab.test.tsx:38-48`) renderiza só a `WorldTab` e
  os `<pre>` de debug — **não** tem botão Salvar. Para a parte "o Salvar não
  fica desabilitado", afira o equivalente disponível no nível certo:
  `validateDraft(draft)` não produz nenhum erro com `tab === 'world'`. Não monte
  a `BuilderEditorScreen` só para isso.
- Caso 27 em modo custom: `draft.meta.world_mode = 'custom'`, como já se faz em
  `WorldTab.test.tsx:66-68`.
- Caso 28: comece com `'x'.repeat(7000)` em `draft.world` (1 750 tokens, abaixo
  do limite) e `fireEvent.change` no textarea custom com `'x'.repeat(9000)`
  (2 250 tokens). Assim o teste exercita a transição, que é o que a live region
  promete, e não só o estado final.

### Inventário da suíte existente

Nenhum teste existente muda de asserção nem de preparação. Verificado arquivo a
arquivo:

- `frontend/src/components/builder/WorldTab.test.tsx` (8 testes hoje, mais os do
  TCK-058): todos usam `getByLabelText`, `getByRole` e `getByText` de strings
  específicas, e nenhum conta elementos da aba nem usa `getAllBy*` amplo que um
  `<p>` novo pudesse desequilibrar. O arquivo é tocado só para **acrescentar**
  os casos 27 e 28.
- `frontend/src/builder/validate.test.ts`: não é editado. O caso 19 do design
  ("excesso de tokens não é erro", `world.md` com 20 000 caracteres não produz
  `ValidationError`) já foi entregue pelo TCK-058 e continua verde aqui — é
  justamente o teste que prova que este ticket não bloqueia o salvar.
- `frontend/src/i18n.test.ts`: não é editado. O teste
  `strings > has the same keys in en and pt-br` (`i18n.test.ts:78-84`) cobre
  automaticamente as três chaves novas; chave só em `en` quebra antes disso, no
  `tsc -b`, pelo `Record<StringKey, string>`.
- `frontend/src/screens/BuilderEditorScreen.test.tsx`: não é editado. O
  contador não altera contagem de abas inválidas nem o painel de validação.

Falha: não há caminho de erro novo. Sem rede, sem estado persistido, sem
validação.

## Rollout e kill switch

N/A — sem flag. É texto informativo dentro de uma aba já protegida pela flag
`builder` (`backend/app/builder_doc.py:342` devolve 503 no `PUT` quando
desligada). Reverter o commit remove o bloco e não deixa resíduo: nada é gravado
em disco, nada muda no `world.md`, nenhuma chave de configuração é lida.

`risk: low`: superfície de leitura apenas, sem escrita, sem rede, sem efeito no
documento salvo.

## Observabilidade

Eventos: nenhum evento novo — o contador é cliente puro e o projeto não tem
telemetria de frontend.

O número que ele estima já é medido do lado do servidor: `context_budget`
(`backend/app/turn.py`, com `estimated_tokens` calculado por `estimate_tokens`,
`backend/app/compact.py:49`). É por isso que a fórmula tem que ser a mesma:
divergir faz o autor confiar num número que o motor desmente.

Métrica de sucesso: para um mesmo cenário, o valor mostrado na aba Mundo bate
com a parcela do mundo dentro de `context_budget.estimated_tokens` do primeiro
turno (mesma ordem de grandeza, diferença explicada só pelas outras seções do
prompt).

## i18n

*(Tabela fechada pelo design-specialist, copiada literalmente. Nas duas colunas
de valor, aspas simples e crase não fazem parte da string: o valor é o texto
puro.)*

| Chave | en | pt-br |
|---|---|---|
| `builder.world.tokens` | ≈{count} tokens in world.md | ≈{count} tokens no world.md |
| `builder.world.tokens.hint` | Rough estimate: about 4 characters per token. | Estimativa grosseira: cerca de 4 caracteres por token. |
| `builder.world.tokens.over` | Past ~{max} tokens. The whole world goes into the prompt on every turn and shares a limited budget with the scene, the cast and the history. You can still save — just know what you're spending. | Passou de ~{max} tokens. O mundo inteiro entra no prompt em todo turno e divide um orçamento limitado com a cena, o elenco e o histórico. Dá para salvar assim mesmo — só saiba o que está gastando. |

Posição no `strings.ts`: as `builder.world.tokens.*` entram logo antes de
`builder.world.variables.title`, nos dois dicionários, na mesma ordem.

Chaves reaproveitadas: nenhuma além das que já existem na aba. Chaves removidas:
nenhuma.

Regra: nenhuma string literal no componente, e nada de concatenar duas strings
traduzidas em JSX — o contador e o hint são dois `<p>` separados exatamente por
isso.

## Colisão de arquivos declarada

- `frontend/src/components/builder/WorldTab.tsx`, `WorldTab.test.tsx`,
  `strings.ts` e `builderEditor.css`: também são tocados pelo **TCK-058**.
  Resolvido pela dependência (`blockedBy: [TCK-058]`), que põe os dois em waves
  diferentes.
- `frontend/src/strings.ts`: também é tocado pelo **TCK-057**
  (`builder.starts.*`, bloco diferente do arquivo). O coordenador aloca em wave
  separada; os `files` declaram o arquivo real de qualquer forma, para o guard de
  colisão enxergar.
