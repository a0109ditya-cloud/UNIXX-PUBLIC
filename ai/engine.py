"""
VIGIL AI Engine - end-to-end pipeline:
    Audio -> validation -> preprocessing -> AASIST inference -> risk engine -> structured result

This is the integration point the backend team calls.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Dict

from .config import MODEL_NAME, MODEL_VERSION
from .detector import get_detector
from .preprocessing import AudioValidationError, preprocess_audio

# Risk engine lives at top-level risk_engine/; import with fallback
try:
    from risk_engine.engine import get_risk_engine
except ImportError:
    # fallback if run as module
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from risk_engine.engine import get_risk_engine


def analyze_audio(audio_path: str) -> Dict:
    """
    Main VIGIL interface - single file in, structured result out.

    Args:
        audio_path: path to audio file (wav/flac/mp3/m4a/ogg)

    Returns:
        {
            "prediction": "bonafide" | "spoof" | "error",
            "model_score": float 0..1 (bonafide_score, softmax, NOT calibrated),
            "spoof_score": float 0..1,
            "bonafide_logit": float,
            "spoof_logit": float,
            "logits": [spoof_logit, bonafide_logit],
            "risk_score": int 0..100,
            "risk_level": "LOW"|"MEDIUM"|"HIGH"|"CRITICAL" | "UNKNOWN",
            "recommended_action": str,
            "model": "AASIST",
            "model_version": str,
            "status": "success" | "error",
            "error": str | None,
            "error_code": str | None,
            "processing_time_ms": int | None,
        }

    Never raises - errors are returned as status="error" dict.
    Thread-safe, CPU-only.
    """
    t0 = time.time()
    try:
        # 1. Validation + preprocessing
        waveform = preprocess_audio(audio_path)
        # Silence check: near-silence is OOD for AASIST and should not be scored as LOW/bonafide
        # Realtime already skips, but file API should return UNKNOWN with clear guidance
        if waveform.abs().max().item() < 0.001 or waveform.pow(2).mean().sqrt().item() < 0.001:
            elapsed_ms = int((time.time() - t0) * 1000)
            return {
                "prediction": "error",
                "model_score": 0.0,
                "spoof_score": 0.0,
                "bonafide_logit": 0.0,
                "spoof_logit": 0.0,
                "logits": [0.0, 0.0],
                "risk_score": 0,
                "risk_level": "UNKNOWN",
                "recommended_action": "reject - silence detected, request voiced speech (3-5s at normal volume)",
                "signals": {},
                "model": MODEL_NAME,
                "model_version": MODEL_VERSION,
                "status": "error",
                "error": "Silence detected (max amplitude <0.001, rms <0.001) - not valid speech for anti-spoofing",
                "error_code": "SILENCE_DETECTED",
                "processing_time_ms": elapsed_ms,
            }

        # 2. AASIST inference
        detector = get_detector()
        inf = detector.infer(waveform)

        # 3. Risk engine — direct, no channel compensation (truthful)
        # Do NOT adjust thresholds to make compressed genuine look bonafide; record actual model output.
        risk_engine = get_risk_engine()
        risk = risk_engine.evaluate(bonafide_score=inf["bonafide_score"])

        elapsed_ms = int((time.time() - t0) * 1000)

        return {
            "prediction": inf["prediction"],
            "model_score": inf["model_score"],
            "spoof_score": inf["spoof_score"],
            "bonafide_logit": inf["bonafide_logit"],
            "spoof_logit": inf["spoof_logit"],
            "logits": inf["logits"],
            "risk_score": risk["risk_score"],
            "risk_level": risk["risk_level"],
            "recommended_action": risk["recommended_action"],
            "signals": risk["signals"],
            "model": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "status": "success",
            "error": None,
            "error_code": None,
            "processing_time_ms": elapsed_ms,
        }

    except AudioValidationError as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        return {
            "prediction": "error",
            "model_score": 0.0,
            "spoof_score": 0.0,
            "bonafide_logit": 0.0,
            "spoof_logit": 0.0,
            "logits": [0.0, 0.0],
            "risk_score": 0,
            "risk_level": "UNKNOWN",
            "recommended_action": "reject - invalid audio input, request valid audio",
            "signals": {},
            "model": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "status": "error",
            "error": str(e),
            "error_code": getattr(e, "code", "INVALID_AUDIO"),
            "processing_time_ms": elapsed_ms,
        }
    except FileNotFoundError as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        return {
            "prediction": "error",
            "model_score": 0.0,
            "spoof_score": 0.0,
            "bonafide_logit": 0.0,
            "spoof_logit": 0.0,
            "logits": [0.0, 0.0],
            "risk_score": 0,
            "risk_level": "UNKNOWN",
            "recommended_action": "reject - model or file not found",
            "signals": {},
            "model": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "status": "error",
            "error": str(e),
            "error_code": "NOT_FOUND",
            "processing_time_ms": elapsed_ms,
        }
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        return {
            "prediction": "error",
            "model_score": 0.0,
            "spoof_score": 0.0,
            "bonafide_logit": 0.0,
            "spoof_logit": 0.0,
            "logits": [0.0, 0.0],
            "risk_score": 0,
            "risk_level": "UNKNOWN",
            "recommended_action": "reject - internal error, retry or escalate",
            "signals": {},
            "model": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "status": "error",
            "error": f"{type(e).__name__}: {e}",
            "error_code": "INTERNAL_ERROR",
            "processing_time_ms": elapsed_ms,
        }


def analyze_waveform(waveform, sample_rate: int) -> Dict:
    """
    Streaming-friendly variant - accepts in-memory waveform.
    waveform: np.ndarray
    sample_rate: int
    Returns same schema as analyze_audio (no file path).
    """
    t0 = time.time()
    try:
        from .preprocessing import preprocess_waveform

        tensor = preprocess_waveform(waveform, sample_rate)
        if tensor.abs().max().item() < 0.001 or tensor.pow(2).mean().sqrt().item() < 0.001:
            elapsed_ms = int((time.time() - t0) * 1000)
            return {
                "prediction": "error",
                "model_score": 0.0,
                "spoof_score": 0.0,
                "bonafide_logit": 0.0,
                "spoof_logit": 0.0,
                "logits": [0.0, 0.0],
                "risk_score": 0,
                "risk_level": "UNKNOWN",
                "recommended_action": "reject - silence detected, request voiced speech",
                "signals": {},
                "model": MODEL_NAME,
                "model_version": MODEL_VERSION,
                "status": "error",
                "error": "Silence detected (max <0.001) - not valid speech",
                "error_code": "SILENCE_DETECTED",
                "processing_time_ms": elapsed_ms,
            }
        detector = get_detector()
        inf = detector.infer(tensor)
        risk_engine = get_risk_engine()
        risk = risk_engine.evaluate(bonafide_score=inf["bonafide_score"])
        elapsed_ms = int((time.time() - t0) * 1000)
        return {
            "prediction": inf["prediction"],
            "model_score": inf["model_score"],
            "spoof_score": inf["spoof_score"],
            "bonafide_logit": inf["bonafide_logit"],
            "spoof_logit": inf["spoof_logit"],
            "logits": inf["logits"],
            "risk_score": risk["risk_score"],
            "risk_level": risk["risk_level"],
            "recommended_action": risk["recommended_action"],
            "signals": risk["signals"],
            "model": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "status": "success",
            "error": None,
            "error_code": None,
            "processing_time_ms": elapsed_ms,
        }
    except AudioValidationError as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        return {
            "prediction": "error",
            "model_score": 0.0,
            "spoof_score": 0.0,
            "bonafide_logit": 0.0,
            "spoof_logit": 0.0,
            "logits": [0.0, 0.0],
            "risk_score": 0,
            "risk_level": "UNKNOWN",
            "recommended_action": "reject - invalid audio input",
            "signals": {},
            "model": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "status": "error",
            "error": str(e),
            "error_code": getattr(e, "code", "INVALID_AUDIO"),
            "processing_time_ms": elapsed_ms,
        }
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        return {
            "prediction": "error",
            "model_score": 0.0,
            "spoof_score": 0.0,
            "bonafide_logit": 0.0,
            "spoof_logit": 0.0,
            "logits": [0.0, 0.0],
            "risk_score": 0,
            "risk_level": "UNKNOWN",
            "recommended_action": "reject - internal error",
            "signals": {},
            "model": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "status": "error",
            "error": f"{type(e).__name__}: {e}",
            "error_code": "INTERNAL_ERROR",
            "processing_time_ms": elapsed_ms,
        }
