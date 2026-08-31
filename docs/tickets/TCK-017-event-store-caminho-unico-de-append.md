---
id: TCK-017
title: Unificar a escrita do event store num único append transacional
status: done
points: 2
blockedBy: [TCK-015]
files:
  - backend/app/sessions.py
  - backend/tests/test_sessions.py
migration: false
ui: false
risk: low
---

## Problema

O event store tem hoje **dois** caminhos de escrita, e nenhum dos dois calcula o
`seq` de forma obviamente correta.

1. `append_events` (`backend/app/sessions.py:277`) abre `with conn:` e dentro
   dele faz `SELECT COALESCE(MAX(seq), 0) FROM events WHERE session_id = ?`
   seguido dos `INSERT`. O `with conn:` do sqlite3 do Python **não abre**
   transação: ele só faz commit/rollback ao sair. O `SELECT` roda em autocommit
   e o `BEGIN` implícito só nasce no primeiro `INSERT` (`isolation_level`
   default é `""`, ou seja, deferred). Duas escritas concorrentes na mesma
   sessão podem ler o mesmo `MAX(seq)`; hoje o que impede a corrupção é o
   `UNIQUE(session_id, seq)` do schema (`backend/app/sessions.py:35`) — a
   segunda escrita explode com `IntegrityError` em vez de serializar. Está
   correto por acidente, e o acidente aparece como turno perdido para o jogador
   (o `except sqlite3.Error` em `run_turn` transforma isso em erro de turno).
2. `set_compact` (`backend/app/sessions.py:318`) repete o mesmo `SELECT
   MAX(seq)+1` e o mesmo `INSERT` numa cópia colada. Duas cópias da regra de
   numeração é uma a mais: quando o TCK-015 mudou o payload do evento `compact`,
   mudar num lugar e esquecer o outro é o modo de falha óbvio.

## Escopo

Dentro:
- Transação explícita (`BEGIN IMMEDIATE`) envolvendo o `SELECT MAX(seq)` e os
  `INSERT` em `backend/app/sessions.py`.
- Função privada única de append (`_append_in_tx`) usada tanto por
  `append_events` quanto por `set_compact`.
- `set_compact` passa a gravar o evento `compact` pelo caminho unificado e a
  atualizar a projeção (`compact`, `compact_seq`, `updated_at`) na mesma
  transação.
- Testes de concorrência e de atomicidade em `backend/tests/test_sessions.py`.

Fora (explícito):
- Mudar as assinaturas públicas de `append_events`, `set_compact`, `get_compact`
  ou `read_events`: este ticket é interno ao módulo. As assinaturas são as
  publicadas pelo TCK-015.
- Trocar sqlite por outro store, pool de conexões, ou manter conexão aberta
  entre chamadas: `_connect()` por operação continua sendo o padrão do repo.
- Remover o `UNIQUE(session_id, seq)`: ele continua como rede de segurança, e
  removê-lo exigiria migração destrutiva.
- Retry automático em `SQLITE_BUSY`: fora de escopo, o motor é local e
  monousuário.

### Testes existentes que este ticket invalida

Grep em `backend/tests/`: **nenhum**. Nenhum teste afere o SQL emitido nem o
modo de transação; `backend/tests/test_sessions.py:173`
(`test_append_events_is_atomic_on_failure`) afere o resultado observável
(nenhum evento gravado quando um insert falha), que continua igual. Os testes de
`backend/tests/test_compact.py` que passam por `set_compact` continuam válidos
sem adaptação porque a assinatura e o efeito observável não mudam — este ticket
**não** edita `backend/tests/test_compact.py`, deliberadamente: os cenários de
`set_compact` deste ticket vivem em `test_sessions.py`, e `test_compact.py`
pertence aos tickets do compact.

## Comportamento esperado

Do ponto de vista do chamador: idêntico ao de hoje, exceto que duas escritas
simultâneas na mesma sessão **serializam** em vez de uma delas falhar com
`IntegrityError`. A numeração de `seq` continua contígua e por sessão, e o
evento `compact` continua ocupando um `seq` na mesma sequência dos turnos.

## Detalhes técnicos

- `conn.execute("BEGIN IMMEDIATE")` antes do `SELECT MAX(seq)`, com
  `conn.commit()` no caminho feliz. `BEGIN IMMEDIATE` pega o write lock na hora,
  que é exatamente o que falta hoje. Com `journal_mode=WAL` já ligado
  (`backend/app/sessions.py:112`), leituras concorrentes continuam passando.
- **Rollback em qualquer exceção, não só `sqlite3.Error`.** O caminho de falha
  mais provável nem é do sqlite: `json.dumps(payload)`
  (`backend/app/sessions.py:288`) levanta `TypeError` para payload não
  serializável, e é exatamente isso que
  `backend/tests/test_sessions.py:173` exercita
  (`test_append_events_is_atomic_on_failure`, com a classe `NotSerializable`).
  Hoje a atomicidade nesse caso depende do `conn.close()` do `finally`
  (`:301`), que faz rollback implícito da transação aberta — comportamento do
  módulo, não escolha do código. Com o `BEGIN IMMEDIATE` explícito, o rollback
  também vira explícito:

  ```python
  conn.execute("BEGIN IMMEDIATE")
  try:
      ...                 # SELECT MAX(seq), INSERTs, UPDATE
      conn.commit()
  except sqlite3.Error as exc:
      conn.rollback()
      emit("session_db_error", op="append_events", error=str(exc))
      raise
  except BaseException:
      conn.rollback()
      raise
  finally:
      conn.close()
  ```

  O `except sqlite3.Error` continua existindo só para emitir a telemetria que já
  existe; o `except BaseException` é o que garante a atomicidade para
  `TypeError`, `KeyboardInterrupt` e qualquer outra coisa. O `with conn:` sai.
- Alternativa rejeitada: `isolation_level=None` + gestão manual em todas as
  funções. Mexeria em `create_session` e `list_sessions` sem necessidade.
- **Armadilha**: `with conn:` **e** `BEGIN IMMEDIATE` explícito juntos levantam
  `sqlite3.OperationalError: cannot start a transaction within a transaction`.
  Escolha um; aqui o controle é explícito.
- Contenção: `sqlite3.connect` usa `timeout=5.0` por padrão e o código não o
  altera (`backend/app/sessions.py:111`), então a segunda thread a pedir o write
  lock espera até 5 s antes de levantar `OperationalError: database is locked`.
  É essa premissa que sustenta o cenário de concorrência abaixo, e é por isso
  que retry em `SQLITE_BUSY` fica fora de escopo: o motor é local e monousuário,
  e duas escritas simultâneas na mesma sessão são medidas em milissegundos.
- `_append_in_tx(conn, session_id, events, now) -> int` devolve o último `seq`
  gravado — é o que `set_compact` precisa para preencher `covered_seq` sem um
  segundo `SELECT`.
- `set_compact` continua emitindo `session_db_error` com `op="set_compact"` no
  `except sqlite3.Error`, e `append_events` com `op="append_events"`: os dois
  eventos de telemetria já existem e não mudam de nome.

## Contrato público

N/A. Nenhuma assinatura, rota ou schema novo é exposto para outro ticket; as
funções públicas de `backend/app/sessions.py` mantêm exatamente as assinaturas
publicadas pelo TCK-015.

## Acceptance criteria

- [ ] `append_events` e `set_compact` chamam o mesmo helper de append; o texto
      `SELECT COALESCE(MAX(seq), 0)` aparece **uma única vez** em
      `backend/app/sessions.py`.
- [ ] O `SELECT` de `MAX(seq)` roda depois de um `BEGIN IMMEDIATE` e antes do
      commit, na mesma conexão.
- [ ] Duas chamadas concorrentes de `append_events` na mesma sessão produzem
      `seq` contíguos e sem buraco, sem `IntegrityError`, com o `timeout=5.0`
      default do `sqlite3.connect` como única espera (nenhum retry no código).
- [ ] Falha no meio de um lote continua não gravando nenhum evento do lote nem
      atualizando `updated_at`, **e** o `rollback()` é explícito: o teste passa
      com uma exceção que não é `sqlite3.Error`.
- [ ] `set_compact` grava evento e projeção na mesma transação: um payload não
      serializável faz `json.dumps` levantar e nenhum evento `compact` fica no
      banco, com a projeção (`compact`, `compact_seq`) inalterada.
- [ ] `npm run check` verde.

## Cenários de teste

- Feliz: `append_events` de 3 eventos seguido de `set_compact` → `seq` 1,2,3,4
  em `read_events`, com o `compact` em 4.
- Feliz: `set_compact` devolve/registra `covered_seq` coerente com o último
  `seq` de turno anterior a ele.
- Borda: `append_events` com lista vazia → nenhum evento novo, `updated_at`
  atualizado (comportamento de hoje, preservado).
- Borda: duas threads chamando `append_events` na mesma sessão (usando
  `concurrent.futures.ThreadPoolExecutor` com duas tarefas e conexões
  independentes, já que o módulo abre uma conexão por chamada) → 4 eventos,
  `seq` de 1 a 4, nenhum duplicado. A serialização vem do `BEGIN IMMEDIATE` mais
  o `timeout=5.0` default do sqlite3.
- Falha (`append_events`): reusar o mecanismo já existente em
  `backend/tests/test_sessions.py:173` — um payload contendo uma instância de
  classe qualquer (`NotSerializable`) faz `json.dumps` levantar `TypeError`.
  Asserção nova: além do estado preservado que aquele teste já afere, o
  `rollback()` acontece antes do `close()`, verificado por uma segunda conexão
  aberta depois da exceção que não enxerga nenhum evento.
- Falha (`set_compact`): chamar `set_compact(session_id, "resumo", covered_seq,
  {"bad": object()})` → `TypeError` do `json.dumps`, nenhum evento `compact` no
  banco, e `get_compact` devolvendo o par anterior intacto. Este é o mecanismo
  de injeção de falha do caminho de compact: `set_compact` grava strings puras e
  o `hud` não passa por ele, então monkeypatch de `HudState` não serviria.
- Falha (`UPDATE sessions` de `append_events`): `hud` com um valor que faz
  `model_dump_json` levantar não é construível em pydantic v2; use o mesmo
  payload não serializável do caso acima, que já exercita o rollback do lote
  inteiro — incluindo o `UPDATE`.

## Rollout e kill switch

N/A. Mudança interna de transação, sem flag: não há estado intermediário para
desligar e o comportamento observável é o mesmo de hoje no caminho feliz.
Rollback é `git revert` do PR, sem migração associada.

## Observabilidade

Eventos: `session_db_error` (`op`, `error`) — já existente, agora emitido também
para falhas de transação (`BEGIN`/`COMMIT`), não só de `INSERT`.
Métrica de sucesso: zero ocorrências de `session_db_error` com `error` contendo
`UNIQUE constraint failed: events.session_id, events.seq` no log de uma sessão
jogada de ponta a ponta.

## i18n

N/A. Nenhum texto de usuário.
