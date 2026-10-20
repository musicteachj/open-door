"""The turn's events as the stream will send them: camelCase, and the spec's payloads."""

from datetime import date
from uuid import UUID

from app.ai.citations import CitationEvent
from app.ai.fixed_texts import HrContact
from app.ai.turn import (
    Citation,
    Error,
    Escalation,
    Status,
    TextDelta,
    ToolFinished,
    ToolStarted,
    TurnCompleted,
    TurnStarted,
    TurnUsage,
)

TURN = UUID("11111111-1111-1111-1111-111111111111")


def test_each_event_serializes_to_the_specs_payload() -> None:
    citation = CitationEvent(
        marker=1,
        offset_utf16=214,
        section_id="CA-4.3",
        passage_id="p2",
        title="Sick leave",
        group_name="California addendum",
        audience_label="California",
        last_updated=date(2026, 9, 12).isoformat(),
        deep_link="/handbook/CA-4.3?passage=p2",
        cited_text="text",
    )
    usage = TurnUsage(10, 2)
    assert TurnStarted(TURN).to_json() == {"turnId": str(TURN)}
    assert Status("Searching the handbook…").to_json() == {"text": "Searching the handbook…"}
    assert TextDelta("Hi").to_json() == {"text": "Hi"}
    assert Citation(citation).to_json() == citation.to_json()
    assert ToolStarted("t1", "search_handbook", "sick").to_json() == {
        "id": "t1",
        "name": "search_handbook",
        "summary": "sick",
    }
    assert ToolFinished("t1", True, "sick", 12).to_json() == {
        "id": "t1",
        "ok": True,
        "summary": "sick",
        "durationMs": 12,
    }
    dana = HrContact("Dana Whitfield", "d@x.example", "HR Business Partner", "Denver HQ")
    assert Escalation("sensitive", "msg", (dana,)).to_json() == {
        "kind": "sensitive",
        "message": "msg",
        "hrContact": [
            {
                "name": "Dana Whitfield",
                "workEmail": "d@x.example",
                "jobTitle": "HR Business Partner",
                "locationName": "Denver HQ",
            }
        ],
        "offerCase": False,
    }
    assert Error("refusal", "msg").to_json() == {
        "code": "refusal",
        "message": "msg",
        "requestId": None,
    }
    assert TurnCompleted(TURN, "claude-opus-5-5", usage).to_json() == {
        "turnId": str(TURN),
        "servedBy": "claude-opus-5-5",
        "usage": {
            "inputTokens": 10,
            "outputTokens": 2,
        },
    }


def test_the_stream_names_match_the_spec() -> None:
    names = [
        TurnStarted.name,
        Status.name,
        TextDelta.name,
        Citation.name,
        ToolStarted.name,
        ToolFinished.name,
        Escalation.name,
        Error.name,
        TurnCompleted.name,
    ]
    assert names == [
        "turn.started",
        "status",
        "text.delta",
        "citation",
        "tool.started",
        "tool.finished",
        "escalation",
        "error",
        "turn.completed",
    ]


def test_an_incomplete_answer_is_marked_on_the_completed_event_only_when_it_is() -> None:
    usage = TurnUsage(1, 1)
    assert "incomplete" not in TurnCompleted(TURN, "m", usage).to_json()
    assert TurnCompleted(TURN, "m", usage, incomplete=True).to_json()["incomplete"] is True


def test_the_answer_length_is_counted_in_utf16_units() -> None:
    from app.ai.turn import utf16_length

    assert utf16_length("abc") == 3
    assert utf16_length("\U0001f600 ok") == 5
    assert utf16_length("é") == 1


def test_an_error_is_logged_by_its_type_only() -> None:
    from app.ai.text import error_name

    assert error_name(ValueError("a secret question")) == "ValueError"
