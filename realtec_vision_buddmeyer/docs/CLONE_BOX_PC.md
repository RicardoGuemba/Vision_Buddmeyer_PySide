# Clonar e executar no Box PC (Guilherme)

Este guia cobre o **Vision Buddmeyer** (`realtec_vision_buddmeyer`) num PC industrial típico (Windows ou Linux), com o modelo **Mask2Former** já incluído no repositório via **Git LFS**.

## O que vai descarregar

- Código-fonte (pasta `realtec_vision_buddmeyer/`).
- Metadados do modelo em `model_best/` (`config.json`, `preprocessor_config.json`, `task.json`, `training_args.bin`).
- **Pesos:** `model_best/model.safetensors` (~**181 MB**). Não são “só alguns bytes”: o ficheiro é grande; por isso está em **Git LFS** (limite do GitHub para blobs normais é 100 MB).

## Pré-requisitos no Box PC

1. **Git** (2.x ou superior): [https://git-scm.com/downloads](https://git-scm.com/downloads)
2. **Git LFS** (obrigatório para receber os pesos):
   - Windows: instalador em [https://git-lfs.com](https://git-lfs.com) ou `winget install Git.GitLFS`
   - Linux: `sudo apt install git-lfs` (Debian/Ubuntu) e depois `git lfs install` uma vez por utilizador
3. **Python 3.11 ou 3.12** (64 bits): [https://www.python.org/downloads/](https://www.python.org/downloads/)  
   Marque “Add Python to PATH” no instalador Windows.
4. **Câmera USB** e permissões de câmera (Windows: Definições → Privacidade → Câmara).

## Clonar o repositório

Substitua a URL pela do repositório que a Realtec lhe indicar (ex.: GitHub).

```bash
git clone https://github.com/RicardoGuemba/Vision_Buddmeyer_PySide.git
cd Vision_Buddmeyer_PySide
git lfs install
git lfs pull
```

Confirme que o ficheiro de pesos é real (não 130 bytes de “pointer”):

```bash
# Windows PowerShell
(Get-Item realtec_vision_buddmeyer\model_best\model.safetensors).Length

# Linux / macOS
ls -lh realtec_vision_buddmeyer/model_best/model.safetensors
```

Deve mostrar aproximadamente **181 MB**. Se vir ~130 bytes, corra de novo `git lfs pull` na raiz do clone.

## Ambiente Python

```bash
cd realtec_vision_buddmeyer
python -m venv .venv
```

**Windows (cmd):**

```bat
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**Windows (PowerShell):**

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**Linux:**

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### PyTorch no Box PC

O `requirements.txt` instala `torch` a partir do PyPI. Num PC **só CPU**, isso costuma ser suficiente. Se precisar de **CUDA** no Windows, siga a matriz oficial da PyTorch e instale o wheel indicado para a sua versão de driver/CUDA **antes** ou **depois** de alinhar com o projeto: [https://pytorch.org/get-started/locally/](https://pytorch.org/get-started/locally/)

## Configuração mínima antes de correr

1. **`config/config.yaml`** (ou variáveis de ambiente, se usarem):
   - `streaming.usb_camera_index`: índice da câmera USB no OpenCV (0, 1, 2…). No primeiro arranque, teste qual abre a câmera certa.
   - `detection.model_path`: deve permanecer `model_best` se os ficheiros estiverem nessa pasta após o `git lfs pull`.
   - `cip.simulated: true` para testar **sem** CLP real; `false` quando ligar ao Omron na rede.

2. **Rede / CLP:** com `simulated: false`, o IP e timeouts em `config.yaml` têm de corresponder ao equipamento.

## Executar a aplicação

Na pasta `realtec_vision_buddmeyer` com o venv ativo:

```bash
python main.py
```

## Teste rápido só visão (sem Qt prolongado)

```bash
cd realtec_vision_buddmeyer
python -m scripts.smoke_test_segmentation --frames 5 --camera 0 --confidence 0.5
```

Ajuste `--camera` se a USB não for o índice 0.

## Testes automáticos (opcional)

```bash
cd realtec_vision_buddmeyer
pip install pytest pytest-qt
python -m pytest tests/ -q
```

## Documentação adicional

- Pipeline de segmentação: `docs/SEGMENTATION_PIPELINE.md`
- Contrato de tags CLP: `docs/TAG_CONTRACT.md`

## Resumo para o Guilherme

| Passo | Comando / ação |
|--------|----------------|
| 1 | Instalar Git + **Git LFS** |
| 2 | `git clone …` → `cd` para a pasta do repo |
| 3 | `git lfs install` e `git lfs pull` |
| 4 | `cd realtec_vision_buddmeyer` → criar venv → `pip install -r requirements.txt` |
| 5 | Ajustar `config/config.yaml` (câmera, CLP simulado/real) |
| 6 | `python main.py` |

Em caso de falha no `git lfs pull` (firewall, proxy corporativo), peça à equipa IT abertura para `github.com` e `github-cloud.githubusercontent.com` ou use um pacote offline com a pasta `model_best` completa copiada de outra máquina.
