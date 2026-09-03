# ooc-local

Motor local de RP narrativo: backend FastAPI (`backend/`, uv) + frontend
React/Vite/TS (`frontend/`). Plano de fases em `dev/implementation-plan.md`
(fora do git): uma fase aberta por vez, fase fecha com critério de verde jogado
de verdade e tag `fase-N`.

## Comandos

- `npm run dev` — sobe API (uvicorn :8000) e web (vite :5173, proxy `/api`).
- `npm run check` (= `verify`) — pytest do backend + `tsc -b` do frontend.
- `npm run build` — build do frontend.
- Config de runtime em `~/.ooc-local/config.yaml` (criada com defaults no
  primeiro uso; papéis narrator/utility/builder).

## HRZ Workflow

- Manifesto: `.claude/pipeline.json`. Tickets: `docs/tickets/` (convenção no
  README de lá). Métricas: `docs/pipeline-metrics.csv`.
- Pre-commit roda o mesmo `verify` do CI. **Worktree novo não herda a config**:
  rode `git config core.hooksPath .githooks` em cada worktree, e
  `npm ci --prefix frontend` antes do primeiro commit (o hook roda o `verify`,
  que falha sem `node_modules`).
- Toda wave parte de `origin/main` atualizada; merge é gate humano. Combinação
  dos PRs de uma wave é testada por `scripts/integration-check.mjs`
  (branch `integration/wave-N`, CI dispara no push).
- Isolamento de execução: estratégia `port` (base 4000). E2E ainda não existe;
  quando existir, porta e baseURL vêm do ambiente, nunca fixas.
- Modelos dos agentes: Opus em quem planeja (product-manager, spec-critic,
  design-specialist, review-briefer), Sonnet em quem executa (implementer,
  qa-tester). Na wave o modelo vem do template de dispatch, não do frontmatter.
- Interface freeze: contrato público de um ticket congela quando outro ticket da
  wave depende dele; mudança de contrato vira ticket de foundation, que roda em
  wave anterior à dos consumidores.

## Git

- Commit, branch e PR em inglês, `type(scope): summary`, falando só do conteúdo.
  Sem ID de ticket nem menção a wave, spec ou agente. Merge por squash com o
  título do PR.

## Código

- Comentários e identificadores em inglês, mínimos. UI e prompts nascem i18n
  (en/pt-br).
- Strings do frontend vivem em `frontend/src/strings/{common,builder,game}.ts`
  (`strings.ts` só compõe). Ticket de UI do builder toca só `builder.ts`; do
  jogo, só `game.ts`. É o que permite um ticket de cada na mesma wave.
- Tudo que é sistema (HUD, stats, tags, comandos) é determinístico no engine; o
  LLM só narra e emite tags.
