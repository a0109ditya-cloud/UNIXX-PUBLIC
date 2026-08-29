# VIGIL — Voice Security Engine (AI + Cybersecurity Module v0.1)

**Course:** Smart India Hackathon (SIH) — Team VIGIL  
**Module Owner:** AI + Cybersecurity + Risk-Engine (Aditya integration)  
**Status:** GitHub-ready handoff, CPU-only, Windows 11 / Python 3.11.9

## Purpose
Detect AI-spoofed / replayed voice and produce a VIGIL risk decision for call security. Input is raw audio, output is structured JSON with `prediction`, `model_score` (uncalibrated), `risk_score`, `risk_level`, `recommended_action`.

> **Security axiom:** Voice authenticity != identity proof. A genuine voice can still belong to an attacker. No irreversible action solely from one AI prediction.

## Architecture
```
Vigil/
├── ai/
│   ├── aasist/                 # cloned, UNMODIFIED (models/AASIST.py, config/AASIST.conf, weights/AASIST.pth 1.2MB)
│   ├── config.py               # 16kHz/64600, thresholds, weights, CPU
│   ├── preprocessing.py        # validate, load (soundfile→torchaudio), mono, resample, tiling pad
│   ├── detector.py             # AASIST CPU wrapper (lazy singleton, softmax not calibrated)
│   ├── engine.py               # analyze_audio(path) / analyze_waveform(array,sr) pipeline
│   └── __init__.py             # public contract: from ai import analyze_audio
├── risk_engine/
│   ├── signals.py              # aasist_signal + 5 placeholders (weight 0)
│   ├── engine.py               # weighted avg → 0-100 → LOW/MEDIUM/HIGH/CRITICAL (prototype)
│   └── config.py
├── tests/
│   ├── fixtures/               # synthetic tones (OOD) + human_speech_10s.ogg / human_speech_4s.wav
│   └── test_ai_engine.py       # 15 tests (14 synthetic + 1 genuine conditional)
├── docs/
│   ├── AI_MODULE.md            # full spec
│   └── HUMAN_SPEECH_VALIDATION.md # real human OGG result (spoof CRITICAL, Opus OOD)
└── backend/vigil_integration.py # example FastAPI handler for Aditya
```

## Model
**AASIST** (Jung et al., ICASSP 2022) — SincConv + RawNet2 encoder + spectro-temporal GAT, 297,866 params, ASVspoof2019 LA trained. Checkpoint `ai/aasist/models/weights/AASIST.pth` (1,281,532 bytes). Input raw waveform `16kHz, 64600 samples (~4.04s)`, output logits `[spoof, bonafide]`, `softmax[1]=bonafide_score` (**not calibrated probability**). Paper uses `logits[:,1]` as CM score.

## Installation
Windows 11, Python 3.11.9, CPU-only.
```powershell
pip install -r ai/requirements.txt  # torch 2.13.0+cpu, torchaudio 2.11.0+cpu, soundfile 0.14.0, numpy 2.4.6
# For fresh install prefer matched: torch==2.3.1 torchaudio==2.3.1
```
Verify:
```powershell
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
python tests/test_ai_engine.py
```

## Audio Requirements
- Formats: `.wav .flac .mp3 .m4a .ogg .aiff` (ogg via soundfile Vorbis, mp3 may need torchcodec)
- Sample rates: any → 16kHz, Channels: stereo→mono, Length: tiled if <4.04s, truncated if >4.04s, Size <50MB

## Running Inference
```python
from ai import analyze_audio
r = analyze_audio(r"C:\Users\ASUS\Vigil\tests\fixtures\human_speech_4s.wav")
print(r["prediction"], r["risk_level"], r["recommended_action"])
# streaming: from ai import analyze_waveform; analyze_waveform(np_array, 16000)
```

**Example output (real human WhatsApp OGG, 10s truncated):**
```json
{"prediction":"spoof","model_score":2.01e-05,"risk_score":100,"risk_level":"CRITICAL","recommended_action":"block sensitive action - require strong verification (OTP + trusted-device / manual review)","model":"AASIST","status":"success","processing_time_ms":1598}
```

## Testing
```powershell
python tests/test_ai_engine.py  # 15 tests: 14 synthetic OOD + 1 genuine conditional
```
- Synthetic sine/noise → expected `CRITICAL/spoof` (OOD, not speech)
- Corrupt/empty/unsupported/missing/None → `error` with `error_code`
- Human speech `human_speech_4s.wav` → `SKIP` if silence, else actual result (see `docs/HUMAN_SPEECH_VALIDATION.md` — flagged `spoof CRITICAL` due to Opus compression, not proof of accuracy)

## Risk Engine (Prototype)
`score = 1 - bonafide_score` weighted avg `/sum(weights)` → `risk_score 0-100` → `LOW ≤30, MEDIUM ≤60, HIGH ≤85, CRITICAL >85` (prototype, not calibrated). Only `aasist` weight 1.0 now; future signals add via `SignalResult` with weight in `ai/config.py`.

## Security Assumptions
Voice authenticity != identity proof, replay possible, genuine voice can be attacker, illness/noise/compression ≠ fraud, high-risk → stronger verification, sensitive audio not stored unnecessarily, no irreversible action from one AI prediction alone.

## Known Limitations
- Opus-compressed (WhatsApp) human speech scored `CRITICAL` — domain OOD; clean mic may differ.
- No speaker ID, no calibration, fixed 4s window, silence scored `bonafide LOW` (realtime skips `rms<0.001`).
- See `docs/AI_MODULE.md#Limitations`.

## Backend Integration for Aditya
```python
from ai import analyze_audio
out = analyze_audio(file_path)
if out["status"]=="error": return {"allow":False, "error":out["error"]}
if out["risk_level"] in ("HIGH","CRITICAL"): trigger_otp_or_passkey(out)
# out["model_score"] is uncalibrated — log, don't show as % to user
```
Copy `ai/`, `risk_engine/`, `ai/aasist/models/weights/AASIST.pth` preserving relative layout. Do not import `ai/aasist/main.py` (requires tensorboard/GPU).

## Git
`git status` clean, no secrets, `.gitignore` covers `.venv/`, `__pycache__/`, `human_speech` already committed as validation sample (small). Do not delete `ai/aasist` checkpoint.

## Docs
- `docs/AI_MODULE.md` — full spec
- `docs/HUMAN_SPEECH_VALIDATION.md` — real human OGG result

## Human Action Required
- Provide clean 3-5s mic recording (16kHz wav) for bonafide LOW demo if needed; WhatsApp sample shows Opus OOD behavior.
