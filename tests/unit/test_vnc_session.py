from pathlib import Path
import shutil
import subprocess

import pytest


def test_vnc_session_javascript() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the VNC session JavaScript tests")
    proc = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("vnc_session.test.cjs"))],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
