"""
VIGIL AASIST Detector - CPU-safe wrapper around the original AASIST model.

- Does NOT modify ai/aasist source.
- Loads pretrained AASIST.pth on CPU.
- Exposes deterministic inference: waveform (64600,) -> logits/probs/prediction.
- Clearly distinguishes raw model output vs calibrated probability (we do NOT claim calibration).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict

import torch
import torch.nn.functional as F

from .config import AASIST_CONFIG_PATH, AASIST_WEIGHTS_PATH, DEVICE, MODEL_NAME, TARGET_NUM_SAMPLES

# Ensure aasist package is importable
_AASIST_PARENT = str(Path(__file__).parent / "aasist")
if _AASIST_PARENT not in sys.path:
    sys.path.insert(0, _AASIST_PARENT)


class AASISTDetector:
    """
    Lazy-loaded singleton wrapper. Keeps model on CPU.
    Input: torch.Tensor shape (64600,) float32  OR  (1, 64600)
    Output: dict with prediction, logits, scores.
    Score semantics:
        - logits[0] = spoof logit, logits[1] = bonafide logit (per AASIST training label: 0=spoof, 1=bonafide)
        - bonafide_score = softmax(logits)[1] in [0,1] - NOT a calibrated probability.
        - spoof_score = 1 - bonafide_score (or softmax[0])
        - raw bonafide logit also provided as model_logit (unbounded)
    """

    _instance: "AASISTDetector | None" = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        config_path: Path = AASIST_CONFIG_PATH,
        weights_path: Path = AASIST_WEIGHTS_PATH,
        device: str = DEVICE,
    ):
        if getattr(self, "_initialized", False):
            return
        self.config_path = Path(config_path)
        self.weights_path = Path(weights_path)
        self.device = torch.device(device)
        self.model = None
        self.model_config: Dict | None = None
        self._load_model()
        self._initialized = True

    def _load_model(self):
        if not self.config_path.exists():
            raise FileNotFoundError(f"AASIST config not found: {self.config_path}")
        if not self.weights_path.exists():
            raise FileNotFoundError(f"AASIST weights not found: {self.weights_path}")

        with open(self.config_path, "r") as f:
            cfg = json.load(f)

        self.model_config = cfg["model_config"]

        # Import here to avoid import at module load if weights missing
        from models.AASIST import Model  # type: ignore

        model = Model(self.model_config)
        state = torch.load(str(self.weights_path), map_location=self.device)
        # state is OrderedDict of params directly (not wrapped)
        model.load_state_dict(state)
        model.to(self.device)
        model.eval()
        self.model = model
        self.full_config = cfg

    @torch.no_grad()
    def infer(self, waveform: torch.Tensor) -> Dict:
        """
        Run AASIST inference.
        Args:
            waveform: Tensor shape (64600,) or (1, 64600), dtype float32.
        Returns:
            dict with:
                prediction: "bonafide" | "spoof"
                bonafide_score: float in [0,1] (softmax prob, NOT calibrated)
                spoof_score: float in [0,1]
                bonafide_logit: float (raw logit, unbounded)
                spoof_logit: float
                logits: [spoof_logit, bonafide_logit]
                model: str
        """
        if self.model is None:
            raise RuntimeError("Model not loaded")

        # Normalize input shape
        if waveform.dim() == 1:
            if waveform.shape[0] != TARGET_NUM_SAMPLES:
                raise ValueError(
                    f"Expected waveform length {TARGET_NUM_SAMPLES}, got {waveform.shape[0]}"
                )
            x = waveform.unsqueeze(0)  # (1, 64600)
        elif waveform.dim() == 2:
            if waveform.shape[1] != TARGET_NUM_SAMPLES:
                raise ValueError(
                    f"Expected waveform length {TARGET_NUM_SAMPLES}, got shape {waveform.shape}"
                )
            x = waveform
        else:
            raise ValueError(f"Expected 1D or 2D tensor, got shape {waveform.shape}")

        x = x.to(self.device).float()

        # AASIST forward returns (hidden, logits)
        _, logits = self.model(x, Freq_aug=False)  # logits shape (B,2)
        # logits[:,0]=spoof, logits[:,1]=bonafide
        probs = F.softmax(logits, dim=1)

        spoof_logit = logits[0, 0].item()
        bonafide_logit = logits[0, 1].item()
        spoof_score = probs[0, 0].item()
        bonafide_score = probs[0, 1].item()

        pred_idx = int(torch.argmax(logits, dim=1)[0].item())
        prediction = "bonafide" if pred_idx == 1 else "spoof"

        return {
            "prediction": prediction,
            "predicted_class": pred_idx,  # 0=spoof, 1=bonafide
            "bonafide_score": float(bonafide_score),
            "spoof_score": float(spoof_score),
            # Alias for integration contract: model_score = bonafide_score
            "model_score": float(bonafide_score),
            "bonafide_logit": float(bonafide_logit),
            "spoof_logit": float(spoof_logit),
            "logits": [float(spoof_logit), float(bonafide_logit)],
            "model": MODEL_NAME,
        }

    def infer_from_path(self, waveform_tensor: torch.Tensor) -> Dict:
        """Wrapper that matches old naming - same as infer."""
        return self.infer(waveform_tensor)


# Singleton accessor
_detector_singleton: AASISTDetector | None = None

def get_detector() -> AASISTDetector:
    global _detector_singleton
    if _detector_singleton is None:
        _detector_singleton = AASISTDetector()
    return _detector_singleton
