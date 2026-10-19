"""Shared boundary definitions, not a second transfer implementation."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
common = (ROOT / "tests/support/engine.hpp").read_text()
