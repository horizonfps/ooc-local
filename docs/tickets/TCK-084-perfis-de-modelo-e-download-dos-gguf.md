---
id: TCK-084
title: Declarar perfis de modelo na config e baixar os GGUF do perfil
status: ready
points: 5
blockedBy: []
files:
  - backend/app/config.py
  - backend/app/models.py
  - backend/tests/test_models_download.py
  - backend/tests/test_config.py
migration: false
ui: false
risk: low
---

## Problema

Hoje o projeto é "traga seu modelo": o `DEFAULT_CONFIG` (`config.py:10-20`)
aponta os três papéis para `Cydonia-24B-v4.3` num servidor que o jogador tem que
ter subido sozinho em `127.0.0.1:5001`, e nada no repositório diz **qual**
arquivo baixar, de onde, nem quanto de VRAM cada combinação come. A sub-fase 4.5
troca isso por perfil pré-configurado: `recommended` para placa de 12 GB e
`premium` para 16 GB+, com narrator e utility carregados ao mesmo tempo.

Sem os perfis declarados em código, o comando de subir os dois servidores
(TCK-085) não tem o que ler, e o usuário continua garimpando repositório de GGUF
no Hugging Face.

## Escopo

Dentro:
- `backend/app/config.py`: `ProfileModel` e o campo opcional
  `profiles: dict[str, dict[str, ProfileModel]] = {}` em `Config`.
- `backend/app/models.py` novo: `DEFAULT_PROFILES`, `resolve_profile`,
  `models_dir`, `download_profile`, e o `argparse` com o subcomando `download`.
- `backend/tests/test_models_download.py` novo; cenários de perfil novos em
  `backend/tests/test_config.py`.

Fora (explícito):
- `serve`. Subir `llama-server` é o TCK-085, que acrescenta o subcomando ao
  mesmo `argparse`. O `add_subparsers` já nasce preparado.
- Mudar `DEFAULT_CONFIG`. A instalação existente continua apontando para o
  KoboldCpp em `:5001`; quem troca a config do usuário é o `--write-config` do
  TCK-085, e só quando pedido.
- Escolher modelo por detecção de VRAM. O perfil é escolhido pelo usuário na
  linha de comando; o comando **imprime** o tamanho total para ele decidir, e não
  adivinha hardware.
- Verificação de hash/`sha256` do GGUF. O Hugging Face não expõe um checksum
  simples e uniforme por arquivo nesse endpoint; a validação aqui é por
  **tamanho** contra o `Content-Length`, que é o que dá para fazer sem
  dependência nova e o que pega o caso real (download interrompido).
- `huggingface_hub` como dependência. `httpx` já está em
  `backend/pyproject.toml:7` e resolve; acrescentar um SDK inteiro para montar
  uma URL não se paga.
- Baixar os modelos próprios do projeto. Eles ainda não existem; os perfis
  apontam para GGUF públicos interinos, e trocar o `hf_repo` depois é uma linha
  de YAML.
- Qualquer arquivo de `frontend/`.

## Comportamento esperado

```
uv run python -m app.models download --profile recommended
```

Imprime o que vai baixar (repo, arquivo, tamanho) e o total, baixa cada GGUF que
ainda não está completo em `~/.ooc-local/models/` e imprime o resultado. Arquivo
já presente com o tamanho certo é pulado. Download interrompido é **retomado** de
onde parou, não recomeçado. Rede caindo no meio deixa o arquivo parcial no disco
e sai com código diferente de zero, para a próxima execução continuar.

`--profile` desconhecido: erro claro e código 2, antes de qualquer rede.

## Detalhes técnicos

### `backend/app/config.py`

```python
class ProfileModel(BaseModel):
    hf_repo: str
    file: str
    port: int
    ctx: int = 8192
    gpu_layers: int = -1


class Config(BaseModel):
    ...
    profiles: dict[str, dict[str, ProfileModel]] = {}
```

Mapa de mapas (`nome do perfil -> papel -> modelo`) e não um modelo com campos
`narrator`/`utility` fixos: os papéis do projeto já são um `dict` livre
(`Config.models`, `config.py:40`), e um perfil que amanhã queira declarar
`builder` não deve exigir mudança de schema. Default `{}`, então toda config
existente continua válida sem uma linha nova.

`gpu_layers: -1` significa "tudo na GPU", que é a convenção do
`--n-gpu-layers` do llama.cpp; quem tem placa apertada baixa o número no YAML.

### `backend/app/models.py`

```python
DEFAULT_PROFILES: dict[str, dict[str, ProfileModel]] = {
    "recommended": {
        "narrator": ProfileModel(
            hf_repo="TheDrummer/Rocinante-12B-v1.1-GGUF",
            file="Rocinante-12B-v1.1-Q4_K_M.gguf",
            port=5101, ctx=24576, gpu_layers=-1),
        "utility": ProfileModel(
            hf_repo="lmstudio-community/Qwen3.5-4B-GGUF",
            file="Qwen3.5-4B-Q4_K_M.gguf",
            port=5102, ctx=8192, gpu_layers=-1),
    },
    "premium": {
        "narrator": ProfileModel(
            hf_repo="bartowski/TheDrummer_Cydonia-24B-v4.3-GGUF",
            file="TheDrummer_Cydonia-24B-v4.3-Q4_K_M.gguf",
            port=5101, ctx=24576, gpu_layers=-1),
        "utility": ProfileModel(
            hf_repo="unsloth/Qwen3.5-4B-GGUF",
            file="Qwen3.5-4B-Q8_0.gguf",
            port=5102, ctx=8192, gpu_layers=-1),
    },
}
```

Repositórios e arquivos **confirmados** (não invente variação de nome; a
convenção difere entre publicadores):

| perfil | papel | repo | arquivo | tamanho |
| --- | --- | --- | --- | --- |
| recommended | narrator | [TheDrummer/Rocinante-12B-v1.1-GGUF](https://huggingface.co/TheDrummer/Rocinante-12B-v1.1-GGUF) | `Rocinante-12B-v1.1-Q4_K_M.gguf` | 7,48 GB |
| recommended | utility | [lmstudio-community/Qwen3.5-4B-GGUF](https://huggingface.co/lmstudio-community/Qwen3.5-4B-GGUF) | `Qwen3.5-4B-Q4_K_M.gguf` | 2,71 GB |
| premium | narrator | [bartowski/TheDrummer_Cydonia-24B-v4.3-GGUF](https://huggingface.co/bartowski/TheDrummer_Cydonia-24B-v4.3-GGUF) | `TheDrummer_Cydonia-24B-v4.3-Q4_K_M.gguf` | 14,33 GB |
| premium | utility | [unsloth/Qwen3.5-4B-GGUF](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF) | `Qwen3.5-4B-Q8_0.gguf` | 4,48 GB |

Contas de VRAM, para ficarem no `--help` e no README de quem for revisar:
`recommended` soma **10,2 GB** de pesos, o que deixa ~1,8 GB de folga para KV
cache numa placa de 12 GB — dentro do alvo do plano (narrator ≤ 8 GB + utility
2–3 GB). `premium` soma **18,8 GB**: roda inteiro na GPU a partir de 20 GB
(3090/4090); em 16 GB é preciso baixar `gpu_layers` do narrator. Isso é dito em
voz alta no `--help` do `--profile` e impresso antes do download, porque "premium
= 16 GB+" no plano é o piso da faixa, não a promessa de tudo na VRAM.

Rocinante 12B é a linhagem Nemo que o plano nomeia para o narrator próprio, e
Cydonia 24B é o narrator interino de hoje; os dois são **provisórios**, e trocar
por `ooc-local/narrator-12b-GGUF` depois é editar duas strings.

`Qwen3.5-4B` e não `1.7B`: a linha pequena do Qwen3.5 é 0.8B / 2B / 4B / 9B — o
1.7B que o plano cita é da geração Qwen3 e não existe nesta. Fontes:
[Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) e
[Unsloth, "Qwen3.5 — How to Run Locally"](https://unsloth.ai/docs/models/qwen3.5).
Mesma correção registrada no TCK-083.

Os nomes de arquivo e os tamanhos da tabela foram lidos em 03/09/2026 da API
pública `https://huggingface.co/api/models/<hf_repo>/tree/main` (campo `size`,
em bytes): `Rocinante-12B-v1.1-Q4_K_M.gguf` 7,48 GB; `Qwen3.5-4B-Q4_K_M.gguf`
(lmstudio-community) 2,71 GB; `TheDrummer_Cydonia-24B-v4.3-Q4_K_M.gguf`
14,33 GB; `Qwen3.5-4B-Q8_0.gguf` (unsloth) 4,48 GB. Se um arquivo sumir do
repo, o `download` falha com 404 e o erro diz o nome; não invente variação de
nome.

### `resolve_profile`

```python
def resolve_profile(name: str, config: Config) -> dict[str, ProfileModel]:
    if name in config.profiles:
        return config.profiles[name]
    if name in DEFAULT_PROFILES:
        return DEFAULT_PROFILES[name]
    raise UnknownProfile(name)
```

Config do usuário **ganha** do embutido, por nome inteiro de perfil (não há
merge campo a campo: meia sobrescrita é pior que nenhuma, porque esconde qual
arquivo vai ser baixado). É assim que se aponta o perfil para os pesos próprios
quando eles existirem.

### Download

Destino: `models_dir()` = `CONFIG_DIR / "models"` (`config.py:7`), criado com
`mkdir(parents=True, exist_ok=True)`. URL:
`https://huggingface.co/{hf_repo}/resolve/main/{file}` — o endpoint público de
download direto, sem SDK e sem token para repo aberto.

```python
def download_one(model: ProfileModel, dest_dir: Path, client: httpx.Client) -> str
```

Algoritmo:
1. `local = dest_dir / model.file`; `have = local.stat().st_size` se existir,
   senão 0.
2. `GET` com `headers={"Range": f"bytes={have}-"}` quando `have > 0`, em
   streaming (`client.stream("GET", url, ...)`).
3. Status `416` (range além do fim) ou `Content-Range` cujo total é igual a
   `have` → arquivo já completo, devolve `"skipped"`.
4. Status `206` → abre em `"ab"` e anexa; se o arquivo completar, o retorno é
   `"resumed"`. Status `200` (sem `Range`, ou servidor que o ignorou) → abre em
   `"wb"` e escreve do zero; se completar, o retorno é `"downloaded"`.
5. Escreve em blocos de `CHUNK_BYTES = 1 << 20` com `iter_bytes`, sem carregar o
   arquivo em memória — são gigabytes.
6. No fim, compara o tamanho final com o total anunciado (`Content-Length` no
   caso 200, total do `Content-Range` no caso 206). Diferente → apaga **não**,
   deixa o parcial no disco (é o que permite retomar) e devolve `"partial"`, com
   o comando saindo com código 1.
7. `follow_redirects=True`: o Hugging Face responde `302` para um CDN.

Timeout: `httpx.Timeout(None, connect=30.0)` — sem teto de leitura, porque um
GGUF de 14 GB numa linha lenta ultrapassa qualquer valor razoável; o que precisa
falhar rápido é a conexão.

Costura para teste: a função recebe o `httpx.Client` pronto, e quem o constrói é
`download_profile`. O teste passa
`httpx.Client(transport=httpx.MockTransport(handler))`, servindo bytes falsos e
implementando `Range` no handler. Nenhum teste toca a rede, e `httpx` já é
dependência do projeto (`pyproject.toml:7`) — `MockTransport` vem com ele.

### CLI

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.models")
    sub = parser.add_subparsers(dest="command", required=True)
    download = sub.add_parser("download")
    download.add_argument("--profile", required=True)
    download.add_argument("--role", action="append")   # baixar só um papel
    ...

if __name__ == "__main__":
    raise SystemExit(main())
```

`--role` repetível filtra quais papéis baixar (útil quando só o utility mudou).
Sem ele, todos.

## Contrato público

```python
# backend/app/config.py
class ProfileModel(BaseModel):
    hf_repo: str
    file: str
    port: int
    ctx: int = 8192
    gpu_layers: int = -1

class Config(BaseModel):
    ...
    profiles: dict[str, dict[str, ProfileModel]] = {}

# backend/app/models.py
DEFAULT_PROFILES: dict[str, dict[str, ProfileModel]]   # "recommended", "premium"
CHUNK_BYTES: int
class UnknownProfile(Exception): ...

def models_dir() -> Path                                # CONFIG_DIR / "models"
def resolve_profile(name: str, config: Config) -> dict[str, ProfileModel]
def download_one(model: ProfileModel, dest_dir: Path, client: httpx.Client) -> str
    # "downloaded" (escrito do zero e completo) | "resumed" (206, anexado e completo)
    # | "skipped" (já estava completo) | "partial" (tamanho final != anunciado)
def download_profile(name: str, config: Config, roles: list[str] | None = None) -> dict
def main(argv: list[str] | None = None) -> int

# CLI
# uv run python -m app.models download --profile recommended [--role narrator ...]
```

Consumidor já enfileirado: TCK-085 (`serve` lê `resolve_profile`, `models_dir`,
`port`, `ctx` e `gpu_layers`, e imprime o trecho de `providers`/`models`).

## Acceptance criteria

- [ ] `Config` sem a chave `profiles` carrega e resolve para `{}`.
- [ ] YAML com `profiles.recommended.narrator.{hf_repo,file,port}` carrega e
      `resolve_profile("recommended", config)` devolve o do **usuário**, não o
      embutido.
- [ ] `resolve_profile` de um nome só existente em `DEFAULT_PROFILES` devolve o
      embutido; de um nome inexistente levanta `UnknownProfile`.
- [ ] `ProfileModel` sem `ctx`/`gpu_layers` resolve para `8192` e `-1`; sem
      `hf_repo`, `file` ou `port` levanta `ValidationError`.
- [ ] `download --profile recommended` com transporte mockado grava os dois
      arquivos em `models_dir()` com o conteúdo servido.
- [ ] Arquivo já presente com o tamanho completo é pulado, sem `GET` de corpo.
- [ ] Arquivo parcial é retomado: o handler recebe `Range: bytes=N-`, responde
      `206`, e o arquivo final tem o conteúdo inteiro e correto.
- [ ] Servidor que ignora o `Range` e responde `200` faz o arquivo ser reescrito
      do zero, e o resultado final é correto (sem bytes duplicados).
- [ ] Resposta cujo tamanho final não bate com o anunciado devolve `"partial"`,
      **mantém** o arquivo parcial no disco e faz o comando sair com código 1.
- [ ] `--profile fantasma` sai com código 2 e não faz requisição nenhuma.
- [ ] `--role utility` baixa só o utility.
- [ ] O comando imprime, antes de baixar, repo, arquivo e tamanho total do
      perfil.
- [ ] `backend/pyproject.toml` sem dependência nova.
- [ ] `npm run check` verde.

## Cenários de teste

Suíte existente que muda de preparação: **nenhuma**. Verificado:

- `backend/tests/test_config.py:7-12`
  (`test_creates_default_config_when_missing`) compara `DEFAULT_CONFIG` byte a
  byte. Este ticket **não** edita `DEFAULT_CONFIG`, e `profiles` tem default
  `{}`, então o teste segue verde sem edição.
- `backend/tests/test_config.py:14-24` valida o erro de papel com provider
  desconhecido; `profiles` não passa pelo `model_validator`
  (`config.py:47-53`), que itera `self.models`, não `self.profiles`. Um perfil
  não referencia provider e não deve entrar nessa validação.
- Nenhum outro teste da suíte constrói `Config` com campo posicional ou compara
  `Config` inteiro por igualdade (os `_config()` dos arquivos de teste usam
  `Config.model_validate({...})` com chaves nomeadas), então campo opcional novo
  não os afeta.
- `test_config.py` entra em `files` só pelos cenários **novos** de perfil.

Cenários novos em `backend/tests/test_config.py`:
- Feliz: YAML com um perfil completo → `ProfileModel` populado.
- Borda: perfil sem `ctx`/`gpu_layers` → defaults.
- Borda: config sem `profiles` → `{}`.
- Falha: `ProfileModel` sem `file` → `ValidationError`.

Cenários novos em `backend/tests/test_models_download.py`, com
`httpx.MockTransport` e `monkeypatch.setattr(models, "models_dir", lambda: tmp_path / "models")`
— nenhum toca a rede nem `~/.ooc-local`:
- Feliz: perfil de dois papéis baixado do zero.
- Feliz: retomada com `206`, conteúdo final íntegro.
- Borda: arquivo completo → `"skipped"` e zero bytes transferidos.
- Borda: servidor ignora `Range` e responde `200` → reescrita do zero.
- Borda: `--role` filtrando um papel só.
- Borda: `resolve_profile` com perfil do usuário sobrescrevendo o embutido.
- Falha: tamanho final diferente do anunciado → `"partial"`, arquivo mantido,
  código 1.
- Falha: `--profile` inexistente → código 2, `handler` nunca chamado.
- Conteúdo: `DEFAULT_PROFILES` tem `recommended` e `premium`, cada um com
  `narrator` e `utility`, com portas **diferentes** entre os dois papéis (é o
  que o TCK-085 precisa para subir dois processos).

## Rollout e kill switch

N/A. Comando de linha de comando rodado à mão, fora do `npm run dev`. Não é
importado por `main.py` nem por `turn.py`. O campo `profiles` é opcional e vazio
por padrão: uma instalação que nunca rodar o comando não percebe diferença
nenhuma.

## Observabilidade

Eventos: N/A (`emit`) — comando de lote, mesmo motivo dos outros da fase.

Saída em stdout: uma linha por papel antes de baixar
(`narrator TheDrummer/Rocinante-12B-v1.1-GGUF Rocinante-12B-v1.1-Q4_K_M.gguf 7.48 GB`),
o total do perfil, e uma linha de resultado por papel
(`downloaded` / `resumed` / `skipped` / `partial`). `download_profile` devolve o
mesmo como dicionário `papel -> resultado`.

Métrica de sucesso: numa máquina limpa, `download --profile recommended` seguido
de `serve` (TCK-085) leva o jogador do zero a um turno jogado sem ele abrir o
Hugging Face no navegador nenhuma vez.

## i18n

N/A. Saída de operador no terminal, em inglês, como o resto do código. Nenhuma
string entra em `frontend/src/strings/`.
