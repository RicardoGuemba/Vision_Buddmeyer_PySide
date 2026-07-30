# Buddmeyer Vision System v2.0 — Mark2

Sistema de visão computacional para pick-and-place de embalagens Buddmeyer com braço MakerQuest Mark2 (Arduino Uno + Sensor Shield V5).

## Características

- **Segmentação em tempo real** com Mask2Former (`model_best/`)
- **Actuação Mark2** via USB serial (`MOVE` / `HOME` / `STOP`)
- **Calibração** pixel ↔ mundo ↔ robô (homografia) na aba dedicada
- **UI PySide6:** Operação, Configuração, Calibração Mark2, Diagnósticos
- **Fontes de vídeo:** MP4, USB, GigE, GenTL
- **Smoke test:** detecção → acionar motor (sem pose)

## Requisitos

| Requisito | Valor |
|-----------|-------|
| SO | macOS 12+, Ubuntu 22.04+, Windows 10/11 |
| Python | 3.10+ |
| Hardware | Arduino Uno, Shield V5, 4 servos, fonte 5 V ≥2 A |
| Git LFS | Obrigatório para pesos do modelo (~181 MB) |

## Instalação rápida

```bash
cd realtec_vision_buddmeyer
python3 -m venv ../venv && source ../venv/bin/activate
pip install -r requirements.txt
python main.py
```

Gravar firmware: `firmware/mark2_uno/mark2_uno.ino` (Arduino IDE, 115200 baud).

## Estrutura

```
realtec_vision_buddmeyer/
├── main.py
├── config/          # config.yaml + mark2.yaml
├── robot/           # serial, IK, calibração, FSM, worker
├── firmware/        # sketch Arduino
├── detection/       # Mask2Former
├── streaming/
├── ui/
├── tests/
└── docs/
    FEATURE_mark2_integration.md
    FEATURE_mark2_coordinate_sync.md
```

## Configuração

- Visão / câmera: `config/config.yaml`
- Mark2 / serial / geometria / calibração: `config/mark2.yaml`

## Testes

```bash
python -m pytest tests/ -q
# Serial com hardware:
MARK2_PORT=/dev/cu.usbmodem1101 python -m scripts.smoke_test_mark2_serial
```

© Realtec — Buddmeyer Vision + Mark2
