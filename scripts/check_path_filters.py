"""Fail when a CI job's path filter misses a file its tests read: `make check-workflows`.

The CI workflow runs each heavy job (API, Web, E2E) only when a changed file matches that job's
filter in the `changes` job (`.github/workflows/ci.yml`). A test that reads a file outside its own
app (a design token file, the handbook, the Makefile) has a gap if the filter leaves that file out:
a change to it would skip the job whose tests depend on it. This scans the test sources for such
reads and checks each against the job's filter. Standard library only; needs Python 3.10 or newer
(the Makefile runs it with 3.13); run from anywhere.

    python3 scripts/check_path_filters.py [--list]     (--list prints every read it found)

What it recognizes, because it is what the tests really do (a read it cannot see is a gap in this
script, not a license to skip the filter):

- Python tests (apps/api/tests, job `api`): a path built from `Path(__file__)` with `.parent`,
  `.parents[N]`, and `/ "segment"` (a segment may hold slashes or `..`), also through a name the
  file or any other test file assigns it to (`ROOT = Path(__file__).resolve().parents[3]`,
  `EVAL_DIR` imported from a helper module). A path that stays inside apps/api is the test's own.
- Web unit tests (apps/web/src, job `web`) and browser tests (apps/web/e2e, job `e2e`):
  `import ... from '../../relative/path'`, `join|resolve(import.meta.dirname, 'a', '..', 'b')`,
  and `${process.cwd()}/../relative` (the working directory is apps/web). A path that stays inside
  apps/web is the test's own.

A file counts as covered when one of the job's globs matches it; a directory when one matches a
file inside it. A path that does not exist is skipped (a temporary file the test writes).
"""

import ast
import posixpath
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ".github/workflows/ci.yml"

Parts = tuple[str, ...]
EXISTENCE_CHECKS = frozenset({"is_file", "is_dir", "exists"})


# --- Reads found in Python tests ----------------------------------------------------------------


def _normalize(parts: list[str]) -> Parts | None:
    """Apply `..` and `.`; None if the path climbs above the repository root."""
    out: list[str] = []
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not out:
                return None
            out.pop()
        else:
            out.append(part)
    return tuple(out)


class _PathEvaluator:
    """Evaluates the path expressions a test builds, to repository-relative parts."""

    def __init__(self, file_parts: Parts, names: dict[str, set[Parts]]) -> None:
        self.file_parts = file_parts
        self.names = names

    def values(self, node: ast.expr) -> set[Parts]:
        if isinstance(node, ast.Name):
            return set(self.names.get(node.id, ()))
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Name)
                and func.id == "Path"
                and len(node.args) == 1
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "__file__"
            ):
                return {self.file_parts}
            if isinstance(func, ast.Attribute) and func.attr in ("resolve", "absolute"):
                return self.values(func.value)
            return set()
        if isinstance(node, ast.Attribute) and node.attr == "parent":
            return {p[:-1] for p in self.values(node.value) if p}
        if isinstance(node, ast.Subscript):
            base, index = node.value, node.slice
            if (
                isinstance(base, ast.Attribute)
                and base.attr == "parents"
                and isinstance(index, ast.Constant)
                and isinstance(index.value, int)
            ):
                return {
                    p[: -(index.value + 1)] for p in self.values(base.value) if len(p) > index.value
                }
            return set()
        if (
            isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Div)
            and isinstance(node.right, ast.Constant)
            and isinstance(node.right.value, str)
        ):
            joined = (
                _normalize([*p, *node.right.value.split("/")]) for p in self.values(node.left)
            )
            return {p for p in joined if p is not None}
        return set()


def python_reads(source: str, file_parts: Parts, names: dict[str, set[Parts]]) -> set[Parts]:
    """Every maximal path expression in `source` that resolves, other than the repository root."""
    tree = ast.parse(source)
    evaluator = _PathEvaluator(file_parts, names)
    found: set[Parts] = set()

    def visit(node: ast.AST, suppress: bool) -> None:
        # `suppress`: this node is part of a larger path expression, or the receiver of an
        # existence check, so it is not a read of its own.
        is_division = isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
        if is_division and not suppress and isinstance(node, ast.expr):
            found.update(evaluator.values(node))
        existence_check = (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in EXISTENCE_CHECKS
        )
        for child in ast.iter_child_nodes(node):
            visit(
                child,
                is_division
                or (existence_check and child is getattr(node, "func", None))
                or (suppress and isinstance(node, ast.Attribute)),
            )

    visit(tree, False)
    return found


def python_names(source: str, file_parts: Parts, names: dict[str, set[Parts]]) -> None:
    """Add to `names` each `NAME = <path expression>` this file assigns (any scope)."""
    evaluator = _PathEvaluator(file_parts, names)
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                names.setdefault(target.id, set()).update(evaluator.values(node.value))


def module_level_names(source: str) -> set[str]:
    return {
        node.targets[0].id
        for node in ast.parse(source).body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    }


def imported_names(source: str) -> set[str]:
    return {
        alias.asname or alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }


def api_test_reads(root: Path) -> set[Parts]:
    """A name means what the file itself assigns it or, if the file imports it, what another test
    file assigns it at module level. (A `root` parameter in one test is not another's `root`.)"""
    files = sorted((root / "apps/api/tests").rglob("*.py"))
    sources = {f: (f.read_text(encoding="utf-8"), tuple(f.relative_to(root).parts)) for f in files}
    exported: dict[str, set[Parts]] = {}
    per_file: dict[Path, dict[str, set[Parts]]] = {f: {} for f in files}
    for _ in range(3):  # a name may be built from one a later file defines
        for f, (text, parts) in sources.items():
            local = per_file[f]
            for name in imported_names(text):
                if name in exported:
                    local.setdefault(name, set()).update(exported[name])
            python_names(text, parts, local)
            for name in module_level_names(text):
                exported.setdefault(name, set()).update(local.get(name, ()))
    reads: set[Parts] = set()
    for f, (text, parts) in sources.items():
        reads |= python_reads(text, parts, per_file[f])
    return reads


# --- Reads found in web tests -------------------------------------------------------------------

_RELATIVE_IMPORT = re.compile(r"""(?:from|import|require\()\s*['"](\.{1,2}/[^'"]+)['"]""")
_DIRNAME_CALL = re.compile(
    r"""(?:join|resolve)\(\s*import\.meta\.dirname((?:\s*,\s*['"][^'"]*['"])*)\s*\)"""
)
_CWD_TEMPLATE = re.compile(r"""\$\{process\.cwd\(\)\}/(\.\.[^'"`]*)""")
_QUOTED = re.compile(r"""['"]([^'"]*)['"]""")
WEB_DIR: Parts = ("apps", "web")


def web_reads(text: str, file_parts: Parts) -> set[Parts]:
    directory = file_parts[:-1]
    found: set[Parts] = set()

    def add(base: Parts, relative: str) -> None:
        resolved = _normalize([*base, *relative.split("/")])
        if resolved:
            found.add(resolved)

    for match in _RELATIVE_IMPORT.finditer(text):
        add(directory, match.group(1))
    for match in _DIRNAME_CALL.finditer(text):
        add(directory, "/".join(_QUOTED.findall(match.group(1))))
    for match in _CWD_TEMPLATE.finditer(text):
        add(WEB_DIR, match.group(1))
    return found


def web_test_reads(root: Path) -> set[Parts]:
    """Reads by the Vitest unit tests (apps/web/src)."""
    base = root / "apps/web/src"
    files = [*base.rglob("*.test.ts"), *base.rglob("*.test.tsx"), *(base / "test").rglob("*.ts*")]
    reads: set[Parts] = set()
    for f in sorted(set(files)):
        reads |= web_reads(f.read_text(encoding="utf-8"), tuple(f.relative_to(root).parts))
    return reads


def e2e_test_reads(root: Path) -> set[Parts]:
    """Reads by the browser tests and their helpers (apps/web/e2e, not the captures)."""
    base = root / "apps/web/e2e"
    reads: set[Parts] = set()
    for f in sorted(base.rglob("*.ts")):
        relative = f.relative_to(base)
        if relative.parts[0] == "captures":
            continue
        reads |= web_reads(f.read_text(encoding="utf-8"), tuple(f.relative_to(root).parts))
    return reads


# --- The filters --------------------------------------------------------------------------------


def parse_filters(workflow: str) -> dict[str, list[str]]:
    """The globs of each filter in the `filters: |` block of the paths-filter step: a line
    `  name:` opens a filter and a line `- 'glob'` adds to it. Comments are skipped."""
    lines = workflow.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if re.match(r"\s*filters:\s*\|\s*$", line)), None
    )
    if start is None:
        raise ValueError("no `filters: |` block found in the workflow")
    indent = len(lines[start]) - len(lines[start].lstrip())
    filters: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if stripped and len(line) - len(line.lstrip()) <= indent:
            break  # the block ended
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith(":") and not stripped.startswith("-"):
            current = filters.setdefault(stripped[:-1], [])
        elif stripped.startswith("-") and current is not None:
            current.append(stripped[1:].strip().strip("'\""))
    return filters


def glob_matches(glob: str, path: str) -> bool:
    """paths-filter's matching, for the globs the workflow uses: `**` crosses folders, `*` and `?`
    do not cross a slash."""
    out = ""
    i = 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif glob.startswith("**", i):
            out += ".*"
            i += 2
        elif glob[i] == "*":
            out += "[^/]*"
            i += 1
        elif glob[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(glob[i])
            i += 1
    return re.fullmatch(out, path) is not None


def covered(path: str, globs: list[str], *, is_dir: bool) -> bool:
    probe = f"{path}/anything" if is_dir else path
    return any(glob_matches(g, probe) for g in globs)


# --- The check ----------------------------------------------------------------------------------

# (filter name, the app whose own paths are not outside reads, how to find that job's reads)
JOBS = (
    ("api", ("apps", "api"), api_test_reads),
    ("web", WEB_DIR, web_test_reads),
    ("e2e", WEB_DIR, e2e_test_reads),
)


def problems_in(root: Path, workflow: str) -> tuple[list[str], list[str]]:
    """(the problems, every outside read found as 'job: path')."""
    filters = parse_filters(workflow)
    problems: list[str] = []
    listing: list[str] = []
    for job, own, find in JOBS:
        if job not in filters:
            problems.append(f"the `{job}` filter is missing from {CI_WORKFLOW}")
            continue
        for parts in sorted(find(root)):
            if parts[: len(own)] == own:
                continue
            target = root.joinpath(*parts)
            if not target.exists():
                continue
            path = posixpath.join(*parts)
            listing.append(f"{job}: {path}")
            if not covered(path, filters[job], is_dir=target.is_dir()):
                problems.append(
                    f"a {job} test reads {path}, which the `{job}` filter in {CI_WORKFLOW} omits:"
                    f" a change to it would skip the {job} job"
                )
    return problems, listing


def main(root: Path = REPO, argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    workflow = (root / CI_WORKFLOW).read_text(encoding="utf-8")
    problems, listing = problems_in(root, workflow)
    if "--list" in arguments:
        print("\n".join(listing))
    if problems:
        print("check_path_filters FAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"{len(listing)} reads outside the tests' own apps, all inside their job's filter.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
