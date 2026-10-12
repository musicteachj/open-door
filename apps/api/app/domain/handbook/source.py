"""What the module reads from disk and hands to the domain."""

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceFile:
    """One file, already split and parsed by the module.

    `text` is the whole file exactly as read: it feeds the content hash. `data` is the parsed YAML:
    a section's front matter, or all of handbook.yaml. `body` is the markdown after the front
    matter, and `body_line_offset` is how many file lines come before it, so line 1 of the body is
    line `body_line_offset + 1` of the file. `field_lines` maps a key in `data` (nested keys joined
    with a dot, such as `applies_to.states`) to its line in the file, so an error can point at it.
    """

    path: str
    text: str
    data: Mapping[str, object] = field(default_factory=dict)
    body: str = ""
    body_line_offset: int = 0
    field_lines: Mapping[str, int] = field(default_factory=dict)
