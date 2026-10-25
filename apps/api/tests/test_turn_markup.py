"""Tool-call markup in model text: only markup that reaches into unchecked text counts."""

import pytest

from app.ai import turn as turn_module

TAG = "<invoke name=" + chr(34) + "x" + chr(34) + ">"


def bare_run(sent_tail: str, held: str = "") -> turn_module.TurnRun:
    run = object.__new__(turn_module.TurnRun)
    run.sent_tail = sent_tail
    run.held = held
    return run


def test_markup_already_in_the_sent_tail_cannot_fail_later_clean_text() -> None:
    run = bare_run("earlier " + TAG)
    send, leaked = run._hold("A clean sentence that follows, long enough to send most of it.")
    assert not leaked
    assert send


def test_new_markup_after_an_old_tail_still_fails() -> None:
    run = bare_run("earlier " + TAG)
    with pytest.raises(turn_module._ToolMarkupInText):
        run._hold(" and now " + TAG)


def test_markup_split_between_the_held_text_and_new_text_still_fails() -> None:
    run = bare_run("", held="Sure. <inv")
    with pytest.raises(turn_module._ToolMarkupInText):
        run._hold('oke name="x">')


def test_a_status_note_with_markup_fails() -> None:
    with pytest.raises(turn_module._ToolMarkupInText):
        bare_run("")._check_note_for_markup("Checking " + TAG)


def test_markup_split_between_held_text_and_a_note_fails() -> None:
    with pytest.raises(turn_module._ToolMarkupInText):
        bare_run("", held="Sure. <inv")._check_note_for_markup('oke name="x">')


def test_markup_split_across_two_notes_fails() -> None:
    run = bare_run("Checking <inv")
    with pytest.raises(turn_module._ToolMarkupInText):
        run._check_note_for_markup('oke name="x"> now')


def test_a_clean_note_after_an_old_tail_passes() -> None:
    bare_run("earlier " + TAG)._check_note_for_markup("Looking at the handbook.")
