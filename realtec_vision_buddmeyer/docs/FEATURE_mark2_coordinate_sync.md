# FEATURE: Calibração / sincronização de coordenadas visão ↔ Mark2

| Campo | Valor |
|--------|--------|
| **Autor** | Realtec |
| **Data** | 2026-07-30 |
| **Estado** | implementado |
| **Issue / ticket** | — |

---

## 1. Contexto e problema

- **Situação atual:** só existe escala linear `roi_calibration_mm_per_px`.
- **Utilizador afetado:** técnico de calibração / integração Mark2.
- **Porque agora:** pick-and-place exige homografia + origem do robô.

## 2. Objetivo

- **Objetivo principal:** wizard de calibração com homografia, origem/rotação e RMSE.
- **Não-objectivos:** movimento automático durante calibração; alteração do Mask2Former.

## 3. Requisitos funcionais

| ID | Descrição | Prioridade |
|----|-----------|------------|
| RF-01 | Wizard 3 passos (pontos, origem, validação) | P0 |
| RF-02 | Clique no vídeo → (u,v) em pixels do frame | P0 |
| RF-03 | Homografia ≥4 pontos e persistência em mark2.yaml | P0 |
| RF-04 | Live px / world mm / robot mm / alcançável | P0 |
| RF-05 | RMSE vs max_rmse_mm | P0 |

## 8. Critérios de aceitação

| ID | Critério | Como verificar |
|----|----------|----------------|
| CA-01 | Homografia com ≥4 pontos | `pytest tests/test_mark2_calibration.py` |
| CA-02 | RMSE reportado | idem |
| CA-03 | Fora do workspace → não alcançável | idem |
| CA-04 | Calibração sem Arduino | UI aba Calibração |

## 11. Checklist

- [x] mark2_calibration.py
- [x] Clique em pixels
- [x] Página wizard
- [x] Testes
