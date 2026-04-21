# Pipeline de Instance Segmentation (Mask2Former)

Este documento descreve o pipeline de detecção atualizado baseado em
**instance segmentation** (modelo `Mask2FormerForUniversalSegmentation`
treinado pelo cliente, em `realtec_vision_buddmeyer/model_best/`).

O objetivo é fornecer à plataforma de pick-and-place três informações
por embalagem, cada uma derivada da máscara e, portanto, mais robusta
do que o bounding box:

1. **X, Y**: centróide geométrico da máscara (mais estável do que o
   centro do bbox para formas irregulares/rotacionadas).
2. **Ângulo do eixo maior**: orientação da embalagem em graus `[0, 180)`,
   calculada via PCA (autodecomposição da matriz de covariância dos
   pixels ativos da máscara).
3. **Área (px²)**: contagem de pixels da máscara, usada para
   priorização: a melhor detecção combina confiança com área
   normalizada (`best_by_priority`).

## Arquitetura

```
┌──────────────────────────────────────────────────────────────────┐
│ Streaming (USB / GigE / RTSP / vídeo)                            │
│     ↓  frame BGR                                                 │
│ InferenceWorker (QThread)                                        │
│     ↓  frame → PIL → Mask2FormerImageProcessor                   │
│     ↓  tensors → model (MPS / CUDA / CPU)                        │
│     ↓  outputs movidos para CPU (estável para interpolate)       │
│ SegmentationPostProcessor                                        │
│     ↓  post_process_instance_segmentation (transformers)         │
│     ↓  masks + scores + labels                                   │
│ mask_geometry.compute_mask_geometry (PCA 2D)                     │
│     ↓  centróide, área, ângulo, elongation                       │
│ Detection (bbox, mask, angle_deg, area_px, centroid_override)    │
│     ↓                                                            │
│ DetectionResult.best_by_priority (confiança + área)              │
│     ↓                                                            │
│ DetectionEvent.to_plc_data (dict)                                │
│     ↓                                                            │
│ CIPClient.write_detection_result → CLP Omron NX102               │
│   Tags: CENTROID_X, CENTROID_Y, CENTROID_ANGLE, OBJECT_AREA, ... │
└──────────────────────────────────────────────────────────────────┘
```

## Escolha de Task e Modelo

`ModelLoader._detect_task` inspeciona, nesta ordem:

1. `model_best/task.json` (campo `task`).
2. `model_best/config.json` → `model_type` contra lista de tipos de
   segmentação (`mask2former`, `maskformer`, `oneformer`).
3. `architectures` contendo `Segmentation`.
4. Heurística por nome (quando o modelo vem do hub).

Se a task for `instance_segmentation`, o modelo é carregado como
`Mask2FormerForUniversalSegmentation` e o `InferenceEngine` escolhe
`SegmentationPostProcessor`; caso contrário, mantém o pipeline clássico
de object detection (DETR/RT-DETR) sem regressão.

## Geometria da Máscara (`mask_geometry.py`)

Para uma máscara binária `(H, W)`:

- **Centróide**: média dos índices `(y, x)` dos pixels ativos.
- **Área**: `np.nonzero(mask)[0].size`.
- **Ângulo**: ângulo (em graus, `[0, 180)`) do autovetor associado ao
  **maior autovalor** da matriz de covariância dos pixels ativos.
  Para retângulos alongados (caso típico de embalagens), esse autovetor
  é colinear ao lado maior.
- **Elongation**: `major_axis_length / minor_axis_length`, proxy de
  achatamento.

Justificativa: PCA de segunda ordem é analiticamente equivalente a
ajustar uma elipse de inércia à distribuição de massa da máscara,
robusto a buracos/fragmentação (diferente de `cv2.fitEllipse`, que só
usa o contorno).

### Convenção de ângulo

- Referencial: eixo X horizontal da imagem.
- Como `Y` cresce para baixo em imagens, o sentido de rotação positivo é
  **horário** para o operador humano. Isto é consistente com o que o
  VideoWidget/OpenCV desenha.
- Devido à simetria de 180° de um retângulo, o valor é reduzido para
  `[0, 180)`.

## Priorização (`best_by_priority`)

A plataforma de pick otimiza o deslocamento priorizando embalagens
maiores entre as detectadas. O score usado é:

```
score(d) = w_conf * d.confidence + w_area * (d.effective_area_px / max_area)
```

com pesos configuráveis. Isto implementa o requisito do cliente
("conciliar confiança e maior área para otimizar deslocamento do robô").

## TAGs do CLP

Duas novas TAGs (tipo `REAL`, direção `WRITE`) foram adicionadas:

| Tag lógica      | Nome PLC          | Descrição                           |
|-----------------|-------------------|-------------------------------------|
| `CentroidAngle` | `CENTROID_ANGLE`  | Ângulo do eixo maior, graus [0,180) |
| `ObjectArea`    | `OBJECT_AREA`     | Área da embalagem (px² ou mm²)      |

Quando `preprocess.roi_calibration_mm_per_px != 1`, a área é convertida
para mm² (`area_mm2 = area_px * (mm_per_px)^2`). O ângulo é invariante
à escala e enviado como está.

Todos os campos preexistentes (`CENTROID_X`, `CENTROID_Y`, `CONFIDENCE`,
etc.) continuam sendo escritos com o mesmo contrato; `write_detection_result`
agora aceita `angle_deg` e `area` como parâmetros opcionais com default
`0.0`, preservando compatibilidade com chamadas antigas.

## MPS / Apple Silicon

`ModelLoader._resolve_device("auto")` prioriza MPS no M4.

Para evitar bugs conhecidos de `torch.nn.functional.interpolate` em MPS
durante o pós-processamento de máscaras, os outputs do modelo são movidos
para CPU antes de `post_process_instance_segmentation`. A inferência
permanece em MPS (onde está o ganho computacional); apenas o
pós-processamento roda em CPU. Em benchmarks, o overhead é desprezível
comparado ao tempo de inferência.

## Testes

- `tests/test_mask_geometry.py`: máscaras sintéticas com ângulos
  conhecidos (0°, 15°, 30°, 45°, 60°, 75°, 120°, 150°), discos e
  retângulos, verificando centróide, área e ângulo.
- `tests/test_segmentation_postprocess.py`: com um processor fake,
  valida filtragem por confiança, por classe, construção de `Detection`
  com todos os novos campos e respeito a `max_detections`.
- `tests/test_events_segmentation.py`: prioridade conf+área e
  `to_plc_data` com defaults para modelos sem segmentação.
- `tests/test_tag_map_segmentation.py`: whitelist das novas TAGs.
- `tests/test_model_validator_segmentation.py`: aceita `mask2former` e
  mantém compatibilidade com `detr`/`rtdetr`.

## Smoke test com câmera USB

```
python -m scripts.smoke_test_segmentation --frames 10 --camera 0 --save debug.png
```

O script captura frames, roda o pipeline completo e imprime por frame:
número de detecções, tempo de inferência, e, para a melhor detecção,
confiança, `(x, y)`, ângulo e área. Sai com código 0 apenas se houve
pelo menos uma detecção (com embalagem no FOV).
