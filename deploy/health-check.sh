#!/usr/bin/env bash
# Is the app up *and running the release we just deployed*?
#
#   deploy/health-check.sh <health-url> <vX.Y.Z tag> [tries]
#
# Polls <health-url> once a second, up to [tries] times (default 30). Passes
# when it returns HTTP 2xx and, from v0.4.0 on, reports "version": "X.Y.Z"
# matching the tag, so a restart that left the old code running doesn't count
# as a successful deploy. Older releases don't report a version (update.sh
# still deploys them when rolling back), so for those a 2xx is enough.
#
# Exit: 0 up, 1 not up (reason on stderr), 2 bad arguments.
# Used by update.sh; separate so tests can run it against a local server.
set -euo pipefail

FIRST_VERSIONED=v0.4.0  # first release whose /health reports its version

url=${1:-}
tag=${2:-}
tries=${3:-30}
if [[ -z $url || ! $tag =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ || ! $tries =~ ^[1-9][0-9]*$ ]]; then
    echo "usage: $0 <health-url> <vX.Y.Z tag> [tries]" >&2
    exit 2
fi
want=${tag#v}

# Version-aware comparison (v0.10.0 is newer than v0.4.0).
reports_version() { [[ $(printf '%s\n' "$FIRST_VERSIONED" "$tag" | sort -V | head -n1) == "$FIRST_VERSIONED" ]]; }

why="no successful response from $url"
for ((i = 1; i <= tries; i++)); do
    (( i > 1 )) && sleep 1
    body=$(curl -fsS --max-time 5 "$url" 2>/dev/null) || { why="no successful response from $url"; continue; }
    # /health is our own small JSON object; pull out "version" without needing jq.
    got=$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' <<<"$body")
    if [[ -n $got ]]; then
        [[ $got == "$want" ]] && exit 0
        why="expected version $want, /health reports $got"
    elif reports_version; then
        why="expected version $want, /health reports no version"
    else
        exit 0  # pre-$FIRST_VERSIONED release: a 2xx is all it can tell us
    fi
done

echo "health check failed after $tries tries: $why" >&2
exit 1
