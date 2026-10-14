from pathlib import Path
import shutil
import subprocess

import pytest


def test_live_following_state_regressions():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed for the browser-state regression check")
    root = Path(__file__).resolve().parent
    result = subprocess.run([node, "test_live_ui.js"], cwd=root, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
