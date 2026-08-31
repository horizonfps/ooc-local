# Tickets — HRZ Workflow

Um ticket é a especificação completa de um PR revisável (máx. 5 pontos).
Template: [`.claude/templates/ticket.md`](../../.claude/templates/ticket.md).

## Convenção

- ID: `TCK-NNN`, sequencial, nunca reutilizado. Arquivo: `TCK-NNN-slug.md`.
- Ciclo de status: `draft → ready → in_progress → in_review → done`.
- `ready` exige aprovação do spec-critic; `done` exige PR mergeado.
- `blockedBy` lista IDs de tickets que expõem contrato consumido por este.
- Waves saem de `node <skill>/scripts/dag.mjs` sobre este diretório.

## Regra do projeto

O plano de fases (`dev/implementation-plan.md`) manda: uma fase aberta por vez.
Tickets de uma wave pertencem sempre à mesma fase.
