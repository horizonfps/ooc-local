---
id: TCK-005
title: Persistir sessões em event store SQLite e expor criar, listar e abrir
status: done
points: 5
blockedBy: [TCK-001]
files:
  - backend/app/sessions.py
  - backend/app/main.py
  - backend/tests/test_sessions.py
migration: true
ui: false
risk: medium
---

## Problema

O app não guarda nada: `/api/chat` é stateless e o histórico vive só no `useState`
de `frontend/src/App.tsx`. O critério de verde da Fase 1 é literalmente "jogo 5
turnos, fecho o app, reabro, continuo a sessão do ponto onde parei" — sem
persistência a fase não fecha. A UI (TCK-009, TCK-012) já foi especificada
contra três rotas de sessão que ainda não existem.

## Escopo

Dentro:
- `backend/app/sessions.py`: conexão SQLite em `~/.ooc-local/sessions.db`,
  criação de schema idempotente (`CREATE TABLE IF NOT EXISTS`), event store
  append-only e as funções de serviço do contrato público.
- Rotas em `backend/app/main.py`: `POST /api/sessions`, `GET /api/sessions`,
  `GET /api/sessions/{session_id}`.
- Modelos de resposta pydantic (`SessionSummary`, `SessionDetail`, `TurnView`).
- HUD inicial da sessão gravado na criação, a partir de `hud_from_start`
  (TCK-001).
- `backend/tests/test_sessions.py`, com o caminho do banco redirecionado para
  `tmp_path`.

Fora (explícito):
- Jogar o turno (`POST /api/sessions/{id}/turn`) — TCK-006. Nenhuma chamada de
  LLM entra aqui.
- Deletar, renomear ou duplicar sessão — a UI da Fase 1 não tem esses controles
  (spec de UI, tema 01).
- Sessão efêmera do preview do builder (`ephemeral: true`) — Fase 2.
- Compact e janela de contexto — TCK-007/TCK-006. Este ticket grava eventos, não
  monta contexto.
- Migração de dados: não existe banco anterior. `CREATE TABLE IF NOT EXISTS` é
  toda a "migration" da Fase 1; não introduzir alembic.

## Comportamento esperado

Do ponto de vista do chamador da API:

- `POST /api/sessions {"scenarioId": "exemplo-escola"}` cria a sessão, grava o
  HUD inicial e devolve 201 com a sessão já pronta para jogar (prólogo incluso,
  `turns: []`). `scenarioId` inexistente → 404. Corpo sem `scenarioId` → 422
  (validação do FastAPI). `startId` opcional; ausente usa `default_start` do
  cenário, e `startId` inexistente → 404.
- `GET /api/sessions` devolve a lista de sessões ordenada por `updatedAt`
  decrescente — a última jogada no topo, que é o caso de uso do critério de
  verde. Sem sessões, 200 com `[]`.
- `GET /api/sessions/{id}` devolve prólogo, guia, turnos em ordem cronológica e
  HUD atual. Id inexistente → 404 com `{"detail": "session not found"}`.
- O event store é append-only: eventos nunca são atualizados nem apagados. A
  linha da sessão guarda projeções mutáveis (`hud`, `updated_at`) para a
  listagem não precisar varrer eventos.

## Detalhes técnicos

- `sqlite3` da stdlib (nada de ORM). Conexão por chamada, `check_same_thread`
  default, `PRAGMA journal_mode=WAL` e `PRAGMA foreign_keys=ON` na abertura.
- Caminho do banco: `DB_PATH = CONFIG_DIR / "sessions.db"` reusando `CONFIG_DIR`
  de `app.config` (`~/.ooc-local`). Expor `db_path()` que consulta
  `OOC_SESSIONS_DB` do ambiente antes do default — é assim que o teste aponta
  para `tmp_path` sem monkeypatch de módulo.
- Schema:

```sql
CREATE TABLE IF NOT EXISTS sessions (
  id            TEXT PRIMARY KEY,
  scenario_id   TEXT NOT NULL,
  scenario_name TEXT NOT NULL,
  start_id      TEXT NOT NULL,
  created_at    TEXT NOT NULL,   -- ISO-8601 UTC com sufixo Z
  updated_at    TEXT NOT NULL,
  hud           TEXT NOT NULL    -- HudState em JSON
);
CREATE TABLE IF NOT EXISTS events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL REFERENCES sessions(id),
  seq        INTEGER NOT NULL,
  kind       TEXT NOT NULL,      -- player_turn | narrator_turn | tag | compact
  payload    TEXT NOT NULL,      -- JSON
  created_at TEXT NOT NULL,
  UNIQUE(session_id, seq)
);
CREATE INDEX IF NOT EXISTS events_session_seq ON events(session_id, seq);
```

- `seq` é por sessão, começa em 1, calculado como `MAX(seq)+1` dentro da mesma
  transação do insert; a `UNIQUE(session_id, seq)` é a rede de segurança contra
  corrida.
- `append_events(session_id, events)` grava a lista inteira numa transação só —
  é o que o TCK-006 usa para gravar turno do jogador + turno do narrador + tags
  atomicamente (turno pela metade não pode existir no banco).
- `id` da sessão = `uuid4().hex`.
- `turns` da resposta são derivados dos eventos `player_turn`/`narrator_turn` em
  ordem de `seq`; `index` começa em 1 e é compartilhado pelo par
  (jogador e narrador do mesmo turno têm o mesmo `index`). `kind: "compact"` e
  `kind: "tag"` nunca aparecem na resposta.
- `prologue` e `playGuide` vêm do start do cenário na hora da leitura (não são
  copiados para o banco): editar o cenário em disco e reabrir a sessão reflete a
  edição, que é o princípio "arquivo é a fonte da verdade" da spec §2.
  Consequência aceita e documentada: cenário renomeado/apagado quebra sessões
  antigas — `GET /api/sessions/{id}` responde 404 com
  `{"detail": "scenario not found"}` e a listagem usa o `scenario_name`
  gravado (por isso ele é desnormalizado na tabela).
- JSON de resposta em camelCase (`scenarioId`, `turnCount`, `updatedAt`), como a
  spec de UI assume; usar `alias` + `model_config = ConfigDict(populate_by_name=True)`
  e `response_model_by_alias=True`.

Testes existentes que este ticket invalida: **nenhum**.
`backend/tests/test_chat.py` e `test_flags.py` só exercitam `/api/chat`;
`test_config.py` só o loader de config. As rotas novas são adicionadas ao mesmo
`app`, sem alterar as existentes.

## Contrato público

```
POST /api/sessions            body: {"scenarioId": str, "startId": str | null}
  201 -> SessionDetail
  404 -> {"detail": "scenario not found"} | {"detail": "start not found"}

GET  /api/sessions
  200 -> [SessionSummary]     # updatedAt desc

GET  /api/sessions/{id}
  200 -> SessionDetail
  404 -> {"detail": "session not found"} | {"detail": "scenario not found"}
```

```ts
type SessionSummary = {
  id: string; scenarioId: string; scenarioName: string;
  turnCount: number; updatedAt: string; location: string;
}
// location = hud["location"] da projeção gravada na linha da sessão
type TurnView = { index: number; role: 'player' | 'narrator'; text: string }
type SessionDetail = {
  id: string; scenarioId: string; scenarioName: string;
  prologue: string; playGuide: string | null;
  turns: TurnView[]; hud: HudState;     // HudState: TCK-001
}
```

```python
# backend/app/sessions.py  (consumido pelo TCK-006 e TCK-007)
def db_path() -> Path: ...
def init_db() -> None: ...
def create_session(scenario_id: str, start_id: str | None = None) -> SessionDetail: ...
def list_sessions() -> list[SessionSummary]: ...
def get_session(session_id: str) -> SessionDetail: ...              # SessionNotFound
def get_session_row(session_id: str) -> SessionRow: ...
def read_events(session_id: str, kinds: tuple[str, ...] | None = None) -> list[Event]: ...
def append_events(session_id: str, events: list[NewEvent], hud: HudState | None = None) -> None: ...
class SessionNotFound(Exception): ...

class SessionRow(BaseModel):
    id: str
    scenario_id: str
    start_id: str
    hud: HudState

class Event(BaseModel):
    id: int
    seq: int
    kind: str
    payload: dict
    created_at: str
```

`NewEvent = (kind: str, payload: dict)`. `append_events` atualiza `updated_at`
sempre e `hud` quando recebido, na mesma transação.

Schema do `payload` por `kind` (contrato consumido pelo TCK-006 e TCK-007;
`TurnView.text` deriva daqui):

```python
player_turn:   {"text": str}                 # mensagem crua do jogador
narrator_turn: {"text": str}                 # texto já limpo de tags
tag:           {"kind": str, "args": list[str], "raw": str, "valid": bool}
compact:       {...}                         # reservado ao TCK-007
```

## Acceptance criteria

- [ ] `POST /api/sessions` com o cenário exemplo responde 201, com `turns: []`,
      `prologue` não vazio e `hud.turn == 0` com os defaults do start.
- [ ] Duas sessões criadas → `GET /api/sessions` devolve as duas, mais recente
      primeiro, com `turnCount` correto.
- [ ] `GET /api/sessions/{id}` devolve os turnos em ordem de `seq`, pares
      jogador/narrador com o mesmo `index`.
- [ ] Ids inexistentes (sessão, cenário, start) respondem 404 com `detail`
      específico, nunca 500.
- [ ] `append_events` com dois eventos e HUD novo grava tudo ou nada: forçando
      falha no segundo insert (segundo `NewEvent` com `payload` não serializável
      em JSON), nenhum evento fica no banco e o HUD antigo permanece.
- [ ] Reabrir o banco (nova conexão) devolve o mesmo estado — persistência real,
      não cache em memória.
- [ ] `init_db()` rodado duas vezes não falha nem duplica tabela.
- [ ] Resposta em camelCase, conforme o contrato.
- [ ] `npm run check` verde.

## Cenários de teste

- Feliz: criar sessão → listar → abrir → os três respondem coerentes entre si.
- Feliz: `append_events` com um `player_turn` e um `narrator_turn` → `GET`
  devolve dois `TurnView` com `index == 1`.
- Borda: sessão sem nenhum evento → `turns: []` e `turnCount: 0` (a UI mostra
  `sessions.item.turnsZero`).
- Borda: `startId` explícito diferente do default → prólogo do start pedido.
- Borda: `updatedAt` de duas sessões criadas no mesmo segundo → ordenação
  estável (desempate por `created_at`, depois por `id`), sem flakiness no teste.
- Falha: `POST` com `scenarioId` inexistente → 404 e **nenhuma** linha criada em
  `sessions`.
- Falha: `GET /api/sessions/{id}` com id aleatório → 404 `session not found`.
- Falha: cenário apagado do disco depois da sessão criada → `GET` da sessão
  responde 404 `scenario not found` e a **listagem continua funcionando**,
  usando o `scenario_name` gravado.

## Rollout e kill switch

Sem flag: são rotas novas, sem consumidor até o TCK-009, e desligá-las não
adianta (a UI da Fase 1 não funciona sem sessão). O rollback é reverter o PR; o
banco em `~/.ooc-local/sessions.db` é local, descartável e recriado do zero por
`init_db()` — apagar o arquivo é o "reset de fábrica", e isso vai escrito no
ticket porque é a recuperação de qualquer estado corrompido durante a fase.

## Observabilidade

Eventos: `session_created` (`session_id`, `scenario_id`, `start_id`);
`session_db_error` (`op`, `error`) quando o SQLite levanta.
Métrica de sucesso: sessão criada, fechada e reaberta com o mesmo histórico e o
mesmo HUD (critério de verde da fase).

## i18n

N/A — a API devolve conteúdo do cenário (no idioma do cenário) e `detail` de
erro em inglês, técnico, não exibido cru: a UI mapeia status HTTP para as chaves
`game.notFound.*` / `sessions.error.*` criadas no TCK-008.
