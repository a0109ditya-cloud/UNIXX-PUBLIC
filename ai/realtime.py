"""
VIGIL Realtime Mic Demo — thin wrapper over modular ai.realtime_stream.
Kept for backward compat: `python ai/realtime.py` still works.
New implementation: `python -m ai.realtime_stream` (sliding 4.04s window, 2s stride).

Uses existing detector via analyze_waveform — no duplication.
"""
from ai.realtime_stream import run_microphone

if __name__ == "__main__":
    run_microphone()
