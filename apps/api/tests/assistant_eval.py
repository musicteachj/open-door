"""Loads the assistant eval's modules (evals/assistant/*.py, outside the API package) for tests.

The eval folder is run as a script (`run.py`), and its modules import each other as the package
`assistant` with evals/ on the path. The tests put evals/ on the path the same way and import each
module by that name, so a test and the runner share one copy of every class.
"""

import importlib
import sys
from dataclasses import fields
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID

EVAL_DIR = Path(__file__).resolve().parents[3] / "evals" / "assistant"
RUN_PATH = EVAL_DIR / "run.py"
# `assistant` is a package under evals/, so the modules import each other as `assistant.graders`
# whether they run as a script (run.py puts evals/ on the path) or under test (here).
if str(EVAL_DIR.parent) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR.parent))


def load_eval_module(filename: str) -> ModuleType:
    """The module in evals/assistant/`filename`, imported as `assistant.<stem>`, so every test and
    the runner share one copy of each."""
    return importlib.import_module(f"assistant.{Path(filename).stem}")


def load_runner() -> ModuleType:
    return load_eval_module("run.py")


def load_graders() -> ModuleType:
    return load_eval_module("graders.py")


def load_datasets() -> ModuleType:
    return load_eval_module("datasets.py")


def load_judge() -> ModuleType:
    return load_eval_module("judge.py")


def load_handgrades() -> ModuleType:
    return load_eval_module("handgrades.py")


def load_scoreboard() -> ModuleType:
    return load_eval_module("scoreboard.py")


def make_trace(
    *,
    person_id: UUID,
    item_id: str = "item-1",
    persona: str = "priya",
    question: str = "a question",
    answer_text: str = "",
    **overrides: Any,
) -> Any:
    """An `ItemTrace` for a grader test: a turn that did nothing unless the test says otherwise."""
    run = load_runner()
    values: dict[str, Any] = {
        "item_id": item_id,
        "persona": persona,
        "question": question,
        "person_id": person_id,
        "answer_text": answer_text,
        "citations": (),
        "tool_uses": (),
        "tool_results": (),
        "guard": None,
        "main_model_called": True,
        "model_call_count": 1,
        "escalations": (),
        "error_codes": (),
        "status_note_count": 0,
        "status_notes": (),
        "retracted_texts": (),
        "usage": (),
        "turn_status": "completed",
        "turn_error_code": None,
        "cost_usd": Decimal(0),
    }
    unknown = set(overrides) - {f.name for f in fields(run.ItemTrace)}
    assert not unknown, f"ItemTrace has no field {sorted(unknown)}"
    values.update(overrides)
    return run.ItemTrace(**values)
