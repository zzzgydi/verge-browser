from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
API_SERVER = ROOT / "apps" / "api-server"
PYTHON_PACKAGES = ROOT / "packages" / "python"

for candidate in (ROOT, API_SERVER, PYTHON_PACKAGES):
    path = str(candidate)
    if path not in sys.path:
        sys.path.insert(0, path)
