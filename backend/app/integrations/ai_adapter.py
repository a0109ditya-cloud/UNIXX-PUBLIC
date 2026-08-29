from __future__ import annotations

from typing import Any

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai import analyze_audio


def analyze_voice_file(file_path: str | Path) -> dict[str, Any]:
    return analyze_audio(str(file_path))
