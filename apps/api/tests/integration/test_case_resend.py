"""A case sent twice: the stored words are decrypted once, and the repeat leaves an audit trail.

The first look (read-only, before the screening) only learns whether an earlier case exists. The
decision, same words and turn or a conflict, is made once, under the person's lock.
"""

from typing import Any
from uuid import uuid4

import pytest

from app.modules.cases import service
from app.modules.cases.texts import MAX_WAITING_CASES
from tests.integration.test_case_service import (  # noqa: F401
    WORDS,
    Env,
    audit_of,
    case_rows,
    env,
    flagged_turn,
    problem,
    send,
)

pytestmark = pytest.mark.integration


async def test_a_repeated_send_decrypts_once_and_is_recorded(env: Env) -> None:  # noqa: F811
    submission = uuid4()
    first = await send(env, env.leo, submission_id=submission)
    env.keys.unwraps = 0
    asked = len(env.transport.requests)

    again = await send(env, env.leo, submission_id=submission)

    assert (again.case.id, again.created) == (first.case.id, False)
    assert env.keys.unwraps == 1
    # No screening for a repeat.
    assert len(env.transport.requests) == asked
    [event] = await audit_of(env, "case.resubmitted")
    assert (event.target_type, event.target_id, event.via) == ("case", first.case.id, "ui")
    assert event.actor_person_id == env.leo
    assert WORDS not in repr(event.before) + repr(event.after)
    assert len(await audit_of(env, "case.opened")) == 1


async def test_a_send_with_different_words_is_a_conflict_and_not_recorded(env: Env) -> None:  # noqa: F811
    submission = uuid4()
    await send(env, env.leo, submission_id=submission)
    env.keys.unwraps = 0

    refused = await problem(send(env, env.leo, WORDS + " Again.", submission_id=submission))

    assert (refused.status_code, refused.code) == (409, "case-submission-conflict")
    assert env.keys.unwraps == 1
    assert await audit_of(env, "case.resubmitted") == []
    assert len(await case_rows(env, env.leo)) == 1


async def test_a_second_tab_for_the_same_turn_is_recorded_once_and_not_screened(
    env: Env,  # noqa: F811
) -> None:
    turn = await flagged_turn(env, env.leo, "sensitive")
    first = await send(env, env.leo, turn_id=turn)
    env.keys.unwraps = 0
    asked = len(env.transport.requests)

    again = await send(env, env.leo, turn_id=turn, submission_id=uuid4())

    assert (again.case.id, again.created) == (first.case.id, False)
    assert env.keys.unwraps == 1
    assert len(env.transport.requests) == asked
    [event] = await audit_of(env, "case.resubmitted")
    assert event.target_id == first.case.id


async def test_a_repeat_at_the_waiting_limit_still_returns_the_earlier_case(
    env: Env,  # noqa: F811
) -> None:
    submission = uuid4()
    first = await send(env, env.leo, submission_id=submission)
    for _ in range(MAX_WAITING_CASES - 1):
        await send(env, env.leo)

    again = await send(env, env.leo, submission_id=submission)

    assert (again.case.id, again.created) == (first.case.id, False)
    assert len(await audit_of(env, "case.resubmitted")) == 1


async def test_an_earlier_case_gone_between_the_looks_is_not_found_and_inserts_nothing(
    env: Env,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submission = uuid4()
    await send(env, env.leo, submission_id=submission)
    real = service._earlier
    calls = 0

    async def gone_on_the_second_look(*args: Any, **kwargs: Any) -> Any:
        # The first look finds the case; by the locked look its sandbox has ended.
        nonlocal calls
        calls += 1
        return await real(*args, **kwargs) if calls == 1 else None

    monkeypatch.setattr(service, "_earlier", gone_on_the_second_look)

    refused = await problem(send(env, env.leo, submission_id=submission))

    assert refused.status_code == 404
    assert len(await case_rows(env, env.leo)) == 1
    assert await audit_of(env, "case.resubmitted") == []
