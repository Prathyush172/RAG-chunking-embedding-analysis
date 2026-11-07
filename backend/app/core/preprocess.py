"""
preprocess.py (backend core) — thin re-export of the top-level preprocess module.

The canonical implementation lives at the repo root (preprocess.py) so that
it can be run as `python preprocess.py` without installing the package.
This module makes it importable as `app.core.preprocess` from within the
backend package.
"""
from __future__ import annotations

# Re-export everything from the top-level module
import importlib
import sys
from pathlib import Path

# Insert repo root onto sys.path so the top-level preprocess module is found
_REPO_ROOT = Path(__file__).resolve().parents[3]  # backend/app/core/preprocess.py -> repo root
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_top = importlib.import_module("preprocess")

clean_text = _top.clean_text
preprocess_document = _top.preprocess_document
run_preprocessing = _top.run_preprocessing
load_corpus_config = _top.load_corpus_config

__all__ = [
    "clean_text",
    "preprocess_document",
    "run_preprocessing",
    "load_corpus_config",
]
