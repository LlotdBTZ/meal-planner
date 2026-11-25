# CLAUDE.md

Guidance for Claude (and any contributor) working in this repo.

## Project

Meal Planner: a personal, self-hosted web app. Paste a TikTok/Instagram/blog
link → recipe name + ingredients are extracted → user reviews and saves →
pick meals for the week → combined grocery list → copy into iPhone Notes.

- Design (source of truth for *what*): `docs/superpowers/specs/2026-11-24-meal-planner-design.md`
- Build plan (source of truth for *order*): `docs/superpowers/plans/2026-11-24-meal-planner-plan.md`
- Stack: Python ≥3.11, FastAPI, Jinja2 server-rendered pages, vanilla JS,
  SQLite (stdlib `sqlite3`), yt-dlp, Claude API. No frontend build step.
- Runs on a Raspberry Pi 3 B+ (1GB RAM) next to Pi-hole: port 8080,
  systemd, no Docker. Keep memory and dependencies lean.
- GitHub repo settings are managed by Terraform in `infra/github/`.

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'   # setup
.venv/bin/pytest -q                                           # tests
.venv/bin/ruff check . && .venv/bin/ruff format --check .     # lint + format check
.venv/bin/ruff format .                                       # auto-format
.venv/bin/python -m app.main                                  # run locally (http://localhost:8080)
terraform -chdir=infra/github fmt -check && terraform -chdir=infra/github validate
```

## Development lifecycle

### 1. Plan before building
- New features or behaviour changes start from the design doc. If a change
  contradicts the design, update the design (in the same PR) and get the
  owner's approval first. Don't silently drift.
- Large work is broken into plan tasks; one task ≈ one PR.

### 2. Branches
- `main` is always deployable. Never commit directly to `main`.
- Branch per change: `feat/<short-name>`, `fix/<short-name>`,
  `chore/<short-name>`, `docs/<short-name>`, `infra/<short-name>`.
- Keep branches short-lived; rebase on `main` before opening/merging a PR.

### 3. Commits
- Conventional Commits: `feat:`, `fix:`, `test:`, `refactor:`, `docs:`,
  `chore:`, `ci:`, `infra:`. Imperative mood, ≤72-char subject.
- Small, focused commits; each one should leave tests passing.

### 4. Tests (test-driven where practical)
- Pure logic (units/combining, list text, parsing, DB, auth) is written
  test-first: failing test → minimal code → refactor.
- Network-facing code (yt-dlp, Claude, transcription, HTTP fetch) sits behind
  small interfaces; tests use fakes or recorded fixtures. **Tests never hit
  the network or real APIs** and never need API keys.
- Every bug fix starts with a test that reproduces the bug.
- Don't weaken or delete a test to make it pass; fix the code or explain why
  the test was wrong in the PR.

### 5. Pull requests
- Every change lands through a PR into `main`, squash-merged.
- PR description: what and why, link to the plan task / issue, how it was
  tested, screenshots for UI changes, and any follow-ups.
- CI must be green (tests, lint, format, shellcheck, terraform validate,
  gitleaks) before merge; branch protection on `main` enforces it.
- Review the diff yourself before asking for review; for non-trivial
  changes, request a code review (e.g. `/code-review`).

### 6. Definition of done
- Behaviour matches the design; tests cover the new behaviour and pass.
- `ruff check` and `ruff format --check` clean.
- Docs updated (README for anything user-facing or deployment-related;
  design doc if behaviour changed).
- No TODOs without a linked issue.

### 7. Releases and deployment
- Version in `pyproject.toml` follows SemVer; tag releases `vX.Y.Z` on `main`
  and note changes in `CHANGELOG.md`.
- Deploy to the Pi only from a tagged `main` commit using `deploy/update.sh`.
- Database schema changes go through numbered migrations in `app/db.py`
  (`PRAGMA user_version`). Never edit a migration that has shipped; add a new one.
  Migrations must be safe on existing data (nightly backups exist, but don't rely on them).

## Security and secrets
- **The repo is public.** Treat every commit, PR, issue, and CI log as
  published forever. Use obviously fake values in tests and examples.
- If a secret is ever pushed, rotate it first; rewriting history is not enough.
- Secrets live only in `.env` on the Pi (see `.env.example`) and in the
  environment for Terraform (`GITHUB_TOKEN`). Never commit `.env`,
  `cookies.txt`, `*.tfstate`, `*.tfvars` with secrets, or API keys.
- Validate and escape all user input; Jinja autoescape stays on.
- Redirect targets (e.g. login `next=`) must be local paths only.
- Pin dependency minimum versions; review dependency bumps in their own PR.
- GitHub Actions are pinned to full commit SHAs (Dependabot bumps them).
  Workflows get read-only tokens by default; never use `pull_request_target`.
- yt-dlp is the exception: it auto-updates weekly on the Pi because sites
  change often.

## Code conventions
- Type hints on public functions; `from __future__ import annotations`.
- Keep modules small and single-purpose (see layout in the plan).
- Stdlib first; add a dependency only when it clearly earns its RAM on a Pi 3.
- User-facing errors are plain-English messages, never stack traces.

## Claude-specific
- Read the design and plan before starting a task; say which plan task
  you're on.
- Don't commit, push, or open PRs unless the owner asked for it in this session.
- When using the Claude API in app code, load the `claude-api` skill first to
  confirm model IDs and API shape.
