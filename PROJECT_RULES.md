# Regras do Projeto — Realtec Vision Buddmeyer (Mark2)

## Stack

- UI: PySide6
- Camadas: `streaming/`, `detection/`, `robot/`, `ui/`, `config/`, `core/`, `firmware/`
- Actuação: Arduino + Mark2 via `robot/mark2_serial.py`

## Testes

`python -m pytest tests/ -q` em `realtec_vision_buddmeyer/`.
