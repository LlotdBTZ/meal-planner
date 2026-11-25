#!/usr/bin/env bash
# Regenerate the hash-locked dependency files from pyproject.toml.
#   requirements.txt      runtime deps, exactly what the Pi installs
#   requirements-dev.txt  runtime + dev tools for CI and local dev; built with
#                         requirements.txt as a constraint so shared versions match
# yt-dlp is left out of both: it auto-updates on the Pi (see CLAUDE.md).
#
# Usage: scripts/lock-deps.sh [--upgrade]   (--upgrade bumps everything)
# CI runs this and fails if either file changes.
set -euo pipefail

cd "$(dirname "$0")/.."

uv=uv
[[ -x .venv/bin/uv ]] && uv=.venv/bin/uv

common=(--universal --python-version 3.11 --generate-hashes --no-emit-package yt-dlp -q)

"$uv" pip compile pyproject.toml "${common[@]}" "$@" -o requirements.txt
"$uv" pip compile pyproject.toml --extra dev -c requirements.txt "${common[@]}" "$@" \
    -o requirements-dev.txt
