#!/usr/bin/env bash
# Deploy a tagged release of Meal Planner on the Pi.
#
#   cd ~/meal-planner && git fetch --tags origin
#   sudo deploy/update.sh            # newest vX.Y.Z tag on main
#   sudo deploy/update.sh v0.2.0     # a specific tag (also how you roll back)
#   sudo deploy/update.sh --auto     # what the auto-deploy timer runs (see below)
#
# Only tags whose commit is on main are deployed. If the new release fails its
# health check, the previous release is put back.
#
# --auto: fetch tags from origin and deploy the newest one if it isn't running
# yet. Tags that failed, or that you rolled back from by hand, are skipped until
# you deploy them by hand. Run every 15 minutes by
# meal-planner-autodeploy.timer, from the *deployed* copy of this script.
set -euo pipefail

PREFIX=/opt/meal-planner
DATA_DIR=/var/lib/meal-planner
ENV_FILE=/etc/meal-planner/.env
SKIP_FILE=$PREFIX/skipped-tags  # tags auto-deploy won't touch
KEEP_RELEASES=3

die() { echo "error: $*" >&2; exit 1; }
log() { echo "==> $*"; }

[[ $EUID -eq 0 ]] || die "run with sudo"

AUTO=0
if [[ ${1:-} == --auto ]]; then AUTO=1; shift; fi

# The git checkout to deploy from: $MEAL_PLANNER_REPO (set by the timer), else
# the checkout this script lives in.
REPO=${MEAL_PLANNER_REPO:-$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null || true)}
[[ -n $REPO && -d $REPO/.git ]] || die "no git checkout found (set MEAL_PLANNER_REPO)"
git_() { git -c safe.directory="$REPO" -C "$REPO" "$@"; }

# One deploy at a time (timer vs. manual run).
exec 9>/run/meal-planner-deploy.lock
flock -n 9 || die "another deploy is running"

if [[ $AUTO == 1 ]]; then
    # Fetch as the checkout's owner so root never writes into their .git.
    owner=$(stat -c %U "$REPO/.git")
    runuser -u "$owner" -- git -C "$REPO" fetch --quiet --tags --prune origin \
        || die "git fetch failed"
fi

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

PREVIOUS=$(readlink "$PREFIX/current" 2>/dev/null || true)
RELEASE="$PREFIX/releases/$TAG"

if [[ $AUTO == 1 ]]; then
    if [[ $PREVIOUS == "$RELEASE" ]]; then
        exit 0  # already running the newest release
    fi
    if grep -qxF "$TAG" "$SKIP_FILE" 2>/dev/null; then
        echo "$TAG is on the skip list ($SKIP_FILE); deploy it by hand to retry"
        exit 0
    fi
fi

log "Deploying $TAG${PREVIOUS:+ (was $(basename "$PREVIOUS"))}"

# Back up first: a new release may run database migrations on start.
if [[ -f $DATA_DIR/meal-planner.db && -n $PREVIOUS ]]; then
    log "Backing up the database"
    systemctl start meal-planner-backup.service
fi

if [[ $RELEASE != "$PREVIOUS" ]]; then
    STAGING=$(mktemp -d "$PREFIX/releases/.staging.XXXXXX")
    trap 'rm -rf "$STAGING"' EXIT
    git_ archive --format=tar "$TAG" | tar -x -C "$STAGING"
    chmod 755 "$STAGING"
    rm -rf "$RELEASE"
    mv "$STAGING" "$RELEASE"
    trap - EXIT
fi

# Called inside 'if', where set -e is off, so every step checks for failure itself.
activate() {  # point current at a release, install its dependencies, restart
    log "Installing dependencies for $(basename "$1")"
    "$PREFIX/venv/bin/pip" install --quiet --upgrade pip || return 1
    "$PREFIX/venv/bin/pip" install --quiet -e "$1" || return 1
    ln -sfn "$1" "$PREFIX/current.new" || return 1
    mv -T "$PREFIX/current.new" "$PREFIX/current" || return 1
    log "Restarting"
    systemctl restart meal-planner.service || return 1
}

healthy() {
    local port
    port=$(sed -n 's/^PORT=//p' "$ENV_FILE" 2>/dev/null | tr -d "\"' " | tail -n1)
    for _ in $(seq 1 30); do
        curl -fsS "http://127.0.0.1:${port:-8080}/health" >/dev/null 2>&1 && return 0
        sleep 1
    done
    return 1
}

if activate "$RELEASE" && healthy; then
    log "$TAG is up"
    sed -i "/^${TAG//./\\.}\$/d" "$SKIP_FILE" 2>/dev/null || true
    if [[ $AUTO == 0 ]]; then
        # A hand-picked older tag is a rollback: stop auto-deploy undoing it.
        for newer in $(git_ tag --merged "$MAIN" --contains "$TAG^{commit}" --list 'v[0-9]*' \
                       | grep -vxF "$TAG" || true); do
            grep -qxF "$newer" "$SKIP_FILE" 2>/dev/null || echo "$newer" >>"$SKIP_FILE"
            log "Auto-deploy will skip $newer (deploy it by hand to undo)"
        done
    fi
    # Keep the newest few releases so rolling back is just 'update.sh <old tag>'.
    find "$PREFIX/releases" -mindepth 1 -maxdepth 1 -type d -name 'v*' -printf '%T@ %p\n' \
        | sort -rn | tail -n +$((KEEP_RELEASES + 1)) | cut -d' ' -f2- \
        | while read -r old; do [[ $old == "$RELEASE" ]] || rm -rf "$old"; done
    exit 0
fi

echo "error: $TAG did not pass the health check. Recent logs:" >&2
journalctl -u meal-planner.service -n 30 --no-pager >&2 || true
grep -qxF "$TAG" "$SKIP_FILE" 2>/dev/null || echo "$TAG" >>"$SKIP_FILE"

if [[ -n $PREVIOUS && $PREVIOUS != "$RELEASE" && -d $PREVIOUS ]]; then
    log "Rolling back to $(basename "$PREVIOUS")"
    if activate "$PREVIOUS" && healthy; then
        log "Rolled back; $(basename "$PREVIOUS") is up"
    else
        echo "error: rollback to $(basename "$PREVIOUS") also failed" >&2
    fi
fi
exit 1
