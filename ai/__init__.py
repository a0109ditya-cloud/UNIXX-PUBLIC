"""
VIGIL AI package — public integration contract.

Backend team: import analyze_audio from ai.

Example:
    from ai import analyze_audio
    result = analyze_audio("path/to/audio.wav")
    print(result["prediction"], result["risk_level"], result["recommended_action"])
"""
from .engine import analyze_audio, analyze_waveform
from .detector import AASISTDetector, get_detector
from .preprocessing import preprocess_audio, preprocess_waveform, AudioValidationError
from .config import MODEL_NAME, MODEL_VERSION

__all__ = [
    "analyze_audio",
    "analyze_waveform",
    "AASISTDetector",
    "get_detector",
    "preprocess_audio",
    "preprocess_waveform",
    "AudioValidationError",
    "MODEL_NAME",
    "MODEL_VERSION",
]
