"""The CI check scripts: one gitleaks version, path filters that cover what tests read, and the
npm audit with its dated exceptions.

`scripts/check_tool_versions.py` and `scripts/check_path_filters.py` run in the Workflows job and
in `make check-workflows`; `scripts/check_npm_audit.py` reads `npm audit --json` in the Security
workflow and in `make audit`. These tests prove their judgment on small fake inputs, and that the
real repository passes the first two (the same run CI does). No Docker, no network, no database.
"""

import importlib.util
import json
import re
import sys
from dataclasses import replace
from datetime import date
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
npm_audit = load("check_npm_audit")


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


# --- check_npm_audit ----------------------------------------------------------------------------

PICOMATCH = "GHSA-fc5q-39xc-vjpf"
ACCEPTED = (
    npm_audit.Accepted(
        advisory=PICOMATCH,
        package="picomatch",
        severity="high",
        until=date(2026, 12, 17),
        reason="no fixed release",
        build_only=False,
    ),
)
BUILD_ONLY = (
    npm_audit.Accepted(
        advisory=PICOMATCH,
        package="picomatch",
        severity="high",
        until=date(2026, 12, 17),
        reason="no fixed release; build tools only",
        build_only=True,
    ),
)
GONE = f"{PICOMATCH} (picomatch): no longer reported at high or critical; remove its exception"
BEFORE = date(2026, 12, 17)
AFTER = date(2026, 12, 18)


def advisory(package: str, ghsa: str, severity: str = "high") -> dict[str, object]:
    return {
        "source": 1,
        "name": package,
        "dependency": package,
        "title": f"{package} is vulnerable",
        "url": f"https://github.com/advisories/{ghsa}",
        "severity": severity,
        "range": "<=4.0.7",
    }


def report(*advisories: dict[str, object]) -> dict[str, object]:
    """An `npm audit --json` report: each advisory on its own package, and one package that only
    depends on the first (its `via` names the package, as npm writes it)."""
    vulnerabilities: dict[str, object] = {}
    for item in advisories:
        name = str(item["name"])
        vulnerabilities[name] = {
            "name": name,
            "severity": item["severity"],
            "via": [item],
            "nodes": [f"node_modules/{name}"],
        }
    if advisories:
        first = str(advisories[0]["name"])
        dependent = "a-tool-that-depends-on-it"
        vulnerabilities[dependent] = {
            "name": dependent,
            "severity": "high",
            "via": [first],
            "nodes": [f"node_modules/{dependent}"],
        }
    return recount({"auditReportVersion": 2, "vulnerabilities": vulnerabilities})


def recount(audit: dict[str, object]) -> dict[str, object]:
    """Set the report's own total to its entries, as npm writes it (after a test adds one)."""
    audit["metadata"] = {"vulnerabilities": {"total": len(audit["vulnerabilities"])}}  # type: ignore[arg-type]
    return audit


def test_a_clean_report_passes() -> None:
    assert npm_audit.problems_in(report(), BEFORE, ()) == ([], [])


def test_an_accepted_advisory_passes_until_its_date() -> None:
    problems, notes = npm_audit.problems_in(
        report(advisory("picomatch", PICOMATCH)), BEFORE, ACCEPTED
    )
    assert problems == []
    assert notes == [f"{PICOMATCH} (picomatch, high): accepted until 2026-12-17"]


def test_an_accepted_advisory_still_passes_on_its_last_day() -> None:
    problems, _notes = npm_audit.problems_in(
        report(advisory("picomatch", PICOMATCH)), date(2026, 12, 17), ACCEPTED
    )
    assert problems == []


def test_an_accepted_advisory_fails_after_its_date() -> None:
    problems, _notes = npm_audit.problems_in(
        report(advisory("picomatch", PICOMATCH)), AFTER, ACCEPTED
    )
    assert problems == [f"{PICOMATCH} (picomatch, high): its exception ended on 2026-12-17"]


def test_any_other_high_or_critical_advisory_fails_beside_an_accepted_one() -> None:
    problems, _notes = npm_audit.problems_in(
        report(
            advisory("picomatch", PICOMATCH),
            advisory("vite", "GHSA-aaaa-bbbb-cccc"),
            advisory("undici", "GHSA-dddd-eeee-ffff", "critical"),
        ),
        BEFORE,
        ACCEPTED,
    )
    assert problems == [
        "GHSA-aaaa-bbbb-cccc (vite, high): vite is vulnerable",
        "GHSA-dddd-eeee-ffff (undici, critical): undici is vulnerable",
    ]


def test_moderate_and_low_advisories_pass_as_before() -> None:
    advisories = (
        advisory("a", "GHSA-aaaa-aaaa-aaaa", "moderate"),
        advisory("b", "GHSA-bbbb-bbbb-bbbb", "low"),
    )
    assert npm_audit.problems_in(report(*advisories), BEFORE, ()) == ([], [])


def test_an_accepted_advisory_raised_above_its_accepted_severity_fails() -> None:
    problems, _notes = npm_audit.problems_in(
        report(advisory("picomatch", PICOMATCH, "critical")), BEFORE, ACCEPTED
    )
    assert problems == [
        f"{PICOMATCH} (picomatch, critical): accepted only at high; look at it again"
    ]


@pytest.mark.parametrize("severity", ["moderate", "low"])
def test_an_accepted_advisory_lowered_below_high_is_noted_for_removal(severity: str) -> None:
    assert npm_audit.problems_in(
        report(advisory("picomatch", PICOMATCH, severity)), BEFORE, ACCEPTED
    ) == (
        [],
        [GONE],
    )


def test_advisories_without_a_ghsa_link_or_number_stay_apart() -> None:
    first = advisory("vite", "x") | {"url": "", "source": None, "title": "first problem"}
    second = advisory("vite", "x") | {"url": "", "source": None, "title": "second problem"}
    both = report(first)
    both["vulnerabilities"]["vite"]["via"].append(second)  # type: ignore[index]
    problems, _notes = npm_audit.problems_in(both, BEFORE, ())
    assert problems == [
        "an npm advisory with no id (vite, high): first problem",
        "an npm advisory with no id (vite, high): second problem",
    ]


def test_an_advisory_lowered_but_still_failing_keeps_its_exception() -> None:
    at_critical = (replace(ACCEPTED[0], severity="critical"),)
    problems, notes = npm_audit.problems_in(
        report(advisory("picomatch", PICOMATCH, "high")), BEFORE, at_critical
    )
    assert problems == []
    assert notes == [f"{PICOMATCH} (picomatch, high): accepted until 2026-12-17"]


def lockfile(**dev: bool | None) -> dict[str, object]:
    packages: dict[str, object] = {"": {"name": "open-door-web"}}
    for name, flag in dev.items():
        packages[f"node_modules/{name}"] = {"version": "1.0.0"} | ({"dev": flag} if flag else {})
    return {"lockfileVersion": 3, "packages": packages}


def test_a_build_only_exception_passes_when_every_copy_is_a_dev_dependency() -> None:
    problems, _notes = npm_audit.problems_in(
        report(advisory("picomatch", PICOMATCH)), BEFORE, BUILD_ONLY, lockfile(picomatch=True)
    )
    assert problems == []


@pytest.mark.parametrize(
    ("lock", "said"),
    [
        (lockfile(picomatch=None), "node_modules/picomatch is not a dev dependency"),
        (lockfile(), "node_modules/picomatch is not in the lockfile"),
        (None, "no lockfile to check it against"),
    ],
)
def test_a_build_only_exception_fails_when_the_package_could_ship(
    lock: dict[str, object] | None, said: str
) -> None:
    problems, _notes = npm_audit.problems_in(
        report(advisory("picomatch", PICOMATCH)), BEFORE, BUILD_ONLY, lock
    )
    assert problems == [f"{PICOMATCH} (picomatch, high): accepted for build tools only, but {said}"]


def test_a_build_only_exception_needs_the_packages_install_paths() -> None:
    no_nodes = report(advisory("picomatch", PICOMATCH))
    del no_nodes["vulnerabilities"]["picomatch"]["nodes"]  # type: ignore[index]
    problems, _notes = npm_audit.problems_in(no_nodes, BEFORE, BUILD_ONLY, lockfile(picomatch=True))
    assert problems == [
        f"{PICOMATCH} (picomatch, high): accepted for build tools only, "
        "but the report names no install path for it"
    ]


@pytest.mark.parametrize("severity", ["", "urgent"])
def test_an_advisory_of_unknown_severity_fails(severity: str) -> None:
    problems, _notes = npm_audit.problems_in(
        report(advisory("vite", "GHSA-aaaa-bbbb-cccc", severity)), BEFORE, ()
    )
    assert problems == [f"GHSA-aaaa-bbbb-cccc (vite, {severity}): vite is vulnerable"]


def test_an_advisory_reported_twice_keeps_its_highest_severity() -> None:
    twice = report(advisory("picomatch", PICOMATCH))
    raised = advisory("picomatch", PICOMATCH, "critical")
    twice["vulnerabilities"]["fdir"] = {"name": "fdir", "via": [raised], "nodes": []}  # type: ignore[index]
    recount(twice)
    problems, _notes = npm_audit.problems_in(twice, BEFORE, ACCEPTED)
    assert problems == [
        f"{PICOMATCH} (picomatch, critical): accepted only at high; look at it again"
    ]


def test_an_accepted_advisory_on_another_package_fails() -> None:
    problems, _notes = npm_audit.problems_in(
        report(advisory("micromatch", PICOMATCH)), BEFORE, ACCEPTED
    )
    assert problems == [f"{PICOMATCH} (micromatch, high): micromatch is vulnerable"]


def test_an_advisory_reached_through_many_packages_is_named_once() -> None:
    item = advisory("picomatch", "GHSA-aaaa-bbbb-cccc")
    twice = report(item)
    twice["vulnerabilities"]["tinyglobby"] = {"name": "tinyglobby", "via": [item, "picomatch"]}  # type: ignore[index]
    recount(twice)
    problems, _notes = npm_audit.problems_in(twice, BEFORE, ACCEPTED)
    assert problems == ["GHSA-aaaa-bbbb-cccc (picomatch, high): picomatch is vulnerable"]


@pytest.mark.parametrize("today", [BEFORE, AFTER])
def test_an_exception_no_longer_needed_is_noted_not_failed(today: date) -> None:
    assert npm_audit.problems_in(report(), today, ACCEPTED) == (
        [],
        [GONE],
    )


@pytest.mark.parametrize(
    "broken",
    [
        {"error": {"code": "ENOTFOUND", "summary": "request to registry failed"}},
        {"auditReportVersion": 2},
        {"vulnerabilities": []},
        # Shaped like an empty audit, but not npm's: no report version.
        {"vulnerabilities": {}},
        {"auditReportVersion": 1, "vulnerabilities": {}},
        [],
        None,
        # Each of these carries npm's report version, so the shape checks are what refuse it.
        {"auditReportVersion": 2, "vulnerabilities": {"x": {"name": "x", "via": None}}},
        {"auditReportVersion": 2, "vulnerabilities": {"x": {"name": "x", "via": "picomatch"}}},
        # Cut short: vite came through esbuild, but esbuild's entry (and its advisory) is missing.
        {
            "auditReportVersion": 2,
            "vulnerabilities": {"vite": {"name": "vite", "via": ["esbuild"]}},
        },
    ],
)
def test_a_report_that_is_not_an_audit_fails(broken: object) -> None:
    problems, _notes = npm_audit.problems_in(broken, BEFORE, ACCEPTED)
    assert problems
    assert problems[0].startswith("The npm audit report is unusable")


@pytest.mark.parametrize(
    "metadata",
    [
        {"vulnerabilities": {"total": None}},
        {"vulnerabilities": {"total": 0}},
        {"vulnerabilities": {"total": 2}},
        {"vulnerabilities": {"total": "1"}},
        {"vulnerabilities": [1]},
        None,
    ],
)
def test_a_report_whose_total_disagrees_with_its_entries_fails(metadata: object) -> None:
    # One entry, quietly missing another the report counted (or no count at all).
    audit = report(advisory("picomatch", PICOMATCH))
    del audit["vulnerabilities"]["a-tool-that-depends-on-it"]  # type: ignore[attr-defined]
    audit["metadata"] = metadata
    problems, _notes = npm_audit.problems_in(audit, BEFORE, ACCEPTED)
    assert problems == [npm_audit.UNUSABLE]


def test_main_reads_the_report_and_lockfile_and_sets_the_exit_code(tmp_path: Path) -> None:
    clean, bad, garbled = tmp_path / "clean.json", tmp_path / "bad.json", tmp_path / "x.json"
    lock = tmp_path / "package-lock.json"
    clean.write_text(json.dumps(report()))
    bad.write_text(json.dumps(report(advisory("vite", "GHSA-aaaa-bbbb-cccc"))))
    garbled.write_text("npm ERR! network")
    lock.write_text(json.dumps(lockfile()))
    assert npm_audit.main([str(clean), str(lock)]) == 0
    assert npm_audit.main([str(bad), str(lock)]) == 1
    assert npm_audit.main([str(garbled), str(lock)]) == 1
    assert npm_audit.main([str(tmp_path / "missing.json"), str(lock)]) == 1
    assert npm_audit.main([str(clean), str(tmp_path / "missing-lock.json")]) == 1
    assert npm_audit.main([str(clean)]) == 2


def test_every_exception_names_an_advisory_a_package_a_date_and_a_reason() -> None:
    # An empty list is fine: the script then fails on every high or critical advisory, as
    # `npm audit --audit-level=high` did.
    for entry in npm_audit.ACCEPTED:
        assert re.fullmatch(r"GHSA(-[0-9a-z]{4}){3}", entry.advisory)
        assert entry.package
        assert entry.severity in npm_audit.FAILING
        assert isinstance(entry.build_only, bool)
        assert entry.reason.strip()
        assert isinstance(entry.until, date)


def test_ci_and_make_audit_both_go_through_the_script() -> None:
    workflow = (REPO / ".github/workflows/security.yml").read_text()
    makefile = (REPO / "Makefile").read_text()
    for text in (workflow, makefile):
        assert "scripts/check_npm_audit.py" in text
        assert "npm audit --json" in text
        assert "package-lock.json" in text
        assert "npm audit --audit-level" not in text
        assert "-gt 1" in text
        # An exit status above 1 isn't swallowed (npm's error reports are the script's to refuse).
        assert "|| true" not in text.split("npm audit --json")[1].split("\n")[0]
