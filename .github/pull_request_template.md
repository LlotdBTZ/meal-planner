## What and why

<!-- What changes, and why. Link the plan task or issue: "Closes #123" -->

## How it was tested

- [ ] New behaviour has tests (bug fixes start with a failing test)
- [ ] `pytest --cov`, `ruff check`, `ruff format --check`, `mypy` pass locally
- [ ] Manually checked (describe; screenshots for UI changes)

## Checklist

- [ ] Matches the design doc (or the design doc is updated in this PR)
- [ ] `CHANGELOG.md` updated under `[Unreleased]` for user-visible changes
- [ ] README / docs updated if user-facing or deployment changed
- [ ] Dependency changes: `requirements.txt` regenerated (see CLAUDE.md)
- [ ] Schema changes are additive migrations (rollback must keep working)
- [ ] No secrets, `.env`, cookies, or state files; nothing personal (this repo is public)
