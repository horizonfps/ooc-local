---
id: TCK-046
title: Salvar, recarregar e guardar a saida do editor de cenario
status: done
points: 3
blockedBy: [TCK-036, TCK-043]
files:
  - frontend/src/api.ts
  - frontend/src/strings.ts
  - frontend/src/useUnsavedGuard.ts
  - frontend/src/useUnsavedGuard.test.ts
  - frontend/src/screens/BuilderEditorScreen.tsx
  - frontend/src/screens/BuilderEditorScreen.test.tsx
  - frontend/src/screens/builderEditor.css
migration: false
ui: true
risk: high
---

## Problema

O shell do editor (TCK-036) carrega o cenário e mantém um rascunho que **não vai
para lugar nenhum**. Falta o ciclo que fecha a edição: salvar, tratar o arquivo
alterado por fora, recarregar do disco e impedir que a pessoa saia perdendo
trabalho.

É o ponto do builder que sobrescreve arquivo autoral, então é onde o kill switch
da fase precisa estar visível na tela.

## Escopo

Dentro:
- Botão de save na topbar, indicador `builder.editor.saving`, atalho Ctrl+S/Cmd+S.
- `PUT` com `revision`, diálogo de conflito 409 com recarregar/sobrescrever,
  tratamento de 503 (kill switch) e de 500.
- Painel de validação bloqueando o save, com salto para a aba e o campo.
- Reload do disco, com confirmação quando sujo.
- `useUnsavedGuard(dirty, opts)` cobrindo fechar a aba e navegação por hash.
- Chaves i18n de save/conflito/reload/saída/validação.

Fora (explícito):
- Merge de conflito: a UI só oferece recarregar ou sobrescrever.
- Conteúdo das abas e regras de campo (TCK-037, 047, 038, 048).
- Autosave.

## Comportamento esperado

Salvar grava e o indicador volta para "Tudo salvo". Salvar com o arquivo
alterado por fora abre o diálogo de conflito, e **nenhuma** das opções é
escolhida sozinha — perder edição sem escolher é o único desfecho inaceitável
aqui. Recarregar relê o disco (confirmando antes se houver rascunho). Sair com
rascunho pendente sempre pergunta.

Com o builder desligado por flag no backend, salvar responde 503 e a tela diz
isso com todas as letras, em vez de mostrar um erro genérico.

## Detalhes técnicos

### Save

`PUT /api/builder/scenarios/{id}` com o documento inteiro + `revision`
(TCK-043).

- Antes de enviar, roda `validateDraft` (TCK-036, ampliado pelas abas). Falhou:
  nada é enviado; painel `role="alert"` no topo do painel ativo, com
  `builder.editor.validation.summaryTitle`, uma lista de links
  `builder.editor.validation.jump` que troca de aba e foca o campo, e o resumo
  `builder.editor.save.error.validationOne`/`...validationOther`. O foco vai
  para o painel.
- Sucesso: `loaded = draft`, `revision` novo, anúncio `builder.editor.saved` com
  `{folder}` na região live, botão de save desabilitado. Sem toast que some
  sozinho — o indicador da topbar já é o feedback permanente.
- 409: diálogo com `builder.editor.save.error.conflict.title`/`.body`,
  `builder.editor.conflict.reload` (descarta o rascunho e relê),
  `builder.editor.conflict.overwrite` (reenvia com `force: true`) e
  `common.cancel` (foco inicial).
- 503: `ErrorState` com `builder.editor.save.error.disabled.title`/`.body`, sem
  retry automático — a flag está desligada no `config.yaml` e reenviar não muda
  nada.
- Outra falha: `ErrorState` acima do painel com
  `builder.editor.save.error.title`/`.body` e `onRetry`. O rascunho continua
  intacto na tela; o corpo diz para recarregar do disco antes de tentar de novo,
  porque um 500 pode ter gravado parte dos arquivos (declarado no TCK-043).
- O botão fica desabilitado quando limpo ou salvando, com `aria-busy`, e a
  topbar mostra `builder.editor.saveShortcut`.
- Ctrl+S / Cmd+S salvam de qualquer lugar do editor, com `preventDefault()` para
  não abrir o "salvar página" do browser.

### Reload

Botão `builder.editor.reload`. Limpo: relê e anuncia
`builder.editor.reloaded`. Sujo: confirma antes com
`builder.editor.reload.confirmTitle`/`.confirmBody`/`.confirmSubmit` +
`common.cancel`. É o teste vivo de "o arquivo é a fonte da verdade": editar o
YAML por fora, clicar aqui e ver o campo mudar.

### Guard de saída

```ts
export function useUnsavedGuard(dirty: boolean, opts: {
  scenarioId: string
  onSave: () => Promise<void>
  onDiscard: () => void
}): void
```

Um hook só, cobrindo:

1. `beforeunload` com `preventDefault()` quando `dirty` (o texto é do browser,
   sem string nossa).
2. Navegação interna por hash: intercepta o `hashchange`, guarda o destino,
   restaura o hash anterior com `location.replace` (sem empilhar histórico) e
   abre o diálogo `builder.editor.leave.title`/`.body` com
   `builder.editor.leave.stay` (foco inicial),
   `builder.editor.leave.saveAndLeave` e `builder.editor.leave.discard`.
3. Troca de aba dentro do editor **nunca** bloqueia: o hook ignora destino que
   case `#/builder/{scenarioId}/{qualquer aba}`.

Armadilha: o `useHashRoute` também escuta `hashchange`. Restaurar o hash no
guard não pode gerar loop — compare o hash restaurado antes de agir e ignore o
evento cujo `location.hash` já é o esperado. O botão físico de voltar do browser
cai no caso 2.

O botão `builder.editor.back` da topbar (TCK-036) passa a navegar por hash e
portanto passa pelo guard sem código extra.

### API

```ts
export function saveScenarioDocument(id: string, doc: ScenarioDocument, force?: boolean): Promise<{ revision: string }>
```

Trate 409 e 503 **sem** passar pelo `classifyError` genérico: os dois têm
tratamento próprio nesta tela (o `classifyError` mapeia 503 para
`error.chatDisabled`, que aqui seria mentira).

## Contrato público

```ts
// frontend/src/useUnsavedGuard.ts
export function useUnsavedGuard(dirty: boolean, opts: { scenarioId: string; onSave: () => Promise<void>; onDiscard: () => void }): void
// frontend/src/api.ts
export function saveScenarioDocument(id: string, doc: ScenarioDocument, force?: boolean): Promise<{ revision: string }>
```

Consumidor: TCK-041 (o preview chama o `onSave` do shell em
`builder.preview.saveAndRestart`).

## Acceptance criteria

- [ ] Save com sucesso desabilita o botão e anuncia o caminho salvo.
- [ ] Save com 409 abre o diálogo; "sobrescrever" reenvia com `force: true`;
      "recarregar" descarta e relê; cancelar não faz nada.
- [ ] Save com 503 mostra a mensagem de builder desligado, sem retry.
- [ ] Save com 500 mostra o erro e mantém o rascunho na tela.
- [ ] Validação falhando não envia nada e o link do painel leva à aba e ao
      campo.
- [ ] Reload com rascunho pendente pede confirmação; cancelar mantém o rascunho.
- [ ] Sair com rascunho pendente abre o diálogo; "continuar editando" mantém o
      hash original.
- [ ] Trocar de aba nunca abre o diálogo de saída.
- [ ] Ctrl+S salva e não abre o diálogo do browser.
- [ ] `strings.en` e `strings['pt-br']` seguem com as mesmas chaves.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente que muda de preparação: `BuilderEditorScreen.test.tsx`
(TCK-036) ganha casos; as asserções existentes ficam como estão — o botão de
save e o de reload são conteúdo adicional na topbar, que o TCK-036 já deixou
como slot vazio. Se algum teste do TCK-036 afirmar a ausência do botão de save,
ele é adaptado na preparação, nunca no que afere.

Cenários novos:
- `useUnsavedGuard.test.ts` — feliz: hash para fora com `dirty` restaura o hash
  e sinaliza o diálogo; borda: hash para outra aba do mesmo cenário passa
  direto; borda: `dirty: false` não intercepta nada; borda: `beforeunload` só
  chama `preventDefault` quando sujo; borda: remover o listener no unmount.
- `BuilderEditorScreen.test.tsx` — feliz: editar e salvar manda `PUT` com o
  `revision` recebido e volta a limpo; feliz: Ctrl+S salva; falha: 409 abre o
  diálogo e "sobrescrever" reenvia com `force: true`; falha: 503 mostra a
  mensagem de flag desligada; falha: 500 mantém o rascunho; borda: validação
  estrutural bloqueia o save e o link salta para a aba Starts; borda: reload
  sujo pede confirmação e, confirmado, refaz o `GET`.

## Rollout e kill switch

Kill switch: `flags.builder` em `~/.ooc-local/config.yaml`
(`flags: {builder: false}`), lido por `Config.flag("builder")` no backend
(TCK-043/TCK-044), default **on**, sem restart. Desligado, o `PUT` responde 503
e esta tela mostra `builder.editor.save.error.disabled.*` — a edição continua
possível na tela, mas nada é gravado, e a pessoa sabe por quê.

`risk: high` porque é a tela que dispara escrita em arquivo autoral. As
mitigações: save explícito (sem autosave), `revision`/409 do TCK-043, bloqueio
de save enquanto a validação falha, guard de saída nas três frentes e a flag
acima.

## Observabilidade

Eventos: nenhum no frontend; o backend emite `builder_doc_saved`,
`builder_doc_conflict` e `builder_rejected` (TCK-043).
Métrica de sucesso: editar um campo, salvar, abrir o YAML no editor de texto e
ver a mudança — e o inverso, editar por fora, recarregar e ver a tela mudar.

## i18n — chaves novas

| chave | en | pt-br |
|---|---|---|
| `builder.editor.save` | `Save` | `Salvar` |
| `builder.editor.saving` | `Saving…` | `Salvando…` |
| `builder.editor.saved` | `Saved to scenarios/{folder}` | `Salvo em scenarios/{folder}` |
| `builder.editor.saveShortcut` | `Ctrl+S saves` | `Ctrl+S salva` |
| `builder.editor.save.error.title` | `Couldn't save` | `Não consegui salvar` |
| `builder.editor.save.error.body` | `Part of the files may have been written. Reload from disk before trying again.` | `Parte dos arquivos pode ter sido escrita. Recarregue do disco antes de tentar de novo.` |
| `builder.editor.save.error.disabled.title` | `Saving is turned off` | `Salvar está desligado` |
| `builder.editor.save.error.disabled.body` | `The builder flag is off in ~/.ooc-local/config.yaml. Turn it on to write to disk again.` | `A flag builder está desligada em ~/.ooc-local/config.yaml. Ligue de novo para gravar no disco.` |
| `builder.editor.save.error.validationOne` | `1 field needs fixing before saving.` | `1 campo precisa de conserto antes de salvar.` |
| `builder.editor.save.error.validationOther` | `{count} fields need fixing before saving.` | `{count} campos precisam de conserto antes de salvar.` |
| `builder.editor.save.error.conflict.title` | `The files changed on disk` | `Os arquivos mudaram no disco` |
| `builder.editor.save.error.conflict.body` | `scenarios/{folder} was edited outside the app after you opened it. Reload to take the disk version, or overwrite to keep what's on this screen.` | `scenarios/{folder} foi editado fora do app depois que você abriu. Recarregue para ficar com a versão do disco, ou sobrescreva para manter o que está nesta tela.` |
| `builder.editor.conflict.reload` | `Reload and lose my edits` | `Recarregar e perder minhas edições` |
| `builder.editor.conflict.overwrite` | `Overwrite the files` | `Sobrescrever os arquivos` |
| `builder.editor.reload` | `Reload from disk` | `Recarregar do disco` |
| `builder.editor.reload.confirmTitle` | `Discard your unsaved changes?` | `Descartar suas mudanças não salvas?` |
| `builder.editor.reload.confirmBody` | `Reloading reads the files again and throws away what you edited here.` | `Recarregar lê os arquivos de novo e joga fora o que você editou aqui.` |
| `builder.editor.reload.confirmSubmit` | `Reload and discard` | `Recarregar e descartar` |
| `builder.editor.reloaded` | `Reloaded from disk` | `Recarregado do disco` |
| `builder.editor.leave.title` | `Leave without saving?` | `Sair sem salvar?` |
| `builder.editor.leave.body` | `{scenario} has unsaved changes. They only exist in this tab.` | `{scenario} tem mudanças não salvas. Elas só existem nesta aba.` |
| `builder.editor.leave.stay` | `Keep editing` | `Continuar editando` |
| `builder.editor.leave.saveAndLeave` | `Save and leave` | `Salvar e sair` |
| `builder.editor.leave.discard` | `Leave and discard` | `Sair e descartar` |
| `builder.editor.validation.summaryTitle` | `Fix these before saving` | `Conserte isto antes de salvar` |
| `builder.editor.validation.jump` | `Go to {field}` | `Ir para {field}` |

## Ressalva registrada na wave 4

- O PUT do TCK-043 serializa YAML em forma canonica: o primeiro save de cenario escrito a mao reescreve os arquivos e muda o revision sem edicao do usuario. Use SEMPRE o revision retornado pelo PUT como novo baseline do rascunho; nunca compare com o revision do GET anterior ao save.
