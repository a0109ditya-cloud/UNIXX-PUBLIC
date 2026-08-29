import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import sounddevice as sd
import numpy as np
import soundfile as sf
from ai import analyze_waveform

SR=16000
WINDOW=4.0
print("Devices:")
print(sd.query_devices())
# Use default input
try:
    sd.check_input_settings(samplerate=SR, channels=1)
    print(f"Input check OK at {SR}Hz")
except Exception as e:
    print(f"Input check failed: {e}")
    print("Trying 44100Hz fallback...")
    SR=44100

print(f"\nRecording 4s - speak NOW (will save to debug.wav and analyze)...")
audio = sd.rec(int(WINDOW*SR), samplerate=SR, channels=1, dtype='float32')
sd.wait()
audio = audio[:,0]
rms=float(np.sqrt(np.mean(audio**2)))
amax=float(np.max(np.abs(audio)))
print(f"rms={rms:.5f} amax={amax:.5f} samples={len(audio)}")
# Save for manual check
out = ROOT/"tests"/"fixtures"/"debug_realtime.wav"
sf.write(str(out), audio, SR)
print(f"Saved {out}")
# Always analyze, even if quiet
from ai import analyze_waveform
r=analyze_waveform(audio, SR)
import json
print(json.dumps(r, indent=2))
print(f"\nIf rms <0.001, mic is silent/muted - check Windows mic volume. amax should be >0.05 when speaking.")
