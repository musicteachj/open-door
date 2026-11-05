"""The eval runner's --model option against the real database: the conversations are pinned to the
set's model, and the run records it (Phase 7, stage 2). The scripted model makes no paid call."""

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from tests.integration.test_assistant_eval_runner_db import args, make_env, run

pytestmark = pytest.mark.integration

SONNET_55 = "claude-sonnet-5-5"


@pytest.mark.parametrize("set_name", ["smoke", "full"])
async def test_a_run_of_another_model_pins_its_conversations_and_records_that_model(
    tmp_path: Path,
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    database_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    set_name: str,
) -> None:
    pinned: list[Any] = []
    real = run.create_conversation

    async def spy(db: Any, actor: Any, pins: Any, keys: Any) -> Any:
        pinned.append(pins)
        return await real(db, actor, pins, keys)

    monkeypatch.setattr(run, "create_conversation", spy)
    env = make_env(tmp_path, app_engine, owner_engine, database_settings)
    out_json = tmp_path / "run.json"

    await run.run_cli(
        args(tmp_path, "--yes", "--model", SONNET_55, "--json", str(out_json), name=set_name),
        env=env,
    )

    assert pinned
    assert {pins.model for pins in pinned} == {SONNET_55}
    document = json.loads(out_json.read_text(encoding="utf-8"))
    assert document["models"]["assistant"] == SONNET_55
    assert document["models"]["guard"] == run.GUARD_MODEL_ID
