---
id: TCK-079
title: Exportar as sessões jogadas como JSONL de juiz, director e minds
status: ready
points: 5
blockedBy: [TCK-078]
files:
  - backend/app/dataset.py
  - backend/tests/test_dataset_export.py
migration: false
ui: false
risk: low
---

## Problema

A sub-fase 4.2 do plano precisa transformar as sessões do `sessions.db` em
exemplos de treino por tarefa. Hoje não existe nenhum caminho de saída de dados
do projeto: o banco só é lido pelas rotas de sessão, e o único jeito de ver o que
foi jogado é abrir SQLite na mão.

O TCK-078 entregou `replay_session`, que devolve por turno todos os argumentos
que os builders receberam. Falta quem chame os builders com esses argumentos,
descubra o que o engine aceitou naquele turno e escreva as linhas.

Sem isso, a Fase 4 não tem dado nenhum para treinar o utility próprio, e as
sub-fases 4.3 e 4.4 ficam bloqueadas em zero.

## Escopo

Dentro:
- `backend/app/dataset.py` novo: subcomando `export` com `argparse`, a função
  `export_dataset(out_dir)`, a decisão de `split` e as três funções que montam a
  linha de cada tarefa.
- `backend/tests/test_dataset_export.py` novo.

Fora (explícito):
- `narrator.jsonl`. Precisa do texto cru do narrador com as tags, que o event
  store não guarda; é o TCK-080, que também passa a persistir o cru. Este ticket
  escreve **três** arquivos.
- Subcomandos `label` e `eval`: TCK-081 e TCK-082. O `argparse` já nasce com
  subparser (`add_subparsers(dest="command", required=True)`) para os dois
  entrarem sem reescrever a raiz, mas só `export` existe aqui.
- Formatar para treino (prefixo de tarefa, chat template): TCK-083, em
  `backend/app/training.py`. Este ticket escreve o dado bruto por tarefa, no
  formato de mensagens do próprio engine.
- Curadoria, deduplicação, balanceamento por cenário e filtro de qualidade. São
  trabalho manual do usuário sobre o JSONL, fora do repositório.
- Sessões efêmeras. `list_sessions` (`sessions.py:242-271`) já filtra
  `ephemeral = 0`; é a definição de "sessão de verdade" que o exportador usa.
- Dependência Python nova. `argparse`, `json`, `hashlib` e `pathlib` são da
  biblioteca padrão; `backend/pyproject.toml` **não** muda.
- Qualquer arquivo de `frontend/`.

## Comportamento esperado

`uv run python -m app.dataset export --out ../datasets/2026-09` percorre todas as
sessões não efêmeras do `sessions.db`, rejoga cada uma e grava três arquivos
JSONL no diretório indicado (criado se não existir): `judge.jsonl`,
`director.jsonl`, `minds.jsonl`. No fim imprime um resumo em stdout com quantas
sessões e turnos entraram, quantas linhas por tarefa e quantos itens foram
pulados, por motivo.

Sessão cujo cenário não carrega mais é pulada inteira, sem derrubar a exportação.
Turno que o replay marcou como não fiel (`exact is False`) é pulado.

O comando é somente-leitura sobre o banco e idempotente: rodar duas vezes no
mesmo diretório reescreve os mesmos arquivos com o mesmo conteúdo, na mesma
ordem.

## Detalhes técnicos

### Formato da linha

Uma linha JSON por exemplo, `ensure_ascii=False`, `\n` no fim:

```json
{"task": "judge", "locale": "pt-br", "scenario_id": "exemplo-escola",
 "session_id": "ab12...", "turn": 3, "split": "train",
 "messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}],
 "engine_label": {"stats": {"reputacao": -5}}, "applied": true}
```

`messages` é **exatamente** o que o builder da tarefa montaria naquele turno —
nada de reescrever o prompt aqui. As chamadas, com os campos do `TurnSnapshot`:

```python
build_judge_messages(scenario, snap.hud_after_tags, snap.message,
                     snap.narrator_text, snap.touched_ids)
build_director_messages(scenario, snap.hud_start, snap.cast_before,
                        snap.message, window)
build_minds_messages(scenario, snap.cast_after, snap.minds_before,
                     snap.message, snap.narrator_text)
```

`window` do director é `events_to_messages(snap.history_before[-(DIRECTOR_WINDOW_TURNS * 2):], locale)`,
a mesma fatia de `turn.py:350-353`. `events_to_messages` e
`DIRECTOR_WINDOW_TURNS` vêm de `turn.py`/`director.py`; importar `turn` a partir
de `dataset` é seguro (nem `turn.py` nem `replay.py` importam `dataset`).

### `engine_label`

O que o engine efetivamente aplicou naquele turno, no **mesmo formato** que o
modelo teria que emitir:

- juiz: `{"stats": {id: delta}}` a partir dos eventos `stat` do turno com
  `source == "judge"` (`turn.py:504`, `hud.py:197-198`). Sem nenhum, `{"stats": {}}`.
- director: `{"scene": snap.cast_after}`. É o elenco que valeu depois do turno,
  que é o que `validate_cast_ids` devolveu quando houve evento `cast`, e o
  elenco mantido quando não houve (`turn.py:376-385` só grava o evento quando os
  ids mudaram).
- minds: `{id: {attitude, emoji, event}}` só para os ids cujo valor **mudou**
  em relação a `snap.minds_before` — porque `merge_minds` (`minds.py:177-242`)
  recebe um delta e devolve o mapa completo; o alvo do modelo é o delta, não o
  mapa. Sem evento `minds` no turno, `{}`.

`applied: bool` diz se o engine registrou algum efeito daquela tarefa naquele
turno (evento `stat` de juiz, evento `cast`, evento `minds`).

**Ambiguidade declarada, e é por isso que existe a rotulagem por professor.**
`engine_label` vazio com `applied: false` significa as duas coisas ao mesmo
tempo: "o utility disse que nada mudou" e "o utility falhou, foi recusado ou
estava desligado por flag". O event store não distingue os casos — a recusa só
existe no log (`judge_rejected`), não nos eventos. Treinar direto nessas linhas
ensinaria o modelo a calar quando o Cydonia quebrou. A linha é exportada mesmo
assim, com `applied` explícito, e quem decide o que fazer com ela é o TCK-081
(rótulo do professor) e a curadoria manual. **Não** filtre por `applied` aqui: o
exportador não tem opinião, ele só não mente.

### `split`

```python
HOLDOUT_PCT = 10

def split_for(session_id: str) -> str:
    bucket = int(hashlib.sha256(session_id.encode()).hexdigest()[:8], 16) % 100
    return "holdout" if bucket < HOLDOUT_PCT else "train"
```

Determinístico e por **sessão**, nunca por turno: dois turnos da mesma sessão
compartilham elenco, mundo e personagens, e separá-los vazaria o holdout para o
treino. `sha256` e não `hash()`, que é aleatorizado por processo em Python e
daria um corte diferente a cada execução.

### Varredura

```python
for summary in list_sessions():                  # ephemeral = 0 (sessions.py:250)
    try:
        replay = replay_session(summary.id)
    except (ScenarioNotFound, SessionNotFound):
        skipped["scenario"] += 1
        continue
    for snap in replay.turns:
        if not snap.exact:
            skipped["inexact"] += 1
            continue
        ...
```

Ordem estável: `list_sessions` ordena por `updated_at DESC, created_at DESC,
id DESC` (`sessions.py:251`) e os turnos vêm em ordem de `seq`. É o que torna
duas execuções byte a byte iguais.

Os três arquivos são abertos uma vez cada, no início, e escritos em streaming —
sessão de 200 turnos não acumula lista em memória.

### CLI

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.dataset")
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    ...

if __name__ == "__main__":
    raise SystemExit(main())
```

`main` recebe `argv` para o teste chamar `dataset.main(["export", "--out", str(tmp)])`
sem `subprocess` e sem mexer em `sys.argv`. Devolve `0` em sucesso.

O banco lido é o de `db_path()` (`sessions.py:121-125`), que respeita
`OOC_SESSIONS_DB`. É assim que o teste aponta para um SQLite temporário e é assim
que o usuário exporta de uma cópia do banco em vez do banco vivo.

### Ressalva de porte

Estimativa ~200 linhas de `dataset.py` e ~230 de teste, ~430 no total.
Exceção registrada pelo coordenador do HRZ Workflow (03/09/2026): o porte de
~430 é aceito porque as três tarefas compartilham o mesmo laço de exportação e
separá-las triplicaria o código de leitura. O corte é obrigatório e já decidido:
os cenários de `engine_label` das três tarefas são um único teste parametrizado.
Não corte o cenário de holdout determinístico nem o de sessão com cenário
apagado.

## Contrato público

```python
# backend/app/dataset.py
TASKS: tuple[str, ...]          # ("judge", "director", "minds")
HOLDOUT_PCT: int                # 10

def split_for(session_id: str) -> str            # "train" | "holdout"
def export_dataset(out_dir: Path) -> dict        # contadores do resumo
def main(argv: list[str] | None = None) -> int
```

Formato de linha (consumido por TCK-081, TCK-082 e TCK-083):

```
{"task": "judge" | "director" | "minds",
 "locale": str, "scenario_id": str, "session_id": str, "turn": int,
 "split": "train" | "holdout",
 "messages": [{"role": str, "content": str}, ...],
 "engine_label": object, "applied": bool}
```

Arquivos de saída: `<out>/judge.jsonl`, `<out>/director.jsonl`,
`<out>/minds.jsonl`.

Consumidores já enfileirados: TCK-080 (acrescenta `narrator.jsonl` com o mesmo
envelope), TCK-081 (`label` lê `messages` e escreve `teacher_label` na mesma
linha), TCK-082 (`eval` lê o holdout), TCK-083 (`training` converte para chat
format).

## Acceptance criteria

- [ ] `uv run python -m app.dataset export --out DIR` cria `DIR` se não existir e
      grava `judge.jsonl`, `director.jsonl` e `minds.jsonl`.
- [ ] Sessão de 2 turnos gera 2 linhas em cada um dos três arquivos.
- [ ] A linha de `judge.jsonl` tem `messages` **idêntico** ao que
      `build_judge_messages(scenario, snap.hud_after_tags, snap.message,
      snap.narrator_text, snap.touched_ids)` devolve (o teste compara com a
      chamada direta, não com string fixa).
- [ ] Idem para director (com `hud_start`, `cast_before` e a janela de
      `DIRECTOR_WINDOW_TURNS * 2` eventos) e para minds (com `cast_after` e
      `minds_before`).
- [ ] Turno em que o juiz mexeu em `reputacao` em -5 tem
      `engine_label == {"stats": {"reputacao": -5}}` e `applied is true`.
- [ ] Turno sem efeito do juiz tem `engine_label == {"stats": {}}` e
      `applied is false`, e **é exportado**.
- [ ] `engine_label` do minds traz só os ids cujo valor mudou em relação a
      `minds_before`, e não o mapa inteiro.
- [ ] `split` é o mesmo para todos os turnos de uma mesma sessão e para todas as
      tarefas, e é estável entre duas execuções do processo.
- [ ] Com 40 sessões de ids conhecidos, a fração `holdout` fica entre 0 e 25% e é
      idêntica em duas execuções (o teste fixa os ids, então o número é exato).
- [ ] Sessão efêmera não aparece em nenhum arquivo.
- [ ] Sessão cujo cenário foi apagado é pulada e a exportação termina com
      código 0, contando o descarte no resumo.
- [ ] Turno com `exact is False` não vira linha em nenhum arquivo.
- [ ] Banco sem sessão nenhuma gera os três arquivos vazios e sai com código 0.
- [ ] Duas execuções seguidas produzem arquivos byte a byte idênticos.
- [ ] `npm run check` verde sem editar nenhum teste existente.

## Cenários de teste

Suíte existente que muda de preparação: **nenhuma**. O ticket só acrescenta
`backend/app/dataset.py` e um arquivo de teste novo; nenhum módulo existente é
editado. Verificado por Grep: não há ocorrência de `dataset` em `backend/app/`
nem em `backend/tests/`.

Preparação de `backend/tests/test_dataset_export.py`: mesmo molde do
`test_replay.py` do TCK-078 —
`monkeypatch.setenv("OOC_SESSIONS_DB", str(tmp_path / "sessions.db"))`
(`test_sessions.py:69-72`) e
`monkeypatch.setattr("app.scenario.scenarios_dir", lambda: root)`
(`test_sessions.py:74-79`), com `create_session` + `append_events` montando os
eventos. Saída em `tmp_path / "out"`. Nenhum teste toca rede nem provider: o
exportador não chama LLM nenhum.

- Feliz: sessão de 2 turnos com tag, stat de juiz, evento `cast` e evento
  `minds` → 6 linhas, envelope completo, `messages` conferido contra a chamada
  direta dos builders.
- Feliz: `engine_label` das três tarefas num turno com efeito.
- Feliz: cenário em `locale: en` → `locale` da linha é `en` e o prompt sai em
  inglês (afere-se por uma palavra do template `en` de `judge.py:44-58`).
- Borda: turno sem efeito nenhum → linhas com `applied: false` presentes.
- Borda: duas sessões de cenários diferentes → `scenario_id` correto em cada
  linha, arquivos com as linhas das duas.
- Borda: sessão efêmera (`create_session(..., ephemeral=True)`) ignorada.
- Borda: banco vazio → três arquivos vazios, código 0.
- Borda: `--out` apontando para diretório já existente com arquivos antigos → é
  sobrescrito, não anexado.
- Borda: `split_for` chamado direto devolve o mesmo valor para o mesmo id em
  chamadas repetidas, e `holdout` para pelo menos um id conhecido fixado no
  teste.
- Falha: cenário apagado depois da sessão criada → sessão pulada, resumo com o
  descarte, código 0.
- Falha: `main([])` sem subcomando sai com `SystemExit` (argparse), e
  `main(["export"])` sem `--out` também.

## Rollout e kill switch

N/A. Comando de linha de comando, rodado à mão, fora do `npm run dev` e de
qualquer rota. Não é importado por `main.py`, por `turn.py` nem por nenhum
módulo do servidor, então não há caminho pelo qual ele afete uma partida. Kill
switch é não rodar o comando.

## Observabilidade

Eventos: N/A no sentido de `emit` — o exportador roda fora do servidor e escrever
no `~/.ooc-local/logs/app.log` a partir de um script de lote poluiria o log que o
relatório do TCK-086 lê. O resumo vai para **stdout**:

```
sessions=12 turns=340 judge=340 director=340 minds=340 skipped_scenario=1 skipped_inexact=7
```

`export_dataset` devolve esse mesmo dicionário de contadores, que é o que o teste
afere (stdout é conferido só num cenário, para garantir que o comando imprime).

Métrica de sucesso: exportação da base real produz ≥ 500 linhas por tarefa com
`applied: true` e `skipped_inexact` abaixo de 5% dos turnos. Abaixo disso não há
dado suficiente para treinar o utility e a resposta é jogar mais, em mais de um
cenário.

## i18n

N/A para UI. O campo `locale` da linha carrega o `scenario.meta.locale` para o
dataset poder ser balanceado por língua no TCK-083; os prompts exportados já
nascem no idioma do cenário porque os builders escolhem o template por
`scenario.meta.locale` (`judge.py:110`, `director.py:76`, `minds.py:87`).
