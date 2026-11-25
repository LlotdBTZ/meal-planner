# Changelog

All notable changes to this project are noted here. Versions follow
[Semantic Versioning](https://semver.org/); releases are tagged `vX.Y.Z` on `main`.

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

[0.1.0]: https://github.com/LlotdBTZ/meal-planner/releases/tag/v0.1.0
