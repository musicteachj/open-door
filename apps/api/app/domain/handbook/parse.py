"""Turn a section's markdown into blocks, refusing anything outside the handbook's subset.

The subset: `##` and `###` headings, paragraphs, bulleted and numbered lists one level deep, bold,
italic, and `handbook:` links. The parser reads markdown-it's token stream and refuses every token
type it doesn't know how to build, so a new kind of markdown fails loudly rather than slipping by.
"""

from dataclasses import dataclass

from markdown_it import MarkdownIt
from markdown_it.token import Token

from app.domain.handbook.blocks import Block, Heading, Inline, Passage
from app.domain.handbook.errors import HandbookError

# CommonMark plus the two extensions we want to see, so they become tokens we can refuse instead of
# plain text.
_PARSER = MarkdownIt("commonmark").enable(["table", "strikethrough"])

_BLOCK_REFUSALS = {
    "html_block": "raw HTML isn't allowed",
    "fence": "code blocks aren't allowed",
    "code_block": "code blocks aren't allowed",
    "blockquote_open": "quotes aren't allowed",
    "table_open": "tables aren't allowed",
    "hr": "horizontal rules aren't allowed",
}
_INLINE_REFUSALS = {
    "html_inline": "raw HTML isn't allowed",
    "image": "images aren't allowed",
    "code_inline": "inline code isn't allowed",
    "hardbreak": "forced line breaks aren't allowed",
    "s_open": "strikethrough isn't allowed",
}
_TEXT_TYPES = {"text", "text_special"}
_LINK_PREFIX = "handbook:"


@dataclass(frozen=True, slots=True)
class LinkRef:
    """A `handbook:` link, to check once every section's ID is known."""

    path: str
    line: int
    target: str


@dataclass(frozen=True, slots=True)
class ParsedBody:
    blocks: tuple[Block, ...]
    links: tuple[LinkRef, ...]
    errors: tuple[HandbookError, ...]


def parse_body(path: str, body: str, line_offset: int) -> ParsedBody:
    return _Parser(path, line_offset).run(_PARSER.parse(body))


class _Parser:
    def __init__(self, path: str, line_offset: int) -> None:
        self.path = path
        self.line_offset = line_offset
        self.blocks: list[Block] = []
        self.links: list[LinkRef] = []
        self.errors: list[HandbookError] = []
        self.passage_count = 0

    def run(self, tokens: list[Token]) -> ParsedBody:
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token.type == "heading_open":
                self._heading(token, tokens[i + 1])
            elif token.type == "paragraph_open":
                inline = tokens[i + 1]
                runs = self._inlines(inline)
                self.blocks.append(Passage(self._next_id(), "paragraph", inlines=runs))
            elif token.type in ("bullet_list_open", "ordered_list_open"):
                end = _closing(tokens, i)
                self._list(token, tokens[i + 1 : end])
                i = end
            else:
                self._refuse_block(token)
                if token.nesting == 1:
                    i = _closing(tokens, i)
            i = _after(tokens, i)
        return ParsedBody(tuple(self.blocks), tuple(self.links), tuple(self.errors))

    def _line(self, token: Token) -> int:
        start = token.map[0] if token.map else 0
        return self.line_offset + start + 1

    def _error(self, token: Token, message: str) -> None:
        self.errors.append(HandbookError(self.path, self._line(token), message))

    def _next_id(self) -> str:
        self.passage_count += 1
        return f"p{self.passage_count}"

    def _refuse_block(self, token: Token) -> None:
        message = _BLOCK_REFUSALS.get(token.type, f"unsupported markdown ({token.type})")
        self._error(token, message)

    def _heading(self, open_token: Token, inline: Token) -> None:
        level = int(open_token.tag[1:])
        runs = self._inlines(inline)
        text = "".join(run.text for run in runs)
        if any(run.link_section_id for run in runs):
            self._error(inline, "links aren't allowed in headings")
        if level == 2:
            self.blocks.append(Heading(2, text))
        elif level == 3:
            self.blocks.append(Heading(3, text))
        else:
            hashes = "#" * level
            self._error(open_token, f"a `{hashes}` heading isn't allowed: use `##` or `###`")

    def _list(self, open_token: Token, inner: list[Token]) -> None:
        items: list[tuple[Inline, ...]] = []
        i = 0
        while i < len(inner):
            token = inner[i]
            if token.type == "list_item_open":
                end = _closing(inner, i)
                item = self._item(inner[i + 1 : end])
                if item is None:
                    self._error(token, "a list item can't be empty")
                else:
                    items.append(item)
                i = end
            i += 1
        self.blocks.append(
            Passage(
                self._next_id(),
                "list",
                items=tuple(items),
                ordered=open_token.type == "ordered_list_open",
            )
        )

    def _item(self, inner: list[Token]) -> tuple[Inline, ...] | None:
        runs: tuple[Inline, ...] | None = None
        i = 0
        while i < len(inner):
            token = inner[i]
            if token.type == "paragraph_open" and runs is None:
                runs = self._inlines(inner[i + 1])
            elif token.type == "paragraph_open":
                self._error(token, "a list item must be a single paragraph")
            elif token.type in ("bullet_list_open", "ordered_list_open"):
                self._error(token, "nested lists aren't allowed")
                i = _closing(inner, i)
            else:
                self._refuse_block(token)
                if token.nesting == 1:
                    i = _closing(inner, i)
            i = _after(inner, i)
        return runs

    def _inlines(self, inline: Token) -> tuple[Inline, ...]:
        line = self._line(inline)
        runs: list[Inline] = []
        bold = italic = 0
        link: str | None = None
        refused: set[str] = set()  # report each kind once per paragraph

        def add(text: str) -> None:
            if not text:
                return
            style = (bold > 0, italic > 0, link)
            if runs and (runs[-1].bold, runs[-1].italic, runs[-1].link_section_id) == style:
                runs[-1] = Inline(runs[-1].text + text, *style)
            else:
                runs.append(Inline(text, *style))

        for child in inline.children or []:
            kind = child.type
            if kind in _TEXT_TYPES:
                add(child.content)
            elif kind == "softbreak":
                add(" ")
            elif kind == "strong_open":
                bold += 1
            elif kind == "strong_close":
                bold -= 1
            elif kind == "em_open":
                italic += 1
            elif kind == "em_close":
                italic -= 1
            elif kind == "link_open":
                href = str(child.attrGet("href") or "")
                target = href[len(_LINK_PREFIX) :]
                if href.startswith(_LINK_PREFIX) and target:
                    link = target
                    self.links.append(LinkRef(self.path, line, target))
                else:
                    self.errors.append(
                        HandbookError(
                            self.path,
                            line,
                            f"link to {href!r} isn't allowed: links must look like `handbook:4.3`",
                        )
                    )
            elif kind == "link_close":
                link = None
            elif kind == "s_close":
                pass  # the opening tag was already refused
            else:
                message = _INLINE_REFUSALS.get(kind, f"unsupported markdown ({kind})")
                if message not in refused:
                    refused.add(message)
                    self.errors.append(HandbookError(self.path, line, message))
        return tuple(runs)


def _closing(tokens: list[Token], start: int) -> int:
    """The index of the token that closes the one opened at `start`."""
    depth = 0
    for i in range(start, len(tokens)):
        depth += tokens[i].nesting
        if depth == 0:
            return i
    return len(tokens) - 1


def _after(tokens: list[Token], i: int) -> int:
    """The index after the construct that ends at `i`: past a paragraph's or heading's tail."""
    if tokens[i].type in ("paragraph_open", "heading_open"):
        return i + 3
    return i + 1
