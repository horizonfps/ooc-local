---
id: TCK-011
title: Renderizar o HUD do engine como faixa de turno, local, hora e clima
status: done
points: 2
blockedBy: [TCK-001, TCK-008]
files:
  - frontend/src/components/Hud.tsx
  - frontend/src/components/Hud.test.tsx
  - frontend/src/components/hud.css
migration: false
ui: true
risk: low
---

## Problema

O HUD é a prova visível da regra transversal do projeto: "tudo que é sistema é
determinístico no engine, o LLM só narra" (`CLAUDE.md`,
`dev/implementation-plan.md`, Stack). Hoje não existe nada disso na UI — a tela
só tem bolhas de texto. Sem o HUD, turno, local, hora e clima só existiriam se o
modelo resolvesse escrevê-los no texto, que é exatamente a fraqueza que o
projeto existe para corrigir.

## Escopo

Dentro:
- `frontend/src/components/Hud.tsx`: componente de apresentação que recebe o
  `HudState` do backend e o estado de turno em andamento, e renderiza a faixa.
- Tradução do código de clima pelo vocabulário fechado, com fallback para código
  desconhecido.
- `hud.css` com a faixa fixa, altura estável e a grade 2×2 abaixo de 480px.
- `Hud.test.tsx`.

Fora (explícito):
- Buscar dados: o componente não faz `fetch`; quem passa `hud` é a tela de jogo
  (TCK-012).
- Stats, barras e ícones de stat — Fase 3. Aqui são quatro campos e ponto.
- Data e dia da semana (o HUD do OOC tem; o HUD da Fase 1, não).
- Mudar local/clima ao longo da sessão: na Fase 1 o engine mantém os defaults do
  start e só o turno e a hora avançam (TCK-006). A UI já suporta qualquer valor.
- Ícone de clima por imagem: só emoji decorativo.

## Comportamento esperado

Copiado/adaptado do tema 03 da spec de UI
(`hrz-drafts/fase-1/ui/03-hud-do-engine.md`):

O HUD é **estado do engine**, nunca texto do modelo. A UI só renderiza o que o
backend mandou. Se o narrador escrever "são 3 da manhã" e o engine disser 08:10,
o HUD mostra 08:10 — divergência é bug do engine/prompt, não da UI.

### Dados

`hud` vem em dois lugares, no mesmo formato (contrato do TCK-001, exposto pelas
rotas do TCK-005/TCK-006): `GET /api/sessions/:id` → `hud` do estado atual; e o
evento SSE `data: {"hud": {...}}` emitido ao fim do turno.

```
{ "turn": 5, "location": "Pátio", "time": "08:10", "weather": "clear" }
```

- `turn` é inteiro ≥ 0.
- `location` é string livre vinda do cenário.
- `time` é string `HH:MM` (24h) já formatada pelo engine — a UI **não** converte
  fuso nem reformata; o relógio é do mundo do jogo, não do sistema.
- `weather` é código de vocabulário fechado, traduzido pela UI: `clear`,
  `cloudy`, `rain`, `storm`, `snow`, `fog`, `night`. Código desconhecido
  renderiza `hud.weather.unknown` (código no `title`), nunca quebra a tela.

### Layout

Faixa horizontal única entre a barra de topo e o histórico, com quatro campos:
turno · local · hora · clima. Cada campo é rótulo (texto secundário, menor) +
valor (texto primário). A faixa **não** rola com o histórico. Altura estável: os
quatro campos ocupam a mesma altura vazios ou preenchidos. Emoji de clima é
decorativo (`aria-hidden`), sempre acompanhado do texto traduzido.

### Atualização

- O HUD muda **uma vez por turno**, quando o evento `hud` chega ao fim do stream
  — não durante o streaming.
- Enquanto o turno está em andamento, o HUD fica com o valor do turno anterior,
  com opacidade levemente reduzida e `aria-busy="true"` no container.
- Ao atualizar, valores que mudaram recebem um destaque breve (~600ms). Com
  `prefers-reduced-motion: reduce`, o destaque não anima (troca direta).
- A região do HUD tem `aria-live="polite"` e `aria-atomic="true"`: ao fim do
  turno o leitor de tela ouve o HUD inteiro numa frase (`hud.announce`), não
  campo a campo.

### Estados

| Estado | Comportamento |
|---|---|
| **Carregando** | Rótulos visíveis com valores em `hud.placeholder` ("—"), altura já reservada. Sem spinner. |
| **Vazio / campo ausente** | Campo que o engine não mandou mostra `hud.placeholder` com `title` = `hud.unavailable`. Nunca esconder o campo. |
| **Erro** | Falha ao obter o HUD **não** derruba a tela: mantém os últimos valores conhecidos e mostra `hud.stale` como texto secundário na faixa. Se nunca houve valor, todos os campos ficam em `hud.placeholder`. |
| **Sucesso** | Valores novos com destaque breve + anúncio único em `aria-live`. |

### Acessibilidade

Faixa é `<dl>` com `<dt>` rótulo e `<dd>` valor. Contraste AA nos rótulos.
Nenhum campo do HUD é interativo na Fase 1: nada focável, nada com aparência de
botão. Destaque de mudança nunca é só cor (acompanha peso de fonte ou
sublinhado temporário).

### Responsividade (360px)

≥480px: quatro campos numa linha. <480px: grade 2×2, ordem turno · local / hora ·
clima; `location` trunca em uma linha com `title` completo. Nunca passa de duas
linhas nem rola horizontalmente.

## Detalhes técnicos

- Assinatura: `Hud({ hud, busy = false, stale = false })`, com
  `hud: HudView | null`. `null` é o estado de carregando/nunca-teve-valor.
- Guardar o valor anterior para detectar campos alterados: `useRef` do `hud`
  anterior comparado por campo; a classe de destaque é aplicada por 600ms via
  `setTimeout` limpo no unmount.
- O tipo do HUD é **declarado neste arquivo** (`export type HudView = { turn:
  number; location?: string | null; time: string; weather?: string | null }`),
  espelhando o `HudState` do TCK-001, com `location` e `weather` opcionais para
  os estados de campo ausente descritos acima. Não importar de `frontend/src/api.ts`: aquele módulo
  nasce no TCK-009, em outra wave, e o tipo estrutural do TypeScript aceita o
  `HudState` do TCK-009 sem conversão quando o TCK-012 ligar os dois. Manter os
  dois tipos idênticos é responsabilidade do TCK-012, que consome ambos.
- Mapa `weather → chave de i18n` e `weather → emoji` como constantes do módulo;
  código fora do mapa cai em `hud.weather.unknown`, com o código cru no `title`.
- `aria-live` fica no container da faixa; o texto anunciado é `hud.announce`
  interpolado, renderizado numa `<span>` visualmente oculta — assim o leitor de
  tela recebe uma frase e não a soma dos `<dt>`/`<dd>`.
- Sem `fetch`, sem `useEffect` de rede: componente de apresentação puro fora o
  timer de destaque.

Testes existentes que este ticket invalida: **nenhum**. Componente novo, sem
consumidor até o TCK-012, nenhum arquivo compartilhado alterado.

## Contrato público

```ts
// frontend/src/components/Hud.tsx  (consumido pelo TCK-012)
export type HudView = { turn: number; location?: string | null; time: string; weather?: string | null }
export function Hud(props: {
  hud: HudView | null
  busy?: boolean      // turno em andamento: opacidade reduzida + aria-busy
  stale?: boolean     // último turno falhou: mostra hud.stale
}): JSX.Element
export const WEATHER_KEYS: Record<string, StringKey>
```

## Acceptance criteria

- [ ] `{ turn: 0, location: 'Portão', time: '07:50', weather: 'clear' }` → quatro
      campos com rótulos traduzidos e valores corretos.
- [ ] `weather: 'rain'` → "Rain" / "Chuva" conforme o locale.
- [ ] `weather: 'tempestade-de-areia'` → `hud.weather.unknown` com o código no
      `title`, sem quebrar.
- [ ] `location` ausente/vazio → `—` com `title` = `hud.unavailable`, altura da
      faixa inalterada.
- [ ] `busy` → container com `aria-busy="true"` e valores do turno anterior.
- [ ] Mudança de valor aplica a classe de destaque e a remove depois de ~600ms.
- [ ] Região com `aria-live="polite"` e `aria-atomic="true"` contendo
      `hud.announce` interpolado.
- [ ] Nenhum elemento do HUD entra na ordem de `Tab`.
- [ ] `hud: null` → quatro rótulos com placeholder e altura reservada.
- [ ] `npm run check` verde.

## Cenários de teste

- Feliz: HUD completo nos dois locales.
- Feliz: `hud` novo com `turn` incrementado → destaque só no campo que mudou.
- Borda: `time: '00:01'` (virada de dia do TCK-006) → renderiza como veio, sem
  conversão.
- Borda: `stale` → `hud.stale` visível junto dos últimos valores conhecidos.
- Borda: desmontar durante os 600ms de destaque → nenhum warning de `setState`
  após unmount.
- Falha: `weather` `null`/vazio → `hud.weather.unknown`, componente não lança.
- Falha: `turn` negativo (não deve acontecer) → renderiza o número como veio; o
  componente não corrige estado do engine.

Verificação manual (fora do `verify`; anotar no PR): `location` de 60 caracteres
em 360px trunca em uma linha sem scroll horizontal; `prefers-reduced-motion:
reduce` troca o valor sem animação.

## Rollout e kill switch

N/A — componente puro sem consumidor até o TCK-012. Rollback é reverter o PR.

## Observabilidade

Eventos: nenhum. A verdade do HUD é do engine e já é observada lá
(`game_turn` traz o número do turno, TCK-006).
Métrica de sucesso: reabrir a sessão mostra o mesmo HUD de antes de fechar o
app (critério de verde da fase).

## i18n

Nenhuma chave nova. Consome a família `hud.*` criada no TCK-008: `hud.turn`,
`hud.location`, `hud.time`, `hud.weather`, `hud.placeholder`, `hud.unavailable`,
`hud.stale`, `hud.announce` e as oito `hud.weather.*` (sete códigos +
`unknown`).
