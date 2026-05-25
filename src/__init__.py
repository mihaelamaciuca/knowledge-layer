"""MCP server package, sys.path bootstrap for the rag_core sibling pkg.

Adds `<repo>/scripts/` to sys.path so `src/*` modules can
`from rag_core import …`. The shared `rag_core` package lives under
`scripts/` (used by the indexer scripts and the MCP server alike) and
isn't a top-level Python package on the deployed image's path by
default.

Must run before any `from src.X import Y` that triggers a rag_core
import. Python evaluates `src/__init__.py` on the first `import src`
or `from src import …`, before any submodule loads.
"""
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
_SCRIPTS_PATH = str(_SCRIPTS_DIR)
if _SCRIPTS_PATH not in sys.path:
    sys.path.insert(0, _SCRIPTS_PATH)
