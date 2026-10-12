"""A section's body as structured blocks: headings and passages.

The API serves these as JSON and the web app renders them as React elements, never as HTML. Each
paragraph and each list is a passage, numbered in order (`p1`, `p2`, ...). Headings aren't passages.
"""

from dataclasses import dataclass
from typing import Literal

type JsonObject = dict[str, object]


@dataclass(frozen=True, slots=True)
class Inline:
    """A run of text with one style. `link_section_id` is set when the run is inside a link."""

    text: str
    bold: bool = False
    italic: bool = False
    link_section_id: str | None = None

    def to_json(self) -> JsonObject:
        return {
            "text": self.text,
            "bold": self.bold,
            "italic": self.italic,
            "linkSectionId": self.link_section_id,
        }


@dataclass(frozen=True, slots=True)
class Heading:
    level: Literal[2, 3]
    text: str

    def to_json(self) -> JsonObject:
        return {"type": "heading", "level": self.level, "text": self.text}


@dataclass(frozen=True, slots=True)
class Passage:
    """A paragraph (`inlines`) or a list (`items`, each a list of inlines)."""

    id: str
    kind: Literal["paragraph", "list"]
    inlines: tuple[Inline, ...] = ()
    items: tuple[tuple[Inline, ...], ...] = ()
    # Only for a list: numbered rather than bulleted.
    ordered: bool = False

    def to_json(self) -> JsonObject:
        if self.kind == "paragraph":
            return {
                "type": "passage",
                "id": self.id,
                "kind": "paragraph",
                "inlines": [inline.to_json() for inline in self.inlines],
            }
        return {
            "type": "passage",
            "id": self.id,
            "kind": "list",
            "ordered": self.ordered,
            "items": [[inline.to_json() for inline in item] for item in self.items],
        }

    @property
    def text(self) -> str:
        """The passage as plain text: a paragraph's words, or one `- item` line per list item."""
        if self.kind == "paragraph":
            return _plain(self.inlines)
        return "\n".join(f"- {_plain(item)}" for item in self.items)


type Block = Heading | Passage


def _plain(inlines: tuple[Inline, ...]) -> str:
    return "".join(inline.text for inline in inlines)


def blocks_to_json(blocks: tuple[Block, ...]) -> list[JsonObject]:
    """The value for a section's `blocks` column."""
    return [block.to_json() for block in blocks]
