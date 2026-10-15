"""One walk over a message's search results, in the order the API counts them."""

import subprocess
import sys
from typing import Any

from app.ai.transport import count_search_results, iter_search_results


def result(name: str) -> dict[str, Any]:
    return {"type": "search_result", "source": name, "title": name, "content": []}


def test_results_come_in_api_order_including_inside_tool_results() -> None:
    content: list[dict[str, Any]] = [
        {"type": "text", "text": "words"},
        result("a"),
        {
            "type": "tool_result",
            "tool_use_id": "t1",
            "content": [{"type": "text", "text": "x"}, result("b"), result("c")],
        },
        {"type": "tool_result", "tool_use_id": "t2", "content": "plain text, not blocks"},
        result("d"),
        {"type": "tool_result", "tool_use_id": "t3", "content": [result("e")]},
    ]

    assert [block["source"] for block in iter_search_results(content)] == list("abcde")
    assert count_search_results(content) == 5


def test_nothing_to_find_is_empty() -> None:
    assert list(iter_search_results([])) == []
    assert list(iter_search_results([{"type": "text", "text": "x"}])) == []


def test_the_scripted_transport_does_not_load_the_database_layer() -> None:
    # The scripted model must run without the ORM: the walk it needs lives in the pure transport
    # module, not in the conversation store. A fresh interpreter shows what an import really loads.
    code = (
        "import sys, app.ai.scripted;"
        "print(sorted(m for m in sys.modules if m.split('.')[0] == 'sqlalchemy'"
        " or m.startswith('app.db') or m == 'app.ai.conversations'))"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )

    assert result.stdout.strip() == "[]"


def test_a_message_whose_content_is_a_plain_string_has_no_results() -> None:
    # The API accepts a user message's content as a string; iterating one would walk characters.
    assert list(iter_search_results("How does sick leave work?")) == []
    assert count_search_results("How does sick leave work?") == 0
    assert count_search_results("") == 0


def test_counting_takes_the_same_input_as_iterating() -> None:
    assert count_search_results(iter([result("a"), result("b")])) == 2
