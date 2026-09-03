---
id: TCK-081
title: Rotular o dataset do utility com um modelo professor
status: ready
points: 3
blockedBy: [TCK-076, TCK-077, TCK-079]
files:
  - backend/app/dataset.py
  - backend/tests/test_dataset_label.py
migration: false
ui: false
risk: low
---

## Problema

O `engine_label` que o TCK-079 exporta é o que o **Cydonia** produziu e o engine
aceitou. O verde da Fase 3 provou que essa fonte é ruim: director devolvendo
prosa, juiz ecoando o exemplo do prompt, minds em três formatos. Pior, o rótulo
vazio é ambíguo por construção — `{"stats": {}}` com `applied: false` tanto pode
ser "nada mudou" quanto "o utility quebrou e o turno seguiu sem ele", e o event
store não distingue os dois (a recusa só existe no log, como `judge_rejected`).

Treinar o utility próprio nesses rótulos ensinaria o modelo pequeno a imitar os
defeitos do grande. O plano (sub-fase 4.2) resolve com **rotulagem por
professor**: um modelo grande responde os mesmos prompts, com o schema forçado do
TCK-076/077, e o rótulo dele é o alvo de treino; o `engine_label` fica na linha
como referência histórica.

## Escopo

Dentro:
- `backend/app/dataset.py`: subcomando `label` no `argparse` já criado pelo
  TCK-079; `label_file(...)`; despacho por tarefa para o par
  (options, parser) correto.
- `backend/tests/test_dataset_label.py` novo.

Fora (explícito):
- Alterar `backend/app/config.py`. **Nenhuma mudança de config é necessária**:
  `Config.models` é `dict[str, ModelRole]` (`config.py:40`) e o validador
  (`config.py:47-53`) só exige que o `provider` referenciado exista, então um
  papel `teacher` no YAML já carrega hoje. O que este ticket faz é falhar com
  mensagem clara quando ele não está lá.
- Rotular `narrator.jsonl`. O alvo do narrator é a prosa que o jogador aceitou;
  não há professor que "corrija" isso, e o plano trata a qualidade do narrator
  por teste cego, não por concordância. `--task narrator` é rejeitado.
- Curadoria por amostra. É trabalho manual do usuário sobre o JSONL de saída, e
  está declarado no plano como tal.
- Medir concordância. É o subcomando `eval`, do TCK-082.
- Paralelismo, retry com backoff, checkpoint parcial em caso de queda. O comando
  é sequencial e, se cair, é retomado com `--in` apontando para a saída parcial
  (ver "resume" nos detalhes).
- Dependência Python nova. Tudo é biblioteca padrão mais o que o backend já usa.

## Comportamento esperado

```
uv run python -m app.dataset label --role teacher --task judge \
  --in datasets/2026-09/judge.jsonl --out datasets/2026-09/judge.labeled.jsonl
```

Para cada linha do arquivo de entrada, o comando manda `messages` para o modelo
do papel indicado na config, faz o parse com o parser daquela tarefa e grava a
mesma linha acrescida de `teacher_label`. Linha cuja resposta não deu parse sai
com `teacher_label: null` e `teacher_reason` com o motivo. No fim imprime um
resumo com quantas foram rotuladas, quantas falharam e quantas foram puladas.

Papel ausente na config: erro claro e código de saída 2, **antes** de qualquer
chamada de rede. Tarefa desconhecida ou `narrator`: erro do argparse.

## Detalhes técnicos

### Despacho por tarefa

```python
LABELERS = {
    "judge":    (judge.JUDGE_OPTIONS,    _parse_judge),
    "director": (director.DIRECTOR_OPTIONS, _parse_director),
    "minds":    (minds.MINDS_OPTIONS,    _parse_minds),
}
```

As `GenerationOptions` são as **mesmas constantes** que o turno usa
(`judge.py:15`, `director.py:12`, `minds.py:13`), já com `json_schema` e
`schema_name` desde o TCK-077. Reusar em vez de recriar é o ponto: se o schema
mudar, o professor muda junto, e o rótulo continua no formato que o engine sabe
consumir.

Exceção deliberada: o juiz usa `JUDGE_OPTIONS_DYNAMIC` quando o cenário da linha
tem `allow_dynamic_stats` (mesma ramificação de `judge_turn`, TCK-077). O cenário
vem de `load_scenario(line["scenario_id"])`.

Parsers: `parse_judgement` (`judge.py:135`) e `parse_minds` (`minds.py:120`) são
puros; `parse_scene` (`director.py:101`) recebe o cenário, porque valida ids
contra o elenco. Por isso o comando carrega o cenário de cada linha, com **cache
por `scenario_id`** — um `dict` local, para não reler o disco a cada linha.
Cenário que não carrega mais: linha copiada com `teacher_label: null` e
`teacher_reason: "scenario_missing"`, sem chamar o modelo.

### Chamada

```python
role = config.models.get(args.role)
if role is None:
    print(f"role '{args.role}' not found in ~/.ooc-local/config.yaml", file=sys.stderr)
    return 2
provider = OpenAICompatProvider(config.providers[role.provider], options)
raw = await provider.complete([ChatMessage(**m) for m in line["messages"]], role.model)
```

`complete` (`base.py:23-26`) é a chamada não-streamada construída sobre
`stream_chat`; é a mesma que `judge_turn` usa (`judge.py:310`). O laço inteiro
roda dentro de um `asyncio.run`, sequencial: um servidor local não ganha nada com
concorrência e um provider remoto seria rate-limitado.

Erro de provider numa linha (timeout, conexão, HTTP) **não** aborta o lote: a
linha sai com `teacher_label: null` e `teacher_reason: "provider_error"`, e o
laço segue. Um lote de 2.000 linhas não pode morrer na linha 1.900.

### Formato de saída

A linha de entrada, intacta, mais:

```json
{"teacher_label": {"stats": {"reputacao": -3}}, "teacher_model": "Cydonia-24B-v4.3",
 "teacher_raw": "...", "teacher_reason": null}
```

`teacher_raw` cortado em `TEACHER_RAW_CHARS = 400`, para o arquivo não inchar com
prosa de modelo confuso e ainda dar para depurar. `teacher_model` na linha porque
um dataset pode ter sido rotulado em duas passadas com modelos diferentes, e sem
isso não há como separar depois.

### Resume e `--relabel`

Linha que já chega com `teacher_label` não-nulo é copiada sem chamar o modelo
(conta em `skipped_labeled`), a menos que `--relabel` seja passado. É o que
permite retomar um lote interrompido apontando `--in` para a saída parcial, e é
o que evita gastar uma hora de GPU de novo por causa de um Ctrl-C.

### Outros argumentos

- `--task {judge,director,minds}`, obrigatório. Linha do arquivo cujo campo
  `task` é diferente do pedido é copiada intacta e conta em `skipped_task`.
- `--limit N`, opcional: rotula as N primeiras linhas e copia o resto. Serve para
  provar a configuração com 5 linhas antes de soltar 2.000.
- `--out` obrigatório, e **não pode ser igual a `--in`** (checagem explícita, erro
  e código 2): sobrescrever a entrada enquanto se lê dela trunca o arquivo.

## Contrato público

```python
# backend/app/dataset.py
TEACHER_RAW_CHARS: int   # 400
LABELERS: dict[str, tuple[GenerationOptions, Callable]]

def label_file(in_path: Path, out_path: Path, task: str, role_name: str,
               config: Config, *, relabel: bool = False, limit: int | None = None) -> dict

# CLI
# uv run python -m app.dataset label --role teacher --task judge|director|minds \
#   --in <jsonl> --out <jsonl> [--relabel] [--limit N]
```

Campos acrescentados à linha (consumidos por TCK-082 e TCK-083):

```
teacher_label: object | null
teacher_reason: str | null    # invalid_json | not_a_list | unknown_ids | over_cap
                              # | scenario_missing | provider_error
teacher_model: str
teacher_raw: str              # cortado em TEACHER_RAW_CHARS
```

## Acceptance criteria

- [ ] `label --role teacher --task judge` com o provider devolvendo
      `{"stats": {"reputacao": -3}}` grava `teacher_label` com esse objeto e
      `teacher_reason: null`, preservando todos os campos originais da linha.
- [ ] O provider é construído com `JUDGE_OPTIONS` para cenário sem stats
      dinâmicos e com `JUDGE_OPTIONS_DYNAMIC` para cenário com
      `allow_dynamic_stats: true` (espionando `OpenAICompatProvider.__init__`).
- [ ] `--task director` usa `DIRECTOR_OPTIONS` e `parse_scene`; resposta com id
      fora do elenco sai com `teacher_label: null` e
      `teacher_reason: "unknown_ids"`.
- [ ] `--task minds` usa `MINDS_OPTIONS` e `parse_minds`; a resposta em lista de
      objetos com `id` (formato tolerado por `_list_to_map`, `minds.py:167`) é
      normalizada para mapa no `teacher_label`.
- [ ] Resposta em prosa sai com `teacher_label: null` e
      `teacher_reason: "invalid_json"`, e o lote continua.
- [ ] Exceção do provider numa linha sai com `teacher_reason: "provider_error"`
      e o lote continua; as linhas seguintes são rotuladas.
- [ ] Papel ausente na config: código de saída 2, mensagem citando o nome do
      papel, e **zero** chamadas ao provider.
- [ ] Cenário da linha que não carrega mais: `teacher_reason: "scenario_missing"`
      e nenhuma chamada ao provider para aquela linha.
- [ ] Linha que já tem `teacher_label` não-nulo é copiada sem chamada; com
      `--relabel`, é rechamada.
- [ ] Linha com `task` diferente do pedido é copiada intacta e contada.
- [ ] `--limit 2` num arquivo de 5 linhas faz exatamente 2 chamadas e copia as
      outras 3.
- [ ] `--in` igual a `--out` é recusado com código 2 sem escrever nada.
- [ ] `--task narrator` é recusado pelo argparse.
- [ ] `npm run check` verde sem editar nenhum teste existente.

## Cenários de teste

Suíte existente que muda de preparação: **nenhuma**. O ticket só acrescenta um
subcomando a `backend/app/dataset.py` (arquivo criado no TCK-079, sem consumidor
em nenhum outro módulo) e um arquivo de teste novo. Nenhuma assinatura existente
muda. `test_dataset_export.py` não é tocado: `export` não conhece `label`.

Preparação de `backend/tests/test_dataset_label.py`: provider mockado com
`monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake)`, exatamente o
padrão de `test_judge.py:126-130` — um `async def fake_stream(self, messages,
model)` que dá `yield` na resposta. Nenhum teste toca a rede. Cenário escrito em
`tmp_path` com `monkeypatch.setattr("app.scenario.scenarios_dir", lambda: root)`
(`_load`, `test_judge.py:96-99`). JSONL de entrada escrito à mão, com o envelope do
TCK-079 — não é preciso rodar `export` para testar `label`, e depender dele
tornaria este teste refém do outro.

- Feliz: 3 linhas de juiz rotuladas, campos originais preservados byte a byte.
- Feliz: director e minds, cada um com seu parser e suas options.
- Feliz: minds respondendo em lista de objetos com `id` → mapa no rótulo.
- Borda: `allow_dynamic_stats: true` → `JUDGE_OPTIONS_DYNAMIC`.
- Borda: `--limit 2` e contagem exata de chamadas.
- Borda: resume — arquivo de entrada com uma linha já rotulada e duas não.
- Borda: `--relabel` refaz a já rotulada.
- Borda: `teacher_raw` cortado em `TEACHER_RAW_CHARS` numa resposta longa.
- Falha: prosa sem JSON → `invalid_json`.
- Falha: `RuntimeError` no fake do provider numa linha → `provider_error` e as
  demais linhas rotuladas.
- Falha: papel ausente → código 2, zero chamadas (o fake registra as chamadas
  numa lista e o teste afirma `calls == []`).
- Falha: `--in == --out` → código 2, arquivo de entrada intacto.

## Rollout e kill switch

N/A. Comando de lote rodado à mão, fora do servidor e do `npm run dev`. Não é
importado por `main.py` nem por `turn.py`; nenhuma partida passa por este código.
O papel `teacher` é opcional na config e sua ausência só afeta este comando.

## Observabilidade

Eventos: N/A (`emit`). Como no TCK-079, o comando roda fora do servidor e não
escreve em `~/.ooc-local/logs/app.log`, para não contaminar o log que o
`app.telemetry report` (TCK-086) usa para comparar modelos em partida.

Resumo em stdout, e o mesmo dicionário devolvido por `label_file`:

```
labeled=1834 failed=12 skipped_labeled=0 skipped_task=0 skipped_scenario=3 model=Cydonia-24B-v4.3
```

Métrica de sucesso: `failed / (labeled + failed)` abaixo de 0,02 rodando o
professor contra um servidor com `structured_output: json_schema`. Acima disso, o
professor não está sendo restringido pelo schema e o dataset não presta.

## i18n

N/A. Nenhuma string de usuário; as mensagens de erro do CLI são de operador e
ficam em inglês, como o resto do código.
