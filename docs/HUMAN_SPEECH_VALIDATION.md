# HUMAN SPEECH VALIDATION — VIGIL v0.1

**Date:** 2026-08-29  
**Host:** Windows 11, Python 3.11.9, torch 2.13.0+cpu, torchaudio 2.11.0+cpu  
**Model:** AASIST (ASVspoof2019 LA, `ai/aasist/models/weights/AASIST.pth`, 297,866 params)  
**Sample:** `C:\Users\ASUS\Downloads\WhatsApp Ptt 2026-08-29 at 07.05.42.ogg` — real human voice message via WhatsApp (10.01s, 16kHz, mono, rms 0.095, Opus-compressed OGG), copied to `tests/fixtures/human_speech_10s.ogg` and `human_speech_4s.wav` (first 4.04s, 64600 samples, for AASIST input)

## Actual VIGIL Output (No Fabrication)

### OGG (original, 10s, truncated to first 4.04s internally)
```json
{
  "prediction": "spoof",
  "model_score": 2.0129213226027787e-05,
  "spoof_score": 0.9999798536300659,
  "bonafide_logit": -5.20157527923584,
  "spoof_logit": 5.6117424964904785,
  "logits": [5.6117424964904785, -5.20157527923584],
  "risk_score": 100,
  "risk_level": "CRITICAL",
  "recommended_action": "block sensitive action - require strong verification (OTP + trusted-device / manual review)",
  "model": "AASIST",
  "status": "success",
  "processing_time_ms": 1598
}
```

### WAV slice (first 4s, 16kHz wav)
```json
{
  "prediction": "spoof",
  "model_score": 2.1161262338864617e-05,
  "spoof_score": 0.99997878074646,
  "bonafide_logit": -5.1786932945251465,
  "spoof_logit": 5.58462381362915,
  "logits": [5.58462381362915, -5.1786932945251465],
  "risk_score": 100,
  "risk_level": "CRITICAL",
  "status": "success",
  "processing_time_ms": 1160
}
```

## Interpretation — Clearly Labeled

- **This is ONE genuine human speech sample.** It was **predicted as `spoof` with `CRITICAL` risk** (`bonafide_score ~2e-05`).
- **This does NOT mean the speaker is spoofing.** It demonstrates a **model limitation**: AASIST trained on clean ASVspoof2019 LA FLAC (studio, 16kHz, no Opus compression). WhatsApp OGG is **Opus-compressed, narrowband, lossy** — out-of-distribution (OOD) for the model. Compression artifacts can resemble spoofing cues to the model.
- **Do NOT use one sample to claim accuracy.** No EER, no calibrated probability. `model_score` is uncalibrated softmax ranking score only.
- **Synthetic fixtures** (`genuine_440hz_4s.wav` sine tones) are **not human speech** and were previously shown to also score `CRITICAL/spoof` as OOD non-speech.

## What This Validates

- Pipeline handles real-world OGG (16kHz, 10s, resampled/truncated) end-to-end: validation → preprocessing (resample already 16k, tiling/truncate) → AASIST logits → softmax → risk 100 CRITICAL → structured result with `status: success`.
- No crash, no hardcoded path, CPU-only, import from clean root OK.

## What It Does NOT Validate

- No proof of model accuracy on clean speech (would need multiple ASVspoof bonafide FLACs or clean mic recordings).
- Opus-compressed speech may need domain adaptation or a different threshold; for VIGIL v0.1, such `CRITICAL` on compressed genuine speech would trigger secondary verification, not auto-block without user consent (per security audit).

## How to Reproduce

```powershell
python -c "import sys; sys.path.insert(0, r'C:\Users\ASUS\Vigil'); from ai import analyze_audio; import json; print(json.dumps(analyze_audio(r'C:\Users\ASUS\Downloads\WhatsApp Ptt 2026-08-29 at 07.05.42.ogg'), indent=2))"
python -c "import sys; sys.path.insert(0, r'C:\Users\ASUS\Vigil'); from ai import analyze_audio; print(analyze_audio(r'C:\Users\ASUS\Vigil\tests\fixtures\human_speech_4s.wav'))"
```
