#!/usr/bin/env bash
# Deploy a tagged release of Meal Planner on the Pi.
#
#   cd ~/meal-planner && git fetch --tags origin
#   sudo deploy/update.sh            # newest vX.Y.Z tag on main
#   sudo deploy/update.sh v0.2.0     # a specific tag (also how you roll back)
#
# Run from your git checkout. Only tags whose commit is on main are deployed.
set -euo pipefail

PREFIX=/opt/meal-planner
DATA_DIR=/var/lib/meal-planner
ENV_FILE=/etc/meal-planner/.env
KEEP_RELEASES=3

die() { echo "error: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run with sudo"
REPO=$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)
git_() { git -c safe.directory="$REPO" -C "$REPO" "$@"; }

if git_ rev-parse --verify --quiet origin/main >/dev/null; then
    MAIN=origin/main
else
    MAIN=main
fi

TAG=${1:-$(git_ describe --tags --abbrev=0 --match 'v[0-9]*' "$MAIN" 2>/dev/null || true)}
[[ -n $TAG ]] || die "no vX.Y.Z tag found on $MAIN (did you 'git fetch --tags'?)"
[[ $TAG =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "'$TAG' is not a vX.Y.Z tag"
git_ rev-parse --verify --quiet "refs/tags/$TAG" >/dev/null || die "tag $TAG not found"
git_ merge-base --is-ancestor "$TAG^{commit}" "$MAIN" || die "$TAG is not on $MAIN"

RELEASE="$PREFIX/releases/$TAG"
echo "==> Deploying $TAG"

# Back up first: a new release may run database migrations on start.
if [[ -f $DATA_DIR/meal-planner.db ]]; then
    echo "==> Backing up the database"
    systemctl start meal-planner-backup.service
fi

STAGING=$(mktemp -d "$PREFIX/releases/.staging.XXXXXX")
trap 'rm -rf "$STAGING"' EXIT
git_ archive --format=tar "$TAG" | tar -x -C "$STAGING"
chmod 755 "$STAGING"
rm -rf "$RELEASE"
mv "$STAGING" "$RELEASE"
trap - EXIT

echo "==> Installing dependencies"
"$PREFIX/venv/bin/pip" install --quiet --upgrade pip
"$PREFIX/venv/bin/pip" install --quiet -e "$RELEASE"

ln -sfn "$RELEASE" "$PREFIX/current.new"
mv -T "$PREFIX/current.new" "$PREFIX/current"

echo "==> Restarting"
systemctl restart meal-planner.service

PORT=$(sed -n 's/^PORT=//p' "$ENV_FILE" 2>/dev/null | tr -d "\"' " | tail -n1)
PORT=${PORT:-8080}
for _ in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
        echo "==> $TAG is up on port $PORT"
        # Keep the newest few releases so rolling back is just 'update.sh <old tag>'.
        current=$(readlink "$PREFIX/current")
        find "$PREFIX/releases" -mindepth 1 -maxdepth 1 -type d -name 'v*' -printf '%T@ %p\n' \
            | sort -rn | tail -n +$((KEEP_RELEASES + 1)) | cut -d' ' -f2- \
            | while read -r old; do [[ $old == "$current" ]] || rm -rf "$old"; done
        exit 0
    fi
    sleep 1
done

echo "error: $TAG did not pass the health check. Recent logs:" >&2
journalctl -u meal-planner.service -n 30 --no-pager >&2 || true
exit 1
