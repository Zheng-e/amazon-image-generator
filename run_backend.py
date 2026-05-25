from __future__ import annotations

import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
for deps_dir in (ROOT / ".webdeps", ROOT / ".deps"):
    if deps_dir.exists():
        sys.path.insert(0, str(deps_dir))

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "backend.app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8010")),
        reload=False,
    )
