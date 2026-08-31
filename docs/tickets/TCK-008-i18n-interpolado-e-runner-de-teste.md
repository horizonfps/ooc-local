---
id: TCK-008
title: Interpolar strings de i18n e instalar o runner de teste do frontend
status: in_review
points: 3
blockedBy: []
files:
  - frontend/src/i18n.ts
  - frontend/src/strings.ts
  - frontend/src/i18n.test.ts
  - frontend/src/test-setup.ts
  - frontend/vite.config.ts
  - frontend/tsconfig.app.json
  - frontend/package.json
  - frontend/package-lock.json
  - package.json
migration: false
ui: true
risk: low
---

## Problema

`frontend/src/i18n.ts` é um dicionário flat de quatro chaves com `t(key)` sem
interpolação; a Fase 1 precisa de ~60 chaves, várias com valor dinâmico
(`{count} turnos`, `Turno {index} pronto`). Pior: **o frontend não tem runner de
teste** — `check:web` é `cd frontend && npx tsc -b`
(`package.json:10`) — então parsing de texto do turno, estado de tela e
formatação de plural não teriam como ser aferidos por ninguém.

Este ticket é metade do **interface freeze** de UI da fase (a outra metade é o
TCK-013). Consumidores já enfileirados: TCK-009, TCK-010, TCK-011, TCK-012,
TCK-013, TCK-014.

## Escopo

Dentro:
- `t(key, params?)` com interpolação de `{name}` e chaves em ponto.
- `frontend/src/strings.ts` com **todas** as chaves da Fase 1 já preenchidas em
  `en` e `pt-br` (tabelas na seção ## i18n deste ticket), mais as quatro chaves
  legadas que `frontend/src/App.tsx` ainda usa.
- Tipagem que quebra o `tsc -b` quando `pt-br` não tem uma chave de `en`.
- `intlLocale` exportado para `Intl.*` nas telas.
- Runner de teste: vitest + jsdom + Testing Library + `test-setup.ts`, com
  `check:web` passando a rodar `tsc -b && vitest run`.

Fora (explícito):
- Rotas, componentes de estado e baseline de CSS — TCK-013.
- Qualquer tela: `App.tsx` **não é tocado**; continua sendo o chat de fumaça da
  Fase 0 (quem o reescreve é o TCK-009).
- Biblioteca de i18n (i18next e afins): 60 chaves e dois locales não justificam
  dependência; a tipagem do TypeScript é o mecanismo de completude.
- Pluralização por `Intl.PluralRules`: a Fase 1 tem um caso de plural (turnos) e
  a spec já define três chaves para ele.
- Chaves de fases futuras (stats, builder, endings).

## Comportamento esperado

Do ponto de vista do consumidor (as telas da fase):

- `t('sessions.item.turnsOther', { count: 7 })` devolve `"7 turns"` / `"7
  turnos"`.
- `t('game.documentTitle')` sem params devolve a string com `{scenario}`
  **literal**: placeholder sem valor permanece visível, porque falha visível é
  melhor que string vazia silenciosa.
- Chave inexistente é erro de compilação, não erro de runtime: `StringKey` é
  derivado do dicionário `en` declarado `as const`.
- Chave presente em `en` e ausente em `pt-br` **quebra o `tsc -b`**, porque o
  dicionário `pt-br` é tipado como `Record<StringKey, string>`. Locale
  incompleto vira erro de build, não bug em produção.
- Locale derivado de `navigator.language` (`pt*` → `pt-br`, senão `en`), como
  hoje em `frontend/src/i18n.ts:19`. `intlLocale` devolve `'pt-BR'` ou `'en'`
  para uso em `Intl.RelativeTimeFormat` e afins — nenhuma tela formata número ou
  data à mão.
- `npm run check` (o `verify` do `.claude/pipeline.json`) passa a rodar os testes
  de frontend junto do `tsc` e do pytest, sem mudar o nome do comando.

## Detalhes técnicos

- Interpolação por `replace` de `/\{(\w+)\}/g` consultando `params`: chave
  ausente devolve o match original. Sem `eval`, sem template engine.
- `strings.ts` é um objeto flat com chaves em ponto (`'sessions.empty.title'`),
  não um objeto aninhado: mantém `StringKey` como união de literais e o acesso
  O(1), e é o formato que o `t()` atual já usa.
- Convivência de `error` (chave legada) com `error.offline.title`: são chaves de
  string distintas num objeto flat, sem conflito.
- vitest reusa a config do Vite (`frontend/vite.config.ts`): bloco
  `test: { environment: 'jsdom', globals: true, setupFiles: ['src/test-setup.ts'] }`,
  e `frontend/tsconfig.app.json` ganha `"types": ["vitest/globals",
  "@testing-library/jest-dom"]`.
- Dev deps novas em `frontend/package.json`: `vitest`, `jsdom`,
  `@testing-library/react`, `@testing-library/jest-dom`,
  `@testing-library/user-event`. O `frontend/package-lock.json` **vai no commit**:
  o CI roda `npm ci --prefix frontend` e lock desatualizado quebra o pipeline.
- Raiz: `"check:web": "cd frontend && npx tsc -b && npx vitest run"`
  (`package.json:10`).
- Teste de tipo para a paridade de locales: um arquivo com
  `// @ts-expect-error` sobre um objeto `pt-br` a que falta uma chave. Se a
  tipagem parar de proteger, o `@ts-expect-error` fica sem erro para suprimir e o
  `tsc -b` falha. É a única forma de aferir isso automaticamente.

Testes existentes que este ticket invalida: **nenhum**, e vale dizer com todas as
letras — o frontend não tem teste algum hoje. A assinatura de `t()` muda de
`t(key)` para `t(key, params?)` de forma retrocompatível, então as quatro
chamadas em `App.tsx` continuam compilando sem edição. O backend não é tocado.

## Contrato público

```ts
// frontend/src/strings.ts
const en = { 'app.title': 'ooc-local', /* ...todas as chaves... */ } as const
export type StringKey = keyof typeof en
const ptBr: Record<StringKey, string> = { /* ...as mesmas chaves... */ }
export const strings = { en, 'pt-br': ptBr }

// frontend/src/i18n.ts
export type { StringKey } from './strings'
export type Locale = 'en' | 'pt-br'
export const locale: Locale
export const intlLocale: string                     // 'en' | 'pt-BR'
export function t(key: StringKey, params?: Record<string, string | number>): string
```

`en` é `as const` para `StringKey` ser união de literais; `ptBr` tipado como
`Record<StringKey, string>` é o que faz locale incompleto quebrar o `tsc -b`.

**Tickets consumidores não criam chave nova.** Se faltar alguma, é mudança de
contrato e volta para este ticket.

## Acceptance criteria

- [ ] `t('game.documentTitle', { scenario: 'Escola' })` devolve a string
      interpolada; `t('game.documentTitle')` devolve com `{scenario}` literal.
- [ ] `t('sessions.item.turnsOther', { count: 7 })` interpola número.
- [ ] Params com chave que não aparece na string são ignorados sem erro.
- [ ] Todas as chaves da seção ## i18n existem em `en` e em `pt-br`, com os
      valores das tabelas (teste percorre as duas listas de chaves e compara).
- [ ] O teste de tipo com `// @ts-expect-error` sobre um `pt-br` incompleto
      compila hoje e falharia se a tipagem deixasse de proteger.
- [ ] `navigator.language = 'pt-BR'` → `locale === 'pt-br'` e `intlLocale ===
      'pt-BR'`; `'en-US'` → `'en'` e `'en'`.
- [ ] `npm run check:web` roda `tsc -b` **e** `vitest run`, ambos passando.
- [ ] `frontend/package-lock.json` atualizado no mesmo commit das devDeps novas.
- [ ] `npm run check` verde.

## Verificação manual

Nada aqui é aferível por vitest/jsdom (sem layout) nem por e2e (o
`.claude/pipeline.json` tem `e2e: null`), então fica fora dos ACs e é conferido à
mão antes do merge:

- Rodar `npm run dev` e confirmar que a tela de fumaça continua funcionando com o
  `t()` novo (título, placeholder, botão, mensagem de erro).
- Remover à mão uma chave de `pt-br` em `strings.ts`, rodar `npx tsc -b`,
  confirmar que falha, e desfazer.

## Cenários de teste

- Feliz: `t()` com e sem params, nos dois locales.
- Feliz: paridade de chaves `en` × `pt-br` (nenhuma sobrando dos dois lados).
- Borda: string sem placeholder recebendo params → devolvida intacta.
- Borda: placeholder repetido (`{name} e {name}`) → substituído nas duas
  ocorrências.
- Borda: valor numérico `0` interpolado → `"0"`, nunca string vazia.
- Falha: `t()` com chave inexistente é impedido pelo tipo (não há caminho de
  runtime); documentar isso no teste com `@ts-expect-error`.
- Falha: `navigator.language` indefinido → cai em `en` sem lançar.

## Rollout e kill switch

N/A — nenhuma tela nova. O único efeito externo é o `check:web` passar a rodar
vitest; se o runner der problema no CI, o rollback é reverter o PR e o script
volta a ser só `tsc -b`.

## Observabilidade

Eventos: nenhum. O frontend da Fase 1 não tem canal de telemetria (a telemetria
de turno é do backend, `emit()` em `backend/app/observability.py`) e este ticket
não abre esse canal.
Métrica de sucesso: os tickets TCK-009 a TCK-014 não precisam criar chave de
i18n — se algum precisar, o freeze falhou.

## i18n

Este ticket **é** o ticket de i18n da fase. Todas as chaves abaixo nascem aqui,
nos dois locales, com estes valores exatos.

### Legado da Fase 0 (usadas por `frontend/src/App.tsx` até o TCK-009)

| Chave | en | pt-br |
|---|---|---|
| `title` | ooc-local | ooc-local |
| `placeholder` | Say something... | Diga algo... |
| `send` | Send | Enviar |
| `error` | Error | Erro |

### Shell e comuns

| Chave | en | pt-br |
|---|---|---|
| `app.title` | ooc-local | ooc-local |
| `app.skipToContent` | Skip to content | Pular para o conteúdo |
| `common.retry` | Try again | Tentar de novo |
| `common.cancel` | Cancel | Cancelar |
| `common.back` | Back | Voltar |
| `common.loading` | Loading… | Carregando… |
| `common.details` | Technical details | Detalhes técnicos |
| `error.offline.title` | Can't reach the local server | Não consegui falar com o servidor local |
| `error.offline.body` | The backend at :8000 didn't answer. Check that `npm run dev` is running and try again. | O backend em :8000 não respondeu. Confira se o `npm run dev` está rodando e tente de novo. |
| `error.chatDisabled.title` | Chat is turned off | O chat está desligado |
| `error.chatDisabled.body` | The `chat` flag is off in ~/.ooc-local/config.yaml. Turn it on and restart the server. | A flag `chat` está desligada em ~/.ooc-local/config.yaml. Ligue e reinicie o servidor. |
| `error.unexpected.title` | Something broke on this screen | Alguma coisa quebrou nesta tela |
| `error.unexpected.body` | The action didn't complete. Try again; if it repeats, check the server log. | A ação não terminou. Tente de novo; se repetir, olhe o log do servidor. |

### Lista de sessões

| Chave | en | pt-br |
|---|---|---|
| `sessions.heading` | Your sessions | Suas sessões |
| `sessions.loading` | Loading sessions… | Carregando sessões… |
| `sessions.empty.title` | No sessions yet | Nenhuma sessão ainda |
| `sessions.empty.body` | Pick a scenario above and start your first session. | Escolha um cenário acima e comece sua primeira sessão. |
| `sessions.error.title` | Couldn't load your sessions | Não consegui carregar suas sessões |
| `sessions.error.body` | The session list didn't come back from the server. Your saved sessions are intact. | A lista de sessões não voltou do servidor. Suas sessões salvas estão intactas. |
| `sessions.item.turnsZero` | Not started | Não começou |
| `sessions.item.turnsOne` | 1 turn | 1 turno |
| `sessions.item.turnsOther` | {count} turns | {count} turnos |
| `sessions.item.meta` | {turns} · last played {when} | {turns} · jogada {when} |
| `sessions.item.open` | Continue {scenario} | Continuar {scenario} |
| `sessions.new.heading` | New session | Nova sessão |
| `sessions.new.scenarioLabel` | Scenario | Cenário |
| `sessions.new.submit` | Start session | Começar sessão |
| `sessions.new.submitting` | Starting… | Começando… |
| `sessions.new.error` | Couldn't start the session. Nothing was saved — try again. | Não consegui começar a sessão. Nada foi salvo — tente de novo. |
| `sessions.new.scenariosError` | Couldn't load scenarios | Não consegui carregar os cenários |

### Tela de jogo

| Chave | en | pt-br |
|---|---|---|
| `game.documentTitle` | {scenario} — ooc-local | {scenario} — ooc-local |
| `game.loading` | Loading session… | Carregando sessão… |
| `game.back` | Back to sessions | Voltar para as sessões |
| `game.prologue.label` | Prologue | Prólogo |
| `game.empty.hint` | Your turn. Type what you do or say. | Sua vez. Escreva o que você faz ou fala. |
| `game.input.label` | Your action | Sua ação |
| `game.input.placeholder` | What do you do? | O que você faz? |
| `game.input.send` | Send | Enviar |
| `game.input.sending` | Narrating… | Narrando… |
| `game.input.hint` | Enter sends · Shift+Enter for a new line | Enter envia · Shift+Enter quebra linha |
| `game.turn.playerLabel` | You | Você |
| `game.turn.narratorLabel` | Narrator | Narrador |
| `game.turn.thinking` | The narrator is writing… | O narrador está escrevendo… |
| `game.turn.done` | Turn {index} done | Turno {index} pronto |
| `game.turn.partial` | Incomplete turn | Turno incompleto |
| `game.turn.error` | The turn stopped halfway | O turno parou no meio |
| `game.turn.errorBody` | The narrator didn't finish. Your message was kept — send it again. | O narrador não terminou. Sua mensagem foi guardada — mande de novo. |
| `game.scrollToLatest` | Jump to latest | Ir para o mais recente |
| `game.notFound.title` | Session not found | Sessão não encontrada |
| `game.notFound.body` | This session doesn't exist anymore. Go back and pick another one. | Essa sessão não existe mais. Volte e escolha outra. |

### HUD

| Chave | en | pt-br |
|---|---|---|
| `hud.turn` | Turn | Turno |
| `hud.location` | Location | Local |
| `hud.time` | Time | Hora |
| `hud.weather` | Weather | Clima |
| `hud.placeholder` | — | — |
| `hud.unavailable` | Not tracked yet | Ainda não rastreado |
| `hud.stale` | Showing the last known state | Mostrando o último estado conhecido |
| `hud.announce` | Turn {turn}, {location}, {time}, {weather} | Turno {turn}, {location}, {time}, {weather} |
| `hud.weather.clear` | Clear | Limpo |
| `hud.weather.cloudy` | Cloudy | Nublado |
| `hud.weather.rain` | Rain | Chuva |
| `hud.weather.storm` | Storm | Tempestade |
| `hud.weather.snow` | Snow | Neve |
| `hud.weather.fog` | Fog | Neblina |
| `hud.weather.night` | Night | Noite |
| `hud.weather.unknown` | Unknown | Desconhecido |

### Texto do turno

| Chave | en | pt-br |
|---|---|---|
| `turnText.speakerLabel` | {name} says | {name} diz |
| `turnText.narrationLabel` | Narration | Narração |
| `turnText.rawFallback` | Shown as the narrator wrote it | Mostrado como o narrador escreveu |
