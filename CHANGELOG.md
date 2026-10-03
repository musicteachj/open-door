# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This is a development log first and a release log second. Entries accumulate under
**Unreleased** on `dev`, and each release pull request from `dev` into `main` cuts them into a
version (`0.x.y` while the app is being built, `1.0.0` when it is complete).

## [Unreleased]

### Added

- The repository: README, license notice, `.gitignore`, and this changelog.
- **The plan, before any code** (planning). The approved initial plan is kept verbatim and frozen in
  `docs/plans/`. `docs/ROADMAP.md` is the living plan, with a status table for all ten phases. The
  design spec in `docs/specs/` records each decision and the reason for it. Also added:
  - `docs/WHAT-THIS-IS-NOT.md`, which says what the app and its assistant will never do.
  - Six decision records in `docs/adr/`.
  - `CLAUDE.md`, the project rules.
- **The Claude Design brief and handoff format** (planning). `docs/design/BRIEF.md` can be pasted
  into Claude Design to start the design system and screens. The rest of `docs/design/` defines how
  designs come back: tokens, a component inventory, and a per-screen `notes.md` with acceptance
  criteria.
- The README now states the seven rules the assistant never breaks and links to every document.
- **A rule that commits and pull requests must be human readable** (planning): plain-language
  subjects, short explanations of what changed and why, and a standard four-part PR description.
- **The API foundation** (Phase 0, stage 1). A FastAPI backend with a health check at
  `/api/v1/health` that says whether the API can reach its database. Settings are checked at
  startup, so a missing or malformed value stops the server instead of failing later. Every
  response carries a request ID that also appears in the logs, errors come back in the standard
  problem-details format without leaking internal details, and logs are one JSON object per
  line. Also added:
  - A development Postgres with pgvector in Docker, and the first database migration, which turns
    on the vector extension for handbook search. New migrations come out already linted and
    formatted.
  - Integration tests that run against the real database.
  - An export of the API's OpenAPI schema to `apps/web/openapi.json`, which the web app's client
    will be generated from. A check fails if the file falls out of date.
  - A `Makefile` for the everyday commands: `make db`, `make migrate`, `make dev-api`,
    `make openapi`, and `make check-api`, which runs every API check.

  Review findings deliberately left for later phases are recorded in `docs/BACKLOG.md`.

### Changed

- **The pre-PR code review covers the whole branch** (project rules). `/code-review medium` now
  reviews everything the pull request will contain, measured against its base branch, not just
  the uncommitted changes. That closes a gap where a commit already on the branch could go
  unreviewed.
