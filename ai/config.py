"""
VIGIL AI Config — central configuration for AASIST inference and risk engine.
Keep configuration separate from implementation. No hardcoded machine paths.
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths — relative to this file, configurable via env if needed
# ---------------------------------------------------------------------------
AI_DIR = Path(__file__).parent
AASIST_DIR = AI_DIR / "aasist"
AASIST_CONFIG_PATH = AASIST_DIR / "config" / "AASIST.conf"
AASIST_WEIGHTS_PATH = AASIST_DIR / "models" / "weights" / "AASIST.pth"

# Fallback weights (AASIST-L lighter variant) — not used by default
AASIST_L_WEIGHTS_PATH = AASIST_DIR / "models" / "weights" / "AASIST-L.pth"

# ---------------------------------------------------------------------------
# Audio / Model input
# ---------------------------------------------------------------------------
TARGET_SAMPLE_RATE = 16000          # Hz — AASIST trained at 16kHz
TARGET_NUM_SAMPLES = 64600          # ~4.0375s at 16kHz — fixed length input
TARGET_DURATION_SEC = TARGET_NUM_SAMPLES / TARGET_SAMPLE_RATE

# Supported audio extensions (lowercase)
SUPPORTED_EXTENSIONS = {".wav", ".flac", ".mp3", ".m4a", ".ogg", ".aiff", ".aif"}

# Max file size guard (bytes) — 50 MB prevents OOM from huge files
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024

# ---------------------------------------------------------------------------
# Device — CPU only for hackathon prototype (Windows 11, no CUDA)
# ---------------------------------------------------------------------------
DEVICE = "cpu"

# ---------------------------------------------------------------------------
# Model metadata
# ---------------------------------------------------------------------------
MODEL_NAME = "AASIST"
MODEL_VERSION = "1.0.0"  # VIGIL wrapper version
MODEL_PAPER = "Jung et al., AASIST — Audio Anti-Spoofing using Integrated Spectro-Temporal Graph Attention Networks (ICASSP 2022)"
MODEL_TRACK = "LA"  # Logical Access — ASVspoof2019 LA trained
MODEL_SAMPLE_RATE = 16000

# ---------------------------------------------------------------------------
# Risk engine thresholds
# ---------------------------------------------------------------------------
# risk_score = int((1 - bonafide_score) * 100)  where bonafide_score ∈ [0,1] (softmax prob of class 1)
RISK_THRESHOLDS = {
    "LOW": 30,       # 0-30  -> LOW
    "MEDIUM": 60,    # 30-60 -> MEDIUM
    "HIGH": 85,      # 60-85 -> HIGH
    "CRITICAL": 100, # 85-100-> CRITICAL
}

# Signal weights for v0.1 — only AASIST active, others reserved 0.0
SIGNAL_WEIGHTS = {
    "aasist": 1.0,
    "speaker_consistency": 0.0,   # future
    "prosody_anomaly": 0.0,       # future
    "conversation_risk": 0.0,     # future
    "call_metadata": 0.0,         # future
    "behavioral": 0.0,            # future
}

# Action mapping
RISK_ACTIONS = {
    "LOW": "allow - normal monitoring",
    "MEDIUM": "allow - increased monitoring, flag for review",
    "HIGH": "secondary verification required (OTP / passkey / trusted-device)",
    "CRITICAL": "block sensitive action - require strong verification (OTP + trusted-device / manual review)",
}
