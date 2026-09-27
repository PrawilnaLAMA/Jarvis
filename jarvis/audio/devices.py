"""Urządzenia audio (sounddevice/PortAudio)."""

import ctypes
import logging
import sys
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

_alsa_handler = None  # referencja, żeby callback nie został usunięty przez GC


def suppress_alsa_errors() -> None:
    """Na Linuksie ALSA/JACK zasypują konsolę komunikatami przy wyszukiwaniu urządzeń
    (dawniej filtrowane grepem w Makefile) – wyciszamy je u źródła."""
    global _alsa_handler
    if not sys.platform.startswith("linux") or _alsa_handler is not None:
        return
    try:
        asound = ctypes.cdll.LoadLibrary("libasound.so.2")
    except OSError:
        return
    handler_type = ctypes.CFUNCTYPE(
        None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
    )
    _alsa_handler = handler_type(lambda *args: None)
    asound.snd_lib_error_set_handler(_alsa_handler)


def _default_hostapi_devices(kind: str) -> list[tuple[int, dict[str, Any]]]:
    import sounddevice as sd

    hostapi = sd.default.hostapi
    channels_key = f"max_{kind}_channels"
    return [
        (i, d) for i, d in enumerate(sd.query_devices()) if d["hostapi"] == hostapi and d[channels_key] > 0
    ]


def list_devices() -> dict[str, list[dict[str, str]]]:
    """Urządzenia domyślnego API (MME na Windows, ALSA na Linuksie) – do wyboru w ustawieniach."""
    try:
        return {
            "inputs": [{"name": d["name"]} for _, d in _default_hostapi_devices("input")],
            "outputs": [{"name": d["name"]} for _, d in _default_hostapi_devices("output")],
        }
    except Exception:
        log.exception("Nie udało się pobrać listy urządzeń audio")
        return {"inputs": [], "outputs": []}


def resolve_device(name: str, kind: str) -> int | None:
    """Indeks urządzenia o podanej nazwie albo None (= domyślne)."""
    if not name:
        return None
    try:
        devices = _default_hostapi_devices(kind)
    except Exception:
        return None
    for index, d in devices:
        if d["name"] == name:
            return index
    for index, d in devices:
        if name.lower() in d["name"].lower():
            return index
    log.warning("Nie znaleziono urządzenia %s „%s” – używam domyślnego", kind, name)
    return None


def rms(samples: np.ndarray) -> float:
    """Średnia kwadratowa sygnału w skali 0..1 (dla int16 i float)."""
    if samples.size == 0:
        return 0.0
    x = samples.astype(np.float32)
    if samples.dtype == np.int16:
        x /= 32768.0
    return float(np.sqrt(np.mean(x * x)))


def ui_level(value: float, reference: float) -> float:
    """Poziom 0..1 do animacji: `reference` to typowa głośność mowy, skala zbliżona do percepcji."""
    return float(min(1.0, (value / reference) ** 0.6)) if value > 0 else 0.0


def resample(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Prosta zmiana częstotliwości (filtr uśredniający + interpolacja liniowa) – wystarcza dla mowy."""
    if src_rate == dst_rate or samples.size == 0:
        return samples
    x = samples.astype(np.float32)
    if src_rate > dst_rate:
        k = max(1, int(round(src_rate / dst_rate)))
        if k > 1:
            x = np.convolve(x, np.ones(k, dtype=np.float32) / k, mode="same")
    n_out = int(round(x.size * dst_rate / src_rate))
    out = np.interp(np.linspace(0, x.size - 1, n_out), np.arange(x.size), x)
    return out.astype(samples.dtype) if samples.dtype != np.int16 else np.clip(out, -32768, 32767).astype(np.int16)
