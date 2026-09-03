---
id: TCK-083
title: Formatar o dataset para treino e versionar as receitas de LoRA em training/
status: ready
points: 4
blockedBy: [TCK-079, TCK-080, TCK-081]
files:
  - .gitignore
  - backend/app/training.py
  - backend/tests/test_training_format.py
  - training/README.md
  - training/eval.md
  - training/configs/utility-qwen35-2b-lora.yaml
  - training/configs/utility-qwen35-4b-lora.yaml
  - training/configs/narrator-nemo-12b-lora.yaml
migration: false
ui: false
risk: low
---

## Problema

O JSONL que sai do `app.dataset` (TCK-079/080) está no formato do **engine**: uma
lista de `messages` por tarefa, mais o rótulo em campo separado. Nenhum treinador
consome isso: SFT com LoRA espera uma conversa completa, com a resposta esperada
como última mensagem `assistant`.

E falta o outro lado do plano: "treino fora do repositório; receita dentro". Hoje
não existe `training/`, não existe registro de qual base treina onde, nem de que
o utility é **um LoRA multi-tarefa com prefixo** (JUDGE / DIRECTOR / MINDS) e não
três adaptadores. Sem isso escrito, a receita mora só na cabeça de quem rodou o
treino, e a Fase 4 não é reproduzível.

## Escopo

Dentro:
- `backend/app/training.py` novo: subcomando `format`, com `--target utility` e
  `--target narrator`.
- `backend/tests/test_training_format.py` novo.
- `training/README.md`: o que treina onde, o que vai para o Hugging Face, o que
  nunca entra no git.
- `training/eval.md`: o loop de verde da fase, transcrito como passos
  executáveis.
- `training/configs/*.yaml`: três receitas de LoRA.

Fora (explícito):
- **`training/format.py`.** O plano pedia o formatador dentro de `training/`, e
  ele fica em `backend/app/training.py` **de propósito**: `pytest` do backend tem
  `testpaths = ["tests"]` (`backend/pyproject.toml:20-22`) e roda com o pacote
  `app` no path; um módulo solto em `training/` só seria importável por um teste
  com gambiarra de `sys.path`, e o `npm run check` (pre-commit e CI) não o
  cobriria. `training/README.md` aponta para o comando. Os YAMLs e os `.md`, que
  são conteúdo sem teste, ficam em `training/`.
- **Rodar treino.** Nenhum script chama Unsloth, nenhuma dependência de ML entra
  em `backend/pyproject.toml`. Os YAMLs são **dados** lidos pelo notebook/script
  que o usuário roda na RTX 5070 ou na GPU alugada, fora do repositório.
- **DPO do narrator.** O plano cita "passe curto de DPO contra positividade e
  slop" na sub-fase 4.4. **Fora desta fase de tickets**: exige dataset de pares
  preferidos, que não existe e não sai do event store. Registrado como pendência
  em `training/README.md`, sem YAML e sem código.
- Pesos, checkpoints, adaptadores, GGUF. Nada disso entra no git;
  `training/README.md` diz isso com todas as letras. O `.gitignore` atual
  (`dev/`, `__pycache__/`, `.venv/`, `node_modules/`, `dist/`,
  `.pytest_cache/`) **não** ignora nada em `training/`; este ticket acrescenta a
  linha `training/out/` ao `.gitignore` (está em `files`), e é para lá que os
  YAMLs apontam a saída de treino e o dataset formatado.
- Baixar ou servir modelo: TCK-084 e TCK-085.
- `backend/app/dataset.py`. Este ticket **não o edita** — lê o JSONL que ele
  produz, e é isso que permite os dois rodarem em waves diferentes sem colisão.

## Comportamento esperado

```
uv run python -m app.training format --target utility \
  --in judge.labeled.jsonl --in director.labeled.jsonl --in minds.labeled.jsonl \
  --out train/utility.jsonl

uv run python -m app.training format --target narrator \
  --in narrator.jsonl --out train/narrator.jsonl
```

Sai um JSONL de conversas prontas para SFT. No alvo `utility`, o system prompt de
cada exemplo começa com uma linha de prefixo de tarefa (`JUDGE`, `DIRECTOR` ou
`MINDS`) e a última mensagem é a resposta esperada em JSON compacto. No alvo
`narrator`, o system é o prompt-mestre daquele turno e a última mensagem é o
texto cru com as tags.

Por padrão só entram linhas de `split: "train"`. O conjunto separado não vaza
para o treino sem alguém digitar `--allow-holdout`, de propósito.

## Detalhes técnicos

### Formato de saída

```json
{"messages": [{"role": "system", "content": "JUDGE\nAvalie o turno e ..."},
              {"role": "user", "content": "[ATRIBUTOS]\n..."},
              {"role": "assistant", "content": "{\"stats\":{\"reputacao\":-3}}"}],
 "task": "judge", "locale": "pt-br"}
```

- O prefixo é a **primeira linha** do system, seguida de `\n` e do system
  original, sem tocar no resto. É o que faz um LoRA só atender as três tarefas: o
  modelo aprende a chavear pelo prefixo. Os três identificadores são `JUDGE`,
  `DIRECTOR` e `MINDS` — em inglês, como todo identificador do projeto, mesmo com
  o prompt em pt-br (o plano os escreve em português no texto corrido; o código
  não segue).
- A resposta é `json.dumps(label, ensure_ascii=False, separators=(",", ":"))`.
  Compacto e sem espaço porque é o que o modelo vai ter que emitir, e cada
  espaço treinado é um token gasto por turno em produção. `ensure_ascii=False`
  porque emoji e acento são conteúdo legítimo do minds.
- No alvo `narrator`, `messages` é a lista da linha inteira (system + janela +
  ação do jogador) mais `{"role": "assistant", "content": <engine_label>}`, que
  é o texto cru gravado pelo TCK-080.

### Escolha do rótulo

`--label-source {teacher,engine,teacher-or-engine}`, default `teacher`.

- `teacher`: usa `teacher_label`; linha sem ele (ou `null`) é pulada e contada.
- `engine`: usa `engine_label`.
- `teacher-or-engine`: professor quando houver, engine como reserva.

Default `teacher` porque é a decisão do plano: os rótulos do engine vêm do
Cydonia, que falhou como utility, e treinar neles propagaria o defeito. Quem
quiser o contrário digita.

No alvo `narrator` a opção não se aplica: o alvo é sempre o texto cru
(`engine_label`), e passar `--label-source teacher` com `--target narrator` é
erro de argumento (código 2).

### Filtros

- `--split {train,holdout,all}`, default `train`. `holdout` e `all` exigem
  `--allow-holdout`; sem ele, erro e código 2. É a única proteção que o repo tem
  contra o vazamento que invalidaria toda a avaliação da fase, e por isso é
  redundante de propósito.
- `--in` é repetível (`action="append"`), para juntar as três tarefas do utility
  num arquivo só. A ordem de saída é a ordem dos arquivos e das linhas dentro
  deles — determinística; embaralhar é papel do treinador.
- Linha com `task` que não bate com o alvo (`narrator` num arquivo de utility, ou
  o contrário) é pulada e contada.

### `training/configs/*.yaml`

Campos mínimos e consensuais, sem inventar bandeira de Unsloth que não foi
confirmada. Base do intervalo de valores: o guia oficial de hiperparâmetros de
LoRA da Unsloth
([unsloth.ai/docs — LoRA Hyperparameters Guide](https://unsloth.ai/docs/get-started/fine-tuning-llms-guide/lora-hyperparameters-guide)),
que recomenda `r` entre 16 e 64, `lr` entre 1e-4 e 2e-4, 1 a 3 épocas, e a
convenção própria deles de `lora_alpha == r` quando `use_rslora` está ligado.

```yaml
# training/configs/utility-qwen35-2b-lora.yaml
base_model: unsloth/Qwen3.5-2B
max_seq_length: 4096
load_in_4bit: true
lora:
  r: 32
  lora_alpha: 32
  use_rslora: true
learning_rate: 0.0002
num_train_epochs: 2
per_device_train_batch_size: 2
gradient_accumulation_steps: 8
dataset: ../datasets/train/utility.jsonl
notes: >
  Multi-task LoRA. Task prefix is the first line of the system message
  (JUDGE / DIRECTOR / MINDS). Train in non-thinking mode.
```

O arquivo de 4B é o mesmo com `base_model: unsloth/Qwen3.5-4B`; o do narrator usa
`base_model: mistralai/Mistral-Nemo-Base-2407`, `max_seq_length: 8192`, `r: 64`,
`lora_alpha: 64`, `num_train_epochs: 1`, `learning_rate: 0.0001` e
`dataset: ../datasets/train/narrator.jsonl`.

Repositórios confirmados:
[unsloth/Qwen3.5-2B-GGUF](https://huggingface.co/unsloth/Qwen3.5-2B-GGUF),
[unsloth/Qwen3.5-4B-GGUF](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF),
[mistralai/Mistral-Nemo-Base-2407](https://huggingface.co/mistralai/Mistral-Nemo-Base-2407)
(12B, Apache 2.0, base pré-treinado — é a linhagem do Rocinante que o plano pede).

**Correção de fato para registrar no `training/README.md`:** o plano cita
"Qwen3.5-1.7B/4B", e a linha pequena do Qwen3.5 é **0.8B / 2B / 4B / 9B** — o
1.7B pertence à geração Qwen3. O equivalente mais próximo do 1.7B é o **2B**, e é
ele que entra no bake-off. Fontes: [Qwen/Qwen3.5-2B](https://huggingface.co/Qwen/Qwen3.5-2B),
[Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) e
[Unsloth, "Qwen3.5 — How to Run Locally"](https://unsloth.ai/docs/models/qwen3.5),
que lista 0.8B/2B/4B/9B como a linha pequena. Escreva isso no README; quem for
treinar não pode descobrir sozinho que o repo do plano não existe.

Segunda nota para o README, decidida pelo coordenador em 03/09/2026: os modelos
pequenos do Qwen3.5 (0.8B a 9B e o 27B) são **densos**; os MoE da família são
só os com sufixo `-A3B`/`-A10B`/`-A17B` (35B-A3B, 122B-A10B, 397B-A17B). O
bloco de atenção é híbrido (Gated DeltaNet + atenção), e a família é
visão-linguagem nativa, mas nada disso é MoE, então a decisão "denso, não MoE"
do plano está mantida e a base de treino é `unsloth/Qwen3.5-2B` e
`unsloth/Qwen3.5-4B` (espelhos da Unsloth dos pesos `Qwen/Qwen3.5-2B` e
`Qwen/Qwen3.5-4B`, mesmos links acima; a Unsloth documenta o fine-tune deles no
mesmo guia). Se o guia da Unsloth exigir versão mínima da biblioteca para a
arquitetura híbrida, registre a versão no README em vez de fixar no YAML.

### `training/README.md`

Seções obrigatórias, curtas: onde treina o quê (utility na RTX 5070 local,
LoRA de 2B–4B cabendo em 4–6 GB; narrator em GPU alugada), como gerar o dataset
(a sequência `app.dataset export` → `label` → `app.training format`), onde vão os
pesos (Hugging Face, **nunca** o repositório), as duas notas de fato acima, e o
que está fora desta fase (DPO do narrator, variante premium no Mistral Small
24B).

### `training/eval.md`

O loop de verde da Fase 4, transcrito do plano em passos executáveis, com o
comando de cada um: 10 turnos no exemplo-escola com turno completo abaixo de
30 s; `app.dataset eval --split holdout` com concordância igual ou acima da do
Cydonia e `rejected == 0.0` (TCK-082); `app.telemetry report` comparando latência
e rejeição por modelo (TCK-086); `[SUGGEST:]` e `[STAT:]` em pelo menos 8 dos 10
turnos; teste cego de 10 pares de prosa, com o protocolo do sorteio descrito.

## Contrato público

```python
# backend/app/training.py
TASK_PREFIXES = {"judge": "JUDGE", "director": "DIRECTOR", "minds": "MINDS"}

def format_dataset(in_paths: list[Path], out_path: Path, target: str, *,
                   label_source: str = "teacher", split: str = "train",
                   allow_holdout: bool = False) -> dict

def main(argv: list[str] | None = None) -> int

# CLI
# uv run python -m app.training format --target utility|narrator \
#   --in <jsonl> [--in <jsonl> ...] --out <jsonl> \
#   [--label-source teacher|engine|teacher-or-engine] \
#   [--split train|holdout|all] [--allow-holdout]
```

Linha de saída: `{"messages": [{"role", "content"}...], "task": str, "locale": str}`.

Nenhum ticket desta fase consome estas assinaturas; quem consome o arquivo é o
treinador, fora do repositório.

## Acceptance criteria

- [ ] `format --target utility` com uma linha de cada tarefa produz três
      conversas, cada uma com o system começando por `JUDGE\n`, `DIRECTOR\n` ou
      `MINDS\n` seguido do system original inalterado.
- [ ] A última mensagem é `assistant` com o `teacher_label` serializado em JSON
      compacto (sem espaço depois de `:` e `,`) e com acento/emoji preservados.
- [ ] Linha sem `teacher_label` é pulada com `--label-source teacher` e incluída
      com `--label-source engine` e com `teacher-or-engine`.
- [ ] `format --target narrator` produz a lista de mensagens original mais um
      `assistant` com o texto cru; o system **não** ganha prefixo.
- [ ] `--target narrator --label-source teacher` sai com código 2.
- [ ] Só linhas de `split: "train"` entram por padrão; `--split all` sem
      `--allow-holdout` sai com código 2; com a flag, inclui.
- [ ] `--in` repetido concatena os arquivos na ordem dada, de forma
      determinística entre execuções.
- [ ] Linha de tarefa incompatível com o alvo é pulada e contada.
- [ ] O resumo em stdout traz `written`, `skipped_label`, `skipped_split` e
      `skipped_task`.
- [ ] `training/README.md` existe e diz: utility treina local, narrator em GPU
      alugada, pesos vão para o Hugging Face e nunca para o git, o 1.7B do plano
      é 2B no Qwen3.5, e o DPO do narrator está fora desta fase.
- [ ] `training/eval.md` existe e lista os cinco critérios do loop de verde com
      o comando de cada um.
- [ ] Os três YAMLs existem, carregam com `yaml.safe_load` e têm `base_model`,
      `max_seq_length`, `lora.r`, `lora.lora_alpha`, `learning_rate`,
      `num_train_epochs` e `dataset` (o teste afere isso, para o YAML não
      apodrecer com chave errada).
- [ ] `backend/pyproject.toml` sem dependência nova.
- [ ] `.gitignore` contém a linha `training/out/`, e os três YAMLs e o
      `format` do CLI apontam a saída para dentro de `training/out/`.
- [ ] `npm run check` verde sem editar nenhum teste existente.

## Cenários de teste

Suíte existente que muda de preparação: **nenhuma**. O ticket acrescenta um
módulo e um arquivo de teste; `backend/app/dataset.py` não é editado e nenhuma
assinatura existente muda. Verificado por Grep: não há ocorrência de `training`
em `backend/app/` nem em `backend/tests/`.

Preparação de `backend/tests/test_training_format.py`: JSONL de entrada escrito à
mão em `tmp_path` com o envelope do TCK-079/080 (não se roda `export` aqui — o
teste de formatação não pode depender do banco), e `format_dataset` chamado
direto. Nenhum provider, nenhuma rede, nenhum SQLite. Os YAMLs são lidos com
`yaml.safe_load` a partir do caminho resolvido por
`Path(__file__).resolve().parents[2] / "training" / "configs"` — o mesmo salto de
diretório que `scenarios_dir` usa (`scenario.py:247-253`).

- Feliz: uma linha de cada tarefa → prefixo certo, resposta compacta.
- Feliz: alvo narrator → sem prefixo, `assistant` com o cru.
- Feliz: rótulo com acento e emoji sobrevive (`ensure_ascii=False`).
- Borda: as três opções de `--label-source`.
- Borda: `--in` repetido, ordem determinística.
- Borda: linha de tarefa incompatível pulada.
- Borda: arquivo de entrada vazio → saída vazia, código 0.
- Falha: `--split all` sem `--allow-holdout` → código 2, arquivo de saída não
  criado.
- Falha: `--target narrator --label-source teacher` → código 2.
- Conteúdo: os três YAMLs carregam e têm as chaves obrigatórias; os dois `.md`
  existem e não estão vazios.

## Rollout e kill switch

N/A. Comando de lote e arquivos de conteúdo. Nada disso é importado pelo
servidor; `training/` não entra em nenhum build e não é empacotado.

## Observabilidade

Eventos: N/A (`emit`) — mesmo motivo dos outros comandos de lote da fase.

Resumo em stdout, e o mesmo dicionário devolvido por `format_dataset`:

```
target=utility written=1802 skipped_label=32 skipped_split=201 skipped_task=0
```

Métrica de sucesso: `skipped_label / (written + skipped_label)` abaixo de 0,05
com `--label-source teacher`. Acima disso, a rotulagem do TCK-081 falhou demais e
não adianta treinar.

## i18n

N/A para UI. Os prefixos de tarefa são identificadores em inglês e **não** são
traduzidos: um LoRA multi-tarefa que chaveia por prefixo precisa de um token
estável, e traduzir o prefixo por locale criaria três chaves para a mesma tarefa.
O conteúdo dos prompts continua no idioma do cenário, e o campo `locale` de cada
linha existe para o dataset ser balanceado por língua antes do treino.
