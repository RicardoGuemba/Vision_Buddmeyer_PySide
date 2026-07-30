# Realtec Vision Buddmeyer — Visão Geral (Mark2)

Sistema de visão para pick-and-place de embalagens Buddmeyer com braço MakerQuest Mark2 comandado por Arduino Uno + Sensor Shield V5.

## O que o sistema faz

1. Captura vídeo (USB, ficheiro, GigE/GenTL).
2. Segmenta embalagens com **Mask2Former**.
3. Calcula ponto de pega, estabiliza detecção e converte coordenadas (calibração homografia).
4. Comanda 4 servos via serial USB (`MOVE` / `HOME` / `STOP`).
5. UI PySide6: Operação, Configuração, **Calibração Mark2**, Diagnósticos.

## Actuação

| Componente | Função |
|------------|--------|
| Python `robot/` | IK, planner, FSM, calibração |
| Arduino firmware | PWM servos, protocolo serial |
| Shield V5 | Ligação física dos servos |

## Stack

PySide6, PyTorch/Transformers (Mask2Former), OpenCV, pyserial, Pydantic/YAML.

© Realtec — Buddmeyer Vision + Mark2
