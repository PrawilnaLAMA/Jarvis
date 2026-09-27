"""Lokalne wykrywanie „Hey Jarvis” (openWakeWord) i detekcja mowy (Silero VAD).

Modele (kilka MB) pobierane są przy pierwszym uruchomieniu do data/models.
"""

import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

WAKE_MODEL = "hey_jarvis_v0.1"
_REQUIRED_FILES = (f"{WAKE_MODEL}.onnx", "melspectrogram.onnx", "embedding_model.onnx", "silero_vad.onnx")


def models_present(models_dir: Path) -> bool:
    return all((models_dir / name).exists() for name in _REQUIRED_FILES)


def ensure_models(models_dir: Path) -> None:
    if models_present(models_dir):
        return
    from openwakeword.utils import download_models

    log.info("Pobieram modele słowa wywołania do %s", models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    download_models(model_names=["hey_jarvis"], target_directory=str(models_dir))
    if not models_present(models_dir):
        raise RuntimeError("Nie udało się pobrać modeli słowa wywołania.")


class WakeWordDetector:
    def __init__(self, models_dir: Path):
        from openwakeword import Model

        self._model = Model(
            wakeword_models=[str(models_dir / f"{WAKE_MODEL}.onnx")],
            inference_framework="onnx",
            melspec_model_path=str(models_dir / "melspectrogram.onnx"),
            embedding_model_path=str(models_dir / "embedding_model.onnx"),
        )

    def score(self, frame: np.ndarray) -> float:
        """Prawdopodobieństwo (0..1), że właśnie padło „Hey Jarvis”."""
        return float(self._model.predict(frame).get(WAKE_MODEL, 0.0))

    def reset(self) -> None:
        self._model.reset()


class VoiceActivityDetector:
    def __init__(self, models_dir: Path):
        from openwakeword import VAD

        self._vad = VAD(model_path=str(models_dir / "silero_vad.onnx"))

    def probability(self, frame: np.ndarray) -> float:
        """Prawdopodobieństwo mowy w ramce 80 ms."""
        return float(self._vad.predict(frame, frame_size=640))
