from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agent_framework' / 'src'))
sys.path.insert(0, str(ROOT / 'agent_template_backend'))
