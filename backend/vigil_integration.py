"""
VIGIL Backend Integration Example - copy/adapt into your FastAPI/Flask service.

This is NOT a full server, just the stable contract the backend team should use.
"""
import sys
from pathlib import Path

# Ensure Vigil root is on path if backend is run standalone
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai import analyze_audio  # stable contract

def handle_upload(file_path: str) -> dict:
    """
    Example handler for an uploaded call recording.
    Returns a dict the frontend can render.

    IMPORTANT: ai output != identity proof. See docs/AI_MODULE.md.
    """
    result = analyze_audio(file_path)

    # Structured logging for SIEM/monitoring
    # log.info("vigil_ai", extra=result)

    if result["status"] == "error":
        return {
            "allowed": False,
            "reason": result["error"],
            "error_code": result["error_code"],
            "risk_level": "UNKNOWN",
            "next_step": "Request valid audio (wav/flac 16kHz mono, 1-8s)",
        }

    # Risk-based decision - adapt thresholds to product needs
    if result["risk_level"] == "LOW":
        action = "allow"
        next_step = "Proceed - normal monitoring"
    elif result["risk_level"] == "MEDIUM":
        action = "allow_with_monitoring"
        next_step = "Proceed - increased logging, flag for review"
    elif result["risk_level"] == "HIGH":
        action = "require_verification"
        next_step = "Secondary verification required: OTP / passkey / trusted-device"
    else:  # CRITICAL
        action = "block_sensitive"
        next_step = "Block sensitive action - require strong verification (OTP + trusted-device / manual review)"

    return {
        "allowed": action in ("allow", "allow_with_monitoring"),
        "prediction": result["prediction"],          # bonafide/spoof
        "model_score": result["model_score"],        # uncalibrated, don't show as % to user
        "risk_score": result["risk_score"],
        "risk_level": result["risk_level"],
        "recommended_action": result["recommended_action"],
        "next_step": next_step,
        "processing_time_ms": result["processing_time_ms"],
    }

if __name__ == "__main__":
    import json
    demo_file = ROOT / "tests" / "fixtures" / "genuine_440hz_4s.wav"
    print(json.dumps(handle_upload(str(demo_file)), indent=2))
