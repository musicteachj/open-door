"""The isolation proof for the fairness clones (spec "The fairness set", plan Task 18, Review focus
7): adding the clones to the eval sandbox must not change what any other eval item's tools return.

**What it runs.** Every tool call in the committed full-set recordings (redteam.jsonl.gz,
qa.jsonl.gz, and actions.jsonl.gz: the recorded model responses hold each `tool_call` with its
name and input), once as the item's asker in a sandbox without the clones and once in a sandbox
with them, under the same code and the same clock, and compares the results.

**Coverage.** Every recorded call of the tools that read people, time off, and cases is run:
`get_my_profile`, `find_people` (the directory), `get_time_off_balance`, `check_time_off`,
`list_time_off_requests` (a team's and HR's lists), `get_my_cases`, and `list_cases` (HR's queue).
Not run: `search_handbook` (it reads the handbook, which has no people in it, and needs an
embedding), and the three `propose_*` tools (each stores a confirm card under a conversation and
turn, and the card carries a random ID). The proposals read the same people and requests the
tools above read, and the isolation of those reads is what is proved here.

If a call's result differs, the test fails naming the items, the tool, and the input.
"""

import gzip
import json
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.tools.registry import ToolContext, run_tool
from app.db.tenancy import TenantContext, tenant_session
from app.modules.handbook.asker import load_asker
from app.modules.handbook.search import pinned_version_id
from app.modules.identity.actor import load_actor
from tests.assistant_eval import EVAL_DIR, load_datasets, load_runner
from tests.integration.conftest import TEST_KEYS

pytestmark = pytest.mark.integration

run = load_runner()
datasets = load_datasets()

FIXTURES = EVAL_DIR / "fixtures"
# The tools whose results are compared. See the module docstring for what is left out and why.
PROVED = {
    "get_my_profile",
    "find_people",
    "get_time_off_balance",
    "check_time_off",
    "list_time_off_requests",
    "get_my_cases",
    "list_cases",
}
LEFT_OUT = {
    "search_handbook",
    "propose_time_off_request",
    "propose_time_off_decision",
    "propose_cancel_time_off",
}

Call = tuple[str, str, str, str]  # (asker, tool, input as JSON, the first item that made it)


def askers_by_item() -> dict[str, str]:
    by_item: dict[str, str] = {}
    for items in (datasets.load_redteam(), datasets.load_qa(), datasets.load_actions()):
        by_item.update({item.id: item.asker for item in items})
    return by_item


def recorded_calls() -> Iterator[dict[str, Any]]:
    """Every tool call in the committed recordings, once for each asker, tool, and input."""
    askers = askers_by_item()
    seen: set[tuple[str, str, str]] = set()
    for name in ("redteam", "qa", "actions"):
        text = gzip.decompress((FIXTURES / f"{name}.jsonl.gz").read_bytes()).decode("utf-8")
        for line in text.splitlines():
            record = json.loads(line)
            if record["kind"] != "model":
                continue
            for event in record.get("events", []):
                if event["type"] != "tool_call":
                    continue
                asker = askers[record["item"]]
                key = (asker, event["name"], json.dumps(event["input"], sort_keys=True))
                if key not in seen:
                    seen.add(key)
                    yield {
                        "asker": asker,
                        "tool": event["name"],
                        "input": event["input"],
                        "item": record["item"],
                    }


def test_the_recordings_have_tool_calls_to_prove_and_we_know_every_tool_in_them() -> None:
    calls = list(recorded_calls())

    tools = {c["tool"] for c in calls}
    assert tools <= PROVED | LEFT_OUT, tools - PROVED - LEFT_OUT
    proved = [c for c in calls if c["tool"] in PROVED]
    assert len(proved) >= 20
    # The tools that read the directory, a team, or HR's lists are among them.
    assert {"find_people", "list_time_off_requests", "list_cases"} <= {c["tool"] for c in proved}


async def results_in(
    clones: Any,
    calls: list[dict[str, Any]],
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
) -> list[tuple[bool, str, str]]:
    """Each call's result in a fresh sandbox with the given clones."""
    results: list[tuple[bool, str, str]] = []
    async with run.fixed_sandbox(app_engine, owner_engine, TEST_KEYS, clones=clones) as company:
        for call in calls:
            person = next(p for p in company.people if p.persona_key == call["asker"])
            ctx = TenantContext(company.tenant_id, person.id)
            async with tenant_session(app_engine, ctx) as db:
                actor = await load_actor(db, company.tenant_id, person.id)
                assert actor is not None
                asker = await load_asker(db, actor)
                version_id = await pinned_version_id(db)
            assert version_id is not None
            tool_ctx = ToolContext(
                engine=app_engine,
                tenant_ctx=ctx,
                actor=actor,
                asker=asker,
                version_id=version_id,
                embedder=None,
                now=run.NOW,
                conversation_id=uuid4(),
                turn_id=uuid4(),
            )
            outcome = await run_tool(call["tool"], call["input"], tool_ctx)
            results.append(
                (outcome.is_error, json.dumps(outcome.content, sort_keys=True), outcome.summary)
            )
    return results


async def test_no_recorded_tool_call_returns_anything_different_with_the_clones_in_the_sandbox(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    calls = [c for c in recorded_calls() if c["tool"] in PROVED]

    without = await results_in((), calls, app_engine, owner_engine)
    with_clones = await results_in(None, calls, app_engine, owner_engine)  # None: the committed set

    assert len(with_clones) == len(without) == len(calls)
    differing = [
        f"{c['item']} ({c['asker']}) {c['tool']} {json.dumps(c['input'], sort_keys=True)}"
        for c, before, after in zip(calls, without, with_clones, strict=True)
        if before != after
    ]
    assert differing == []
    # The proof is not vacuous: the calls returned real data.
    assert sum(1 for _, content, _ in without if len(content) > 60) >= 15


async def test_the_clones_are_visible_to_the_directory_so_the_proof_could_have_failed(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """A search for a clone's name finds it with the clones in, and nothing without them: the
    comparison above would catch a clone that leaked into any other item's result."""
    call = [
        {
            "asker": "dana",
            "tool": "find_people",
            "input": {"scope": "everyone", "query": "Lindqvist"},
            "item": "x",
        }
    ]

    without = await results_in((), call, app_engine, owner_engine)
    with_clones = await results_in(None, call, app_engine, owner_engine)

    assert "Lindqvist" not in without[0][1]
    assert "Lindqvist" in with_clones[0][1]
