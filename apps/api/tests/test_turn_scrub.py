"""Lone surrogates from the model are replaced where events enter the loop, except in thinking
blocks, which go back to the model with their signatures and must stay byte for byte."""

from app.ai.pricing import Usage
from app.ai.transport import Finished
from app.ai.turn import scrubbed

LONE = "\ud83d"
NO_USAGE = Usage(0, 0, 0, 0)


def test_scrubbing_a_finished_message_leaves_thinking_blocks_as_they_came() -> None:
    thinking = {"type": "thinking", "thinking": f"note {LONE}", "signature": "sig"}
    redacted = {"type": "redacted_thinking", "data": f"opaque {LONE}"}
    message = {
        "role": "assistant",
        "content": [thinking, redacted, {"type": "text", "text": f"Done {LONE}"}],
    }
    finished = Finished(
        message=message,
        stop_reason="end_turn",
        stop_details=None,
        usage=NO_USAGE,
        iterations=(),
        served_by="claude-opus-5-5",
    )

    content = scrubbed(finished).message["content"]

    assert content[0] == thinking
    assert content[1] == redacted
    assert content[2] == {"type": "text", "text": "Done �"}
