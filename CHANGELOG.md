# Changelog

All notable changes to this project are noted here. Versions follow
[Semantic Versioning](https://semver.org/); releases are tagged `vX.Y.Z` on `main`.

## [Unreleased]

## [0.5.0] - 2026-11-24

### Changed

- Deploys check that `/health` reports the version just deployed, not just that it
  answers, so a restart that left the old code running rolls back instead of passing.
  Releases before 0.4.0 (which don't report a version) still only need to answer. The
  auto-deploy timer runs the *deployed* `update.sh`, so this takes effect for deploys
  made after the release containing it is running.

## [0.4.0] - 2026-11-24

### Added

- `/health` reports the running version (`{"status": "ok", "version": "X.Y.Z"}`), so a
  deploy can be confirmed from any device on the network without SSH.

## [0.3.1] - 2026-11-24

CI, supply-chain, and developer-tooling hardening. The app, its runtime dependencies, and
the deploy scripts are unchanged from 0.3.0.

### Added

- A versioned pre-commit hook (`scripts/git-hooks/pre-commit`) that blocks commits
  containing secrets (gitleaks) and runs ruff on staged Python files. Install it with the
  `ln -sf` line in the README's Development section.

### Changed

- Dev tools and the build backend are locked with hashes in `requirements-dev.txt`, and
  `scripts/lock-deps.sh` regenerates both lock files. Dev setup in the README changed.

### Security

- CI audits the locked dependencies (runtime and dev tools) with pip-audit on every PR
  and push, and weekly to catch newly published advisories. It's a required check on `main`.
- Release tags (`v*`) are protected by repository rulesets: once pushed they can't be
  moved or deleted, and only repo admins can create them.
- CI checks the GitHub Actions workflows with zizmor (security) and actionlint
  (correctness); both are required checks on `main`.
- Dependabot waits 7 days before proposing a new dependency or action release, so a
  compromised release is usually caught first. Security updates aren't delayed.
- OpenSSF Scorecard grades the repo's supply-chain practices weekly and on every push to
  `main`, with results in GitHub code scanning.

## [0.3.0] - 2026-11-24

### Added

- MIT license, a security policy with private vulnerability reporting, and issue templates.
- `install.sh` warns when the kernel's memory controller is off (the default on Raspberry
  Pi), since the app's memory cap can't work without it.

### Fixed

- Login redirects refuse targets containing control characters; browsers drop tabs and
  newlines, so `/<tab>/evil.example` could redirect off-site.
- The recipe editor ignores file uploads in text fields instead of failing with a server
  error.
- The jobs API only returns error messages written for the user, never internal details.
- The extraction worker closes its database connection on shutdown, and the editor closes
  uploaded files after reading the form.

### Changed

- Deploys are reproducible: `requirements.txt` locks exact runtime versions with hashes.
  CI tests those versions and the Pi installs exactly them (yt-dlp still self-updates).
- CI enforces type checking (mypy), a 95% test-coverage floor, and security lint (ruff `S`
  rules). Unclosed files or connections in tests now fail the run.

## [0.2.0] - 2026-11-24

### Added

- Releases deploy themselves: the Pi checks for a new `vX.Y.Z` tag every 15 minutes,
  deploys it, and rolls back to the previous release if the health check fails.
- `deploy/update.sh` keeps a skip list: releases that failed, and newer releases after a
  manual rollback, aren't deployed automatically until you deploy them by hand.
- CI for a public repo: gitleaks secret scanning, shellcheck, CodeQL, Dependabot, actions
  pinned to commit SHAs, and a release workflow that publishes GitHub Releases from this
  file.

### Changed

- The repository is public. Secret scanning and push protection are on, and `main` is
  protected (PR, linear history, required checks).

## [0.1.0] - 2026-11-24

First release.

### Added

- Paste or share a TikTok, Instagram, or blog link (or paste a caption) to pull out the
  recipe name and ingredients: caption first, then spoken audio via speech-to-text, and
  schema.org recipe data on blog pages. Runs as a background job with live progress.
- Review and edit screen before saving, with warnings and the original ingredient text.
- Recipe list with search, recipe pages, editing, and deleting.
- This week: pick meals and get one grocery list grouped by aisle, with amounts converted
  and added up, and "already have it" ticks.
- Copy list as plain text for iPhone Notes, with a fallback for plain HTTP.
- Single-password login with a one-year session cookie and a failed-login limit.
- Add to Home Screen: web app manifest, icons, and Apple meta tags.
- Raspberry Pi deployment: `install.sh`, tagged-release `update.sh` with backup and health
  check, a memory-capped systemd service, nightly database backups (14 kept), and weekly
  yt-dlp updates.
- README covering setup, the iOS share-sheet Shortcut, Instagram cookies, optional
  Tailscale HTTPS, and backup and restore.

[Unreleased]: https://github.com/LlotdBTZ/meal-planner/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/LlotdBTZ/meal-planner/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/LlotdBTZ/meal-planner/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/LlotdBTZ/meal-planner/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/LlotdBTZ/meal-planner/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/LlotdBTZ/meal-planner/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/LlotdBTZ/meal-planner/releases/tag/v0.1.0
