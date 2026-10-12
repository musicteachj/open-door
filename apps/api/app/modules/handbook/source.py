"""Read the handbook's files from disk and parse their YAML for the pure domain.

The domain can't import YAML or touch the disk, so this is where handbook.yaml and each section's
front matter become plain values. A YAML syntax error is reported here with its file and line, in
the same form the domain's validation errors take.
"""

from pathlib import Path

import yaml

from app.domain.handbook.errors import HandbookError, HandbookInvalid
from app.domain.handbook.models import Handbook
from app.domain.handbook.source import SourceFile
from app.domain.handbook.validate import load_handbook

CONFIG_NAME = "handbook.yaml"
_FENCE = "---"


class _Loader(yaml.SafeLoader):
    """SafeLoader, except an impossible date such as 2026-13-45 stays a string.

    The default raises a bare ValueError with no line. As a string it reaches the domain's own
    date check, which reports the field and its line like any other bad value.
    """


def _lenient_timestamp(loader: yaml.SafeLoader, node: yaml.Node) -> object:
    try:
        return yaml.SafeLoader.yaml_constructors["tag:yaml.org,2002:timestamp"](loader, node)
    except ValueError:
        return loader.construct_scalar(node)  # type: ignore[arg-type]


_Loader.add_constructor("tag:yaml.org,2002:timestamp", _lenient_timestamp)


def parse_config(path: str, text: str) -> SourceFile:
    """handbook.yaml: all of it is data, and there is no body."""
    data, lines = _load_yaml(path, text, first_line=1)
    return SourceFile(path=path, text=text, data=data, field_lines=lines)


def parse_section(path: str, text: str) -> SourceFile:
    """A section file: YAML front matter between `---` lines, then the markdown body."""
    lines = text.split("\n")
    if lines[0].rstrip() != _FENCE:
        raise _error(path, 1, "the file must start with `---` and YAML front matter")
    closing = next((i for i in range(1, len(lines)) if lines[i].rstrip() == _FENCE), None)
    if closing is None:
        raise _error(path, 1, "the front matter is never closed with a `---` line")
    front_matter = "\n".join(lines[1:closing])
    data, field_lines = _load_yaml(path, front_matter, first_line=2)
    body_line_offset = closing + 1
    body = "\n".join(lines[body_line_offset:])
    return SourceFile(
        path=path,
        text=text,
        data=data,
        body=body,
        body_line_offset=body_line_offset,
        field_lines=field_lines,
    )


def read_handbook(root: Path) -> Handbook:
    """Read, parse, and validate the handbook under `root`. Raises HandbookInvalid."""
    errors: list[HandbookError] = []
    config: SourceFile | None = None
    files: list[SourceFile] = []

    config_path = root / CONFIG_NAME
    try:
        config = parse_config(CONFIG_NAME, config_path.read_text(encoding="utf-8"))
    except HandbookInvalid as invalid:
        errors.extend(invalid.errors)
    for path in sorted([*root.glob("sections/*.md"), *root.glob("addenda/*/*.md")]):
        relative = path.relative_to(root).as_posix()
        try:
            files.append(parse_section(relative, path.read_text(encoding="utf-8")))
        except HandbookInvalid as invalid:
            errors.extend(invalid.errors)

    if errors or config is None:
        # Syntax errors come first and alone: validating the files that did parse would blame
        # them for links to the files that didn't.
        raise HandbookInvalid(errors)
    return load_handbook(config, files)


def _error(path: str, line: int, message: str) -> HandbookInvalid:
    return HandbookInvalid([HandbookError(path, line, message)])


def _load_yaml(
    path: str, text: str, *, first_line: int
) -> tuple[dict[str, object], dict[str, int]]:
    """Parse `text`, whose first line is line `first_line` of the file.

    Returns the mapping and the file line of each key (nested keys joined with a dot).
    """
    try:
        node = yaml.compose(text, Loader=_Loader)
        data = yaml.load(text, Loader=_Loader)  # noqa: S506 (a SafeLoader subclass)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        line = first_line + (mark.line if mark else 0)
        problem = getattr(error, "problem", None) or str(error)
        raise _error(path, line, f"YAML syntax error: {problem}") from error
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise _error(path, first_line, "the YAML must be a mapping of fields")
    lines: dict[str, int] = {}
    if isinstance(node, yaml.MappingNode):
        _record_lines(node, "", first_line, lines)
    return data, lines


def _record_lines(
    node: yaml.MappingNode, prefix: str, first_line: int, lines: dict[str, int]
) -> None:
    for key_node, value_node in node.value:
        key = f"{prefix}{key_node.value}"
        lines[key] = first_line + key_node.start_mark.line
        if isinstance(value_node, yaml.MappingNode):
            _record_lines(value_node, f"{key}.", first_line, lines)
