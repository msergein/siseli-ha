# conftest.py — pytest/unittest discovery helper
# This file ensures the tests/ directory is recognized as a test package.
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest


@pytest.fixture(autouse=True)
def _disable_monitor_journal(monkeypatch):
    """Tests must not append to the real /data/monitor.jsonl; monitor tests enable it."""
    from src.siseli_local_bridge import fakecloud
    monkeypatch.setattr(fakecloud, "LIVE_MONITOR", False, raising=False)
