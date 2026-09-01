---
id: TCK-045
title: Criar, duplicar e deletar cenario pela lista do builder
status: done
points: 3
blockedBy: [TCK-035]
files:
  - frontend/src/api.ts
  - frontend/src/strings.ts
  - frontend/src/screens/BuilderListScreen.tsx
  - frontend/src/screens/BuilderListScreen.test.tsx
  - frontend/src/screens/builder.css
  - frontend/src/test-setup.ts
migration: false
ui: true
risk: medium
---

## Problema

A lista do builder existe (TCK-035) e é só leitura. Sem criar cenário pela UI,
o critério de verde da fase ("crio um cenário novo inteiro pela UI") morre no
primeiro passo, e a única saída continua sendo `mkdir` na mão.

## Escopo

Dentro:
- Formulário de criação acima da lista, com slug automático e validação.
- Diálogos modais de duplicar e deletar, com confirmação por digitação no
  destrutivo.
- `createBuilderScenario`, `duplicateBuilderScenario`, `deleteBuilderScenario`
  em `api.ts`.
- Polyfill de `HTMLDialogElement` em `frontend/src/test-setup.ts`.
- Ação do estado vazio (`builder.list.empty.action`).
- Chaves i18n de criar/duplicar/deletar.

Fora (explícito):
- Renomear pasta (o backend não expõe; duplicar + deletar cobre).
- Import/export `.zip` (Fase 8).
- Qualquer tela de edição.

## Comportamento esperado

A pessoa cria um cenário informando nome, pasta e idioma; ao dar certo, a tela
navega direto para `#/builder/{id}/identity`. Duplica informando a pasta nova.
Deleta depois de digitar o nome da pasta. Erro nunca fecha o diálogo sem
explicação, e erro na lista não impede criar.

## Detalhes técnicos

### Criar

`section.builder-create` acima da lista, com campo nome (obrigatório,
`maxLength` 80), campo pasta (hint `builder.create.folderHint`) e select de
idioma (default = `locale` do app, de `i18n.ts`). O formulário aparece
habilitado mesmo enquanto a lista carrega ou falha — criar não depende da
lista.

A pasta é preenchida por slug do nome **enquanto a pessoa não editar a pasta**;
depois disso para de seguir. Slug: minúsculas, `NFD` + remoção de diacríticos,
não-alfanumérico vira `-`, colapsa `-` repetido, corta `-` das pontas, limita a
64 caracteres. Extraia isso como `slugify` no próprio arquivo da tela e exporte
— o TCK-049 precisa da mesma função para semear backgrounds a partir de
`hud.location`.

Validação no cliente antes do POST: nome vazio →
`builder.create.error.nameRequired`; pasta vazia ou fora de `^[a-z0-9-]+$` →
`builder.create.error.invalidFolder`; pasta já na lista →
`builder.create.error.duplicate` com `{folder}`. A mensagem vai num
`<p role="alert">` ligado por `aria-describedby`, o input ganha
`aria-invalid="true"` e recebe foco.

409 do servidor → mesma mensagem de duplicata. Qualquer outro erro →
`builder.create.error.failed` num `ErrorState` abaixo do form. Sucesso: anuncia
`builder.create.success` na região live que o TCK-035 já criou e navega para
`#/builder/{id}/identity`.

Submit desabilitado durante o envio, com `aria-busy` e rótulo
`builder.create.submitting`.

### Duplicar e deletar

Os dois usam `<dialog>` nativo com `showModal()`, `aria-labelledby` no título,
`Esc` fecha, foco inicial no controle não destrutivo e foco de volta no botão
que abriu. Nunca `window.confirm`. Os botões ficam no
`div.builder-card-actions` que o TCK-035 já deixou no cartão, **fora** da
âncora (nunca aninhados), com o nome do cenário no `aria-label`
(`builder.duplicate.title`, `builder.delete.title`). Item inválido também os
tem: copiar e apagar pasta quebrada é seguro e necessário.

Duplicar: campo único de pasta nova, pré-preenchido com `{folder}-copy` e
desconflitado contra a lista carregada (`-copy-2`, `-copy-3`…). Sucesso: fecha,
insere o cartão, anuncia `builder.duplicate.success`. Erro:
`builder.duplicate.error` dentro do diálogo, sem fechar.

Deletar: corpo `builder.delete.body` com `{folder}`, e confirmação por digitação
(`builder.delete.confirmLabel`) — o botão destrutivo só habilita com match
exato do nome da pasta. Sucesso: remove o cartão, anuncia
`builder.delete.success`, foco vai para o `h1`. Erro: `builder.delete.error`
dentro do diálogo.

`<dialog>` em jsdom não implementa `showModal`/`close`. Acrescente ao
`frontend/src/test-setup.ts` um polyfill mínimo (define
`HTMLDialogElement.prototype.showModal` e `.close` alternando o atributo
`open`), condicionado a `typeof HTMLDialogElement !== 'undefined'` e a métodos
ainda ausentes. O componente **não** muda por causa do ambiente de teste.

### API

```ts
export function createBuilderScenario(body: { folder: string; name: string; locale: string }): Promise<BuilderScenarioItem>
export function duplicateBuilderScenario(id: string, folder: string): Promise<BuilderScenarioItem>
export function deleteBuilderScenario(id: string): Promise<void>
```

`deleteBuilderScenario` responde 204 sem corpo: **não** pode passar pelo helper
`request<T>`, que faz `response.json()`. Faça um `fetch` próprio que checa
`response.ok` e lança `ApiError` com o `detailOf` já existente.

### Responsividade

`@media (max-width: 480px)`: ações secundárias em linha própria abaixo do meta,
44px de altura, diálogos em largura total com margem de `1rem`.

## Contrato público

```ts
// frontend/src/screens/BuilderListScreen.tsx
export function slugify(value: string): string
```

Consumidor: TCK-049 (semeia chaves de background a partir de `hud.location`).

## Acceptance criteria

- [ ] Digitar o nome preenche a pasta por slug; editar a pasta congela o
      auto-preenchimento.
- [ ] Criar com pasta já na lista mostra a mensagem de duplicata sem POST.
- [ ] Criar com sucesso navega para `#/builder/{id}/identity`.
- [ ] Duplo clique no submit dispara um único POST.
- [ ] Duplicar pré-preenche `{folder}-copy` desconflitado e insere o cartão
      novo.
- [ ] Deletar só habilita o botão destrutivo com o nome da pasta digitado
      exatamente; ao concluir, o foco vai para o `h1`.
- [ ] Erro na lista mantém o formulário de criação usável.
- [ ] `Esc` fecha os diálogos e devolve o foco ao gatilho.
- [ ] `strings.en` e `strings['pt-br']` seguem com as mesmas chaves.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente que muda de preparação: `BuilderListScreen.test.tsx` (TCK-035)
ganha casos; as asserções existentes ficam como estão — o formulário e os botões
são conteúdo adicional, e nenhum teste da lista afirma ausência deles. Se algum
teste do TCK-035 afirmar "não existe botão X", ele é adaptado na preparação
(consulta mais específica), nunca no que afere. `i18n.test.ts` cobre as chaves
novas sem alteração.

Cenários novos:
- Feliz: criar → POST com `{folder, name, locale}` → hash vira
  `#/builder/novo/identity`.
- Feliz: duplicar → POST no endpoint de duplicate → cartão novo na lista.
- Feliz: deletar com o nome digitado → DELETE → cartão some.
- Borda: `slugify('Ação na Escola!')` → `acao-na-escola`.
- Borda: `-copy` já existente na lista sugere `-copy-2`.
- Borda: estado vazio com ação move o foco para o campo nome.
- Falha: POST 409 → mensagem de duplicata no campo pasta, sem navegar.
- Falha: DELETE 500 → `builder.delete.error` dentro do diálogo, cartão intacto.
- Falha: duplicar com pasta inválida → `builder.create.error.invalidFolder`
  reaproveitada no diálogo.

## Rollout e kill switch

Com `flags.builder: false` no backend, as rotas de escrita de **documento e
mídia** respondem 503 (TCK-043/TCK-044); as rotas de pasta do TCK-030 não são
gateadas, então esta tela continua funcionando com a flag desligada. É
deliberado: criar e apagar pasta não sobrescreve trabalho autoral, que é o que
a flag protege. `risk: medium` pelo diálogo de deletar, mitigado pela
confirmação por digitação.

## Observabilidade

Eventos: nenhum no frontend; o backend emite `builder_scenario_created`,
`_duplicated` e `_deleted` (TCK-030).
Métrica de sucesso: criar um cenário pela tela e ele aparecer na lista ao
recarregar a página.

## i18n — chaves novas

| chave | en | pt-br |
|---|---|---|
| `builder.list.empty.action` | `Create a scenario` | `Criar um cenário` |
| `builder.create.heading` | `New scenario` | `Novo cenário` |
| `builder.create.nameLabel` | `Name` | `Nome` |
| `builder.create.namePlaceholder` | `The name players see` | `O nome que o jogador vê` |
| `builder.create.folderLabel` | `Folder` | `Pasta` |
| `builder.create.folderHint` | `Folder name inside scenarios/. Lowercase letters, numbers and hyphens.` | `Nome da pasta dentro de scenarios/. Letras minúsculas, números e hífens.` |
| `builder.create.localeLabel` | `Scenario language` | `Idioma do cenário` |
| `builder.create.submit` | `Create scenario` | `Criar cenário` |
| `builder.create.submitting` | `Creating…` | `Criando…` |
| `builder.create.error.nameRequired` | `Give the scenario a name.` | `Dê um nome ao cenário.` |
| `builder.create.error.invalidFolder` | `Use only lowercase letters, numbers and hyphens.` | `Use só letras minúsculas, números e hífens.` |
| `builder.create.error.duplicate` | `The folder {folder} already exists. Pick another one.` | `A pasta {folder} já existe. Escolha outra.` |
| `builder.create.error.failed` | `Couldn't create the scenario. Nothing was written to disk — try again.` | `Não consegui criar o cenário. Nada foi escrito no disco — tente de novo.` |
| `builder.create.success` | `Scenario {name} created` | `Cenário {name} criado` |
| `builder.duplicate.action` | `Duplicate` | `Duplicar` |
| `builder.duplicate.title` | `Duplicate {scenario}` | `Duplicar {scenario}` |
| `builder.duplicate.body` | `Copies the whole folder, media included.` | `Copia a pasta inteira, mídia incluída.` |
| `builder.duplicate.folderLabel` | `New folder` | `Nova pasta` |
| `builder.duplicate.submit` | `Duplicate` | `Duplicar` |
| `builder.duplicate.submitting` | `Duplicating…` | `Duplicando…` |
| `builder.duplicate.success` | `{scenario} duplicated into {folder}` | `{scenario} duplicado em {folder}` |
| `builder.duplicate.error` | `Couldn't duplicate. The original folder wasn't touched — try again.` | `Não consegui duplicar. A pasta original não foi tocada — tente de novo.` |
| `builder.delete.action` | `Delete` | `Deletar` |
| `builder.delete.title` | `Delete {scenario}?` | `Deletar {scenario}?` |
| `builder.delete.body` | `The whole scenarios/{folder} folder goes away, media included. Sessions already played keep their history but stop opening.` | `A pasta scenarios/{folder} inteira vai embora, mídia incluída. Sessões já jogadas guardam o histórico, mas param de abrir.` |
| `builder.delete.confirmLabel` | `Type {folder} to confirm` | `Digite {folder} para confirmar` |
| `builder.delete.submit` | `Delete scenario` | `Deletar cenário` |
| `builder.delete.submitting` | `Deleting…` | `Deletando…` |
| `builder.delete.success` | `{scenario} deleted` | `{scenario} deletado` |
| `builder.delete.error` | `Couldn't delete the folder. Nothing was removed — check that no other program has the files open.` | `Não consegui deletar a pasta. Nada foi removido — veja se outro programa está com os arquivos abertos.` |
