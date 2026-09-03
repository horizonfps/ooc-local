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

## Git

- Commit, branch e PR em inglês, `type(scope): summary`, falando só do conteúdo.
  Merge por squash com o título do PR.

## Código

- Comentários e identificadores em inglês, mínimos. UI e prompts nascem i18n
  (en/pt-br).
- Strings do frontend vivem em `frontend/src/strings/{common,builder,game}.ts`
  (`strings.ts` só compõe). Mudança de UI do builder toca só `builder.ts`; do
  jogo, só `game.ts`, para que as duas possam andar em paralelo.
- Tudo que é sistema (HUD, stats, tags, comandos) é determinístico no engine; o
  LLM só narra e emite tags.
