---
id: TCK-086
title: Relatório de latência, rejeição e tags por modelo a partir do log
status: ready
points: 3
blockedBy: [TCK-077]
files:
  - backend/app/telemetry.py
  - backend/tests/test_telemetry_report.py
migration: false
ui: false
risk: low
---

## Problema

O loop de verde da Fase 4 é uma comparação: "turno completo em menos de 30 s",
"utility com zero rejeição de formato", "narrator emite `[SUGGEST:]` e `[STAT:]`
em pelo menos 8 dos 10 turnos", tudo isso contra a linha de base do Cydonia. Os
números para responder já são escritos a cada turno em `~/.ooc-local/logs/app.log`
por `emit` (`observability.py:22-23`): `game_turn` com `duration_ms`, `tags`,
`suggestions` e `model`; `judge_applied`/`judge_rejected` e os pares equivalentes
de director e minds com `duration_ms`.

Só que ninguém lê. Hoje a única forma de comparar dois modelos é abrir um arquivo
de log rotacionado e contar `grep` na mão, o que ninguém faz duas vezes — e sem
esse número a decisão entre o Cydonia e o modelo próprio vira impressão.

## Escopo

Dentro:
- `backend/app/telemetry.py` novo: leitura e parse das linhas do log (incluindo
  os arquivos rotacionados), agregação por modelo e por papel, subcomando
  `report` com `argparse`.
- `backend/tests/test_telemetry_report.py` novo.

Fora (explícito):
- UI. O relatório é de terminal; nenhum arquivo de `frontend/` é tocado e nenhuma
  rota é criada. O plano não pede tela para isso.
- Mudar `backend/app/observability.py`. O formato do log
  (`"%(asctime)s %(levelname)s %(message)s"` mais `event` e JSON,
  `observability.py:17-23`) é lido como está. Quem acrescenta `model` e
  `structured` aos eventos de recusa é o TCK-077, e este relatório funciona com
  ou sem eles.
- Mudar `backend/app/turn.py` ou qualquer emissor de telemetria. Se um campo
  faltar, o relatório o trata como ausente; não é aqui que se conserta emissor.
- Banco de séries temporais, gráfico, retenção, exportação. Uma leitura, uma
  tabela.
- Correlacionar com o dataset ou com a concordância do TCK-082. São dois números
  que o usuário compara a olho, como o plano descreve.
- Dependência Python nova: `statistics`, `json`, `datetime` e `argparse` são da
  biblioteca padrão.

## Comportamento esperado

```
uv run python -m app.telemetry report --since 2026-09-03T18:00:00
```

Lê o log (e os arquivos rotacionados), filtra pelo instante dado quando houver, e
imprime uma tabela por modelo com: mediana e p90 de duração do turno completo e
de cada chamada do utility, taxa de rejeição de formato por subsistema, média de
tags e de sugestões por turno.

Log inexistente: mensagem e código 0 — não ter jogado ainda não é erro. Linha
corrompida: pulada e contada, nunca derruba o relatório.

## Detalhes técnicos

### Parse da linha

O formatador é `"%(asctime)s %(levelname)s %(message)s"` (`observability.py:17`)
e a mensagem vem de `logger.info("%s %s", event, json.dumps(props,
ensure_ascii=False))` (`observability.py:23`): o `ensure_ascii=False` é o que
põe acento e emoji no log sem escape, e o parser precisa ler UTF-8. O
`asctime` default do `logging` tem um espaço no meio (`2026-09-03 18:04:11,231`),
então:

```python
date, clock, level, rest = line.split(" ", 3)
event, payload = rest.split(" ", 1)
props = json.loads(payload)
when = datetime.strptime(f"{date} {clock}", "%Y-%m-%d %H:%M:%S,%f")
```

Qualquer `ValueError`/`JSONDecodeError` nesse bloco → linha pulada, contador
`malformed` incrementado. Linhas de log de bibliotecas de terceiros não chegam
aqui porque o handler está no logger `"ooc"` (`observability.py:9`), mas uma
linha truncada por rotação no meio da escrita chega, e é o caso real que o
contador cobre.

O `asctime` é hora **local e ingênua**, sem fuso — é o que o `logging` escreve. O
`--since` é lido com `datetime.fromisoformat` e, se vier com fuso, o comando sai
com código 2 e explica que a comparação é em hora local. Converter fuso em cima
de um carimbo que não tem fuso seria inventar informação.

### Arquivos lidos

`LOG_PATH` (`observability.py:7`) mais os backups do `RotatingFileHandler`
(`backupCount=3`, `observability.py:16`): `app.log.3`, `app.log.2`, `app.log.1`,
`app.log` — nessa ordem, do mais antigo para o mais novo. Ler só `app.log`
descartaria silenciosamente a maior parte de uma sessão de comparação, porque o
arquivo rotaciona a cada 2 MB. `--log PATH` sobrescreve o caminho base (é como o
teste aponta para um `tmp_path`).

### Agregação

Chave: `(evento, model)`, com `model` vindo de `props.get("model")` e caindo em
`"unknown"` quando ausente — é o caso das linhas gravadas antes do TCK-077, em
que `judge_rejected` e `*_failed` não carregavam o modelo. Um bucket `unknown`
visível é melhor que somar peras com maçãs.

Por modelo, o relatório imprime:

- **turno**: `n`, mediana e p90 de `game_turn.duration_ms`, média de
  `game_turn.tags` e de `game_turn.suggestions` por turno, e quantos `game_turn`
  saíram com `error` não-nulo.
- **juiz / director / minds**: `n` (`applied` + `rejected`), mediana e p90 de
  `duration_ms` das duas, `rejected_rate` = `rejected / (applied + rejected)` e
  `failed` (contagem de `*_failed`, que é falha de provider, não de formato, e
  por isso fica **fora** da taxa).

Quando o campo `structured` existir (TCK-077), o mesmo modelo aparece em duas
linhas, uma por valor — é exatamente a comparação "com schema x sem schema" que a
sub-fase 4.1 quer medir. Ausente, uma linha só, com `structured=-`.

Percentis com a biblioteca padrão: `statistics.median` e p90 por posto mais
próximo (`sorted_values[min(n - 1, int(math.ceil(0.9 * n)) - 1)]`), sem
interpolação. Determinístico, testável com listas pequenas, sem numpy.

`--model NOME` filtra o relatório a um modelo só, para comparar duas execuções
sem ruído.

### Saída

```
model=Cydonia-24B-v4.3 structured=-
  turn      n=10  p50=41200ms  p90=52100ms  tags/turn=1.4  suggestions/turn=2.1  errors=0
  judge     n=10  p50=3100ms   p90=4200ms   rejected=0.30  failed=0
  director  n=10  p50=2400ms   p90=3000ms   rejected=0.20  failed=0
  minds     n=10  p50=3800ms   p90=5100ms   rejected=0.10  failed=0
```

`report(...)` devolve a mesma estrutura como dicionário, que é o que o teste
afere; a impressão é conferida em um cenário só.

## Contrato público

```python
# backend/app/telemetry.py
TURN_EVENT: str                      # "game_turn"
SUBSYSTEMS: tuple[str, ...]          # ("judge", "director", "minds")

def read_lines(base_path: Path) -> Iterator[tuple[datetime, str, dict]]
def report(base_path: Path, *, since: datetime | None = None,
           model: str | None = None) -> dict
def main(argv: list[str] | None = None) -> int

# CLI
# uv run python -m app.telemetry report [--since ISO] [--log PATH] [--model NOME]
```

Nenhum ticket desta fase consome estas assinaturas; o consumidor é o
`training/eval.md` (TCK-083), que apenas documenta o comando.

## Acceptance criteria

- [ ] Log com 3 `game_turn` do mesmo modelo produz `n=3`, mediana e p90
      corretos (valores escolhidos no teste para a conta ser conferível à mão).
- [ ] `tags/turn` e `suggestions/turn` são a média por `game_turn`, e `errors`
      conta os `game_turn` com `error` não-nulo.
- [ ] 7 `judge_applied` e 3 `judge_rejected` dão `rejected == 0.3` e `n == 10`;
      `judge_failed` não entra na taxa e aparece em `failed`.
- [ ] Dois modelos no mesmo log saem em blocos separados; `--model` filtra um.
- [ ] Linhas com `structured: true` e `structured: false` do mesmo modelo saem em
      blocos separados; linha sem o campo sai como `structured=-`.
- [ ] Evento sem `model` (linha antiga) cai no bucket `unknown` e não some.
- [ ] `--since` corta as linhas anteriores ao instante dado, com igualdade
      **inclusiva** no limite.
- [ ] `--since` com fuso (`2026-09-03T18:00:00+00:00`) sai com código 2.
- [ ] Os arquivos rotacionados `app.log.1`, `.2`, `.3` são lidos junto com
      `app.log`, do mais antigo para o mais novo.
- [ ] Linha truncada, linha sem JSON e linha com JSON que não é objeto são
      puladas, contadas em `malformed`, e o relatório sai normalmente.
- [ ] Log inexistente: mensagem e código 0.
- [ ] Log sem nenhum evento conhecido: tabela vazia, código 0, sem divisão por
      zero.
- [ ] `backend/pyproject.toml` sem dependência nova.
- [ ] `npm run check` verde sem editar nenhum teste existente.

## Cenários de teste

Suíte existente que muda de preparação: **nenhuma**. O ticket acrescenta um
módulo e um arquivo de teste; `backend/app/observability.py` não é editado.
Verificado por Grep: `backend/tests/` não tem nenhum teste de
`observability.py` — a suíte sempre monkeypatcha `emit` no módulo consumidor
(`monkeypatch.setattr(turn, "emit", ...)`, `test_turn_director.py:162`;
`monkeypatch.setattr(main, "emit", ...)`, `test_turn.py:443`) e nunca exercita o
handler de arquivo. Portanto não há teste do formato do log que este ticket
possa quebrar — e é justamente por isso que o parse dele precisa dos cenários de
linha malformada abaixo: **o formato do log não é coberto por nenhum teste hoje**,
e este módulo passa a depender dele.

Preparação de `backend/tests/test_telemetry_report.py`: arquivos de log escritos
à mão em `tmp_path`, com linhas montadas no mesmo formato que
`observability.py:17-23` produz, e `report(tmp_path / "app.log")` chamado
direto. Um cenário de blindagem escreve o log **de verdade** e confere que
`read_lines` consegue lê-lo — é o teste que pega uma futura mudança de
formatador em `observability.py`. Como `setup_logging` retorna cedo quando
`logger.handlers` já existe (`observability.py:13-14`) e o logger `"ooc"` é
global ao processo, esse cenário usa uma fixture própria: (1)
`monkeypatch.setattr("app.observability.LOG_PATH", tmp_path / "app.log")`
**antes** de chamar `setup_logging()`, porque o `RotatingFileHandler` lê
`LOG_PATH` na construção; (2) guarda `list(logger.handlers)`, esvazia
`logger.handlers`, chama `setup_logging()` e `emit(...)`; (3) no teardown,
fecha e remove os handlers criados no teste e restaura a lista guardada. Sem a
fixture o teste passaria ou falharia conforme a ordem de execução da suíte.
Nenhum teste toca `~/.ooc-local`.

- Feliz: um modelo, 3 turnos, agregados conferidos na mão.
- Feliz: juiz com 7 applied e 3 rejected → taxa 0,3.
- Feliz: ida e volta real com `setup_logging` + `emit` + `read_lines`.
- Borda: dois modelos; `--model` filtrando.
- Borda: `structured` true/false/ausente no mesmo log.
- Borda: evento sem `model` → `unknown`.
- Borda: `--since` no limite exato (inclusivo) e um segundo depois.
- Borda: quatro arquivos (`app.log.3`, `.2`, `.1`, `app.log`) lidos em ordem.
- Borda: log só com eventos que o relatório não conhece (`session_created`,
  `lore_injected`) → tabela vazia, código 0.
- Falha: linha truncada no meio do JSON, linha sem espaço nenhum, linha cujo
  JSON é uma lista → `malformed == 3`, relatório íntegro.
- Falha: `--since` com fuso → código 2.
- Falha: caminho de log inexistente → código 0 com mensagem.

## Rollout e kill switch

N/A. Comando de terminal, somente-leitura, fora do `npm run dev` e de qualquer
rota. `app.telemetry` não é importado por `main.py` nem por `turn.py`; nenhuma
partida passa por este código.

## Observabilidade

Eventos: N/A (`emit`). Um relatório que escrevesse no próprio log que analisa
poluiria a medição seguinte — este é o único módulo da fase em que isso seria
literalmente circular.

Saída em stdout: a tabela descrita acima, mais uma linha final com
`lines=<n> malformed=<n> files=<n>`, para o usuário perceber quando metade do
log não deu parse.

Métrica de sucesso: é a métrica da fase inteira. Com o perfil `recommended`
subido pelo TCK-085 e 10 turnos jogados, o relatório mostra `p90` do turno abaixo
de 30.000 ms, `rejected == 0.0` nos três subsistemas do utility e `tags/turn`
acima de 0,8 — os números que fecham a Fase 4.

## i18n

N/A. Relatório de operador no terminal, em inglês. Nenhuma chave nova em
`frontend/src/strings/`.
