# Changelog

All notable changes to this project are noted here. Versions follow
[Semantic Versioning](https://semver.org/); releases are tagged `vX.Y.Z` on `main`.

## [Unreleased]

### Fixed

- Login redirects refuse targets containing control characters; browsers drop tabs and
  newlines, so `/<tab>/evil.example` could redirect off-site.
- The recipe editor ignores file uploads in text fields instead of failing with a server
  error.
- The jobs API only returns error messages written for the user, never internal details.
- The extraction worker closes its database connection on shutdown, and the editor closes
  uploaded files after reading the form.

### Changed

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

[Unreleased]: https://github.com/LlotdBTZ/meal-planner/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/LlotdBTZ/meal-planner/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/LlotdBTZ/meal-planner/releases/tag/v0.1.0
