---
id: TCK-022
title: Tornar o autoscroll barato, flutuar o botão de "ir para o fim" e cancelar o stream
status: in_review
points: 3
blockedBy: []
files:
  - frontend/src/screens/GameScreen.tsx
  - frontend/src/screens/game.css
  - frontend/src/api.ts
  - frontend/src/screens/GameScreen.test.tsx
migration: false
ui: true
risk: low
---

## Problema

Três defeitos no laço de streaming da tela de jogo (TCK-014, mergeado):

1. **Autoscroll a cada delta, com animação.** O efeito de
   `frontend/src/screens/GameScreen.tsx:115` depende de `pending`, e `pending`
   é substituído por um objeto novo a cada `onDelta`
   (`setPending((p) => (p ? { ...p, text: p.text + delta } : p))`, `:168`). Um
   turno de
   350 palavras chega em centenas de deltas, então o efeito roda centenas de
   vezes e chama `scrollToBottom` (`:36`), que usa `behavior: 'smooth'` fora de
   `prefers-reduced-motion`. Cada chamada cancela e reinicia a animação de
   scroll do navegador: em turno longo o histórico fica preso perto do topo
   tremendo, e o main thread gasta layout a cada frame. A spec de UI da fase
   (documento **externo ao repositório**, reproduzido aqui) é explícita:
   "durante o streaming, autoscroll acompanha o texto **apenas se** o usuário já
   estava no fim; se ele rolou para cima para reler, o autoscroll pausa (…).
   Nunca arrastar o usuário de volta à força" e "com `prefers-reduced-motion`,
   todo scroll é instantâneo" — acompanhar não é reanimar.
2. **O botão "ir para o fim" empurra o layout.** `.game-scrollLatest`
   (`frontend/src/screens/game.css:129`) é `align-self: center` com `margin:
   0.25rem 0` dentro do flex de `.game`: quando ele aparece, o histórico encolhe
   e o texto **pula**, justamente enquanto o jogador está lendo o que rolou para
   trás. A spec de UI da fase (documento **externo ao repositório**, reproduzido
   aqui) pede um **botão flutuante**: "aparece um botão flutuante
   `game.scrollToLatest` que retoma" e "botão flutuante de 'ir para o fim' é
   alcançável por teclado e tem rótulo textual".
3. **`streamTurn` sem `AbortController`.** `frontend/src/api.ts:67` faz `fetch`
   e lê o `ReadableStream` num laço `while (true)` sem nenhum sinal de
   cancelamento. Se o componente desmontar no meio do turno — voltar para a
   lista, trocar de sessão, fechar a aba — o laço continua rodando, chamando
   `setPending`/`setHud` em componente desmontado (warning do React e vazamento
   dos handlers), e a conexão SSE fica aberta segurando o worker do backend até
   o turno terminar. `GameScreen` já troca de sessão sem cancelar nada
   (`useEffect` de `[sessionId]`, `:82`).

## Escopo

Dentro:
- Autoscroll coalescido por `requestAnimationFrame` e instantâneo durante o
  streaming; `smooth` só no clique do botão e só sem `prefers-reduced-motion`.
- `.game-scrollLatest` flutuante, sem afetar o fluxo.
- `signal: AbortSignal` opcional em `streamTurn`, `AbortController` por turno em
  `GameScreen`, abortado no unmount e na troca de `sessionId`.
- Cenários de teste em `frontend/src/screens/GameScreen.test.tsx`.

Fora (explícito):
- Botão de **cancelar turno** visível para o jogador: a spec da fase (externa ao
  repositório) é categórica — "Fase 1 **não** tem cancelar turno, nem regenerar,
  nem editar turno. Nada disso aparece na tela". O `AbortController` deste
  ticket é interno, disparado só por desmontagem.
- Mudar o comportamento de `atBottom` / limiar de 32 px (`:137`) ou a regra de
  quando o botão aparece.
- Virtualizar o histórico, paginar turnos antigos, ou memoizar `TurnText`.
- Classificação de erro, `ApiError.detail`, HUD piscando: são do **TCK-023**.
- Redesenhar o botão: cor, raio e `--accent` continuam os que já estão em
  `frontend/src/screens/game.css:129`; muda o **posicionamento**.

### Testes existentes que este ticket invalida

Grep em `frontend/src/screens/GameScreen.test.tsx` (23 testes):

- Nenhum teste afere scroll: `jsdom` não faz layout e `Element.prototype.scrollTo`
  não existe nele, então `scrollToBottom` já cai no ramo `el.scrollTop =
  el.scrollHeight` (`GameScreen.tsx:41`) em toda a suíte atual. Nenhuma
  adaptação; os cenários de scroll deste ticket precisam **stubar**
  `Element.prototype.scrollTo` e `window.matchMedia` explicitamente.
- Nenhum teste afere a posição nem a classe do botão `game.scrollToLatest`
  (grep por `scrollToLatest` em `frontend/src/` só acha
  `GameScreen.tsx:363` e `strings.ts:54`/`:137`). Cenário novo.
- `it('plays a happy turn: ...')` (`:203`), `it('plays two turns in a row ...')`
  (`:231`), `it('records a single player/narrator pair per turn under
  StrictMode')` (`:413`): passam por `streamTurn`. O parâmetro `signal` é
  opcional e os mocks de `fetch` (`mockRoutedFetch`, `:52`) ignoram `init`
  extra, então **nenhuma adaptação**. O caso StrictMode é o que mais sofre com
  abort mal feito (StrictMode monta, desmonta e remonta): ele já existe e é a
  rede de segurança deste ticket — se ele quebrar, o abort está sendo disparado
  em remontagem, não em desmontagem real.
- `frontend/src/components/TurnText.test.tsx` e `Hud.test.tsx` não são tocados.

## Comportamento esperado

Do ponto de vista do jogador:

- Turno longo streama com o texto acompanhando o fim da rolagem de forma suave e
  contínua, sem tremer e sem travar a interface.
- Rolar para cima durante o streaming pausa o acompanhamento e faz aparecer o
  botão "ir para o mais recente" **por cima** do histórico, logo acima do
  formulário, sem mover uma linha do texto que ele está lendo.
- Clicar (ou dar Enter/Espaço com o teclado) no botão volta ao fim e retoma o
  acompanhamento. Com `prefers-reduced-motion: reduce`, a volta é instantânea.
- Sair da sessão no meio de um turno não deixa nada rodando: nenhum erro
  aparece, o turno simplesmente é abandonado.

## Detalhes técnicos

- Efeito de scroll: troque a dependência `pending` por
  `pending?.text.length ?? 0`, e chame o scroll dentro de
  `requestAnimationFrame`, guardando o handle num `useRef` e cancelando o frame
  anterior com `cancelAnimationFrame` antes de agendar o próximo. Assim,
  independentemente de quantos deltas chegarem, no máximo um scroll por frame.
  O cleanup do efeito cancela o frame pendente.
- `scrollToBottom(el, behavior)`: o parâmetro passa a ser explícito.
  Durante o streaming, sempre `'auto'`. No `jumpToLatest` (`:140`),
  `isReducedMotion() ? 'auto' : 'smooth'` — a função `isReducedMotion`
  (`:27`) já existe, já é defensiva contra `matchMedia` ausente, e não muda.
- `.game-scrollLatest`: `position: absolute` ancorado no container `.game` (que
  ganha `position: relative`), `left: 50%` + `transform: translateX(-50%)`,
  `z-index: 2`, `min-height: 44px` (alvo de toque do baseline de UI da fase), e
  classe adicional `game-scrollLatest--floating` para o teste ancorar.
  **Valor do `bottom`**: variável `--game-scrollLatest-bottom: 6rem` declarada
  em `.game`, e o botão usa `bottom: var(--game-scrollLatest-bottom)`. O número
  vem da altura do rodapé de hoje: `.game-footer` tem `padding-top: 0.5rem`
  (`frontend/src/screens/game.css:145`), a textarea tem `min-height: 2.75rem`
  (`:152`) e abaixo dela fica o `.game-input-hint`; 6rem deixa o botão logo
  acima do formulário sem cobri-lo, com folga para a dica de teclado. Ficar numa
  variável é o que permite ajustar o número sem caçar o seletor.
  O botão continua sendo o mesmo `<button type="button">` com o mesmo rótulo
  `t('game.scrollToLatest')`, continua na ordem de tabulação natural (nada de
  `tabIndex` negativo) e continua **depois** do histórico no DOM, como está hoje
  (`GameScreen.tsx:361`).
  `@media (prefers-reduced-motion: reduce)` já zera transições globalmente em
  `frontend/src/index.css:13`; não acrescente transição nova ao botão.
- `streamTurn(sessionId, message, h, options?: { signal?: AbortSignal })`:
  passa `signal` para o `fetch` e, no `catch`/saída do laço, se
  `signal?.aborted` for verdadeiro, **retorna silenciosamente** sem chamar
  `h.onError` — abort não é falha de turno. Chame `reader.cancel()` na saída por
  abort para liberar o stream.
- `GameScreen`: um `useRef<AbortController | null>`; `runTurn` cria um
  controller novo, guarda no ref e o passa; o `useEffect` de limpeza
  (`[sessionId]`, e um `useEffect(() => () => abort(), [])` para o unmount)
  chama `abort()`. No `catch` de `runTurn`, ignore o erro quando
  `controller.signal.aborted` — senão a saída da tela pinta um `ErrorState` num
  componente que está sumindo.
  **Armadilha**: `fetch` abortado rejeita com `DOMException` de `name:
  'AbortError'`, que **não** é `TypeError` — se cair no classificador atual
  (`GameScreen.tsx:199`) vira "unexpected" e o jogador vê um erro fantasma. O
  guard por `signal.aborted` tem que vir antes de qualquer `describeError`.

## Contrato público

```ts
// frontend/src/api.ts
export type TurnOptions = { signal?: AbortSignal }

export function streamTurn(
  sessionId: string,
  message: string,
  h: TurnHandlers,
  options?: TurnOptions,
): Promise<void>
```

`TurnHandlers` (`onDelta`, `onHud`, `onError`) inalterado. O TCK-023 consome
esta assinatura.

## Acceptance criteria

- [ ] Com 50 deltas num único turno, `Element.prototype.scrollTo` é chamado no
      máximo uma vez por frame de animação (aferido com `rAF` stubado e
      contador).
- [ ] Toda chamada de scroll durante o streaming usa `behavior: 'auto'`.
- [ ] O clique em "ir para o mais recente" usa `behavior: 'smooth'` sem
      `prefers-reduced-motion` e `'auto'` com ele.
- [ ] O botão tem a classe `game-scrollLatest--floating` e
      `button.closest('ol')` é `null`.
- [ ] O botão é alcançável por `Tab` e tem nome acessível igual a
      `t('game.scrollToLatest')`.
- [ ] Desmontar o componente no meio de um stream aborta o `fetch` e não produz
      nenhum `console.error` de atualização de estado.
- [ ] Trocar `sessionId` no meio de um stream aborta o stream anterior e não
      mistura texto entre as sessões.
- [ ] Um abort nunca renderiza `ErrorState`.
- [ ] `npm run check` verde (tsc + vitest).

Verificação manual (fora do `npm run check`, porque o jsdom não aplica folha de
estilo externa nem calcula layout — `getComputedStyle` devolveria vazio para
`.game-scrollLatest`):

- [ ] Com `npm run dev` e o histórico rolado para cima, o botão aparece
      **sobreposto** ao histórico, e nenhuma linha de texto se move quando ele
      surge ou some.
- [ ] Em viewport de 360 px de largura, o botão não cobre a textarea nem o
      `game.input.hint`.

## Cenários de teste

- Feliz: turno com muitos deltas e `rAF` controlado → um scroll por frame, todos
  com `behavior: 'auto'`.
- Feliz: rolar para cima (disparar `scroll` com `scrollTop` baixo via
  `fireEvent.scroll` e stubs de `scrollHeight`/`clientHeight`) → botão aparece;
  clicar → `scrollTo` chamado com `smooth` e o botão some.
- Feliz: `matchMedia('(prefers-reduced-motion: reduce)').matches === true`
  stubado → o clique usa `'auto'`.
- Borda: botão renderizado fora do `<ol className="game-history">` (aferido por
  `closest('ol')` ser nulo), com a classe `game-scrollLatest--floating` e com
  nome acessível. O **posicionamento visual** não é aferido aqui: fica na
  verificação manual, porque jsdom não aplica CSS externo.
- Borda: `unmount()` durante o stream → o `AbortSignal` passado ao `fetch` fica
  `aborted`, e nenhum `ErrorState` é renderizado.
- Borda: rerender com `sessionId` novo durante o stream → primeiro controller
  abortado, histórico da sessão nova sem texto da anterior (o teste
  `it('refetches without mixing history when the sessionId prop changes')`,
  `:185`, já cobre o caso sem stream; este é o caso **com** stream).
- Falha: `fetch` rejeitando com `DOMException('AbortError')` sem que o sinal
  esteja abortado (aborto externo) → cai no caminho de erro normal, sem travar
  em "streaming".

## Rollout e kill switch

N/A como flag: mudança de comportamento de UI, sem estado persistido e sem
schema. A rota de escape é `git revert` do PR. O kill switch de produto continua
sendo a flag **`chat`** do backend (default `true`,
`~/.ooc-local/config.yaml`): com ela desligada nenhum turno streama e nenhuma
linha deste ticket executa.

`risk: low` porque o pior caso da mudança é cosmético (scroll não acompanhar) e
está coberto por teste; nada aqui grava dado nem toca a API.

## Observabilidade

N/A no frontend — o projeto não tem telemetria de cliente (grep por `emit` em
`frontend/src/` não devolve nada; toda observabilidade vive em
`backend/app/observability.py`). O sinal equivalente é a suíte do vitest:
os contadores de `scrollTo` e o estado do `AbortSignal` são as asserções que
dizem se a mudança funcionou.

## i18n

Nenhuma chave nova. `game.scrollToLatest` já existe em `en` ("Jump to latest",
`frontend/src/strings.ts:54`) e `pt-br` ("Ir para o mais recente", `:137`), e o
texto não muda — só a posição do botão. A paridade de locales continua aferida
por `frontend/src/i18n.test.ts`, que não é tocado.

`contentGates` está vazio em `.claude/pipeline.json`: não há gate de conteúdo
aplicável a este ticket.
