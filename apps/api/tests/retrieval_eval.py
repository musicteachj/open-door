"""Loads the retrieval eval's runner (evals/retrieval/run.py, outside the API package) for tests."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

RUN_PATH = Path(__file__).resolve().parents[3] / "evals" / "retrieval" / "run.py"


def load_runner() -> ModuleType:
    name = "retrieval_eval_run"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, RUN_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
