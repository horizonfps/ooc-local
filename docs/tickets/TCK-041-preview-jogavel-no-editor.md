---
id: TCK-041
title: Jogar o cenario no painel de preview do editor
status: ready
points: 5
blockedBy: [TCK-033, TCK-036, TCK-038, TCK-040, TCK-046, TCK-049]
files:
  - frontend/src/components/builder/BuilderPreview.tsx
  - frontend/src/components/builder/BuilderPreview.test.tsx
  - frontend/src/components/GamePanel.tsx
  - frontend/src/components/GamePanel.test.tsx
  - frontend/src/screens/BuilderEditorScreen.tsx
  - frontend/src/screens/builderEditor.css
  - frontend/src/api.ts
  - frontend/src/strings.ts
migration: false
ui: true
risk: medium
---

## Problema

O builder sem preview é um formulário de YAML com passos extras. O valor da
Fase 2 é escrever o prólogo e jogar do lado, na mesma tela, com a mesma engine.
O shell (TCK-036) já reserva o `aside` do preview e o `GamePanel` (TCK-040) já
existe; falta o painel que cria a sessão efêmera, deixa escolher o start,
reinicia e avisa quando o que está na tela ainda não está no disco.

Esse aviso é o que evita a conclusão errada mais previsível do builder: editar o
prólogo, jogar, não ver a mudança e achar que o app está quebrado.

`blockedBy` explica cada dependência: TCK-033 (sessão efêmera), TCK-036 (slot do
preview, `draft`, `dirty`), TCK-038 (a chave `builder.starts.defaultBadge`, usada
no seletor de start — chave inexistente quebra o `tsc -b`), TCK-040 (o
`GamePanel`), TCK-046 (o `onSave` do shell, usado em "salvar e reiniciar"),
TCK-049 (último ticket a editar `frontend/src/strings.ts` e
`frontend/src/api.ts` antes deste; a dependência é de colisão de arquivo, não de
contrato).

## Escopo

Dentro:
- `BuilderPreview`: estados ocioso/iniciando/pronto/erro, seletor de start,
  restart, avisos de rascunho não salvo e de arquivos alterados.
- Montagem do painel no `aside` do shell, com o comportamento recolhível já
  especificado no TCK-036.
- Ciclo de vida da sessão efêmera (criar, descartar, abortar stream).
- Prop opcional `onTurnsChanged` no `GamePanel` (mudança aditiva).
- `createSession` com `startId`/`ephemeral` e `deleteSession` em `api.ts`.
- Chaves i18n do preview.

Fora (explícito):
- Sprites e background no painel (TCK-042 — entra no `GamePanel` e aparece nos
  dois lugares de graça).
- Reimplementar turno, HUD, histórico ou erro: tudo isso é do `GamePanel`.
- Persistir a sessão de preview ou listá-la em `#/`.
- Free mode e setup wizard (Fase 7).

## Comportamento esperado

O painel abre **parado**: não cria sessão sozinho, porque toda sessão custa uma
chamada de LLM na primeira ação e o builder passa muito tempo sem jogar. A
pessoa clica em iniciar, escolhe o start, joga.

Enquanto houver rascunho não salvo, o cabeçalho mostra um aviso permanente: o
preview roda o que está **no disco**. Depois de um save com o preview rodando, o
aviso muda para "os arquivos mudaram, reinicie".

Sair do editor, reiniciar ou trocar de start descarta a sessão efêmera.

## Detalhes técnicos

### Sessão

- Iniciar: `POST /api/sessions` com `{ scenarioId, startId, ephemeral: true }`
  (TCK-033).
- Descartar: `DELETE /api/sessions/{id}`. No unmount e no `beforeunload`, use
  `fetch(url, { method: 'DELETE', keepalive: true })` e ignore a resposta —
  falhar aqui não incomoda ninguém, porque o backend limpa efêmeras no boot.
- Um turno em stream é abortado com `AbortController` no unmount; isso já é
  responsabilidade do `GamePanel`, então basta desmontá-lo.
- Trocar de cenário (`id` da rota muda) descarta e volta ao estado ocioso.

### Estados

- **Ocioso**: `EmptyState` com `builder.preview.idle.title`/`.body` e ação
  `builder.preview.start`.
- **Iniciando**: `Loading` com `builder.preview.starting` + skeleton de dois
  blocos.
- **Pronto**: `<GamePanel sessionId={...} regionLabel={t('builder.preview.regionLabel')} />`
  — prólogo, histórico e input idênticos ao jogo, reaproveitando `game.input.*`,
  `game.turn.*`, `game.empty.hint` e `game.scrollToLatest`. Zero chave
  duplicada.
- **Cenário inválido**: quando o shell está no estado inválido (422 do
  TCK-031), o painel mostra `ErrorState` com
  `builder.preview.invalid.title`/`.body` reaproveitando o `{reason}`, e
  **nenhum** botão de iniciar. Consertar vem antes de jogar.
- **Erro ao criar a sessão**: `ErrorState` com `builder.preview.start.error` e
  `onRetry`.
- **Erro de turno**: já é do `GamePanel` (turno parcial preservado,
  `game.turn.error`/`game.turn.errorBody`, retry). Zero chave nova.

### Avisos de sincronia

- `dirty === true` (prop do shell): aviso persistente `builder.preview.stale` em
  `role="status"`, com `builder.preview.saveAndRestart` (chama `onSave` e, no
  sucesso, reinicia) e `builder.preview.restart`.
- Depois de um save bem-sucedido com preview ativo:
  `builder.preview.outdated` com a ação `builder.preview.restart`. O shell
  informa o save pela prop `savedAt: number | null`, e o painel compara com o
  instante em que a sessão foi criada.

### Seletor de start

`<select>` no cabeçalho, rotulado por `builder.preview.startLabel`, listando os
starts **do rascunho** pelo nome, com `builder.starts.defaultBadge` (TCK-038) no
padrão.

- Preview ocioso: trocar só muda a seleção.
- Sessão em andamento com turnos jogados: confirma
  `builder.preview.switchStart.title`/`.body`/`.submit` + `common.cancel`;
  confirmar descarta a sessão e cria outra no start novo.
- Start presente no rascunho e ausente de `loadedStartIds` aparece
  **desabilitado**, com o hint `builder.preview.startUnsaved` — ele não existe
  no disco e a engine não o conhece.

### Restart

Botão `builder.preview.restart`; com turnos jogados, confirma
`builder.preview.restart.title`/`.body` (com `{count}`)/`.submit`. Descarta a
sessão e cria outra no mesmo start; foco volta para o input; anúncio
`builder.preview.restarted`.

Para saber a contagem de turnos sem duplicar estado, o `GamePanel` ganha a prop
opcional `onTurnsChanged?: (count: number) => void`, chamada quando o histórico
muda. É **aditiva**: nenhuma prop existente muda de tipo e nenhum teste do
TCK-040 é alterado — por isso `GamePanel.tsx` e `GamePanel.test.tsx` estão em
`files` deste ticket.

### Acessibilidade e layout

- O painel é `<aside>` com `aria-label` = `builder.preview.regionLabel` e o hint
  `builder.preview.ephemeralHint` abaixo do cabeçalho.
- Iniciar e reiniciar movem o foco para o input do preview.
- Os anúncios do preview vão para uma região live **própria**, separada da do
  editor, para não misturar "salvo" com "turno pronto".
- Em telas estreitas, abrir o preview em tela cheia move o foco para o cabeçalho
  do painel; o botão de fechar é o primeiro tabulável.
- O painel tem rolagem própria e nunca rouba a do editor: histórico com
  `min-height: 0` no filho flex, input fixo no rodapé.
- Trocar de aba de edição **não** derruba o preview — o painel vive no shell,
  fora do `tabpanel`. Não o remonte ao mudar de aba.

### API

```ts
export function createSession(scenarioId: string, opts?: { startId?: string; ephemeral?: boolean }): Promise<SessionDetail>
export function deleteSession(id: string, opts?: { keepalive?: boolean }): Promise<void>
```

`createSession` hoje é `(scenarioId: string)` e é chamada pelo `SessionsScreen`:
mantenha o primeiro parâmetro e acrescente o segundo opcional, para não tocar
naquela tela nem no teste dela. `deleteSession` responde 204: `fetch` próprio,
sem `response.json()`.

## Contrato público

```ts
// frontend/src/components/builder/BuilderPreview.tsx
export type BuilderPreviewProps = {
  scenarioId: string
  draft: BuilderDraft
  loadedStartIds: string[]      // starts que existem no disco
  dirty: boolean
  savedAt: number | null
  invalidReason?: string
  onSave: () => Promise<void>
}
// frontend/src/components/GamePanel.tsx
// GamePanelProps ganha onTurnsChanged?: (count: number) => void
// frontend/src/api.ts
export function deleteSession(id: string, opts?: { keepalive?: boolean }): Promise<void>
```

Consumidor: TCK-042 renderiza a cena dentro do `GamePanel`, então o preview
ganha sprites sem alteração neste arquivo.

## Acceptance criteria

- [ ] O painel abre ocioso e **não** cria sessão sozinho.
- [ ] Iniciar cria a sessão com `ephemeral: true` e o `startId` selecionado.
- [ ] A sessão do preview não aparece na lista de sessões (`#/`).
- [ ] Reiniciar com turnos jogados pede confirmação, manda `DELETE` da antiga e
      cria outra.
- [ ] Trocar de start com sessão em andamento pede confirmação.
- [ ] Start ainda não salvo aparece desabilitado com o hint.
- [ ] Rascunho sujo mostra `builder.preview.stale`; salvar com preview ativo
      troca para `builder.preview.outdated`.
- [ ] "Salvar e reiniciar" chama `onSave` e só então reinicia.
- [ ] Documento inválido esconde o botão de iniciar e mostra o motivo.
- [ ] Desmontar o editor dispara o `DELETE` da sessão efêmera.
- [ ] Trocar de aba de edição não reinicia nem derruba o preview.
- [ ] `strings.en` e `strings['pt-br']` seguem com as mesmas chaves.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente que muda de preparação (asserções preservadas):
`GamePanel.test.tsx` e `GameScreen.test.tsx` (TCK-040) continuam passando — a
prop `onTurnsChanged` é opcional e nenhum comportamento existente muda;
acrescente **um** caso novo em `GamePanel.test.tsx` para a prop.
`SessionsScreen.test.tsx` não muda: `createSession` mantém o primeiro parâmetro
e o segundo é opcional. Confirme os dois pontos ao implementar.

Cenários novos (`BuilderPreview.test.tsx`, `fetch` mockado):
- Feliz: iniciar → POST com `ephemeral: true` e `startId` → o prólogo do start
  aparece.
- Feliz: jogar um turno pelo painel (stream mockado) e ver o HUD atualizar.
- Feliz: reiniciar com 2 turnos → confirmação → DELETE da antiga + POST da nova.
- Borda: `dirty: true` mostra `builder.preview.stale`; "salvar e reiniciar"
  chama `onSave` antes do POST.
- Borda: `savedAt` posterior à criação da sessão troca o aviso para
  `builder.preview.outdated`.
- Borda: start ausente de `loadedStartIds` fica desabilitado no select.
- Borda: desmontar com sessão ativa dispara DELETE com `keepalive`.
- Falha: POST 500 ao iniciar → `builder.preview.start.error` com retry.
- Falha: `invalidReason` presente → sem botão de iniciar, com o motivo na tela.

## Rollout e kill switch

N/A — painel novo dentro do editor. Fechar o preview (o toggle do shell) é o
desligamento manual; nenhuma sessão de verdade é tocada, e a flag `builder` não
gateia sessão efêmera de propósito: jogar não escreve no cenário.

## Observabilidade

Eventos: nenhum no frontend; o backend emite `session_created` com
`ephemeral: true` e `session_deleted` (TCK-033).
Métrica de sucesso: jogar 5 turnos no preview de um cenário criado pela UI, com
a lista de sessões em `#/` continuando limpa depois.

## i18n — chaves novas

| chave | en | pt-br |
|---|---|---|
| `builder.preview.regionLabel` | `Playable preview` | `Preview jogável` |
| `builder.preview.heading` | `Preview` | `Preview` |
| `builder.preview.ephemeralHint` | `Throwaway session: nothing here is saved to your sessions.` | `Sessão descartável: nada aqui é salvo nas suas sessões.` |
| `builder.preview.idle.title` | `Preview not running` | `Preview parado` |
| `builder.preview.idle.body` | `Start it to play the scenario as it is on disk right now.` | `Inicie para jogar o cenário como ele está no disco agora.` |
| `builder.preview.start` | `Start the preview` | `Iniciar o preview` |
| `builder.preview.starting` | `Starting the preview…` | `Iniciando o preview…` |
| `builder.preview.start.error` | `Couldn't start the preview. The scenario files weren't touched — try again.` | `Não consegui iniciar o preview. Os arquivos do cenário não foram tocados — tente de novo.` |
| `builder.preview.startLabel` | `Start` | `Start` |
| `builder.preview.startUnsaved` | `Save first — this start doesn't exist on disk yet.` | `Salve antes — este start ainda não existe no disco.` |
| `builder.preview.stale` | `The preview plays what's on disk. Your unsaved edits aren't in it.` | `O preview joga o que está no disco. Suas edições não salvas não estão nele.` |
| `builder.preview.outdated` | `The files changed. Restart the preview to play the new version.` | `Os arquivos mudaram. Reinicie o preview para jogar a versão nova.` |
| `builder.preview.saveAndRestart` | `Save and restart` | `Salvar e reiniciar` |
| `builder.preview.restart` | `Restart` | `Reiniciar` |
| `builder.preview.restart.title` | `Restart the preview?` | `Reiniciar o preview?` |
| `builder.preview.restart.body` | `The {count} turns played here are discarded. They were never saved anyway.` | `Os {count} turnos jogados aqui são descartados. Eles nunca foram salvos mesmo.` |
| `builder.preview.restart.submit` | `Restart` | `Reiniciar` |
| `builder.preview.restarted` | `Preview restarted` | `Preview reiniciado` |
| `builder.preview.switchStart.title` | `Switch to the start {name}?` | `Trocar para o start {name}?` |
| `builder.preview.switchStart.body` | `The preview restarts and the turns played here are discarded.` | `O preview reinicia e os turnos jogados aqui são descartados.` |
| `builder.preview.switchStart.submit` | `Switch start` | `Trocar de start` |
| `builder.preview.invalid.title` | `Can't play this scenario yet` | `Ainda não dá para jogar este cenário` |
| `builder.preview.invalid.body` | `{reason}. Fix it and the preview starts.` | `{reason}. Conserte e o preview inicia.` |
