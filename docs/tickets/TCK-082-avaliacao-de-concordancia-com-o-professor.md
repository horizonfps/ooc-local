---
id: TCK-082
title: Medir a concordância de um papel candidato com o professor no conjunto separado
status: ready
points: 3
blockedBy: [TCK-081]
files:
  - backend/app/dataset.py
  - backend/tests/test_dataset_eval.py
migration: false
ui: false
risk: low
---

## Problema

A sub-fase 4.3 do plano tem um critério de vitória escrito: "concordância com o
professor no conjunto separado + taxa `*_rejected` da telemetria numa sessão
real. Vence o menor que empatar." O conjunto separado existe desde o TCK-079
(`split: "holdout"`, 10% por hash de sessão) e os rótulos do professor desde o
TCK-081. Não existe quem calcule a concordância.

Sem esse número, o bake-off entre Qwen3.5-2B, Qwen3.5-4B e o Cydonia atual (o plano cita
"1.7B", mas a linha pequena do Qwen3.5 é 0.8B/2B/4B/9B; o 1.7B é da geração
Qwen3. Fonte: [Qwen/Qwen3.5-2B](https://huggingface.co/Qwen/Qwen3.5-2B) e
[Unsloth, Qwen3.5](https://unsloth.ai/docs/models/qwen3.5). A mesma correção
está em TCK-083 e TCK-084) vira
opinião, e a decisão de qual modelo vai no perfil `recommended` (TCK-084) não tem
base.

## Escopo

Dentro:
- `backend/app/dataset.py`: subcomando `eval`; as três métricas por tarefa;
  impressão do relatório.
- `backend/tests/test_dataset_eval.py` novo.

Fora (explícito):
- Rotular. `eval` **não** escreve `teacher_label`; ele lê o que o TCK-081
  gravou. Linha sem `teacher_label` não-nulo é pulada e contada.
- Avaliar o narrator. A qualidade da prosa é decidida por teste cego de 10 pares,
  fora do repositório, como o plano manda. `--task narrator` é recusado.
- Treinar, comparar checkpoints, escolher o vencedor. `eval` imprime números; a
  decisão é do usuário.
- Escrever arquivo de saída. O relatório vai para stdout e o dicionário é
  devolvido pela função. Nada de `--report-json` nesta fatia.
- Ler a telemetria de partida. A outra metade do critério (`*_rejected` numa
  sessão real) é o TCK-086.
- Dependência Python nova.

## Comportamento esperado

```
uv run python -m app.dataset eval --role utility --task judge \
  --in datasets/2026-09/judge.labeled.jsonl
```

Filtra as linhas de `split: "holdout"` com `teacher_label` não-nulo, roda cada
`messages` no modelo do papel indicado, faz o parse com o parser da tarefa e
imprime a concordância com o rótulo do professor, mais a taxa de rejeição de
formato. Rodar o mesmo arquivo com `--role teacher` devolve concordância 1,0 —
propriedade útil de sanidade, e o teste a exercita.

## Detalhes técnicos

### Métricas, por tarefa

Todas determinísticas, sem biblioteca externa, sem aleatoriedade, sem empate
resolvido por ordem de dicionário.

**judge** — sobre a união dos ids que aparecem no rótulo do professor ou no do
candidato, com delta ausente valendo 0:
- `sign`: fração de ids em que `sign(delta_candidato) == sign(delta_professor)`,
  com `sign(x)` em `{-1, 0, +1}`. União vazia (os dois disseram "nada mudou") →
  `1.0`.
- `exact`: fração de **linhas** em que os dois mapas são iguais depois de
  descartar entradas com delta 0 (`{"a": 0}` e `{}` são a mesma resposta).

O sinal é a métrica que importa: o plano já registra que "o engine valida,
clampa e descarta", então errar a magnitude custa pouco e errar a direção
inverte o HUD. É o mesmo critério do commit `judge: exemplo neutro no prompt e
criterio de sinal do delta`.

**director** — Jaccard do conjunto de ids: `|A ∩ B| / |A ∪ B|`, com os dois
vazios valendo `1.0`. Conjunto, não lista: `validate_cast_ids` (`cast.py:45`)
já deduplica e a ordem não tem efeito no engine.

**minds**:
- `coverage`: `|A ∩ B| / |B|`, com `B` = ids do professor; `B` vazio → `1.0`.
  Mede se o candidato falou dos NPCs certos.
- `attitude`: média, sobre os ids em `A ∩ B`, do Jaccard de **tokens** dos dois
  textos de `attitude`, normalizados por `normalize_text` (`lore.py:16`:
  casefold + NFKD sem combinantes) e quebrados por espaço. Interseção vazia →
  `attitude` é `None` para esse exemplo e ele fica **fora** da média; o agregado
  traz `attitude_n` (quantos exemplos entraram na média) ao lado, e `attitude`
  agregado é `None` quando `attitude_n == 0`. Assim um candidato que não cobre
  NPC nenhum sai com `coverage` baixo e `attitude` vazio, nunca com `1.0`
  inflando a média. Não é semântica e não pretende ser: é determinístico, não depende de
  modelo nenhum e distingue "desconfiada" de "encantada", que é o que se quer
  medir. `emoji` e `event` não entram na métrica — emoji é ruído de tokenizer e
  `event` é texto livre longo demais para Jaccard significar algo.

**Todas as tarefas**:
- `rejected`: fração de linhas em que o parser do candidato devolveu `None`. É a
  "taxa de rejeição de formato" do critério de verde da fase.
- `n`: quantas linhas entraram na conta.

### Saída

```
task=judge role=utility model=qwen35-2b-ooc n=182
  sign=0.914 exact=0.802 rejected=0.000
```

Uma linha de cabeçalho e uma de números por execução, para dois `eval` seguidos
poderem ser comparados a olho no terminal. `eval_file` devolve o mesmo como
`dict[str, float | int | str]`.

### Execução

Mesmo esqueleto do `label` (TCK-081): `LABELERS[task]` dá o par (options,
parser); provider construído com `config.models[args.role]` e as options da
tarefa; `complete` em laço sequencial dentro de um `asyncio.run`; cache de
cenário por `scenario_id` para o `parse_scene`. Erro de provider numa linha conta
como rejeição de formato **e** entra num contador separado `provider_errors`, que
é impresso: 30% de rejeição por timeout é um diagnóstico diferente de 30% por
JSON quebrado, e misturar os dois esconde o problema.

Argumentos: `--role` (obrigatório), `--task {judge,director,minds}`
(obrigatório), `--in` (obrigatório), `--limit N` (opcional),
`--split {holdout,train,all}` (opcional, default `holdout`). O default é o que
protege o conjunto separado; `--split train` existe para medir overfitting e é
escolha explícita de quem digita.

## Contrato público

```python
# backend/app/dataset.py
def agreement_judge(teacher: dict, candidate: dict) -> tuple[float, bool]   # (sign, exact)
def agreement_director(teacher: dict, candidate: dict) -> float             # jaccard
def agreement_minds(teacher: dict, candidate: dict) -> tuple[float, float | None]  # (coverage, attitude); attitude None sem ids em comum

def eval_file(in_path: Path, task: str, role_name: str, config: Config, *,
              split: str = "holdout", limit: int | None = None) -> dict

# CLI
# uv run python -m app.dataset eval --role utility --task judge|director|minds \
#   --in <jsonl> [--split holdout|train|all] [--limit N]
```

Nenhum ticket desta fase consome estas assinaturas: o `training/eval.md` do
TCK-083 apenas **documenta** como rodar o comando, e documentação não é
dependência de código. `blockedBy` fica só em TCK-081, de quem `eval` consome o
campo `teacher_label`.

## Acceptance criteria

- [ ] Rodar `eval` com o fake devolvendo exatamente o `teacher_label` de cada
      linha dá `sign == 1.0`, `exact == 1.0` e `rejected == 0.0`.
- [ ] `agreement_judge({"stats": {"a": -5}}, {"stats": {"a": -1}})` dá
      `sign == 1.0` e `exact is False`.
- [ ] `agreement_judge({"stats": {"a": -5}}, {"stats": {"a": 3}})` dá
      `sign == 0.0`.
- [ ] `agreement_judge({"stats": {}}, {"stats": {}})` dá `sign == 1.0` e
      `exact is True`; `{"stats": {"a": 0}}` contra `{"stats": {}}` também dá
      `exact is True`.
- [ ] `agreement_judge({"stats": {"a": -5}}, {"stats": {"b": -5}})` dá
      `sign == 0.0` (união de dois ids, nenhum com sinal igual).
- [ ] `agreement_director` de `["chloe","renan"]` contra `["chloe"]` dá `0.5`;
      dois conjuntos vazios dão `1.0`; ordem trocada dá `1.0`.
- [ ] `agreement_minds` com o candidato cobrindo 1 de 2 ids do professor dá
      `coverage == 0.5`; `attitude` compara só os ids em comum e ignora acento e
      caixa (`"Desconfiada"` contra `"desconfiada"` dá `1.0`).
- [ ] `agreement_minds` sem id em comum (professor `{"chloe": ...}`, candidato
      `{"renan": ...}`) devolve `(0.0, None)`; com os dois vazios devolve
      `(1.0, None)`.
- [ ] No agregado de `eval_file` para minds, `attitude_n` conta só os exemplos
      com id em comum, `attitude` é a média desses e é `None` quando
      `attitude_n == 0`; um lote de 3 exemplos em que só 1 tem interseção dá
      `attitude_n == 1` e `attitude` igual ao Jaccard desse único exemplo.
- [ ] Linha sem `teacher_label` (ou com `null`) é pulada e contada, e não faz
      chamada ao provider.
- [ ] Default `--split holdout` ignora linhas de `train`; `--split all` usa
      todas.
- [ ] Resposta em prosa do candidato conta em `rejected` e não derruba o lote.
- [ ] Exceção do provider numa linha conta em `rejected` **e** em
      `provider_errors`, e as linhas seguintes são avaliadas.
- [ ] Papel ausente na config: código de saída 2 e zero chamadas ao provider.
- [ ] `--task narrator` é recusado pelo argparse.
- [ ] Arquivo sem nenhuma linha elegível imprime `n=0` e sai com código 0, sem
      divisão por zero.
- [ ] `npm run check` verde sem editar nenhum teste existente.

## Cenários de teste

Suíte existente que muda de preparação: **nenhuma**. O ticket acrescenta um
subcomando a `backend/app/dataset.py` e um arquivo de teste novo; nada existente
muda de assinatura. `test_dataset_export.py` e `test_dataset_label.py` não são
tocados — `eval` não altera `export` nem `label`, e as três funções de
concordância são novas.

Preparação de `backend/tests/test_dataset_eval.py`: JSONL escrito à mão com o
envelope do TCK-079 mais `teacher_label`, provider mockado com
`monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake)`
(`test_judge.py:126-130`), cenário em `tmp_path` com
`monkeypatch.setattr("app.scenario.scenarios_dir", lambda: root)`. As três
funções de concordância são testadas **puras**, sem provider nenhum: são elas que
definem o critério da fase e precisam de cobertura direta.

- Feliz: concordância perfeita ponta a ponta nas três tarefas.
- Feliz: tabela de casos das funções puras (igual, sinal certo com magnitude
  errada, sinal errado, id só no professor, id só no candidato, os dois vazios).
- Feliz: `attitude` com acento e caixa diferentes.
- Borda: `agreement_minds` sem interseção → `attitude is None`; lote com 3
  exemplos e 1 interseção → `attitude_n == 1`; lote sem interseção nenhuma →
  `attitude is None` no agregado e `coverage` baixo.
- Borda: `--split` nos três valores.
- Borda: `--limit`.
- Borda: linha com `teacher_label: null` pulada, sem chamada.
- Borda: arquivo vazio → `n=0`, código 0.
- Falha: prosa do candidato → `rejected` sobe, lote segue.
- Falha: exceção do provider → `rejected` e `provider_errors` sobem, lote segue.
- Falha: papel ausente → código 2, `calls == []`.

## Rollout e kill switch

N/A. Comando de lote rodado à mão, somente-leitura, fora do servidor e do
`npm run dev`. Nenhuma partida passa por este código.

## Observabilidade

Eventos: N/A (`emit`), pelo mesmo motivo do TCK-079 e do TCK-081 — escrever no
`~/.ooc-local/logs/app.log` a partir de um lote contaminaria o log que o
`app.telemetry report` (TCK-086) usa para comparar modelos em partida.

Relatório em stdout (e dicionário devolvido por `eval_file`): `task`, `role`,
`model`, `n`, as métricas da tarefa (minds inclui `attitude_n`), `rejected`,
`provider_errors`, `skipped`.

Métrica de sucesso: é literalmente o critério de verde da sub-fase 4.3 — o
utility próprio empata ou ganha do Cydonia em `sign` (juiz), `jaccard`
(director) e `coverage` (minds) no `--split holdout` (`attitude` é
informativo e não entra no critério, por ser `None` quando não há ids em comum), com `rejected == 0.0`
contra servidor com `structured_output: json_schema`.

## i18n

N/A. Relatório de operador, em inglês, no terminal.
