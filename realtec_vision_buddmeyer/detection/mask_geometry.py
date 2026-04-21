# -*- coding: utf-8 -*-
"""
Geometria de máscaras de segmentação.

Extrai propriedades geométricas estáveis e auditáveis das máscaras binárias
do modelo Mask2Former (instance segmentation), relevantes para a plataforma
de pick-and-place:

- Centróide (x, y): média dos índices dos pixels ativos da máscara.
  Mais estável que o centro do bbox para objetos não-retangulares.

- Área (px²): contagem de pixels positivos da máscara, usada para priorização
  do robô (confiança + área normalizada).

- Ângulo do eixo maior (graus em [0, 180)): calculado a partir da caixa
  mínima rotacionada (`cv2.minAreaRect`) sobre o maior contorno da máscara.
  Esta escolha garante que o eixo maior fica SEMPRE paralelo aos lados
  do objeto, propriedade essencial para embalagens retangulares.

- Comprimento dos eixos: lados reais do retângulo mínimo.

Método:
    Primário  : `cv2.minAreaRect` sobre o maior contorno externo.
                Produz ((cx_r, cy_r), (w, h), angle) onde angle ∈ (-90, 0].
                O ângulo do eixo maior é `angle` se w >= h, senão `angle + 90`,
                normalizado em [0, 180).
    Fallback  : PCA 2D da matriz de covariância dos pixels (sem OpenCV).
                O autovetor do maior autovalor é colinear ao lado maior para
                distribuições razoavelmente uniformes em retângulos.

O centróide permanece como a média dos pixels (mais robusto ao formato real
da embalagem) mesmo quando o ângulo vem de minAreaRect. Área é sempre a
contagem de pixels da máscara (e não a área do retângulo mínimo).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np


@dataclass(frozen=True)
class MaskGeometry:
    """Propriedades geométricas extraídas de uma máscara binária."""

    area_px: float            # pixels² (pixels ativos da máscara)
    centroid_x: float         # pixels (coord. imagem original)
    centroid_y: float         # pixels
    angle_deg: float          # [0, 180) — ângulo do eixo maior
    major_axis_length: float  # pixels — lado maior do retângulo mínimo
    minor_axis_length: float  # pixels — lado menor do retângulo mínimo
    elongation: float         # major/minor (≥1), 1 quando quadrado/indefinido

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


def _angle_and_sides_from_min_area_rect(
    bool_mask: np.ndarray,
) -> Optional[Tuple[float, float, float]]:
    """
    Usa `cv2.minAreaRect` para extrair (angle_deg, major_len, minor_len).

    Retorna None se OpenCV não estiver disponível, se não houver contorno
    válido ou se ambos os lados forem degenerados.

    Convenção de saída:
        - angle_deg ∈ [0, 180)
        - major_len ≥ minor_len
    """
    try:
        import cv2  # noqa: WPS433  (import local para tornar o módulo opcional)
    except ImportError:
        return None

    bin_mask = bool_mask.astype(np.uint8)
    contours, _ = cv2.findContours(
        bin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
    )
    if not contours:
        return None

    # Escolhe o maior contorno (mais robusto a pequenas ilhas de ruído)
    contour = max(contours, key=cv2.contourArea)
    if contour.shape[0] < 3:
        return None

    (_, _), (w, h), angle_rect = cv2.minAreaRect(contour)
    w = float(w)
    h = float(h)
    if w <= 0 and h <= 0:
        return None

    # cv2.minAreaRect retorna ângulo em (-90, 0], medido entre o lado horizontal
    # inferior e o eixo X. Ajustamos para o ângulo do *lado maior* em [0, 180).
    if w >= h:
        major_len, minor_len = w, h
        angle = float(angle_rect)
    else:
        major_len, minor_len = h, w
        angle = float(angle_rect) + 90.0

    angle = angle % 180.0
    return angle, major_len, max(minor_len, 1.0)


def _angle_and_sides_from_pca(
    xs: np.ndarray,
    ys: np.ndarray,
    mean_x: float,
    mean_y: float,
) -> Tuple[float, float, float]:
    """
    Fallback PCA puro-NumPy.

    Retorna (angle_deg em [0,180), major_len, minor_len) a partir da
    covariância dos pixels da máscara. Usa fator 4·sqrt(λ) como proxy
    aproximado para o comprimento dos lados (equivalente a ~2·desvio
    padrão em cada direção, escalado para bater com o retângulo).
    """
    dx = xs.astype(np.float64) - mean_x
    dy = ys.astype(np.float64) - mean_y
    cov_xx = float(np.mean(dx * dx))
    cov_yy = float(np.mean(dy * dy))
    cov_xy = float(np.mean(dx * dy))

    cov = np.array([[cov_xx, cov_xy], [cov_xy, cov_yy]], dtype=np.float64)
    try:
        eigvals, eigvecs = np.linalg.eigh(cov)
    except np.linalg.LinAlgError:
        return 0.0, 1.0, 1.0

    order = np.argsort(eigvals)[::-1]
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]

    major_eigval = max(float(eigvals[0]), 0.0)
    minor_eigval = max(float(eigvals[1]), 0.0)

    major_vec = eigvecs[:, 0]
    vx, vy = float(major_vec[0]), float(major_vec[1])

    angle = float(np.degrees(np.arctan2(vy, vx))) % 180.0
    major_len = 4.0 * float(np.sqrt(major_eigval)) if major_eigval > 0 else 1.0
    minor_len = 4.0 * float(np.sqrt(minor_eigval)) if minor_eigval > 0 else 1.0
    return angle, major_len, minor_len


def compute_mask_geometry(
    mask: np.ndarray,
    min_pixels: int = 10,
) -> Optional[MaskGeometry]:
    """
    Calcula centróide, área e ângulo do eixo maior de uma máscara binária.

    Para objetos retangulares (embalagens), o ângulo é estimado pela
    caixa mínima rotacionada do maior contorno. Isto garante eixo
    sempre paralelo aos lados do retângulo detectado, mesmo quando
    a máscara tem bordas serrilhadas/ruído.

    Args:
        mask: Máscara binária (H, W) de uma única instância.
        min_pixels: Número mínimo de pixels para considerar válida.

    Returns:
        MaskGeometry ou None se a máscara é inválida/muito pequena.
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

    rect = _angle_and_sides_from_min_area_rect(bool_mask)
    if rect is not None:
        angle_deg, major_len, minor_len = rect
    else:
        angle_deg, major_len, minor_len = _angle_and_sides_from_pca(
            xs, ys, mean_x, mean_y,
        )

    elongation = float(major_len / minor_len) if minor_len > 1e-9 else 1.0

    return MaskGeometry(
        area_px=float(area),
        centroid_x=mean_x,
        centroid_y=mean_y,
        angle_deg=float(angle_deg),
        major_axis_length=float(major_len),
        minor_axis_length=float(minor_len),
        elongation=elongation,
    )


def major_axis_endpoints(
    geometry: MaskGeometry,
    length_scale: float = 1.0,
) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """
    Retorna os dois pontos extremos do segmento que representa o eixo maior.

    Útil para desenhar o vetor do eixo maior passando pelo centróide na UI.
    Com `length_scale=1.0`, o segmento cobre exatamente o lado maior do
    retângulo mínimo (tamanho real do objeto).

    Args:
        geometry: Geometria calculada.
        length_scale: Escala do comprimento do eixo (1.0 = tamanho real).

    Returns:
        Tuple com ((x0, y0), (x1, y1)).
    """
    angle_rad = np.radians(geometry.angle_deg)
    half = 0.5 * geometry.major_axis_length * float(length_scale)
    dx = float(np.cos(angle_rad)) * half
    dy = float(np.sin(angle_rad)) * half
    cx, cy = geometry.centroid
    return (cx - dx, cy - dy), (cx + dx, cy + dy)
