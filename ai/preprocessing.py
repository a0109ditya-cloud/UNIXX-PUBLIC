"""
VIGIL Audio Preprocessing - robust, reusable, AASIST-faithful.

Handles:
- different sample rates (resample to 16kHz)
- mono/stereo (mix to mono)
- short recordings (tile/repeat-pad like AASIST data_utils.pad)
- long recordings (deterministic truncate to first 64600 samples)
- missing / corrupt / unsupported files -> structured ValidationError

Reusable for offline files and future streaming chunks.
Uses soundfile + torchaudio for maximum compatibility on Windows CPU.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import soundfile as sf
import torch
import torchaudio

from .config import TARGET_NUM_SAMPLES, TARGET_SAMPLE_RATE, SUPPORTED_EXTENSIONS, MAX_FILE_SIZE_BYTES


class AudioValidationError(ValueError):
    """Raised when audio cannot be validated / loaded."""
    def __init__(self, message: str, code: str = "INVALID_AUDIO"):
        super().__init__(message)
        self.code = code


def validate_audio_path(audio_path: str | os.PathLike) -> Path:
    """Validate path exists, extension supported, file size reasonable."""
    if audio_path is None or (isinstance(audio_path, str) and audio_path.strip() == ""):
        raise AudioValidationError("audio_path is empty or None", code="MISSING_PATH")
    p = Path(audio_path)
    if not p.exists():
        raise AudioValidationError(f"File not found: {p}", code="FILE_NOT_FOUND")
    if not p.is_file():
        raise AudioValidationError(f"Not a file: {p}", code="NOT_A_FILE")
    if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise AudioValidationError(
            f"Unsupported extension '{p.suffix}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}",
            code="UNSUPPORTED_FORMAT",
        )
    size = p.stat().st_size
    if size == 0:
        raise AudioValidationError(f"File is empty (0 bytes): {p}", code="EMPTY_FILE")
    if size > MAX_FILE_SIZE_BYTES:
        raise AudioValidationError(
            f"File too large ({size} bytes > {MAX_FILE_SIZE_BYTES}) : {p}", code="FILE_TOO_LARGE"
        )
    return p


def _load_with_soundfile(path: Path) -> Tuple[np.ndarray, int]:
    """Try soundfile first (best for wav/flac). Returns (mono_or_nd, sr)."""
    data, sr = sf.read(str(path), always_2d=False)
    return data, sr


def _load_with_torchaudio(path: Path) -> Tuple[np.ndarray, int]:
    """Fallback via torchaudio."""
    wav, sr = torchaudio.load(str(path))  # (channels, samples)
    # Convert to numpy (samples,) mono or (samples, channels)
    wav_np = wav.numpy()
    if wav_np.shape[0] > 1:
        wav_np = wav_np.mean(axis=0)
    else:
        wav_np = wav_np[0]
    return wav_np, sr


def load_audio(path: Path) -> Tuple[np.ndarray, int]:
    """
    Load audio as numpy float array, shape (num_samples,) mono, and sample_rate.
    Tries soundfile first, falls back to torchaudio. Raises AudioValidationError on failure.
    """
    errors: list[str] = []
    last_err: Exception | None = None
    for loader in (_load_with_soundfile, _load_with_torchaudio):
        try:
            data, sr = loader(path)
            # Ensure numpy array
            data = np.asarray(data)
            if data.ndim == 2:
                # (samples, channels) from soundfile -> mono
                data = data.mean(axis=1)
            if data.size == 0:
                raise AudioValidationError("Decoded audio is empty", code="EMPTY_AUDIO")
            # soundfile may return float64 in [-1,1]; normalize to float32
            if data.dtype != np.float32:
                data = data.astype(np.float32)
            # Check for NaN/Inf
            if not np.isfinite(data).all():
                raise AudioValidationError("Audio contains NaN or Inf", code="CORRUPT_AUDIO")
            return data, int(sr)
        except AudioValidationError:
            raise
        except Exception as e:
            last_err = e
            errors.append(f"{loader.__name__}: {e}")
            continue
    # Prefer soundfile error for corrupt files; hide torchcodec internal message
    err_msg = str(last_err) if last_err else "unknown decode error"
    if "TorchCodec" in err_msg and errors:
        # Use first error (soundfile) which is more informative for corrupt files
        err_msg = errors[0]
        if "TorchCodec" not in err_msg:
            err_msg = f"Corrupt or unsupported audio format - {err_msg}"
    raise AudioValidationError(f"Failed to decode audio: {err_msg}", code="DECODE_FAILED")


def resample_audio(waveform: np.ndarray, orig_sr: int, target_sr: int = TARGET_SAMPLE_RATE) -> np.ndarray:
    """Resample numpy waveform to target_sr using torchaudio."""
    if orig_sr == target_sr:
        return waveform
    # torchaudio expects Tensor (1, N)
    wav_t = torch.from_numpy(waveform).unsqueeze(0)
    resampler = torchaudio.transforms.Resample(orig_freq=orig_sr, new_freq=target_sr)
    resampled = resampler(wav_t)
    return resampled.squeeze(0).numpy().astype(np.float32)


def pad_or_truncate(waveform: np.ndarray, target_len: int = TARGET_NUM_SAMPLES) -> np.ndarray:
    """
    AASIST-faithful length normalization.
    - If longer: truncate to first target_len (deterministic, matches eval pad).
    - If shorter: tile/repeat (np.tile) to fill, not zero-pad. Matches data_utils.pad.
    - If exactly target_len: unchanged.

    Zero-padding would be an out-of-distribution silence that AASIST never saw;
    tiling preserves spectral character for short clips.
    """
    n = waveform.shape[0]
    if n == target_len:
        return waveform
    if n > target_len:
        return waveform[:target_len]
    # Short -> tile
    num_repeats = int(np.ceil(target_len / n))
    tiled = np.tile(waveform, num_repeats)[:target_len]
    return tiled.astype(np.float32, copy=False)


def preprocess_audio(file_path: str | os.PathLike) -> torch.Tensor:
    """
    Main file -> Tensor preprocessing for AASIST.
    Returns: torch.FloatTensor shape (TARGET_NUM_SAMPLES,) on CPU.
    Raises AudioValidationError on invalid input.
    """
    path = validate_audio_path(file_path)
    waveform, sr = load_audio(path)
    if sr != TARGET_SAMPLE_RATE:
        waveform = resample_audio(waveform, sr, TARGET_SAMPLE_RATE)
    waveform = pad_or_truncate(waveform, TARGET_NUM_SAMPLES)
    tensor = torch.from_numpy(waveform).float()
    # Final sanity
    if tensor.shape[0] != TARGET_NUM_SAMPLES:
        raise AudioValidationError(
            f"Preprocessed length mismatch: {tensor.shape[0]} != {TARGET_NUM_SAMPLES}",
            code="PREPROCESS_FAILED",
        )
    if not torch.isfinite(tensor).all():
        raise AudioValidationError("Preprocessed tensor contains NaN/Inf", code="CORRUPT_AUDIO")
    return tensor


def preprocess_waveform(
    waveform: np.ndarray,
    sample_rate: int,
) -> torch.Tensor:
    """
    Reusable for streaming / in-memory audio.
    Args:
        waveform: np.ndarray shape (N,) or (N, C) or (C, N) - will be mono-mixed.
        sample_rate: original sample rate.
    Returns:
        torch.Tensor shape (TARGET_NUM_SAMPLES,)
    """
    if waveform is None or not isinstance(waveform, np.ndarray):
        raise AudioValidationError("waveform must be a numpy array", code="INVALID_INPUT")
    if waveform.size == 0:
        raise AudioValidationError("waveform is empty", code="EMPTY_AUDIO")
    # Mono mix if multi-dimensional
    if waveform.ndim == 2:
        # Heuristic: if shape (C, N) with C small (<=8) and N large, treat as channels-first
        # Otherwise treat as (N, C)
        if waveform.shape[0] <= 8 and waveform.shape[1] > waveform.shape[0] * 4:
            waveform = waveform.mean(axis=0)
        else:
            waveform = waveform.mean(axis=1)
    elif waveform.ndim != 1:
        waveform = waveform.reshape(-1)
    waveform = waveform.astype(np.float32, copy=False)
    if not np.isfinite(waveform).all():
        raise AudioValidationError("waveform contains NaN/Inf", code="CORRUPT_AUDIO")
    if sample_rate != TARGET_SAMPLE_RATE:
        waveform = resample_audio(waveform, sample_rate, TARGET_SAMPLE_RATE)
    waveform = pad_or_truncate(waveform, TARGET_NUM_SAMPLES)
    return torch.from_numpy(waveform).float()


def get_audio_info(file_path: str | os.PathLike) -> Dict:
    """Return audio metadata without full preprocessing - useful for logging."""
    path = validate_audio_path(file_path)
    waveform, sr = load_audio(path)
    duration = waveform.shape[0] / sr
    return {
        "path": str(path),
        "sample_rate": sr,
        "num_samples": int(waveform.shape[0]),
        "duration_sec": float(duration),
        "channels": 1,  # we mono-mix
        "target_sample_rate": TARGET_SAMPLE_RATE,
        "target_num_samples": TARGET_NUM_SAMPLES,
    }
