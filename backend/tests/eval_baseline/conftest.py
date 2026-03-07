"""
pytest configuration for eval_baseline tests.

Adds the eval_baseline directory to sys.path so that eval_metrics / eval_runner
can be imported directly in test files.
"""
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))
