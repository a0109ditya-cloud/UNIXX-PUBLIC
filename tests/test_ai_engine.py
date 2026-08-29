"""
VIGIL AI Engine Tests — 6+ cases. Do NOT invent results. Real AASIST inference.
Run with:  python -m pytest tests/test_ai_engine.py -v
       or  python tests/test_ai_engine.py
"""
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

# Ensure Vigil root on path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai.engine import analyze_audio, analyze_waveform

# ---------------------------------------------------------------------------
# Fixture helpers — generate synthetic audio for tests
# ---------------------------------------------------------------------------
FIXTURE_DIR = ROOT / "tests" / "fixtures"
FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

SR = 16000

def _sine(freq=440, duration=4.0, sr=SR, amplitude=0.5):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)

def _square(freq=440, duration=4.0, sr=SR, amplitude=0.5):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return (amplitude * np.sign(np.sin(2 * np.pi * freq * t))).astype(np.float32)

def ensure_fixtures():
    # AUDIT NOTE: All fixtures are SYNTHETIC NON-SPEECH (sine/square/noise). They are OOD for AASIST
    # which was trained on human speech (ASVspoof2019 LA). They validate pipeline robustness,
    # NOT model accuracy on genuine human speech. For genuine-speech validation, use a real
    # human recording (e.g., tests/fixtures/debug_realtime.wav or ASVspoof bonafide flac).
    # This sine fixture is a SYNTHETIC TONE PROXY, mislabeled as genuine in earlier versions.
    p = FIXTURE_DIR / "genuine_440hz_4s.wav"
    if not p.exists():
        sf.write(str(p), _sine(440, 4.0, SR), SR)
    # Keep legacy filename for backward compatibility, but tests now clearly mark it synthetic
    # noisy (sine + white noise) 4s
    p = FIXTURE_DIR / "noisy_440hz_4s.wav"
    if not p.exists():
        w = _sine(440, 4.0, SR)
        noise = np.random.randn(w.size).astype(np.float32) * 0.2
        sf.write(str(p), (w + noise).astype(np.float32), SR)
    # short 0.5s
    p = FIXTURE_DIR / "short_0.5s.wav"
    if not p.exists():
        sf.write(str(p), _sine(440, 0.5, SR), SR)
    # long 8s
    p = FIXTURE_DIR / "long_8s.wav"
    if not p.exists():
        sf.write(str(p), _sine(440, 8.0, SR), SR)
    # stereo 4s
    p = FIXTURE_DIR / "stereo_4s.wav"
    if not p.exists():
        w = _sine(440, 4.0, SR)
        stereo = np.stack([w, w * 0.8], axis=1)
        sf.write(str(p), stereo, SR)
    # 8kHz variant (tests resampling)
    p = FIXTURE_DIR / "genuine_8khz_4s.wav"
    if not p.exists():
        sf.write(str(p), _sine(440, 4.0, 8000), 8000)
    # spoof proxy: square wave (synthetic, not real TTS — labelled clearly)
    p = FIXTURE_DIR / "spoof_proxy_square_4s.wav"
    if not p.exists():
        sf.write(str(p), _square(440, 4.0, SR), SR)
    # invalid: text file with wav extension
    p = FIXTURE_DIR / "invalid_corrupt.wav"
    if not p.exists():
        p.write_bytes(b"This is not a wav file, it is corrupt")
    # invalid: empty file
    p = FIXTURE_DIR / "empty.wav"
    if not p.exists():
        p.write_bytes(b"")
    # unsupported extension dummy
    p = FIXTURE_DIR / "unsupported.txt"
    if not p.exists():
        p.write_text("not audio")
    print(f"Fixtures ensured in {FIXTURE_DIR}")

ensure_fixtures()

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def assert_success(result, msg=""):
    assert result["status"] == "success", f"Expected success, got {result} {msg}"
    assert result["prediction"] in ("bonafide", "spoof"), f"Bad prediction {result}"
    assert 0.0 <= result["model_score"] <= 1.0, f"model_score out of range {result}"
    assert 0 <= result["risk_score"] <= 100
    assert result["risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert result["model"] == "AASIST"
    assert result["error"] is None

def assert_error(result):
    assert result["status"] == "error", f"Expected error, got {result}"
    assert result["prediction"] == "error"
    assert result["error"] is not None

def test_synthetic_tone_proxy():
    """Synthetic 440Hz sine 4s — NON-SPEECH proxy, OOD for AASIST. Validates pipeline, NOT genuine-speech accuracy."""
    result = analyze_audio(str(FIXTURE_DIR / "genuine_440hz_4s.wav"))
    print("synthetic_tone_proxy (misleadingly named genuine_440hz_4s.wav):", result)
    assert_success(result, "synthetic_tone_proxy")
    # Document OOD expectation: model may return spoof/CRITICAL for non-speech; this is expected

def test_spoof_proxy_audio():
    """Synthetic square-wave as spoof proxy (clearly labelled fixture, not real spoof)."""
    result = analyze_audio(str(FIXTURE_DIR / "spoof_proxy_square_4s.wav"))
    print("spoof_proxy:", result)
    # We do NOT assert which class, because synthetic square wave is not a real spoof sample.
    # We only assert the pipeline runs and returns a valid structured result.
    assert_success(result, "spoof_proxy")
    # Log semantics for manual review
    print(f"  spoof_proxy bonafide_score={result['model_score']:.4f} risk={result['risk_level']}")

def test_noisy_audio():
    result = analyze_audio(str(FIXTURE_DIR / "noisy_440hz_4s.wav"))
    print("noisy:", result)
    assert_success(result, "noisy")

def test_short_audio():
    """0.5s clip → tiled to 4s by preprocessor, must succeed."""
    result = analyze_audio(str(FIXTURE_DIR / "short_0.5s.wav"))
    print("short:", result)
    assert_success(result, "short")

def test_long_audio_truncation():
    """8s clip → truncated to first 4s."""
    result = analyze_audio(str(FIXTURE_DIR / "long_8s.wav"))
    print("long:", result)
    assert_success(result, "long")

def test_stereo_audio():
    result = analyze_audio(str(FIXTURE_DIR / "stereo_4s.wav"))
    print("stereo:", result)
    assert_success(result, "stereo")

def test_resampling_8k():
    """8kHz SYNTHETIC tone must be resampled to 16kHz and succeed — same OOD caveat as above."""
    result = analyze_audio(str(FIXTURE_DIR / "genuine_8khz_4s.wav"))
    print("8k:", result)
    assert_success(result, "8k")

def test_invalid_corrupt_audio():
    result = analyze_audio(str(FIXTURE_DIR / "invalid_corrupt.wav"))
    print("corrupt:", result)
    assert_error(result)
    assert result["error_code"] in ("DECODE_FAILED", "CORRUPT_AUDIO", "EMPTY_AUDIO", "DECODE_FAILED")

def test_empty_file():
    result = analyze_audio(str(FIXTURE_DIR / "empty.wav"))
    print("empty:", result)
    assert_error(result)

def test_unsupported_extension():
    result = analyze_audio(str(FIXTURE_DIR / "unsupported.txt"))
    print("unsupported:", result)
    assert_error(result)
    assert result["error_code"] == "UNSUPPORTED_FORMAT"

def test_missing_file():
    result = analyze_audio(str(FIXTURE_DIR / "does_not_exist_12345.wav"))
    print("missing:", result)
    assert_error(result)
    assert result["error_code"] == "FILE_NOT_FOUND"

def test_invalid_input_none():
    result = analyze_audio(None)  # type: ignore
    print("none:", result)
    assert_error(result)

def test_waveform_interface():
    """Streaming-friendly analyze_waveform."""
    wav = _sine(440, 4.0, SR)
    result = analyze_waveform(wav, SR)
    print("waveform_api:", result)
    assert_success(result, "waveform_api")

def test_risk_engine_thresholds():
    """Risk mapping sanity: bonafide_score 1.0 -> LOW, 0.0 -> CRITICAL."""
    from risk_engine.engine import get_risk_engine
    engine = get_risk_engine()
    assert engine.evaluate(bonafide_score=1.0)["risk_level"] == "LOW"
    assert engine.evaluate(bonafide_score=0.9)["risk_level"] == "LOW"
    assert engine.evaluate(bonafide_score=0.5)["risk_level"] == "MEDIUM"
    assert engine.evaluate(bonafide_score=0.2)["risk_level"] == "HIGH"
    assert engine.evaluate(bonafide_score=0.0)["risk_level"] == "CRITICAL"
    print("risk thresholds ok")


def test_risk_engine_no_usable_signals():
    """Fail-safe: no usable/active signals (total_weight==0) -> UNKNOWN, REQUIRE_VERIFICATION, no auto-allow."""
    from risk_engine.engine import get_risk_engine
    from risk_engine.signals import SignalResult
    engine = get_risk_engine()
    signals = [
        SignalResult(name="aasist", score=0.9, weight=0.0, raw_value=0.1),
        SignalResult(name="prosody_anomaly", score=0.8, weight=0.0, raw_value=0.2),
    ]
    result = engine.evaluate(signals=signals)
    print("no_usable_signals:", result)
    assert result["risk_level"] == "UNKNOWN", f"expected UNKNOWN got {result['risk_level']}"
    assert result["risk_score"] == 0
    assert "REQUIRE_VERIFICATION" in result["recommended_action"]
    # Must not be LOW/allow (fail-open)
    assert result["risk_level"] != "LOW"
    assert "allow - normal" not in result["recommended_action"].lower()
    print("fail-safe UNKNOWN verified")


def test_realtime_queue_bounded():
    """Queue robustness: bounded queue (maxsize 8) drops stale chunks, never grows unbounded, no crash."""
    from ai.realtime_stream import VigilStream
    import queue
    # Verify VigilStream uses bounded queue in run_microphone (check source)
    import pathlib
    src = pathlib.Path(ROOT / "ai" / "realtime_stream.py").read_text()
    assert "queue.Queue(maxsize=" in src, "queue should be bounded"
    assert "put_nowait" in src and "Full" in src, "should handle Full with drop"
    # Functional: push many chunks quickly, ensure no crash and buffer stays bounded
    stream = VigilStream()
    import numpy as np
    chunk = np.random.randn(2048).astype(np.float32) * 0.01
    for _ in range(20):
        stream.push_chunk(chunk, sr=16000)
    # Buffer should be < window (not unbounded)
    assert stream.buffered_seconds < 5.0, f"buffer grew unbounded: {stream.buffered_seconds}"
    print(f"queue bounded test PASS buffered {stream.buffered_seconds:.2f}s")


def test_genuine_human_speech_if_available():
    """Genuine human speech validation — ONLY runs if a real human recording exists.
    Uses tests/fixtures/debug_realtime.wav if it contains speech (rms >0.01), else SKIPs.
    This is the ONLY test that validates genuine-speech behavior; synthetic tones are OOD."""
    p = FIXTURE_DIR / "debug_realtime.wav"
    if not p.exists():
        print("SKIP genuine_human_speech: no debug_realtime.wav — record real speech to validate")
        return
    import soundfile as sf
    data, sr = sf.read(str(p))
    rms = float((data**2).mean()**0.5) if data.size else 0
    if rms < 0.01:
        print(f"SKIP genuine_human_speech: {p} is silence (rms={rms:.5f}), not genuine speech")
        return
    result = analyze_audio(str(p))
    print("genuine_human_speech:", result)
    assert_success(result, "genuine_human_speech")
    print(f"  genuine human speech bonafide_score={result['model_score']:.4f} -> expect LOW/MEDIUM for real bonafide")

if __name__ == "__main__":
    # Manual run without pytest — executes all tests sequentially
    tests = [
        test_synthetic_tone_proxy,  # renamed from test_genuine_audio to avoid misleading name
        test_spoof_proxy_audio,
        test_noisy_audio,
        test_short_audio,
        test_long_audio_truncation,
        test_stereo_audio,
        test_resampling_8k,
        test_invalid_corrupt_audio,
        test_empty_file,
        test_unsupported_extension,
        test_missing_file,
        test_invalid_input_none,
        test_waveform_interface,
        test_risk_engine_thresholds,
        test_risk_engine_no_usable_signals,
        test_realtime_queue_bounded,
        test_genuine_human_speech_if_available,
    ]
    fails = 0
    for t in tests:
        try:
            print(f"\n=== {t.__name__} ===")
            t()
            print("PASS")
        except AssertionError as e:
            fails += 1
            print(f"FAIL: {e}")
        except Exception as e:
            fails += 1
            print(f"ERROR: {type(e).__name__}: {e}")
            import traceback; traceback.print_exc()
    print(f"\n{'='*40}")
    print(f"Tests run: {len(tests)}, failures: {fails}")
    if fails:
        sys.exit(1)
    print("All VIGIL AI tests passed.")
