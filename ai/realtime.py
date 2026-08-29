"""
VIGIL Realtime Mic Demo - 4s windows -> analyze_waveform -> risk.
Requires: pip install sounddevice
Run: python C:/Users/ASUS/Vigil/ai/realtime.py
Ctrl+C to stop.
"""
import sys
from pathlib import Path

# Ensure Vigil root on path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import sounddevice as sd
except ImportError:
    print("Missing sounddevice. Install with: pip install sounddevice")
    print("Also needs PortAudio (comes with sounddevice wheel on Windows).")
    sys.exit(1)

import numpy as np
from ai import analyze_waveform

SR = 16000
WINDOW_SEC = 4.0  # AASIST expects 64600 samples ~4.04s
CHANNELS = 1

def _pick_mic():
    # Prefer Realtek mic array (actual hardware) over virtual EShare mapper
    try:
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            name = d['name'].lower()
            if 'realtek' in name and 'microphone array' in name and d['max_input_channels'] > 0:
                return i
        # fallback to default input
        return sd.default.device[0]
    except Exception:
        return None

def realtime_loop():
    mic = _pick_mic()
    print(f"VIGIL Realtime - SR={SR}Hz, window={WINDOW_SEC}s, mic device={mic}, Ctrl+C to stop")
    print(sd.query_devices(mic))
    print("Speak normally. Each 4s chunk will be analyzed.\n")
    try:
        while True:
            print("Listening 4s ... speak now!", flush=True)
            audio = sd.rec(int(WINDOW_SEC * SR), samplerate=SR, channels=CHANNELS, dtype='float32', device=mic)
            sd.wait()
            audio = audio[:, 0]  # mono
            rms = float(np.sqrt(np.mean(audio**2)))
            amax = float(np.max(np.abs(audio)))
            print(f"  rms={rms:.4f} amax={amax:.4f}")
            if rms < 0.001:
                print(f"  Silence detected (rms={rms:.4f}) -> not analyzed, check mic volume. Retrying...")
                continue
            result = analyze_waveform(audio, SR)
            print(f"  -> {result['prediction']:8s} bonafide_score={result['model_score']:.4f} "
                  f"risk={result['risk_score']:3d} {result['risk_level']:8s} "
                  f"| {result['recommended_action']} "
                  f"({result['processing_time_ms']}ms)")
    except KeyboardInterrupt:
        print("\nStopped.")

if __name__ == "__main__":
    realtime_loop()
