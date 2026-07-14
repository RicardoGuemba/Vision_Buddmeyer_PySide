# Buddmeyer Vision System v2.0

Sistema de visão computacional industrial para automação de expedição (pick-and-place) de embalagens.

## Características

- **Segmentação em tempo real** com Mask2Former (`model_best/`) — centróide, ângulo e área por embalagem
- **Comunicação industrial** com CLP Omron NX102 via CIP/EtherNet-IP
- **Interface desktop PySide6** — abas Operação, Configuração, Diagnósticos
- **Múltiplas fontes de vídeo:** arquivo MP4, USB, GigE, GenTL (RTSP via YAML)
- **Logs estruturados** e modo simulado para desenvolvimento sem CLP

## Requisitos

| Requisito | Valor |
|-----------|-------|
| SO | macOS 12+, Ubuntu 22.04+, Windows 10/11 |
| Python | 3.10+ |
| RAM | 8 GB mínimo (16 GB recomendado) |
| Git LFS | Obrigatório para pesos do modelo (~181 MB) |

## Instalação rápida

```bash
git clone https://github.com/RicardoGuemba/Realtec_Vision_Buddmeyer.git
cd Realtec_Vision_Buddmeyer
git lfs install && git lfs pull

python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r realtec_vision_buddmeyer/requirements.txt
```

## Execução

```bash
cd realtec_vision_buddmeyer
python main.py
```

**Atalhos na raiz do repo:** `Iniciar Realtec Vision.command` (macOS) ou `./Iniciar_Realtec_Vision.sh`.

## Testes

```bash
cd realtec_vision_buddmeyer
python -m pytest tests/ -v
```

## Documentação

| Documento | Descrição |
|-----------|-----------|
| [docs/OVERVIEW.md](docs/OVERVIEW.md) | Visão geral executiva (alto nível) |
| [docs/REFERENCE.md](docs/REFERENCE.md) | Referência técnica (baixo nível) |
| [docs/GUIA_OPERADOR.md](docs/GUIA_OPERADOR.md) | Tutorial das abas para operador |
| [docs/SEGMENTATION_PIPELINE.md](docs/SEGMENTATION_PIPELINE.md) | Pipeline Mask2Former |
| [docs/TAG_CONTRACT.md](docs/TAG_CONTRACT.md) | Contrato de tags CLP |
| [docs/CLONE_BOX_PC.md](docs/CLONE_BOX_PC.md) | Deploy no box PC |
| [ROTEIRO_CLIENTE.md](ROTEIRO_CLIENTE.md) | Guia do cliente (IP, logs) |
| [docs/MACOS_SETUP.md](docs/MACOS_SETUP.md) / [docs/UBUNTU_SETUP.md](docs/UBUNTU_SETUP.md) | Instalação por SO |

## Estrutura

```
realtec_vision_buddmeyer/
├── main.py
├── config/              # settings.py + config.yaml
├── core/                # logger, metrics, exceptions
├── streaming/           # captura + mjpeg_server
├── detection/           # inferência Mask2Former + geometria
├── communication/       # CIP client
├── control/             # robot_controller (FSM)
├── ui/                  # PySide6
├── model_best/          # modelo (Git LFS)
├── tests/
├── scripts/             # smoke_test, check_model
└── docs/
```

## Configuração

Edite `config/config.yaml`. Exemplo:

```yaml
streaming:
  source_type: usb
detection:
  model_path: model_best
  confidence_threshold: 0.5
  inference_fps: 4
cip:
  ip: 192.168.1.10
  port: 44818
  simulated: false
```

## Tags CLP (resumo)

**Visão → CLP:** `PRODUCT_DETECTED`, `CENTROID_X`, `CENTROID_Y`, `CENTROID_ANGLE`, `OBJECT_AREA`, `CONFIDENCE`

**CLP → Visão:** `ROBOT_ACK`, `ROBOT_READY`, `RobotStatus_PickComplete`, `RobotStatus_PlaceComplete`

Lista completa: [docs/TAG_CONTRACT.md](docs/TAG_CONTRACT.md).

## Licença

© Realtec — Sistema de Automação Industrial
