"""
VIGIL Realtime Microphone Layer — modular streaming on top of existing VIGIL pipeline.

Reuse: analyze_waveform() (which reuses detector + risk engine + preprocessing).
Does NOT duplicate AASIST logic, does NOT rewrite detector.

Buffer: TARGET_NUM_SAMPLES (64600 @16kHz = 4.0375s) with sliding/overlapping windows.
Default stride 2.0s (50% overlap) — configurable.

Modular for WebRTC: same VigilStream.push_chunk() can receive WebRTC call audio.
CPU-only, handles mic permission/errors gracefully.
"""
from __future__ import annotations

import time
import threading
import queue
from collections import deque
from typing import Callable, Dict, Optional
from pathlib import Path
import sys

import numpy as np

# Ensure Vigil root on path when run as script
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai.config import TARGET_SAMPLE_RATE, TARGET_NUM_SAMPLES, TARGET_DURATION_SEC
from ai.engine import analyze_waveform

# Optional sounddevice — graceful if missing
try:
    import sounddevice as sd  # type: ignore
    _SD_AVAILABLE = True
except ImportError:
    sd = None  # type: ignore
    _SD_AVAILABLE = False


class VigilStream:
    """
    Sliding-window buffer for VIGIL. Thread-safe.

    Usage:
        stream = VigilStream(window_sec=4.0375, stride_sec=2.0, on_result=print)
        stream.push_chunk(mic_chunk_np, sr=48000)  # mic or WebRTC
        # on_result called for each completed window via analyze_waveform

    For WebRTC: same push_chunk() — caller provides chunk and its sample_rate.
    """
    def __init__(
        self,
        window_samples: int = TARGET_NUM_SAMPLES,
        stride_samples: Optional[int] = None,
        sample_rate: int = TARGET_SAMPLE_RATE,
        on_result: Optional[Callable[[Dict], None]] = None,
        silence_threshold: float = 0.001,
    ):
        self.window = window_samples
        self.sample_rate = sample_rate
        # Default 50% overlap: stride = window // 2
        if stride_samples is None:
            stride_samples = window_samples // 2
        self.stride = stride_samples
        self.on_result = on_result
        self.silence_threshold = silence_threshold

        self._buffer = deque()
        self._buffer_len = 0
        self._lock = threading.Lock()
        self._window_count = 0

    def _resample_if_needed(self, chunk: np.ndarray, sr: int) -> np.ndarray:
        if sr == self.sample_rate:
            return chunk.astype(np.float32, copy=False)
        # Reuse VIGIL resampler (torchaudio) via preprocessing
        from ai.preprocessing import resample_audio
        # Ensure 1D
        if chunk.ndim > 1:
            chunk = chunk.mean(axis=1) if chunk.ndim == 2 else chunk.reshape(-1)
        return resample_audio(chunk.astype(np.float32), sr, self.sample_rate)

    def push_chunk(self, chunk: np.ndarray, sr: Optional[int] = None) -> list[Dict]:
        """
        Push new audio chunk (from mic or WebRTC). Returns list of results for windows completed by this chunk.
        chunk: np.ndarray shape (N,) or (N, channels) or (channels, N)
        sr: sample rate of chunk, defaults to TARGET_SAMPLE_RATE
        """
        if chunk is None or chunk.size == 0:
            return []
        sr = sr or self.sample_rate
        # Mono-mix if needed
        if chunk.ndim == 2:
            if chunk.shape[0] <= 8 and chunk.shape[1] > chunk.shape[0] * 4:
                chunk = chunk.mean(axis=0)
            elif chunk.shape[1] <= 8 and chunk.shape[0] > chunk.shape[1] * 4:
                chunk = chunk.mean(axis=1)
            else:
                chunk = chunk.mean(axis=1) if chunk.shape[0] < chunk.shape[1] else chunk.mean(axis=0)
        elif chunk.ndim != 1:
            chunk = chunk.reshape(-1)

        chunk = self._resample_if_needed(chunk, sr)

        results: list[Dict] = []
        with self._lock:
            # Append to buffer
            self._buffer.extend(chunk.tolist())
            self._buffer_len += len(chunk)

            # Emit while we have a full window
            while self._buffer_len >= self.window:
                # Snapshot window (first `window` samples)
                window_list = [self._buffer[i] for i in range(self.window)]
                window_np = np.array(window_list, dtype=np.float32)

                # Silence check before inference (reuse engine's threshold but avoid wasted inference)
                # We still send through analyze_waveform which will return SILENCE_DETECTED UNKNOWN;
                # here we let analyze_waveform handle it so behavior is consistent.
                # Optionally skip inference for silence to save CPU:
                # if np.max(np.abs(window_np)) < self.silence_threshold and np.sqrt(np.mean(window_np**2)) < self.silence_threshold:
                #     pass

                # Reuse existing VIGIL pipeline — no duplication
                result = analyze_waveform(window_np, self.sample_rate)
                result["_window_index"] = self._window_count
                result["_window_sec"] = self.window / self.sample_rate
                result["_stride_sec"] = self.stride / self.sample_rate
                self._window_count += 1

                if self.on_result:
                    try:
                        self.on_result(result)
                    except Exception:
                        pass
                results.append(result)

                # Slide by stride (keep overlap)
                for _ in range(self.stride):
                    if self._buffer:
                        self._buffer.popleft()
                self._buffer_len -= self.stride
                if self._buffer_len < 0:
                    self._buffer_len = 0

        return results

    # Alias for WebRTC clarity
    def push_webrtc_chunk(self, chunk: np.ndarray, sr: int = 48000) -> list[Dict]:
        """WebRTC typically 48kHz or 16kHz; same buffered sliding window."""
        return self.push_chunk(chunk, sr)

    def reset(self):
        with self._lock:
            self._buffer.clear()
            self._buffer_len = 0
            self._window_count = 0

    @property
    def buffered_seconds(self) -> float:
        return self._buffer_len / self.sample_rate


def _pick_mic_device(preferred: Optional[int] = None) -> Optional[int]:
    if not _SD_AVAILABLE:
        return None
    if preferred is not None:
        return preferred
    try:
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            name = d["name"].lower()
            if "realtek" in name and "microphone array" in name and d["max_input_channels"] > 0:
                return i
        return sd.default.device[0]
    except Exception:
        return None


def run_microphone(
    stream: Optional[VigilStream] = None,
    device: Optional[int] = None,
    window_sec: float = TARGET_DURATION_SEC,
    stride_sec: float = 2.0,
    on_result: Optional[Callable[[Dict], None]] = None,
):
    """
    Capture local microphone and feed VigilStream with sliding windows.
    Displays latest prediction, model_score, risk_score, risk_level, recommended_action.

    Window: 4.0375s (64600 @16k), Stride: 2.0s (50% overlap) by default.
    Processing latency: ~600-1700ms per window on CPU (measured).
    NOT millisecond-level — windowed near-real-time.

    Handles permission/errors gracefully, CPU-compatible.
    """
    if not _SD_AVAILABLE:
        print("[VIGIL] sounddevice not installed. Run: pip install sounddevice")
        print("[VIGIL] PortAudio is bundled with the wheel on Windows.")
        return

    if stream is None:
        window_samples = int(window_sec * TARGET_SAMPLE_RATE)
        stride_samples = int(stride_sec * TARGET_SAMPLE_RATE)
        stream = VigilStream(window_samples=window_samples, stride_samples=stride_samples, on_result=on_result)

    mic = _pick_mic_device(device)
    try:
        dev_info = sd.query_devices(mic) if mic is not None else sd.query_devices(sd.default.device[0])
        print(f"[VIGIL] Realtime mic — window={window_sec:.2f}s stride={stride_sec:.2f}s overlap={(1-stride_sec/window_sec)*100:.0f}%")
        print(f"[VIGIL] Target {TARGET_SAMPLE_RATE}Hz, CPU, mic device={mic}: {dev_info['name'] if isinstance(dev_info, dict) else dev_info}")
        print(f"[VIGIL] Processing latency ~0.6-1.7s per window (not millisecond-level). Ctrl+C to stop.\n")
    except Exception as e:
        print(f"[VIGIL] Could not query mic device {mic}: {e}")
        print("[VIGIL] Check Windows Settings -> Privacy -> Microphone -> Allow apps to access microphone.")
        return

    # Default on_result prints if none provided
    if stream.on_result is None:
        def _print_result(r: Dict):
            status = r.get("status")
            if status == "error" and r.get("error_code") == "SILENCE_DETECTED":
                print(f"  [silence] {r.get('error')} — speak louder (rms/max <0.001)")
                return
            print(f"  -> {r.get('prediction', '?'):8s}  "
                  f"model_score={r.get('model_score', 0):.5f}  "
                  f"risk={r.get('risk_score', 0):3d} {r.get('risk_level','?'):8s}  "
                  f"| {r.get('recommended_action','')}  "
                  f"({r.get('processing_time_ms','?')}ms)  "
                  f"[window #{r.get('_window_index', '?')}]")
        stream.on_result = _print_result

    # Queue for thread-safe handoff from audio callback to processing thread
    audio_q: queue.Queue = queue.Queue()

    def audio_callback(indata, frames, time_info, status):
        if status:
            print(f"[VIGIL] Audio status: {status}", flush=True)
        # indata: (frames, channels) float32
        chunk = indata[:, 0].copy() if indata.ndim == 2 else indata.copy()
        # indata is at device's samplerate; query actual rate
        # sounddevice InputStream will be opened at TARGET_SAMPLE_RATE, so sr is TARGET
        audio_q.put(chunk)

    # Use blocking InputStream with callback
    try:
        with sd.InputStream(
            device=mic,
            channels=1,
            samplerate=TARGET_SAMPLE_RATE,
            dtype="float32",
            callback=audio_callback,
            blocksize=2048,
        ):
            print("[VIGIL] Listening... speak normally. Overlap means you get an update every ~2s.\n")
            while True:
                try:
                    chunk = audio_q.get(timeout=0.5)
                except queue.Empty:
                    continue
                # Feed to sliding buffer — this may emit 0 or 1 windows per chunk
                results = stream.push_chunk(chunk, sr=TARGET_SAMPLE_RATE)
                # on_result already prints; if no window completed, nothing to show
                # Optional: show buffering progress
                if not results and stream.buffered_seconds > 0:
                    # Uncomment for verbose buffering:
                    # print(f"  buffering {stream.buffered_seconds:.1f}/{window_sec:.1f}s", end="\r")
                    pass

    except sd.PortAudioError as e:
        print(f"[VIGIL] Microphone PortAudio error: {e}")
        print("[VIGIL] Fixes: Check mic is plugged in, not used by another app, Windows mic permission allowed, try different device:")
        try:
            print(sd.query_devices())
        except Exception:
            pass
        print("[VIGIL] Try: python -m ai.realtime_stream --device <id>")
    except PermissionError as e:
        print(f"[VIGIL] Microphone permission denied: {e}")
        print("[VIGIL] Windows Settings -> Privacy & security -> Microphone -> Allow apps to access microphone.")
    except KeyboardInterrupt:
        print("\n[VIGIL] Stopped by user.")
    except Exception as e:
        print(f"[VIGIL] Unexpected error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="VIGIL Realtime Microphone - sliding window over existing detector")
    parser.add_argument("--device", type=int, default=None, help="sounddevice input device id (see python -m sounddevice)")
    parser.add_argument("--window", type=float, default=TARGET_DURATION_SEC, help=f"window seconds (default {TARGET_DURATION_SEC:.4f})")
    parser.add_argument("--stride", type=float, default=2.0, help="stride seconds (default 2.0, 50 percent overlap)")
    args = parser.parse_args()
    run_microphone(device=args.device, window_sec=args.window, stride_sec=args.stride)
