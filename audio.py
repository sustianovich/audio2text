"""Level normalization and quality checks for decoded 16 kHz mono audio."""

import numpy as np

SAMPLE_RATE = 16000
TARGET_RMS_DB = -20.0  # Speech level that VAD and speaker embeddings handle best.
MAX_GAIN_DB = 24.0  # Never amplify a near-silent file into pure noise.
PEAK_LIMIT = 0.98
ACTIVE_DB = -50.0  # 50 ms frames below this level are treated as silence.
QUIET_DB = -38.0  # Speech RMS below this is warned about.
CLIP_LEVEL = 0.999
CLIP_RATIO = 0.001


def _db(value: float) -> float:
    return 20 * np.log10(max(float(value), 1e-9))


def speech_level_db(audio: np.ndarray) -> float | None:
    """RMS (dBFS) of the active frames only, so long pauses do not lower it."""
    frame = SAMPLE_RATE // 20
    usable = len(audio) // frame * frame
    if not usable:
        return None
    frames = audio[:usable].reshape(-1, frame)
    rms = np.sqrt(np.mean(np.square(frames, dtype=np.float64), axis=1))
    active = rms[rms > 10 ** (ACTIVE_DB / 20)]
    if not len(active):
        return None
    return _db(np.sqrt(np.mean(np.square(active))))


def analyze(audio: np.ndarray) -> list[str]:
    """Human-readable problems that make a transcript less reliable."""
    warnings = []
    level = speech_level_db(audio)
    if level is None:
        return ["Audio casi silencioso / Audio is almost silent."]
    if level < QUIET_DB:
        warnings.append(
            f"Volumen muy bajo ({level:.0f} dBFS); puede haber errores. / "
            f"Very low volume ({level:.0f} dBFS); expect more errors."
        )
    clipped = float(np.mean(np.abs(audio) >= CLIP_LEVEL))
    if clipped > CLIP_RATIO:
        warnings.append(
            f"Audio saturado ({clipped:.1%} de las muestras); puede haber distorsión. / "
            f"Clipped audio ({clipped:.1%} of samples); expect distortion."
        )
    return warnings


def normalize(audio: np.ndarray) -> np.ndarray:
    """Remove DC offset and move speech towards the target level without clipping."""
    audio = np.asarray(audio, dtype=np.float32)
    if not len(audio):
        return audio
    audio = audio - float(np.mean(audio))
    level = speech_level_db(audio)
    if level is None:
        return audio
    gain_db = min(TARGET_RMS_DB - level, MAX_GAIN_DB)
    gain = 10 ** (gain_db / 20)
    peak = float(np.max(np.abs(audio)))
    if peak * gain > PEAK_LIMIT:
        gain = PEAK_LIMIT / peak
    return (audio * gain).astype(np.float32)
