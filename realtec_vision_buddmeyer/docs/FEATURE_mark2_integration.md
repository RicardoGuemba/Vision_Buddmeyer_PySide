# FEATURE: Integração Mark2 + Arduino

| Campo | Valor |
|--------|--------|
| **Autor** | Realtec |
| **Data** | 2026-07-30 |
| **Estado** | implementado |
| **Issue / ticket** | — |

---

## 1. Contexto e problema

- **Situação atual:** o supervisório falava com CLP Omron via CIP; não há braço Mark2 físico.
- **Utilizador afetado:** operador / integração laboratorial Buddmeyer + MakerQuest Mark2.
- **Porque agora:** substituir CIP por Arduino Uno + Sensor Shield V5 + 4 servos.

## 2. Objetivo

- **Objetivo principal:** detectar embalagens com Mask2Former e comandar o Mark2 por serial USB.
- **Não-objectivos:** alterar captura/Mask2Former; modo automático de produção (fica desligado).

## 3. Requisitos funcionais

| ID | Descrição | Prioridade |
|----|-----------|------------|
| RF-01 | Firmware Arduino READY/MOVE/HOME/STOP | P0 |
| RF-02 | Mark2Serial com lock e timeout | P0 |
| RF-03 | FSM + RobotWorker assíncrono | P0 |
| RF-04 | Pick-and-place semiautomático | P0 |
| RF-05 | Smoke: detecção → acionar motor sem pose | P0 |
| RF-06 | Painel Mark2 na UI | P0 |

## 8. Critérios de aceitação

| ID | Critério | Como verificar |
|----|----------|----------------|
| CA-01 | Serial mock responde READY/OK | `pytest tests/test_mark2_serial.py` |
| CA-02 | FSM rejeita tarefa se BUSY | `pytest tests/test_mark2_controller.py` |
| CA-03 | Smoke não exige calibração | modo `smoke_detection_trigger` na UI |
| CA-04 | Vídeo não bloqueia durante MOVE | RobotWorker em QThread |

## 11. Checklist

- [x] Firmware
- [x] Serial + worker
- [x] UI painel
- [x] Testes unitários
