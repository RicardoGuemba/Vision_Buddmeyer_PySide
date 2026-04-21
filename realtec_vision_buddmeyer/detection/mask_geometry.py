# -*- coding: utf-8 -*-
"""
Geometria de máscaras de segmentação.

Extrai propriedades geométricas estáveis e auditáveis das máscaras binárias
do modelo Mask2Former (instance segmentation), relevantes para a plataforma
de pick-and-place:

- Centróide: média dos índices (y, x) dos pixels ativos da máscara.
  Mais estável que o centro do bbox para objetos não-retangulares.

- Área (px²): contagem de pixels positivos da máscara, usada para priorização
  do robô (confiança + área normalizada).

- Ângulo do eixo maior: calculado a partir do momento de inércia da máscara
  via autodecomposição (PCA 2D) da matriz de covariância dos pixels ativos.
  Retornado em [0, 180) graus, no referencial da imagem (eixo X horizontal,
  sentido horário ao somar, pois Y cresce para baixo em imagens).

Justificativa do método (PCA de segunda ordem):
- Equivalente analiticamente a `cv2.fitEllipse` sobre o contorno em massa,
  mas robusto a buracos e contornos fragmentados.
- Para retângulos alongados (embalagens), o autovetor associado ao maior
  autovalor da covariância é colinear ao lado maior.
- Resiliente a ruído de borda típico em máscaras de Mask2Former quantizadas.

Referência: Bishop, "Pattern Recognition and Machine Learning", §12.1.1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np


@dataclass(frozen=True)
class MaskGeometry:
    """Propriedades geométricas extraídas de uma máscara binária."""

    area_px: float            # pixels²
    centroid_x: float         # pixels (coord. imagem original)
    centroid_y: float         # pixels
    angle_deg: float          # [0, 180) — ângulo do eixo maior em graus
    major_axis_length: float  # pixels — ~2 * sqrt(maior autovalor)
    minor_axis_length: float  # pixels — ~2 * sqrt(menor autovalor)
    elongation: float         # major/minor (≥1), 1 quando circular/indefinido

    @property
    def centroid(self) -> Tuple[float, float]:
        return (self.centroid_x, self.centroid_y)


def _as_bool_mask(mask: np.ndarray) -> np.ndarray:
    """Converte a máscara para bool (H, W), aceita uint8/bool/0-1 float."""
    if mask.ndim != 2:
        raise ValueError(f"Mask deve ser 2D (H,W), recebido shape={mask.shape}")
    if mask.dtype == bool:
        return mask
    return mask > 0


def compute_mask_geometry(
    mask: np.ndarray,
    min_pixels: int = 10,
) -> Optional[MaskGeometry]:
    """
    Calcula centróide, área e ângulo do eixo maior de uma máscara binária.

    Args:
        mask: Máscara binária (H, W) de uma única instância.
        min_pixels: Número mínimo de pixels para considerar a máscara válida.
            Máscaras menores geram ruído numérico no PCA e são descartadas.

    Returns:
        MaskGeometry ou None se a máscara é inválida/muito pequena.

    Convenção de ângulo:
        - Referencial: eixo X horizontal da imagem.
        - Retornado em [0, 180) (objetos retangulares têm simetria de 180°).
        - Sinal compatível com convenção de imagem: atan2(vy, vx).
          Como Y cresce para baixo, um vetor visualmente "subindo-direita"
          (para o operador) terá vy<0 e, portanto, ângulo negativo antes
          do wrap para [0, 180). Isto é o mesmo referencial usado pelo
          VideoWidget/OpenCV.
    """
    bool_mask = _as_bool_mask(mask)

    ys, xs = np.nonzero(bool_mask)
    area = int(ys.size)

    if area < max(1, int(min_pixels)):
        return None

    mean_x = float(xs.mean())
    mean_y = float(ys.mean())

    if area < 3:
        return MaskGeometry(
            area_px=float(area),
            centroid_x=mean_x,
            centroid_y=mean_y,
            angle_deg=0.0,
            major_axis_length=1.0,
            minor_axis_length=1.0,
            elongation=1.0,
        )

    dx = xs.astype(np.float64) - mean_x
    dy = ys.astype(np.float64) - mean_y
    cov_xx = float(np.mean(dx * dx))
    cov_yy = float(np.mean(dy * dy))
    cov_xy = float(np.mean(dx * dy))

    cov = np.array([[cov_xx, cov_xy], [cov_xy, cov_yy]], dtype=np.float64)
    try:
        eigvals, eigvecs = np.linalg.eigh(cov)
    except np.linalg.LinAlgError:
        return MaskGeometry(
            area_px=float(area),
            centroid_x=mean_x,
            centroid_y=mean_y,
            angle_deg=0.0,
            major_axis_length=1.0,
            minor_axis_length=1.0,
            elongation=1.0,
        )

    order = np.argsort(eigvals)[::-1]
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]

    major_eigval = max(float(eigvals[0]), 0.0)
    minor_eigval = max(float(eigvals[1]), 0.0)

    major_vec = eigvecs[:, 0]
    vx, vy = float(major_vec[0]), float(major_vec[1])

    angle_rad = np.arctan2(vy, vx)
    angle_deg = float(np.degrees(angle_rad))
    angle_deg = angle_deg % 180.0

    major_len = 4.0 * float(np.sqrt(major_eigval)) if major_eigval > 0 else 1.0
    minor_len = 4.0 * float(np.sqrt(minor_eigval)) if minor_eigval > 0 else 1.0
    elongation = float(major_len / minor_len) if minor_len > 1e-9 else 1.0

    return MaskGeometry(
        area_px=float(area),
        centroid_x=mean_x,
        centroid_y=mean_y,
        angle_deg=angle_deg,
        major_axis_length=major_len,
        minor_axis_length=minor_len,
        elongation=elongation,
    )


def major_axis_endpoints(
    geometry: MaskGeometry,
    length_scale: float = 1.0,
) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """
    Retorna os dois pontos extremos do segmento que representa o eixo maior.

    Útil para desenhar o vetor do eixo maior passando pelo centróide na UI.

    Args:
        geometry: Geometria calculada.
        length_scale: Escala do comprimento do eixo (1.0 = comprimento real).

    Returns:
        Tuple com ((x0, y0), (x1, y1)).
    """
    angle_rad = np.radians(geometry.angle_deg)
    half = 0.5 * geometry.major_axis_length * float(length_scale)
    dx = float(np.cos(angle_rad)) * half
    dy = float(np.sin(angle_rad)) * half
    cx, cy = geometry.centroid
    return (cx - dx, cy - dy), (cx + dx, cy + dy)
