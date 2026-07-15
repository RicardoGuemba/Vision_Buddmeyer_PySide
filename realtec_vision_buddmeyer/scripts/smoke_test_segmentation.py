#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smoke test end-to-end do pipeline de instance segmentation.

Captura N frames de uma câmera USB OU de um arquivo de vídeo, executa
inferência com o modelo Mask2Former (`model_best`) em MPS/CPU, e valida:
  - O modelo carregou com task == instance_segmentation.
  - Para cada frame com embalagem no FOV, há pelo menos 1 detecção.
  - A melhor detecção possui centróide (x, y), ângulo [0, 180) e área > 0.

Uso (câmera USB - hardware obrigatório):
    python -m scripts.smoke_test_segmentation --source usb --frames 10 --camera 0
    python -m scripts.smoke_test_segmentation --source usb --frames 10 --camera 0 --save debug.png

Uso (arquivo de vídeo - bom para CI/testes funcionais sem hardware):
    python -m scripts.smoke_test_segmentation --source video --video videos/Colchas.mp4 --frames 20

Saída: relatório textual em stdout; código de saída 0 se tudo OK, 2 se
não houver detecções em nenhum frame, 1 em caso de exceção fatal.

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


class _AdapterCaptureProxy:
    """
    Wrapper que adapta a interface do `USBCameraAdapter` para o contrato
    `(ret, frame)` usado pelo loop principal do smoke test. Permite validar
    end-to-end o warmup ativo + cópia defensiva no exato code path usado
    pela produção (StreamManager → USBCameraAdapter → FrameInfo).
    """

    def __init__(self, adapter):
        self._adapter = adapter

    def read(self):
        info = self._adapter.read()
        if info is None or info.frame is None:
            return False, None
        return True, info.frame

    def release(self):
        self._adapter.close()


def _open_camera_via_adapter(index: int, width: int, height: int):
    """Abre a câmera USB pelo `USBCameraAdapter` (com warmup ativo de produção)."""
    from streaming.source_adapters import USBCameraAdapter

    adapter = USBCameraAdapter(camera_index=index, width=width, height=height)
    if not adapter.open():
        raise RuntimeError(f"USBCameraAdapter falhou ao abrir camera index={index}")
    return _AdapterCaptureProxy(adapter)


def _frame_stats(frame: np.ndarray) -> str:
    """Resumo estatístico do frame para detectar imagens pretas/saturadas/canais quebrados."""
    if frame is None:
        return "frame=None"
    h, w = frame.shape[:2]
    ch = frame.shape[2] if frame.ndim == 3 else 1
    mean = float(frame.mean())
    std = float(frame.std())
    mn = int(frame.min())
    mx = int(frame.max())
    # Heurística: detecta frame "preto" (mean<5, std<5) e "branco saturado" (mean>250)
    flag = ""
    if mean < 5 and std < 5:
        flag = " [SUSPEITO: frame quase preto/sem dados]"
    elif mean > 250:
        flag = " [SUSPEITO: frame saturado]"
    elif std < 1:
        flag = " [SUSPEITO: frame uniforme/sem conteúdo]"
    return (
        f"shape={h}x{w}x{ch} dtype={frame.dtype} "
        f"mean={mean:.1f} std={std:.1f} min={mn} max={mx}{flag}"
    )


def _topk_query_scores(outputs, k: int = 5):
    """Retorna os k maiores scores de classe real entre as queries do Mask2Former."""
    import torch

    class_logits = getattr(outputs, "class_queries_logits", None)
    if class_logits is None:
        return []
    with torch.no_grad():
        probs = class_logits.softmax(dim=-1)
        # ignora última coluna ("no object")
        real = probs[..., :-1]
        # Pega o melhor score real por query (max sobre classes reais)
        per_query, _ = real.max(dim=-1)
        # Top-k entre queries do batch 0
        top = torch.topk(per_query[0], k=min(k, per_query.shape[-1]))
        return [float(v) for v in top.values.tolist()]


def _open_video(path: str):
    """Abre um arquivo de vídeo. Levanta RuntimeError em caso de falha."""
    import cv2

    candidates = [Path(path)]
    p = Path(path)
    if not p.is_absolute():
        # Tenta resolver relativo ao root do repositório (um nível acima do pacote)
        candidates.append(ROOT.parent / path)
        candidates.append(ROOT / path)

    for candidate in candidates:
        if candidate.exists():
            cap = cv2.VideoCapture(str(candidate))
            if cap.isOpened():
                print(f"[smoke] vídeo aberto: {candidate}")
                return cap
            cap.release()

    tried = "\n  - ".join(str(c) for c in candidates)
    raise RuntimeError(
        f"Não foi possível abrir o arquivo de vídeo '{path}'. Tentados:\n  - {tried}"
    )


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

    if args.source == "video":
        if not args.video:
            raise RuntimeError("Para --source video é necessário --video <caminho>.")
        cap = _open_video(args.video)
    elif args.use_adapter:
        print("[smoke] usando USBCameraAdapter de produção (warmup ativo + cópia defensiva)")
        cap = _open_camera_via_adapter(args.camera, args.width, args.height)
    else:
        cap = _open_camera(args.camera, args.width, args.height)

    ok_frames = 0
    detections_total = 0
    max_query_seen = 0.0
    last_frame_annotated: Optional[np.ndarray] = None

    try:
        for i in range(args.frames):
            ret, frame = cap.read()
            if not ret:
                # Em vídeos, é comum chegar ao fim antes do total de frames
                print(f"[smoke] frame {i}: falha na captura (fim do vídeo?)")
                break

            print(f"[smoke] frame {i} stats: {_frame_stats(frame)}")

            if args.dump_frames:
                dump_dir = Path(args.dump_frames)
                dump_dir.mkdir(parents=True, exist_ok=True)
                dump_path = dump_dir / f"frame_{i:04d}_raw.png"
                cv2.imwrite(str(dump_path), frame)
                print(f"        -> frame bruto salvo em {dump_path}")

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

            top_scores = _topk_query_scores(outputs, k=5)

            target_sizes = torch.tensor([[frame.shape[0], frame.shape[1]]])
            result = pp.process(
                outputs=outputs,
                target_sizes=target_sizes,
                id2label=loader.model.config.id2label,
                frame_id=i,
                inference_time_ms=(time.perf_counter() - t0) * 1000,
            )
            dt_ms = (time.perf_counter() - t0) * 1000
            mqs = result.max_query_score
            mqs_str = f"{mqs:.3f}" if mqs is not None else "n/a"
            top_str = ", ".join(f"{s:.3f}" for s in top_scores) if top_scores else "n/a"
            if mqs is not None and mqs > max_query_seen:
                max_query_seen = float(mqs)

            print(
                f"[smoke] frame {i}: {result.count} det(s) | "
                f"{dt_ms:.1f} ms | max_query_score={mqs_str} | "
                f"top5_query_scores=[{top_str}] | "
                f"raw_segments={result.raw_segment_count} | "
                f"rejected_by_class={result.rejected_by_class}"
            )
            detections_total += result.count

            if result.has_detections:
                ok_frames += 1
                best = result.best_for_plc(threshold=args.confidence)
                if best is None:
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
        f"detecções totais: {detections_total} | "
        f"max_query_score visto: {max_query_seen:.3f}"
    )
    if ok_frames == 0:
        if max_query_seen > 0 and max_query_seen < args.confidence:
            print(
                "[smoke] FALHA: nenhuma detecção. O modelo emitiu queries mas "
                f"todas abaixo do threshold ({max_query_seen:.3f} < "
                f"{args.confidence:.3f}). Reduza --confidence e tente de novo."
            )
        else:
            print(
                "[smoke] FALHA: nenhuma detecção em nenhum frame "
                "(câmera ocluída? sem embalagem no FOV? id2label desalinhado?)"
            )
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test do pipeline de segmentação")
    parser.add_argument(
        "--source",
        choices=["usb", "video"],
        default="usb",
        help="Fonte de frames: usb (câmera) ou video (arquivo).",
    )
    parser.add_argument("--video", default=None, help="Caminho do arquivo de vídeo (com --source video)")
    parser.add_argument("--frames", type=int, default=5)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--confidence", type=float, default=0.5)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--model", default=None, help="Caminho local ou ID HF; default: ./model_best")
    parser.add_argument("--save", default=None, help="Arquivo para salvar frame anotado")
    parser.add_argument(
        "--dump-frames",
        default=None,
        help="Diretório para salvar cada frame bruto (PNG) capturado. Útil para diagnosticar "
             "se a câmera está fornecendo imagem válida (frame preto, etc.).",
    )
    parser.add_argument(
        "--use-adapter",
        action="store_true",
        help="Abre a câmera via USBCameraAdapter de produção (com warmup ativo e cópia defensiva), "
             "em vez do open ad-hoc. Use para validar end-to-end o code path real do app.",
    )
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
