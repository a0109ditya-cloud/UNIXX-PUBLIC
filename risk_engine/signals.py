"""
VIGIL Signals — extensible signal definitions.

Each signal returns SignalResult(score, weight, name).
For v0.1 only AASIST is active. Future signals added without rewriting RiskEngine.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class SignalResult:
    """Normalized signal: score in [0,1] where 1 = highest risk."""
    name: str
    score: float          # 0..1 risk contribution (1 = spoof/high risk)
    weight: float         # 0..1 weight in final aggregation
    raw_value: float | None = None
    details: Dict | None = None

    def weighted(self) -> float:
        return self.score * self.weight


# ---------------------------------------------------------------------------
# Signal factories — each signal is a pure function
# ---------------------------------------------------------------------------

def aasist_signal(bonafide_score: float, weight: float = 1.0) -> SignalResult:
    """
    Convert AASIST bonafide_score (softmax prob of bonafide, 0..1) to risk.
    risk = 1 - bonafide_score  (high bonafide -> low risk)
    """
    # Clamp
    bonafide_score = max(0.0, min(1.0, float(bonafide_score)))
    risk = 1.0 - bonafide_score
    return SignalResult(
        name="aasist",
        score=risk,
        weight=weight,
        raw_value=bonafide_score,
        details={"bonafide_score": bonafide_score, "spoof_score": risk},
    )


# Placeholders for future signals — return 0 risk with 0 weight so they don't affect v0.1
def speaker_consistency_signal(score: float | None = None, weight: float = 0.0) -> SignalResult:
    return SignalResult(name="speaker_consistency", score=float(score or 0.0), weight=weight, details={"status": "not_implemented"})

def prosody_anomaly_signal(score: float | None = None, weight: float = 0.0) -> SignalResult:
    return SignalResult(name="prosody_anomaly", score=float(score or 0.0), weight=weight, details={"status": "not_implemented"})

def conversation_risk_signal(score: float | None = None, weight: float = 0.0) -> SignalResult:
    return SignalResult(name="conversation_risk", score=float(score or 0.0), weight=weight, details={"status": "not_implemented"})

def call_metadata_signal(score: float | None = None, weight: float = 0.0) -> SignalResult:
    return SignalResult(name="call_metadata", score=float(score or 0.0), weight=weight, details={"status": "not_implemented"})

def behavioral_signal(score: float | None = None, weight: float = 0.0) -> SignalResult:
    return SignalResult(name="behavioral", score=float(score or 0.0), weight=weight, details={"status": "not_implemented"})
