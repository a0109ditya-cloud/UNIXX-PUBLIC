"""
VIGIL Risk Engine — weighted aggregation → risk_score → risk_level → action.

Design:
    model signals (dict of SignalResult)
    → weighted risk calculation
    → risk_score 0..100 (int)
    → LOW / MEDIUM / HIGH / CRITICAL
    → recommended security action

Security principle: AI model output != identity proof.
A voice can be genuine while the caller is still an attacker.

Score semantics: bonafide_score is a softmax output from AASIST logits,
NOT a calibrated probability. Higher means more bonafide-like for ranking
only; do not treat 0.9 as 90% genuine. risk = 1 - bonafide_score.

Extensible: add new signals by registering weight in config SIGNAL_WEIGHTS
and passing SignalResult to evaluate(). No rewrite needed.
"""
from __future__ import annotations

from typing import Dict, List

from .signals import SignalResult, aasist_signal


# Import thresholds from ai/config to keep single source of truth, fallback if not available
try:
    from ai.config import RISK_THRESHOLDS, RISK_ACTIONS, SIGNAL_WEIGHTS
except ImportError:
    RISK_THRESHOLDS = {"LOW": 30, "MEDIUM": 60, "HIGH": 85, "CRITICAL": 100}
    RISK_ACTIONS = {
        "LOW": "allow - normal monitoring",
        "MEDIUM": "allow - increased monitoring, flag for review",
        "HIGH": "secondary verification required (OTP / passkey / trusted-device)",
        "CRITICAL": "block sensitive action - require strong verification (OTP + trusted-device / manual review)",
    }
    SIGNAL_WEIGHTS = {"aasist": 1.0}


def _risk_level_from_score(risk_score: int) -> str:
    if risk_score <= RISK_THRESHOLDS["LOW"]:
        return "LOW"
    if risk_score <= RISK_THRESHOLDS["MEDIUM"]:
        return "MEDIUM"
    if risk_score <= RISK_THRESHOLDS["HIGH"]:
        return "HIGH"
    return "CRITICAL"


class RiskEngine:
    """
    Stateless engine — evaluate() is pure.
    Holds no per-call state; safe for concurrent use.
    """

    def __init__(
        self,
        thresholds: Dict[str, int] | None = None,
        actions: Dict[str, str] | None = None,
        weights: Dict[str, float] | None = None,
    ):
        self.thresholds = thresholds or RISK_THRESHOLDS
        self.actions = actions or RISK_ACTIONS
        self.weights = weights or SIGNAL_WEIGHTS

    def evaluate(
        self,
        bonafide_score: float | None = None,
        signals: List[SignalResult] | None = None,
    ) -> Dict:
        """
        Evaluate risk from signals.

        Args:
            bonafide_score: convenience for v0.1 — if provided, builds AASIST signal internally.
            signals: explicit list of SignalResult (overrides bonafide_score if provided).

        Returns:
            {
                "risk_score": int 0..100,
                "risk_level": "LOW"|"MEDIUM"|"HIGH"|"CRITICAL"|"UNKNOWN",
                "recommended_action": str,
                "signals": {name: {score, weight, weighted}},
                "explanation": str
            }
        Deterministic fail-safe: if no usable/active signals (total_weight == 0),
        returns UNKNOWN with REQUIRE_VERIFICATION — never auto-allow.
        """
        if signals is None:
            if bonafide_score is None:
                raise ValueError("Either bonafide_score or signals must be provided")
            signals = [aasist_signal(bonafide_score, weight=self.weights.get("aasist", 1.0))]

        # Weighted average: sum(weighted) / sum(weights)
        total_weight = sum(s.weight for s in signals)
        if total_weight == 0:
            # Fail-safe: no usable signals — do NOT invent risk 0 -> LOW/ALLOW
            # Deterministic UNKNOWN, require verification for any sensitive action
            signals_dict = {
                s.name: {
                    "score": round(s.score, 4),
                    "weight": s.weight,
                    "weighted": round(s.weighted(), 4),
                    "raw_value": s.raw_value,
                    "details": s.details,
                }
                for s in signals
            }
            return {
                "risk_score": 0,
                "risk_level": "UNKNOWN",
                "recommended_action": "REQUIRE_VERIFICATION - no usable signals, require strong verification before sensitive action",
                "signals": signals_dict,
                "explanation": "No usable/active signals (total_weight==0) -> UNKNOWN, REQUIRE_VERIFICATION (fail-safe, no auto-allow)",
            }

        risk_01 = sum(s.weighted() for s in signals) / total_weight

        # Clamp 0..1
        risk_01 = max(0.0, min(1.0, risk_01))
        risk_score = int(round(risk_01 * 100))
        risk_level = _risk_level_from_score(risk_score)
        recommended_action = self.actions[risk_level]

        signals_dict = {
            s.name: {
                "score": round(s.score, 4),
                "weight": s.weight,
                "weighted": round(s.weighted(), 4),
                "raw_value": s.raw_value,
                "details": s.details,
            }
            for s in signals
        }

        explanation = (
            f"Risk {risk_score}/100 ({risk_level}): "
            f"weighted risk {risk_01:.3f} from {len(signals)} signal(s). "
            f"Action: {recommended_action}. "
            f"Note: AI anti-spoofing signal != identity proof."
        )

        return {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "recommended_action": recommended_action,
            "signals": signals_dict,
            "explanation": explanation,
        }


# Singleton accessor
_engine_singleton: RiskEngine | None = None

def get_risk_engine() -> RiskEngine:
    global _engine_singleton
    if _engine_singleton is None:
        _engine_singleton = RiskEngine()
    return _engine_singleton
