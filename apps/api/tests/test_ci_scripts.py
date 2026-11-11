"""The two CI check scripts: one gitleaks version, and path filters that cover what tests read.

`scripts/check_tool_versions.py` and `scripts/check_path_filters.py` run in the Workflows job and
in `make check-workflows`. These tests prove their judgment on small fake trees, and that the real
repository passes both (the same run CI does). No Docker, no network, no database.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[3]


def load(name: str) -> ModuleType:
    path = REPO / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


versions = load("check_tool_versions")
filters = load("check_path_filters")


# --- check_tool_versions ------------------------------------------------------------------------


def write_versions_tree(
    root: Path,
    *,
    workflow: str,
    makefile: str,
    hook: str,
    ruff_hook: str = "0.17.3",
    ruff_lock: str = "0.17.3",
) -> None:
    (root / ".github/workflows").mkdir(parents=True)
    (root / ".github/workflows/security.yml").write_text(
        f"jobs:\n  s:\n    steps:\n      - env:\n          GITLEAKS_VERSION: {workflow}\n"
    )
    (root / "Makefile").write_text(f"GITLEAKS := ghcr.io/gitleaks/gitleaks:v{makefile}\n")
    (root / ".pre-commit-config.yaml").write_text(
        "repos:\n  - repo: https://github.com/astral-sh/ruff-pre-commit\n"
        f"    rev: v{ruff_hook}\n    hooks:\n      - id: ruff-check\n"
        "  - repo: https://github.com/gitleaks/gitleaks\n"
        f"    rev: v{hook}\n    hooks:\n      - id: gitleaks\n"
    )
    (root / "apps/api").mkdir(parents=True)
    (root / "apps/api/uv.lock").write_text(
        f'[[package]]\nname = "ruff"\nversion = "{ruff_lock}"\nsource = {{ registry = "x" }}\n'
    )


def test_matching_versions_pass(tmp_path: Path) -> None:
    write_versions_tree(tmp_path, workflow="8.30.1", makefile="8.30.1", hook="8.30.1")
    assert versions.main(tmp_path) == 0


@pytest.mark.parametrize("odd", ["workflow", "makefile", "hook"])
def test_one_different_version_fails_and_names_every_file(
    tmp_path: Path, odd: str, capsys: pytest.CaptureFixture[str]
) -> None:
    values = {"workflow": "8.30.1", "makefile": "8.30.1", "hook": "8.30.1"}
    values[odd] = "8.31.0"
    write_versions_tree(tmp_path, **values)
    assert versions.main(tmp_path) == 1
    output = capsys.readouterr().out
    for name in (".github/workflows/security.yml", "Makefile", ".pre-commit-config.yaml"):
        assert name in output
    assert "8.31.0" in output


def test_a_ruff_hook_that_differs_from_the_lockfile_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_versions_tree(
        tmp_path, workflow="8.30.1", makefile="8.30.1", hook="8.30.1", ruff_hook="0.18.0"
    )
    assert versions.main(tmp_path) == 1
    output = capsys.readouterr().out
    assert "ruff versions differ" in output
    assert "apps/api/uv.lock has 0.17.3" in output
    assert ".pre-commit-config.yaml has 0.18.0" in output


def test_a_file_that_names_no_version_fails() -> None:
    problems = versions.problems_in({"Makefile": None, "a.yml": "8.30.1"}, "gitleaks")
    assert problems == ["Makefile: no gitleaks version found"]


def test_each_pattern_reads_its_file() -> None:
    texts = {
        ".github/workflows/security.yml": "        env:\n          GITLEAKS_VERSION: 8.30.1\n",
        "Makefile": "GITLEAKS := ghcr.io/gitleaks/gitleaks:v8.30.1\n",
        ".pre-commit-config.yaml": "  - repo: https://github.com/gitleaks/gitleaks\n"
        "    rev: v8.30.1\n",
    }
    for file, _name, pattern in versions.GITLEAKS_SOURCES:
        assert versions.version_in(texts[file], pattern) == "8.30.1"


def test_the_real_repository_has_one_version_of_each_tool() -> None:
    assert versions.main(REPO) == 0


# --- check_path_filters: the filters ------------------------------------------------------------

WORKFLOW = """\
jobs:
  changes:
    steps:
      - uses: dorny/paths-filter@abc
        with:
          base: ${{ x }}
          filters: |
            api:
              - 'apps/api/**'
              # a comment
              - 'handbook/**'
              - 'Makefile'
            web:
              - 'apps/web/**'
              - "docs/design/**"
            e2e:
              - 'apps/web/**'
              - 'apps/api/**'
  api:
    needs: changes
"""


def test_the_filters_block_is_parsed_by_name() -> None:
    assert filters.parse_filters(WORKFLOW) == {
        "api": ["apps/api/**", "handbook/**", "Makefile"],
        "web": ["apps/web/**", "docs/design/**"],
        "e2e": ["apps/web/**", "apps/api/**"],
    }


def test_a_workflow_without_filters_is_an_error() -> None:
    with pytest.raises(ValueError, match="filters"):
        filters.parse_filters("jobs: {}\n")


@pytest.mark.parametrize(
    ("glob", "path", "matches"),
    [
        ("apps/api/**", "apps/api/tests/test_x.py", True),
        ("apps/api/**", "apps/web/x.ts", False),
        ("Makefile", "Makefile", True),
        ("Makefile", "docs/Makefile", False),
        ("scripts/*", "scripts/a.py", True),
        ("scripts/*", "scripts/image/a.py", False),
        ("**/*.md", "README.md", True),
        ("**/*.md", "docs/a/b.md", True),
        ("docs/specs/a.md", "docs/specs/a.md", True),
    ],
)
def test_globs_match_like_paths_filter(glob: str, path: str, matches: bool) -> None:
    assert filters.glob_matches(glob, path) is matches


# --- check_path_filters: the reads --------------------------------------------------------------


def write(root: Path, relative: str, text: str = "") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def fake_repo(root: Path) -> None:
    """A tree with the files the fake tests read, a CI workflow, and the three test folders."""
    for relative in (
        "handbook/sections/a.md",
        "docs/design/tokens.md",
        "docs/specs/s.md",
        "Makefile",
        "apps/api/app/prompt.md",
        "apps/web/index.html",
    ):
        write(root, relative)
    write(root, ".github/workflows/ci.yml", WORKFLOW)


def problems_for(root: Path) -> list[str]:
    problems: list[str] = filters.problems_in(
        root, (root / ".github/workflows/ci.yml").read_text()
    )[0]
    return problems


def test_a_python_test_reading_a_covered_path_passes(tmp_path: Path) -> None:
    fake_repo(tmp_path)
    write(
        tmp_path,
        "apps/api/tests/test_a.py",
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[3]\n"
        "def test_x():\n"
        "    (ROOT / 'handbook' / 'sections' / 'a.md').read_text()\n"
        "    (ROOT / 'Makefile').read_text()\n",
    )
    assert problems_for(tmp_path) == []


def test_a_python_test_reading_an_uncovered_path_fails_naming_it(tmp_path: Path) -> None:
    fake_repo(tmp_path)
    write(
        tmp_path,
        "apps/api/tests/test_a.py",
        "from pathlib import Path\n"
        "def test_x():\n"
        "    root = Path(__file__).resolve().parents[3]\n"
        "    (root / 'docs/specs/s.md').read_text()\n",
    )
    problems = problems_for(tmp_path)
    assert len(problems) == 1
    assert "docs/specs/s.md" in problems[0]
    assert "`api` filter" in problems[0]


def test_a_name_imported_from_another_test_file_is_followed(tmp_path: Path) -> None:
    fake_repo(tmp_path)
    write(
        tmp_path,
        "apps/api/tests/helper.py",
        "from pathlib import Path\nEVAL_DIR = Path(__file__).resolve().parents[3] / 'docs'\n",
    )
    write(
        tmp_path,
        "apps/api/tests/test_a.py",
        "from helper import EVAL_DIR\n"
        "def test_x():\n"
        "    (EVAL_DIR.parent / 'docs' / 'specs' / 's.md').read_text()\n",
    )
    assert any("docs/specs/s.md" in p for p in problems_for(tmp_path))


def test_a_directory_is_covered_when_the_filter_covers_files_inside(tmp_path: Path) -> None:
    fake_repo(tmp_path)
    write(
        tmp_path,
        "apps/api/tests/test_a.py",
        "from pathlib import Path\n"
        "HANDBOOK = Path(__file__).parents[3] / 'handbook'\n"
        "DESIGN = Path(__file__).parents[3] / 'docs' / 'design'\n",
    )
    problems = problems_for(tmp_path)
    assert len(problems) == 1
    assert "docs/design" in problems[0]


def test_paths_inside_the_tests_own_app_and_temporary_files_are_not_reads(tmp_path: Path) -> None:
    fake_repo(tmp_path)
    write(
        tmp_path,
        "apps/api/tests/test_a.py",
        "from pathlib import Path\n"
        "API = Path(__file__).resolve().parents[1]\n"
        "FIXTURE = Path(__file__).parent / 'fixtures' / 'handbook'\n"
        "def test_x(tmp_path):\n"
        "    (tmp_path / 'docs').write_text('')\n"
        "    (API / 'migrations').is_dir()\n",
    )
    assert problems_for(tmp_path) == []


def test_an_existence_check_alone_is_not_a_read(tmp_path: Path) -> None:
    fake_repo(tmp_path)
    write(
        tmp_path,
        "apps/api/tests/test_a.py",
        "from pathlib import Path\n"
        "def test_x():\n"
        "    root = Path(__file__).resolve().parents[3]\n"
        "    assert (root / 'docs' / 'specs' / 's.md').is_file()\n",
    )
    assert problems_for(tmp_path) == []


def test_a_web_test_is_checked_against_the_web_filter(tmp_path: Path) -> None:
    fake_repo(tmp_path)
    write(
        tmp_path,
        "apps/web/src/styles/tokens.test.ts",
        "import { join } from 'node:path'\n"
        "const designDir = join(import.meta.dirname, '../../../../docs/design')\n"
        "const own = join(import.meta.dirname, '..', '..', 'index.html')\n"
        "import cases from '../../../../handbook/sections/a.md'\n"
        "const seed = `${process.cwd()}/../api/app/prompt.md`\n",
    )
    problems = problems_for(tmp_path)
    # docs/design is in the web filter; handbook and apps/api are not.
    assert len(problems) == 2
    assert any("handbook/sections/a.md" in p for p in problems)
    assert any("apps/api/app/prompt.md" in p for p in problems)
    assert all("`web` filter" in p for p in problems)


def test_a_browser_test_is_checked_against_the_e2e_filter_and_captures_are_skipped(
    tmp_path: Path,
) -> None:
    fake_repo(tmp_path)
    write(
        tmp_path,
        "apps/web/e2e/a.spec.ts",
        "const prompt = resolve(import.meta.dirname, '../../api/app/prompt.md')\n",
    )
    write(
        tmp_path,
        "apps/web/e2e/captures/c.spec.ts",
        "const x = resolve(import.meta.dirname, '../../../../docs/specs/s.md')\n",
    )
    assert problems_for(tmp_path) == []


def test_a_workflow_missing_a_job_filter_is_reported(tmp_path: Path) -> None:
    fake_repo(tmp_path)
    workflow = WORKFLOW.replace("            e2e:\n", "            other:\n")
    problems, _listing = filters.problems_in(tmp_path, workflow)
    assert any("`e2e` filter is missing" in p for p in problems)


def test_the_real_repository_filters_cover_every_read() -> None:
    problems, listing = filters.problems_in(REPO, (REPO / filters.CI_WORKFLOW).read_text())
    assert problems == []
    # The scan found the reads this check exists for, so an empty one cannot pass for a clean one.
    assert any(line.startswith("api: handbook") for line in listing)
    assert any(line.startswith("web: docs/design") for line in listing)
    assert any(line.startswith("e2e: apps/api") for line in listing)
