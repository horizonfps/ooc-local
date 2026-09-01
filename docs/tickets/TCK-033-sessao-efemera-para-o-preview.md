---
id: TCK-033
title: Criar e descartar sessao efemera para o preview do builder
status: done
points: 3
blockedBy: []
files:
  - backend/app/sessions.py
  - backend/app/main.py
  - backend/tests/test_sessions.py
migration: true
ui: false
risk: medium
---

## Problema

O preview do builder joga o cenário de verdade, com a mesma engine. Se cada
tentativa virar uma sessão normal, a lista de sessões da pessoa vira lixeira de
teste em dois dias. A spec §4 define preview como sessão com `ephemeral: true`,
que não persiste, e a UI precisa poder descartá-la ao reiniciar, trocar de start
ou sair do editor.

Hoje `POST /api/sessions` só aceita `scenarioId`/`startId`, toda sessão entra em
`list_sessions()`, e não existe rota para apagar sessão nenhuma.

## Escopo

Dentro:
- Coluna `ephemeral` na tabela `sessions`, com migração em
  `_migrate_session_columns`.
- `create_session(..., ephemeral: bool = False)` e `ephemeral` no corpo de
  `POST /api/sessions`.
- `list_sessions()` passa a excluir efêmeras.
- `delete_session(session_id)` + `DELETE /api/sessions/{id}`.
- `purge_ephemeral_sessions()` chamado em `init_db()`.
- Testes em `backend/tests/test_sessions.py`.

Fora (explícito):
- Deletar sessão normal pela UI (não é escopo da Fase 2; a rota recusa).
- Rewind/branch de sessão (Fase 7).
- Mudar o caminho de turno: `run_turn`, `append_events` e o compact tratam
  sessão efêmera exatamente como qualquer outra.
- Qualquer UI (é o TCK-041).

## Comportamento esperado

`POST /api/sessions` com `{"scenarioId": "x", "startId": "rota-vilao", "ephemeral": true}`
cria uma sessão jogável idêntica a qualquer outra, com uma diferença: ela não
aparece em `GET /api/sessions`, e `DELETE /api/sessions/{id}` a apaga por
completo (sessão + eventos).

Se o app for fechado sem o `DELETE` chegar, a próxima subida do backend apaga as
efêmeras que sobraram — nenhuma efêmera sobrevive a um restart.

Sessão normal continua exatamente como hoje, inclusive em `GET /api/sessions/{id}`
(efêmera também é legível por id enquanto viva; é assim que o preview recarrega).

## Detalhes técnicos

**Por que persistir em vez de não persistir**: todo o caminho de turno já é
SQLite (`append_events` é caminho único desde o TCK-017, `get_compact`/
`set_compact` leem e escrevem na tabela). Uma segunda implementação em memória
duplicaria o event store e faria o preview divergir do jogo — que é exatamente o
que a spec de UI proíbe. A escolha é: persiste igual, é invisível na lista, e é
limpa por `DELETE` e no boot.

`SCHEMA_SQL`: acrescente `ephemeral INTEGER NOT NULL DEFAULT 0` na definição de
`sessions` (banco novo já nasce com a coluna). `_migrate_session_columns` ganha o
mesmo padrão dos campos de compact:

```python
if "ephemeral" not in columns:
    conn.execute("ALTER TABLE sessions ADD COLUMN ephemeral INTEGER NOT NULL DEFAULT 0")
```

Banco existente é migrado no `init_db()` sem perder nada; toda sessão antiga
vira `ephemeral = 0`, que é a verdade.

`list_sessions()`: `WHERE s.ephemeral = 0` no SELECT. Não filtre em Python — a
consulta é a fonte da verdade e a contagem de turnos é subquery.

`delete_session(session_id)`:

- lê a linha; não existe → `SessionNotFound`;
- `ephemeral == 0` → levanta `SessionNotEphemeral` (exceção nova no módulo);
- em uma transação `BEGIN IMMEDIATE`: `DELETE FROM events WHERE session_id = ?`
  e depois `DELETE FROM sessions WHERE id = ?` (nessa ordem, por causa do
  `PRAGMA foreign_keys=ON`), commit; `sqlite3.Error` → rollback + `emit`
  (`session_db_error`, `op="delete_session"`), como nos demais writers.

`purge_ephemeral_sessions()`: apaga, na mesma ordem, os eventos e as linhas de
toda sessão com `ephemeral = 1`. Chamado no fim de `init_db()`, depois da
migração. Emite `ephemeral_sessions_purged` com a contagem quando for maior que
zero.

Rota `DELETE /api/sessions/{session_id}` → 204 sem corpo; `SessionNotFound` →
404 `session not found`; `SessionNotEphemeral` → 409 `session is not ephemeral`.
A UI do preview chama com `keepalive` no unload e ignora a resposta.

`CreateSessionRequest` ganha `ephemeral: bool = False` (sem alias, o nome já é
camelCase-compatível). O `startId` já existe e já é honrado por
`create_session`; nada a fazer ali além de passar o novo argumento adiante.

## Contrato público

```
POST   /api/sessions  body: { scenarioId, startId?, ephemeral?: boolean }
       201 SessionDetail (inalterado)
GET    /api/sessions          -> 200 SessionSummary[]  (sem efêmeras)
GET    /api/sessions/{id}     -> 200 SessionDetail     (inclusive efêmera)
DELETE /api/sessions/{id}     -> 204 | 404 session not found
                                  | 409 session is not ephemeral
```

```python
# backend/app/sessions.py
class SessionNotEphemeral(Exception): ...
def create_session(scenario_id: str, start_id: str | None = None,
                   ephemeral: bool = False) -> SessionDetail: ...
def delete_session(session_id: str) -> None: ...
def purge_ephemeral_sessions() -> int: ...
```

Consumidor: TCK-041 (painel de preview: cria com `ephemeral: true`, troca de
start recriando, `DELETE` no restart e no unmount).

## Acceptance criteria

- [ ] `POST` com `ephemeral: true` devolve 201 e a sessão é jogável (turno
      funciona igual).
- [ ] A sessão efêmera **não** aparece em `GET /api/sessions`.
- [ ] `GET /api/sessions/{id}` da efêmera devolve 200 enquanto ela existe.
- [ ] `DELETE` de efêmera devolve 204 e apaga sessão e eventos.
- [ ] `DELETE` de sessão normal devolve 409 e não apaga nada.
- [ ] `DELETE` de id inexistente devolve 404.
- [ ] `init_db()` sobre um banco com efêmeras apaga todas e mantém as normais
      intactas.
- [ ] Banco criado antes deste ticket é migrado sem perder sessão nem evento.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente que muda de preparação (asserções preservadas):

- `test_sessions.py::test_list_sessions_orders_by_updated_at_desc` e
  `::test_get_sessions_route_lists_camel_case` continuam válidos porque criam
  sessões normais (o default de `ephemeral` é `False`). Nenhuma asserção muda.
- `::test_post_sessions_route_happy_path` afirma campos específicos do corpo,
  não o dicionário inteiro; o corpo não ganha campo novo (a resposta continua
  sendo `SessionDetail`), então segue passando sem alteração.
- `::test_init_db_is_idempotent` passa a exercitar também o purge; mantenha a
  asserção e acrescente o cenário novo abaixo em vez de reescrevê-lo.
- `::test_reopening_db_persists_state` continua provando persistência de sessão
  normal; acrescente o par efêmero como cenário novo.

Cenários novos:
- Feliz: criar efêmera + normal → `list_sessions()` traz só a normal;
  `get_session(efemera.id)` funciona.
- Feliz: jogar um turno na efêmera (fake stream) e confirmar que os eventos
  existem enquanto ela vive.
- Feliz: `DELETE` da efêmera → `read_events` vazio e `get_session` levanta
  `SessionNotFound`.
- Borda: `ephemeral: true` com `startId` explícito honra o start (paridade com
  `test_create_session_explicit_start`).
- Borda: `init_db()` chamado duas vezes seguidas com efêmera no banco apaga uma
  vez e não erra na segunda.
- Borda: migração — crie o banco, remova a coluna criando a tabela sem ela num
  arquivo separado, rode `init_db()` e confirme que a coluna aparece com default
  0 e as sessões continuam listáveis.
- Falha: `DELETE` de sessão normal é 409 e ela continua em `list_sessions()`.
- Falha: erro de SQLite no meio do delete faz rollback e a sessão continua
  íntegra (padrão de
  `test_append_events_is_atomic_on_failure`).

## Rollout e kill switch

N/A — sem flag. A migração é aditiva (coluna com default) e não reescreve linha
existente. Reverter o código com o banco já migrado é seguro: a coluna extra é
ignorada pelo código antigo.

## Observabilidade

Eventos:
- `session_created` (já existente) ganha a propriedade `ephemeral`.
- `ephemeral_sessions_purged` — `count`, emitido só quando `count > 0`.
- `session_deleted` — `session_id`, `events`.
- `session_db_error` (já existente) com `op="delete_session"`.

Métrica de sucesso: depois de uma tarde no builder, `GET /api/sessions` continua
listando só as sessões de verdade, e `ephemeral_sessions_purged` fica em zero na
maioria dos boots (sinal de que o `DELETE` do unmount está chegando).

## i18n

N/A — sem texto de usuário.
