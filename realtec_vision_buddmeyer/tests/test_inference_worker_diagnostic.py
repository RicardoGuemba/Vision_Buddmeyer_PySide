# -*- coding: utf-8 -*-
"""
Testes de observabilidade do InferenceWorker.

Garantem que o pipeline de inferência:
  1. Acumula estatísticas mesmo quando não há detecções no frame.
  2. Emite log periódico de diagnóstico (não fica silencioso).
  3. Sinaliza com WARNING quando o `max_query_score` está abaixo do
     `confidence_threshold` por uma janela inteira (cenário típico do
     "sistema parou de detectar" por threshold alto demais).

Estes testes não criam QThreads reais — exercitam apenas a máquina
de estatísticas (`_update_diagnostic_stats` / `_emit_diagnostic_log`)
para serem rápidos e independentes da event loop do Qt.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _make_worker(threshold: float = 0.5, interval: int = 5):
    """Cria um InferenceWorker minimamente funcional para teste de stats."""
    # Importa dentro da função para evitar custo no module-level se Qt não inicializar.
    from detection.inference_engine import InferenceWorker

    fake_postprocessor = SimpleNamespace(confidence_threshold=threshold)
    worker = InferenceWorker(
        model=MagicMock(),
        processor=MagicMock(),
        postprocessor=fake_postprocessor,
        device="cpu",
        target_fps=10.0,
        diagnostic_log_interval=interval,
    )
    return worker


def _make_result(
    *,
    count: int = 0,
    inference_ms: float = 30.0,
    max_query_score=None,
    raw_segments: int = 0,
    rejected_by_class: int = 0,
):
    """Constrói um DetectionResult para alimentar o worker."""
    from detection.events import DetectionResult, Detection, BoundingBox

    detections = []
    for _ in range(count):
        detections.append(
            Detection(
                bbox=BoundingBox(x1=0, y1=0, x2=10, y2=10),
                confidence=0.99,
                class_id=0,
                class_name="Embalagem",
            )
        )
    return DetectionResult(
        detections=detections,
        inference_time_ms=inference_ms,
        frame_id=0,
        max_query_score=max_query_score,
        raw_segment_count=raw_segments,
        rejected_by_class=rejected_by_class,
    )


class TestInferenceWorkerDiagnostic:
    def test_stats_accumulate_without_detections(self):
        """Mesmo com 0 detecções, frames_processed deve subir e log deve sair."""
        worker = _make_worker(threshold=0.5, interval=3)

        with patch("detection.inference_engine.logger") as log_mock:
            for _ in range(3):
                worker._update_diagnostic_stats(
                    _make_result(count=0, max_query_score=0.2)
                )

            # Deve ter emitido pelo menos uma chamada de log_fn
            assert (log_mock.info.call_count + log_mock.warning.call_count) >= 1
            assert worker._frames_processed == 3

    def test_warning_when_max_query_score_below_threshold(self):
        """
        Cenário do bug do usuário: o modelo emite queries fortes mas todas
        abaixo do threshold. O worker deve emitir WARNING contendo
        'inference_diagnostic' para sinalizar o problema.
        """
        worker = _make_worker(threshold=0.71, interval=5)

        with patch("detection.inference_engine.logger") as log_mock:
            # 5 frames sem detecção, mas com max_query_score = 0.55
            # (abaixo do 0.71). O sistema "vê" mas filtra por threshold.
            for _ in range(5):
                worker._update_diagnostic_stats(
                    _make_result(count=0, max_query_score=0.55)
                )

            assert log_mock.warning.called, (
                "Worker deveria emitir WARNING quando max_query_score "
                "está abaixo do threshold"
            )
            # O log deve conter o evento 'inference_diagnostic' e a hint
            args, kwargs = log_mock.warning.call_args
            assert args[0] == "inference_diagnostic"
            assert kwargs.get("hint") is not None
            assert "threshold" in kwargs["hint"]

    def test_info_when_detections_are_happening(self):
        """Com detecções ocorrendo, o log de diagnóstico é INFO, não WARNING."""
        worker = _make_worker(threshold=0.5, interval=3)

        with patch("detection.inference_engine.logger") as log_mock:
            for _ in range(3):
                worker._update_diagnostic_stats(
                    _make_result(count=1, max_query_score=0.95)
                )

            assert log_mock.info.called
            assert not log_mock.warning.called

    def test_force_emit_on_stop_does_not_emit_when_no_frames(self):
        """Sem frames processados, não deve emitir log de diagnóstico."""
        worker = _make_worker()
        with patch("detection.inference_engine.logger") as log_mock:
            worker._emit_diagnostic_log(force=True)
            assert not log_mock.info.called
            assert not log_mock.warning.called

    def test_stats_window_resets_after_log(self):
        """Após emitir o log, a janela deve resetar para começar nova medição."""
        worker = _make_worker(threshold=0.5, interval=2)
        with patch("detection.inference_engine.logger"):
            for _ in range(2):
                worker._update_diagnostic_stats(
                    _make_result(count=1, max_query_score=0.9, inference_ms=30.0)
                )

        # Após o log, o "última janela" deve ter sido resetada
        assert worker._frames_with_detection == 0
        assert worker._sum_inference_ms == 0.0
        # Mas frames_processed (acumulador absoluto) continua avançando
        assert worker._frames_processed == 2

    def test_warning_when_frame_is_almost_black(self):
        """
        Cenário: câmera USB envia frames pretos (lente coberta / hardware
        com problema). O worker deve sinalizar com WARNING e gerar um hint
        sobre câmera/lente, não sobre threshold.
        """
        import numpy as np

        worker = _make_worker(threshold=0.5, interval=3)
        # Frame "preto": dtype uint8, shape válido, todos os pixels ~0
        black = np.zeros((480, 640, 3), dtype=np.uint8)

        with patch("detection.inference_engine.logger") as log_mock:
            for _ in range(3):
                worker._update_diagnostic_stats(
                    _make_result(count=0, max_query_score=0.001),
                    frame=black,
                )

            assert log_mock.warning.called
            args, kwargs = log_mock.warning.call_args
            assert args[0] == "inference_diagnostic"
            assert kwargs.get("hint") is not None
            # O hint deve mencionar problema de câmera, não threshold
            hint = kwargs["hint"]
            assert "preto" in hint.lower() or "lente" in hint.lower() or "câmera" in hint.lower() or "camera" in hint.lower()

    def test_warning_when_model_says_no_object_with_high_confidence(self):
        """
        Cenário: modelo recebe frames válidos mas está confiante de que
        NÃO há embalagem (max_query_score ≈ 0). Pode ser FOV vazio,
        modelo errado, ou produto fora de domínio. WARNING explícito.
        """
        import numpy as np

        worker = _make_worker(threshold=0.5, interval=3)
        # Frame válido (cinza) — não preto, não saturado
        gray = np.full((480, 640, 3), 127, dtype=np.uint8)
        # Variação realista para que std > 5
        gray[::2, :, :] = 100
        gray[1::2, :, :] = 150

        with patch("detection.inference_engine.logger") as log_mock:
            for _ in range(3):
                worker._update_diagnostic_stats(
                    _make_result(count=0, max_query_score=0.001),
                    frame=gray,
                )

            assert log_mock.warning.called
            args, kwargs = log_mock.warning.call_args
            assert args[0] == "inference_diagnostic"
            assert kwargs.get("hint") is not None
            # Hint deve apontar para FOV/modelo, não threshold ou câmera preta
            hint = kwargs["hint"].lower()
            assert "embalagem" in hint or "fov" in hint or "modelo" in hint

    def test_warning_when_frames_are_frozen(self):
        """
        Cenário: pipeline entrega o mesmo frame N vezes para a inferência
        (ex.: aliasing de buffer ou stream travado). O worker deve detectar
        o frame congelado via hash e emitir WARNING específico, mesmo que
        o conteúdo do frame seja válido (sem ser preto).
        """
        import numpy as np

        worker = _make_worker(threshold=0.5, interval=10)
        rng = np.random.default_rng(42)
        # Frame válido (com variação suficiente para não ativar suspicious_frame)
        same_frame = rng.integers(0, 256, size=(480, 640, 3), dtype=np.uint8)

        with patch("detection.inference_engine.logger") as log_mock:
            for _ in range(10):
                worker._update_diagnostic_stats(
                    _make_result(count=0, max_query_score=0.2),
                    frame=same_frame,
                )

            assert log_mock.warning.called
            args, kwargs = log_mock.warning.call_args
            assert args[0] == "inference_diagnostic"
            # Apenas 1 hash único nos 10 frames
            assert kwargs.get("unique_frame_hashes") == 1
            assert kwargs.get("hint") is not None
            hint = kwargs["hint"].lower()
            assert "congel" in hint or "aliasing" in hint or "mesmo frame" in hint

    def test_unique_hashes_increment_with_changing_frames(self):
        """
        Frames com conteúdo diferente devem gerar hashes diferentes (e o
        contador `unique_frame_hashes` no log deve refletir isso).
        """
        import numpy as np

        worker = _make_worker(threshold=0.5, interval=5)
        rng = np.random.default_rng(7)

        with patch("detection.inference_engine.logger") as log_mock:
            for _ in range(5):
                frame = rng.integers(0, 256, size=(480, 640, 3), dtype=np.uint8)
                worker._update_diagnostic_stats(
                    _make_result(count=1, max_query_score=0.95),
                    frame=frame,
                )

            assert log_mock.info.called
            args, kwargs = log_mock.info.call_args
            assert args[0] == "inference_diagnostic"
            # 5 frames diferentes → 5 hashes únicos
            assert kwargs.get("unique_frame_hashes") == 5

    def test_first_frame_is_dumped_to_disk(self, tmp_path):
        """
        Independente de qualquer WARNING, o PRIMEIRO frame que passa pelo
        worker deve ser salvo em disco para diagnóstico visual em campo.
        """
        import numpy as np
        from detection.inference_engine import InferenceWorker

        fake_postprocessor = SimpleNamespace(confidence_threshold=0.5)
        worker = InferenceWorker(
            model=MagicMock(),
            processor=MagicMock(),
            postprocessor=fake_postprocessor,
            device="cpu",
            target_fps=10.0,
            diagnostic_dump_dir=str(tmp_path),
        )

        rng = np.random.default_rng(1)
        frame = rng.integers(0, 256, size=(120, 160, 3), dtype=np.uint8)
        with patch("detection.inference_engine.logger"):
            worker._maybe_dump_first_frame(frame, frame_id=42)
            # Segunda chamada deve ser no-op (idempotente)
            worker._maybe_dump_first_frame(frame, frame_id=43)

        dumped = list(tmp_path.glob("first_inference_frame_*.png"))
        assert len(dumped) == 1, (
            f"Esperava exatamente 1 dump da primeira frame; achei {len(dumped)}"
        )

    def test_first_frame_dump_disabled_when_dir_is_none(self):
        """Sem dump_dir configurado, não deve tentar gravar nada (no-op)."""
        import numpy as np

        worker = _make_worker()  # sem diagnostic_dump_dir
        rng = np.random.default_rng(1)
        frame = rng.integers(0, 256, size=(60, 80, 3), dtype=np.uint8)

        # Não deve levantar exceção mesmo com cv2 não configurado para escrita
        with patch("detection.inference_engine.logger"):
            worker._maybe_dump_first_frame(frame, frame_id=0)
        assert worker._first_frame_dumped is False

    def test_compute_frame_hash_changes_with_content(self):
        """O hash deve mudar quando o conteúdo do frame muda."""
        import numpy as np
        from detection.inference_engine import InferenceWorker

        rng = np.random.default_rng(0)
        frame_a = rng.integers(0, 256, size=(64, 64, 3), dtype=np.uint8)
        frame_b = rng.integers(0, 256, size=(64, 64, 3), dtype=np.uint8)

        h_a1 = InferenceWorker._compute_frame_hash(frame_a)
        h_a2 = InferenceWorker._compute_frame_hash(frame_a.copy())
        h_b = InferenceWorker._compute_frame_hash(frame_b)

        assert h_a1 == h_a2, "Hash deve ser determinístico para o mesmo conteúdo"
        assert h_a1 != h_b, "Hash deve mudar quando o conteúdo muda"
