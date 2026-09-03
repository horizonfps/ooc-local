---
id: TCK-085
title: Subir um llama-server por papel a partir do perfil e imprimir a config correspondente
status: ready
points: 3
blockedBy: [TCK-076, TCK-084]
files:
  - backend/app/models.py
  - backend/tests/test_models_serve.py
migration: false
ui: false
risk: medium
---

## Problema

Depois do TCK-084 o jogador tem os dois GGUF em `~/.ooc-local/models/` e continua
sem saber o que fazer com eles: precisa descobrir a linha de comando do
`llama-server`, escolher duas portas que não colidam, subir dois processos e
depois traduzir isso para `providers`/`models` no `~/.ooc-local/config.yaml`
(`config.py:10-20`). É exatamente o atrito que a sub-fase 4.5 existe para
eliminar — "substitui o 'traga seu modelo' como caminho padrão".

E tem um detalhe que só o projeto sabe: o papel `utility` deve apontar para um
provider com `structured_output: json_schema` (TCK-076), e o `narrator` não, já
que a saída dele é prosa. Um jogador montando a config na mão erra isso.

## Escopo

Dentro:
- `backend/app/models.py`: subcomando `serve` no `argparse` do TCK-084;
  `serve_profile`, `config_snippet` e `write_config_snippet`.
- `backend/tests/test_models_serve.py` novo.

Fora (explícito):
- `npm run dev`. `serve` é comando à parte, de propósito: o servidor de modelo
  sobe uma vez e fica; a API e o front reiniciam o tempo todo com `--reload`, e
  amarrar os dois faria o `llama-server` recarregar 14 GB a cada `Ctrl+S`.
  `package.json` **não** é editado.
- Baixar. É o `download` do TCK-084. `serve` com arquivo faltando **falha** e
  manda rodar o download; não baixa por conta própria.
- Supervisionar, reiniciar processo caído, health check, espera ativa pelo
  `/health` do llama-server. `serve` sobe, informa e espera; se um processo
  morrer, o usuário vê no terminal.
- Escolher backend de inferência. É `llama-server` (llama.cpp) e ponto: é o que
  serve GGUF, é o que implementa `response_format` com `json_schema`, e o plano
  já descartou Ollama por truncar contexto e não expor DRY/XTC.
- Editar `DEFAULT_CONFIG`. `--write-config` mexe no arquivo do usuário quando
  pedido; o default de fábrica do repositório continua o de hoje.
- Qualquer arquivo de `frontend/`.

## Comportamento esperado

```
uv run python -m app.models serve --profile recommended
```

Confere que os arquivos do perfil estão em `~/.ooc-local/models/`, sobe um
`llama-server` por papel nas portas do perfil, imprime o trecho de config pronto
para colar e fica esperando. `Ctrl+C` derruba os dois processos e sai.

Com `--write-config`, em vez de só imprimir, o trecho é escrito no
`~/.ooc-local/config.yaml` — depois de copiar o arquivo atual para
`config.yaml.bak`.

Arquivo faltando: erro nomeando o papel e o arquivo, instrução para rodar
`download --profile <nome>`, código 2, nenhum processo subido. Binário
`llama-server` fora do PATH: mesma coisa, com a mensagem certa.

## Detalhes técnicos

### Comando de cada processo

```python
[binary, "-m", str(path), "--host", "127.0.0.1", "--port", str(model.port),
 "-c", str(model.ctx), "-ngl", str(model.gpu_layers), "--jinja"]
```

`--jinja` faz o llama-server usar o chat template do próprio GGUF, o que importa
para o Rocinante e o Cydonia (templates de Mistral) e é pré-requisito conhecido
para o caminho de `response_format`/tool calling
([llama.cpp server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)).

`binary` vem, nesta ordem: `--llama-server` na linha de comando, variável de
ambiente `OOC_LLAMA_SERVER`, ou `"llama-server"` no PATH. Três fontes porque no
Windows o binário costuma estar numa pasta solta de release e no Linux vem do
gerenciador de pacotes.

`subprocess.Popen` sem `shell=True`, com a lista de argumentos — caminho com
espaço é a regra em `C:\Users\...`, e `shell=True` quebraria nele.

### Ciclo de vida

```python
def serve_profile(name: str, config: Config, *, binary: str) -> dict[str, subprocess.Popen]
```

Sobe todos, devolve o mapa `papel -> processo` e **não** espera. Quem espera é o
`main`, num `try/except KeyboardInterrupt` que chama `terminate()` em cada
processo, `wait(timeout=10)` e `kill()` no que sobreviver. Separar assim é o que
permite testar a subida sem travar a suíte.

Se o segundo processo falhar ao subir, o primeiro é derrubado antes de a exceção
propagar: dois modelos meio carregados são a pior sobra possível numa GPU de
12 GB. É por isso que este ticket é `risk: medium` — é o único da fase que cria
processo externo.

Verificações **antes** de subir qualquer coisa: todos os arquivos existem, e
`shutil.which(binary)` (ou o caminho absoluto) resolve. Falhar cedo evita o
estado meio-subido.

### Trecho de config

```python
def config_snippet(name: str, profile: dict[str, ProfileModel]) -> str
```

```yaml
providers:
  narrator-local:
    base_url: http://127.0.0.1:5101/v1
    structured_output: none
  utility-local:
    base_url: http://127.0.0.1:5102/v1
    structured_output: json_schema
models:
  narrator: {provider: narrator-local, model: Rocinante-12B-v1.1-Q4_K_M.gguf}
  utility: {provider: utility-local, model: Qwen3.5-4B-Q4_K_M.gguf}
```

Decisões embutidas, que são o valor do comando:
- **um provider por papel**, porque são dois servidores em portas diferentes;
  nome `{papel}-local`.
- `structured_output: json_schema` **só** no provider do utility. O narrator
  produz prosa e um schema ali quebraria o turno; o utility é o que ganha com a
  restrição (TCK-076/077).
- `model` é o nome do arquivo GGUF. O llama-server aceita qualquer string no
  campo `model` de uma requisição quando serve um modelo só, mas usar o nome do
  arquivo deixa a telemetria (`game_turn.model`, `judge_applied.model`) legível
  no relatório do TCK-086, que agrupa por modelo.
- O papel `builder` **não** entra no trecho: o perfil declara `narrator` e
  `utility`, e sobrescrever o `builder` do usuário sem ele pedir seria mudança
  silenciosa de comportamento no editor.

### `--write-config`

1. Lê o `~/.ooc-local/config.yaml` atual com `load_config()` (que o cria com os
   defaults se não existir, `config.py:55-60`).
2. Copia o arquivo para `config.yaml.bak` (sobrescrevendo o `.bak` anterior).
3. Carrega o YAML cru com `yaml.safe_load`, **mescla** as chaves do trecho em
   `providers` e as duas entradas de `models`, e regrava com `yaml.safe_dump`.
4. Imprime o caminho do backup.

Mesclar o YAML cru, e não serializar o objeto `Config`, preserva chaves que o
modelo não conhece. O que **se perde** são comentários e a ordem original —
`yaml.safe_dump` não os mantém. É por isso que existe o backup, é por isso que a
opção é opt-in, e é isso que a mensagem impressa avisa.

## Contrato público

```python
# backend/app/models.py
DEFAULT_LLAMA_SERVER: str            # "llama-server"
LLAMA_SERVER_ENV: str                # "OOC_LLAMA_SERVER"
class MissingModelFile(Exception): ...
class MissingLlamaServer(Exception): ...

def llama_server_command(model: ProfileModel, path: Path, binary: str) -> list[str]
def serve_profile(name: str, config: Config, *, binary: str) -> dict[str, subprocess.Popen]
def config_snippet(name: str, profile: dict[str, ProfileModel]) -> str
def write_config_snippet(snippet: str, path: Path) -> Path   # devolve o .bak
    # snippet é a string de config_snippet; a função faz yaml.safe_load nela,
    # carrega o YAML de path (ou DEFAULT_CONFIG se path não existe), substitui
    # as chaves providers.<nome> e models.<papel> presentes no snippet e
    # preserva todo o resto (language, flags, outros providers, papel builder).

# CLI
# uv run python -m app.models serve --profile recommended \
#   [--llama-server PATH] [--write-config]
```

Nenhum ticket desta fase consome estas assinaturas.

## Acceptance criteria

- [ ] `llama_server_command` produz a lista com `-m`, `--host 127.0.0.1`,
      `--port`, `-c`, `-ngl` e `--jinja`, com os valores do `ProfileModel`.
- [ ] `serve_profile` sobe **um** processo por papel do perfil, com as portas
      diferentes do perfil, e devolve o mapa `papel -> Popen`.
- [ ] Arquivo de um dos papéis ausente: `MissingModelFile`, código 2, mensagem
      citando o papel, o arquivo e o comando `download`, e **zero** `Popen`.
- [ ] `llama-server` não resolvível: `MissingLlamaServer`, código 2, zero
      `Popen`.
- [ ] Falha ao subir o segundo processo derruba o primeiro (`terminate` chamado)
      antes de propagar.
- [ ] `--llama-server /caminho/custom` e `OOC_LLAMA_SERVER` são respeitados,
      nessa ordem de precedência.
- [ ] `config_snippet` traz um provider por papel, com `structured_output:
      json_schema` **só** no do utility, `base_url` com a porta do perfil e `/v1`
      no fim, e `model` igual ao nome do arquivo GGUF.
- [ ] `config_snippet` **não** menciona o papel `builder`.
- [ ] O trecho impresso é YAML válido (`yaml.safe_load` o aceita no teste).
- [ ] `--write-config` cria `config.yaml.bak` com o conteúdo antigo, mescla
      `providers` e as duas entradas de `models`, preserva as demais chaves
      (`language`, `flags`, `builder`) e o resultado carrega com `load_config`.
- [ ] Sem `--write-config`, o `config.yaml` do usuário não é tocado.
- [ ] `npm run check` verde sem editar nenhum teste existente.

## Cenários de teste

Suíte existente que muda de preparação: **nenhuma**. O ticket acrescenta um
subcomando a `backend/app/models.py` (criado no TCK-084, sem consumidor em
`backend/app/`) e um arquivo de teste novo. `test_models_download.py` não é
tocado: `download` não conhece `serve`. Verificado também que
`backend/tests/test_config.py` não constrói caminho de config real — todos os
cenários usam `tmp_path` (`test_config.py:7`, `:15`) —, então escrever config no
teste deste ticket não pode vazar para `~/.ooc-local`.

Preparação de `backend/tests/test_models_serve.py`:
`monkeypatch.setattr(models, "models_dir", lambda: tmp_path / "models")` com
arquivos GGUF **falsos** (alguns bytes, o nome é o que importa),
`monkeypatch.setattr(models.subprocess, "Popen", FakePopen)` com um duplo que
registra `argv` e implementa `poll`, `terminate`, `wait` e `kill`, e
`monkeypatch.setattr(models.shutil, "which", lambda name: "/usr/bin/" + name)`.
Nada de processo real, nada de rede, nada de `~/.ooc-local`. `--write-config`
escreve num `tmp_path / "config.yaml"` passado por parâmetro.

- Feliz: perfil de dois papéis → dois `FakePopen`, argv conferido item a item.
- Feliz: `config_snippet` carregado com `yaml.safe_load` e conferido chave a
  chave, incluindo o `structured_output` de cada provider.
- Feliz: `--write-config` num config com `language`, `flags` e papel `builder` →
  `.bak` criado, chaves preservadas, resultado válido para `load_config`.
- Borda: precedência `--llama-server` > `OOC_LLAMA_SERVER` > PATH.
- Borda: perfil vindo de `config.profiles` (usuário) em vez do embutido.
- Borda: `--write-config` num arquivo que ainda não existe → criado a partir dos
  defaults, mais o trecho.
- Falha: um arquivo faltando → `MissingModelFile`, zero `Popen`.
- Falha: `which` devolvendo `None` → `MissingLlamaServer`, zero `Popen`.
- Falha: `Popen` levantando na segunda chamada → `terminate` chamado no primeiro
  processo, exceção propagada.

## Rollout e kill switch

Não há flag: o comando só roda quando digitado, e nada no servidor o importa
(`main.py` não conhece `app.models`). Desfazer um `--write-config` é
`cp ~/.ooc-local/config.yaml.bak ~/.ooc-local/config.yaml` — o comando imprime
essa linha depois de escrever.

`risk: medium` porque é o único ticket da fase que cria processo externo e o
único que escreve no arquivo de config do usuário. Mitigações no próprio escopo:
verificação de arquivos e de binário **antes** de subir qualquer processo,
derrubada do que já subiu quando um irmão falha, `--write-config` opt-in, backup
obrigatório antes de escrever, e nenhuma amarra com `npm run dev`.

## Observabilidade

Eventos: N/A (`emit`) — comando de terminal, fora do servidor.

Saída em stdout: uma linha por processo subido (`narrator pid=1234 port=5101
ctx=24576 ngl=-1`), o trecho de config, e — com `--write-config` — o caminho do
backup e a linha de comando para desfazer. `serve_profile` devolve o mapa de
processos, que é o que o teste inspeciona.

Métrica de sucesso: numa placa de 12 GB, `download --profile recommended` seguido
de `serve --profile recommended` e da config colada resulta em 10 turnos jogados
no exemplo-escola com turno completo abaixo de 30 s — que é o loop de verde da
Fase 4, medido pelo relatório do TCK-086.

## i18n

N/A. Saída de operador no terminal, em inglês. Nenhuma chave em
`frontend/src/strings/`.
