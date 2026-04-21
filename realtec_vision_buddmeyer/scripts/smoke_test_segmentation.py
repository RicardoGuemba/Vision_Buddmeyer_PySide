#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smoke test end-to-end do pipeline de instance segmentation.

Captura N frames de uma câmera USB, executa inferência com o modelo
Mask2Former (`model_best`) em MPS/CPU, e valida que:
  - O modelo carregou com task == instance_segmentation.
  - Para cada frame com embalagem no FOV, há pelo menos 1 detecção.
  - A melhor detecção possui centróide (x, y), ângulo [0, 180) e área > 0.

Uso:
    python -m scripts.smoke_test_segmentation --frames 10 --camera 0
    python -m scripts.smoke_test_segmentation --frames 10 --camera 0 --save debug.png

Saída: relatório textual em stdout; código de saída 0 se tudo OK.

NOTA: executa em processo único (sem Qt) para facilitar debug;
o pipeline de produção usa QThread via InferenceEngine.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _open_camera(index: int, width: int, height: int, warmup_frames: int = 10):
    import cv2
    import time

    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        raise RuntimeError(f"Não foi possível abrir a câmera USB index={index}")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    time.sleep(0.3)
    for _ in range(warmup_frames):
        ret, _frm = cap.read()
        if ret:
            break
        time.sleep(0.1)
    return cap


def _draw_overlay(frame: np.ndarray, detection) -> np.ndarray:
    import cv2
    import math

    out = frame.copy()
    if detection.has_mask and detection.mask is not None:
        contours, _ = cv2.findContours(
            detection.mask.astype(np.uint8),
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        cv2.drawContours(out, contours, -1, (0, 255, 0), 2)
    cx_f, cy_f = detection.centroid
    cx, cy = int(cx_f), int(cy_f)
    cv2.circle(out, (cx, cy), 8, (0, 255, 255), -1)

    if detection.angle_deg is not None:
        if detection.major_axis_length is not None and detection.major_axis_length > 0:
            half = 0.5 * float(detection.major_axis_length)
        else:
            half = 0.5 * max(detection.bbox.width, detection.bbox.height)
        dx = math.cos(math.radians(detection.angle_deg)) * half
        dy = math.sin(math.radians(detection.angle_deg)) * half
        p1 = (int(cx_f - dx), int(cy_f - dy))
        p2 = (int(cx_f + dx), int(cy_f + dy))
        cv2.line(out, p1, p2, (255, 0, 255), 3)

    label = f"{detection.class_name} {detection.confidence:.0%}"
    if detection.angle_deg is not None:
        label += f" | ang={detection.angle_deg:.1f}"
    if detection.area_px is not None:
        label += f" | A={int(detection.area_px)}"
    cv2.putText(out, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    return out


def run(args) -> int:
    from detection.model_loader import ModelLoader, TASK_INSTANCE_SEGMENTATION
    from detection.segmentation_postprocess import SegmentationPostProcessor
    from detection.postprocess import PostProcessor
    from PIL import Image
    import torch
    import cv2

    model_path = args.model or str(ROOT / "model_best")
    print(f"[smoke] carregando modelo: {model_path}")
    loader = ModelLoader()
    loader.load(model_path, device=args.device)
    print(f"[smoke] task={loader.task} device={loader.device}")

    if loader.task == TASK_INSTANCE_SEGMENTATION:
        pp = SegmentationPostProcessor(
            processor=loader.processor,
            confidence_threshold=args.confidence,
            max_detections=5,
            target_classes=["Embalagem"],
            min_mask_pixels=64,
        )
    else:
        print("[smoke] AVISO: modelo não é de segmentação; usando pós-processador clássico.")
        pp = PostProcessor(
            confidence_threshold=args.confidence,
            target_classes=["Embalagem"],
        )

    cap = _open_camera(args.camera, args.width, args.height)
    ok_frames = 0
    detections_total = 0
    last_frame_annotated: Optional[np.ndarray] = None

    try:
        for i in range(args.frames):
            ret, frame = cap.read()
            if not ret:
                print(f"[smoke] frame {i}: falha na captura")
                continue

            t0 = time.perf_counter()
            rgb = frame[:, :, ::-1]
            pil = Image.fromarray(rgb)
            inputs = loader.processor(images=pil, return_tensors="pt")
            inputs = {k: v.to(loader.device) for k, v in inputs.items()}
            with torch.no_grad():
                outputs = loader.model(**inputs)
            if loader.device != "cpu":
                for k in list(outputs.keys()):
                    v = outputs.get(k)
                    if isinstance(v, torch.Tensor):
                        outputs[k] = v.detach().to("cpu")

            target_sizes = torch.tensor([[frame.shape[0], frame.shape[1]]])
            result = pp.process(
                outputs=outputs,
                target_sizes=target_sizes,
                id2label=loader.model.config.id2label,
                frame_id=i,
                inference_time_ms=(time.perf_counter() - t0) * 1000,
            )
            dt_ms = (time.perf_counter() - t0) * 1000
            print(
                f"[smoke] frame {i}: {result.count} det(s) | "
                f"{dt_ms:.1f} ms"
            )
            detections_total += result.count

            if result.has_detections:
                ok_frames += 1
                best = result.best_by_priority()
                assert 0.0 <= (best.angle_deg or 0.0) < 180.0
                assert (best.area_px or 0.0) > 0
                cx, cy = best.centroid
                assert 0 <= cx < frame.shape[1]
                assert 0 <= cy < frame.shape[0]
                print(
                    f"        -> best: class={best.class_name} conf={best.confidence:.2f} "
                    f"xy=({cx:.1f}, {cy:.1f}) ang={best.angle_deg:.1f}° area={best.area_px:.0f}"
                )
                last_frame_annotated = _draw_overlay(frame, best)

        if args.save and last_frame_annotated is not None:
            cv2.imwrite(args.save, last_frame_annotated)
            print(f"[smoke] frame anotado salvo em {args.save}")
    finally:
        cap.release()

    print(
        f"[smoke] frames com detecção: {ok_frames}/{args.frames} | "
        f"detecções totais: {detections_total}"
    )
    if ok_frames == 0:
        print("[smoke] FALHA: nenhuma detecção em nenhum frame (câmera ocluída? sem embalagem no FOV?)")
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test do pipeline de segmentação")
    parser.add_argument("--frames", type=int, default=5)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--confidence", type=float, default=0.5)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--model", default=None, help="Caminho local ou ID HF; default: ./model_best")
    parser.add_argument("--save", default=None, help="Arquivo para salvar frame anotado")
    args = parser.parse_args()
    try:
        return run(args)
    except Exception as e:
        print(f"[smoke] ERRO: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
