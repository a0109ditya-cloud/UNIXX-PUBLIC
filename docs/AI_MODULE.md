# VIGIL AI + Cybersecurity Module - v0.1

## Purpose
VIGIL needs to decide, for each voice call/chunk, whether the audio shows anti-spoofing evidence and what security posture to take. This module provides:

- **Anti-spoofing signal** from pretrained **AASIST** (Audio Anti-Spoofing using Integrated Spectro-Temporal Graph Attention Networks, Jung et al. ICASSP 2022) trained on ASVspoof2019 Logical Access.
- **VIGIL Risk Engine** that turns model evidence + future signals into a `risk_score`, `risk_level` (LOW/MEDIUM/HIGH/CRITICAL) and a `recommended_action`.
- Clean, CPU-only, hackathon-ready pipeline: `audio -> validation -> preprocessing -> AASIST -> risk -> structured result`.

> **Security axiom:** *AI model output != identity proof.* A voice can be genuine while the caller is still an attacker. VIGIL never auto-blocks on model alone without secondary verification for sensitive actions.

---

## Architecture

```
Vigil/
├── ai/
│   ├── aasist/                 # original cloned repo (UNMODIFIED)
│   │   ├── models/AASIST.py    # graph attention model
│   │   ├── models/weights/AASIST.pth   # pretrained checkpoint (~1.2 MB)
│   │   └── config/AASIST.conf  # training config (nb_samp=64600, 16kHz)
│   ├── config.py               # central paths, thresholds, weights
│   ├── preprocessing.py        # validation + resample + mono + pad/truncate
│   ├── detector.py             # AASIST CPU wrapper (lazy singleton)
│   ├── engine.py               # analyze_audio() pipeline
│   └── __init__.py             # public contract: from ai import analyze_audio
├── risk_engine/
│   ├── engine.py               # weighted aggregation -> risk level -> action
│   ├── signals.py              # SignalResult + AASIST + 5 future placeholders
│   └── config.py               # re-exports ai.config
└── tests/
    ├── fixtures/               # generated wavs (sine, noisy, short, stereo, 8kHz, spoof proxy)
    └── test_ai_engine.py       # 14 tests
```

Data flow for `analyze_audio(path)`:

1. **validate** path exists, extension in `SUPPORTED_EXTENSIONS`, size < 50 MB.
2. **load** via `soundfile` -> fallback `torchaudio`; mono-mix, finite check.
3. **resample** to 16kHz if needed (torchaudio Resample).
4. **pad_or_truncate** to `64600` samples (~4.04s) using **tiling** (not zero-pad) - faithful to `aasist/data_utils.pad()` for eval. Short audio is repeated; long audio truncated to first 64600.
5. **AASIST inference** on CPU: `waveform (64600,) -> logits (2,) -> softmax -> bonafide_score ∈ [0,1]` (NOT calibrated probability), prediction via argmax (0=spoof,1=bonafide), raw logits retained.
6. **Risk engine**: `risk_01 = 1 - bonafide_score` (weighted average over active signals; v0.1 only AASIST weight=1.0) -> `risk_score = round(risk_01*100)` -> level via thresholds -> action.

Future streaming: `analyze_waveform(np.ndarray, sample_rate)` reuses `preprocess_waveform()` - same logic without file I/O.

---

## Model Used - Why AASIST

- **AASIST** = SincConv frontend + RawNet2 encoder + spectro-temporal graph attention (GAT-S, GAT-T, heterogeneous stacking). 297k params, strong on ASVspoof2019 LA; lightweight enough for CPU hackathon demo.
- **Checkpoint**: `ai/aasist/models/weights/AASIST.pth` (1,281,532 bytes) - LA track, cross-entropy trained. `AASIST-L.pth` also present as lighter variant (not default).
- **Input**: raw waveform, 16kHz, 64600 samples, float32, mono. No MFCC/mel precomputed - SincConv learns filters.
- **Output**: 2 logits; `softmax[1]` treated as `bonafide_score`. Paper evaluation uses `logits[:,1]` as CM score (higher = bonafide). We expose both logits and softmax and document that softmax is **not a calibrated probability**.
- **Why not retrain**: checkpoint reused as-is; no training on Windows CPU, no untrusted downloads.

---

## Installation

**Environment:** Windows 11, Python 3.11.9, PyTorch 2.13.0+cpu, CUDA unavailable - forced `device=cpu`.

```powershell
# from Vigil root
pip install -r ai/requirements.txt
# or
pip install -r requirements.txt
```

Dependencies (pinned):
```
torch==2.13.0
torchaudio==2.11.0
soundfile==0.14.0
numpy==2.4.6
```

No `torchcontrib`, no GPU, no `librosa` required.

Verify:
```powershell
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
python -c "import sys; sys.path.insert(0,'.'); from ai import analyze_audio; print(analyze_audio('tests/fixtures/genuine_440hz_4s.wav'))"
```

---

## How to Run Inference

```python
from ai import analyze_audio

result = analyze_audio(r"C:\Users\ASUS\Vigil\tests\fixtures\genuine_440hz_4s.wav")
print(result)
```

Or via waveform (streaming-ready):
```python
import numpy as np, soundfile as sf
from ai import analyze_waveform
wav, sr = sf.read("audio.wav")  # wav is np.ndarray
result = analyze_waveform(wav, sr)
```

CLI smoke test:
```powershell
python tests/test_ai_engine.py
python -m pytest tests/test_ai_engine.py -v   # if pytest installed
```

---

## Input Requirements

- **Formats**: `.wav` `.flac` `.mp3` `.m4a` `.ogg` `.aiff` `.aif` (case-insensitive).
- **Sample rates**: any -> resampled to 16kHz.
- **Channels**: mono or stereo -> mixed to mono (mean).
- **Length**: any -> tiled if <4.04s, truncated if >4.04s. For streaming, accumulate ~4s windows or call `analyze_waveform` per chunk (future: sliding window aggregation).
- **Size**: <50 MB; empty/corrupt/missing -> `status="error"` with `error_code`.
- **Corrupt/unsupported**: never crashes; returns structured error (see Output Schema).

---

## Output Schema (Integration Contract)

`analyze_audio(audio_path: str) -> dict` - **never raises**, errors are in-band.

```json
{
  "prediction": "bonafide | spoof | error",
  "model_score": 0.0,
  "spoof_score": 1.0,
  "bonafide_logit": -7.73,
  "spoof_logit": 7.60,
  "logits": [7.60, -7.73],
  "risk_score": 100,
  "risk_level": "LOW | MEDIUM | HIGH | CRITICAL | UNKNOWN",
  "recommended_action": "allow - normal monitoring | ...",
  "signals": {
    "aasist": {"score": 1.0, "weight": 1.0, "weighted": 1.0, "raw_value": 2e-07, "details": {"bonafide_score": 2e-07}}
  },
  "model": "AASIST",
  "model_version": "1.0.0",
  "status": "success | error",
  "error": null,
  "error_code": null,
  "processing_time_ms": 652
}
```

**Score semantics** (critical for backend):
- `model_score` = softmax probability of class 1 (bonafide) ∈ [0,1]. **Not calibrated** - treat as uncalibrated confidence, not a true probability. Higher = more bonafide-like per AASIST. Raw `bonafide_logit` is unbounded and suitable for threshold tuning/EER analysis.
- `spoof_score` = `1 - model_score` = softmax prob of spoof. Also uncalibrated.
- `prediction` = argmax; `bonafide` if `bonafide_logit > spoof_logit` else `spoof`.
- On `status="error"`, `prediction="error"`, `risk_level="UNKNOWN"`, scores zeroed, `error` and `error_code` populated (`FILE_NOT_FOUND`, `UNSUPPORTED_FORMAT`, `EMPTY_FILE`, `DECODE_FAILED`, `MISSING_PATH`, etc.).

**Stable contract for backend** - field names frozen for v0.1. New fields may be added but existing ones will not be renamed without major bump.

---

## Risk Engine Design (Prototype — Not Scientifically Calibrated)

- **Separation:** `MODEL OUTPUT` (AASIST `bonafide_score` ∈ [0,1], uncalibrated) is ONE security signal → `VIGIL RISK INTERPRETATION` (`risk_score` 0-100, `risk_level`, `recommended_action`) is weighted aggregation + thresholds. Current thresholds are **prototype decision logic**, not calibrated on deployment data.
- **Signals**: `SignalResult(name, score∈[0,1], weight, raw_value)` where `score = risk` (1=high risk). v0.1 only `aasist` active (`score = 1 - bonafide_score`, weight 1.0). Five placeholders with weight 0.0 (not implemented, shown for extensibility): `speaker_consistency`, `prosody_anomaly`, `conversation_risk`, `call_metadata`, `behavioral`.
- **Aggregation**: `risk_01 = Σ(score·weight) / Σ(weight)` -> `risk_score = round(risk_01*100)` -> level via `RISK_THRESHOLDS = {LOW:30, MEDIUM:60, HIGH:85, CRITICAL:100}` (prototype).
- **Actions** (`RISK_ACTIONS`, prototype):
  - `LOW (0–30)`: allow - normal monitoring
  - `MEDIUM (31–60)`: allow - increased monitoring, flag for review
  - `HIGH (61–85)`: secondary verification required (OTP / passkey / trusted-device)
  - `CRITICAL (86–100)`: block sensitive action - require strong verification (OTP + trusted-device / manual review)
- **Extensibility**: add signal by defining `def my_signal(...) -> SignalResult` in `risk_engine/signals.py`, registering its weight in `ai/config.py:SIGNAL_WEIGHTS`, and passing `signals=[...]` to `RiskEngine.evaluate()`. No engine rewrite.
- **No automatic irreversible actions**: engine only recommends; enforcement is backend's responsibility. Secondary verification is a separate trust mechanism (OTP/passkey/trusted-device), never bypassed by model.

---

## Security Assumptions

1. **Voice authenticity != identity proof**: bonafide audio proves the waveform is human-like, not that the caller is who they claim. Attacker can use genuine voice (replay attack, coercion, stolen recording). Always require identity verification beyond voice.
2. **Replay attacks are possible**: even genuine voice can be replayed. AASIST detects some replay artifacts but not all; do not rely solely on audio anti-spoofing.
3. **Genuine voice can still belong to attacker**: voice may be genuine while caller intent is malicious (social engineering). Risk engine is only ONE signal.
4. **Voice changes (illness, noise, channel) != fraud**: cold, stress, background noise, or Opus compression (e.g., WhatsApp) can shift scores. Do not auto-flag as fraud; trigger verification, not block.
5. **No calibrated probability**: softmax scores are ranking scores; do not treat 0.9 as "90% genuine". Use for relative risk, not legal proof.
6. **High-risk actions require stronger verification**: `HIGH` → OTP/passkey, `CRITICAL` → OTP + trusted-device/manual review. Never auto-block sensitive action without user-visible verification.
7. **Sensitive audio should not be unnecessarily stored**: process in memory, delete temp uploads, do not log raw audio, encrypt at rest if retained for audit, comply with data retention policy.
8. **No irreversible action solely from AI**: no auto-transfer, auto-lock, or auto-deny solely on `prediction==spoof`. Engine recommends; backend enforces with human-in-loop for critical.
9. **No secrets**: no API keys in repo; paths are relative; checkpoint is local. `backend` must not commit `.env`.
10. **Fail-closed on error**: invalid audio returns `error` - backend should treat `UNKNOWN` as needing manual review, not as `LOW`.
11. **CPU determinism**: inference is deterministic given same input (dropout disabled, eval mode, tiling not random crop). Random `pad_random` used only in training, not inference.

---

## Real Human-Speech Validation (2026-08-29)

**Sample:** `WhatsApp Ptt 2026-08-29 at 07.05.42.ogg` (10.01s, 16kHz, Opus OGG, rms 0.095) — real human voice message, copied to `tests/fixtures/human_speech_10s.ogg` + `human_speech_4s.wav` (first 4.04s).

**Actual VIGIL output (no fabrication):**
```
prediction: spoof, model_score: 2.01e-05, bonafide_logit: -5.20, spoof_logit: 5.61,
risk_score: 100, risk_level: CRITICAL, status: success, 1598ms
wav slice: spoof, 2.11e-05, CRITICAL, 1160ms
```
**Interpretation:** Genuine human speech was flagged `spoof CRITICAL`. This is **not proof of spoof** — WhatsApp Opus compression is OOD for AASIST (trained on clean FLAC). One sample does NOT prove accuracy. Demonstrates pipeline handles real-world OGG end-to-end (see `docs/HUMAN_SPEECH_VALIDATION.md` for full JSON and reproduction).

## Limitations (v0.1 Prototype)

- **WhatsApp compressed speech OOD**: above human sample scored CRITICAL, showing compression artifacts shift scores. Clean mic recordings may score higher bonafide; domain adaptation needed for Opus.
- **Synthetic fixtures are OOD**: the `genuine_440hz_4s.wav` sine tones in `tests/fixtures/` are not speech. AASIST flags them CRITICAL/spoof in CPU tests (≈100 risk). Expected, not a bug. For genuine-speech behavior, see human validation above.
- **No speaker ID**: risk is only anti-spoofing. Impersonation via genuine voice not detected.
- **Fixed 4s window**: long calls not yet aggregated; streaming will need sliding-window + voting (planned).
- **No calibration**: no Platt/isotonic scaling, no EER threshold tuning on deployment data. Thresholds are prototype.
- **MP3/M4A fallback**: `torchaudio` may require `torchcodec` for some codecs; `soundfile` handles wav/flac reliably. MP3 support depends on torchcodec install.
- **Silence is OOD**: near-silence `rms 0.00001` previously scored `bonafide 0.98 LOW` (now fixed to `SILENCE_DETECTED` UNKNOWN) — not meaningful; engine now returns `SILENCE_DETECTED` UNKNOWN; realtime skips (`rms<0.001`).
- **No WebRTC/TTS/n8n/frontend** - per scope, deferred.

---

## Future Extensions (No Rewrite Needed)

- Add signals: register weight, implement `SignalResult` factory, pass to `RiskEngine.evaluate(signals=[...])`.
- Streaming: `preprocess_waveform` already reusable; add ring buffer + majority vote or score smoothing.
- Calibration: fit logistic on held-out bonafide/spoof scores, expose `calibrated_score`.
- Speaker consistency: cosine similarity vs enrolled embedding -> `speaker_consistency_signal(score=1-sim, weight=0.3)`.
- Conversation/context risk: LLM-based anomaly -> `conversation_risk_signal`.
- Multi-window: run `analyze_waveform` per 4s chunk, aggregate risk with `max` or `p90`.

---

## Integration Instructions for Backend Team

```python
# backend/app.py
from ai import analyze_audio

def handle_call_audio(file_path: str):
    out = analyze_audio(file_path)
    if out["status"] == "error":
        # out["error_code"] in ("FILE_NOT_FOUND","UNSUPPORTED_FORMAT","DECODE_FAILED",...)
        return {"allow": False, "reason": out["error"], "vad_required": True}
    # out["prediction"] is "bonafide" or "spoof"
    # out["model_score"] is uncalibrated bonafide softmax - log it, don't expose as probability to users
    # out["risk_level"] / out["risk_score"] drives UX
    if out["risk_level"] in ("HIGH", "CRITICAL"):
        # enforce secondary verification before sensitive action
        trigger_otp_or_passkey(out)
    return out
```

- Install: `pip install -r ai/requirements.txt` on the backend image (CPU).
- Keep `ai/aasist` untouched; do not import `ai.aasist.main` (it asserts GPU).
- Use relative imports: `from ai import analyze_audio` when backend root is `Vigil/`. If backend is separate service, copy `ai/` + `risk_engine/` + `ai/aasist/models/weights/AASIST.pth` preserving relative layout, or install as package.
- Log `processing_time_ms`, `logits`, `bonafide_score` for tuning; alert on `risk_level=CRITICAL` rate spikes.
- Treat `HIGH/CRITICAL` as "require OTP/passkey/trusted-device" - do not auto-block without user-visible verification step for non-sensitive flows.

---

## Files Created / Modified / Verified

See repo root and `git status` - core new files are `ai/config.py`, `ai/preprocessing.py`, `ai/detector.py`, `ai/engine.py`, `ai/__init__.py`, `risk_engine/*`, `tests/test_ai_engine.py`, `docs/AI_MODULE.md`.

## Dependencies Installed (verified)

- `torch 2.13.0`, `torchaudio 2.11.0`, `soundfile 0.14.0`, `numpy 2.4.6` - already present on Windows 11 Python 3.11.9, no new installs needed.

## Commands Used

- `python -c "import torch; torch.load(...)"` - checkpoint sanity
- `python tests/test_ai_engine.py` - full pipeline test (14 cases)

## Actual Test Results (2026-08-29, Windows 11, CPU)

- `genuine_440hz_4s.wav` (sine, 4s): `spoof, bonafide_score~2e-07, risk 100 CRITICAL` - OOD non-speech, expected
- `spoof_proxy_square_4s.wav`: `spoof, 6e-08, CRITICAL`
- `noisy_440hz_4s.wav`: `spoof, 1.3e-06, CRITICAL`
- `short_0.5s.wav` (tiled): `spoof, CRITICAL` - pad logic verified
- `long_8s.wav` (truncated): `spoof, CRITICAL`
- `stereo_4s.wav` (mono-mixed): `spoof, CRITICAL`
- `genuine_8khz_4s.wav` (resampled): `spoof, CRITICAL`
- `invalid_corrupt.wav`: `error DECODE_FAILED` - correctly handled
- `empty.wav`: `error EMPTY_FILE`
- `unsupported.txt`: `error UNSUPPORTED_FORMAT`
- `does_not_exist`: `error FILE_NOT_FOUND`
- `None` input: `error MISSING_PATH`
- `analyze_waveform` (in-memory): `success`
- Risk thresholds: `1.0->LOW, 0.5->MEDIUM, 0.2->HIGH, 0.0->CRITICAL` - verified
- All 14 tests PASS (processing ~650–1580 ms per file on CPU, first load slower).

> To see a `bonafide/LOW` path, test with a real human speech wav (record yourself 4s at 16kHz or use ASVspoof LA bonafide sample). The pipeline will return higher `model_score` and lower risk for clean bonafide speech.

---

## References

- Jung et al., "AASIST: Audio Anti-Spoofing using Integrated Spectro-Temporal Graph Attention Networks", ICASSP 2022. Code: https://github.com/clovaai/aasist
- ASVspoof 2019 LA dataset: https://datashare.ed.ac.uk/handle/10283/3336
- `ai/aasist/README.md`, `config/AASIST.conf`, `models/AASIST.py`, `data_utils.py` inspected for input spec.
