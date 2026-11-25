#!/usr/bin/env bash
# One-time setup of Meal Planner on a Raspberry Pi (Raspberry Pi OS, Bookworm or later).
#
#   git clone <repo> ~/meal-planner && cd ~/meal-planner
#   sudo deploy/install.sh
#
# Safe to run again: it only creates what is missing and never overwrites .env.
# Afterwards new release tags on main deploy themselves (meal-planner-autodeploy.timer);
# keep this checkout in place, since the timer fetches tags into it.
set -euo pipefail

PREFIX=/opt/meal-planner
DATA_DIR=/var/lib/meal-planner
ENV_DIR=/etc/meal-planner
APP_USER=mealplanner
UNITS=(
    meal-planner.service
    meal-planner-backup.service
    meal-planner-backup.timer
    meal-planner-ytdlp-update.service
    meal-planner-ytdlp-update.timer
    meal-planner-autodeploy.service
    meal-planner-autodeploy.timer
)

die() { echo "error: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run with sudo"
DEPLOY_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(dirname "$DEPLOY_DIR")

echo "==> Installing system packages"
apt-get update -qq
apt-get install -y -qq python3 python3-venv git curl >/dev/null

python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
    || die "Python 3.11+ is required (found $(python3 --version))"

echo "==> Creating the $APP_USER user and directories"
if ! id "$APP_USER" >/dev/null 2>&1; then
    useradd --system --home-dir "$DATA_DIR" --no-create-home \
        --shell /usr/sbin/nologin "$APP_USER"
fi
install -d -o "$APP_USER" -g "$APP_USER" -m 750 "$DATA_DIR"
install -d -o root -g root -m 755 "$PREFIX" "$PREFIX/releases"
install -d -o root -g "$APP_USER" -m 750 "$ENV_DIR"

if [[ ! -f $ENV_DIR/.env ]]; then
    install -o root -g "$APP_USER" -m 640 "$REPO/.env.example" "$ENV_DIR/.env"
    secret=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
    sed -i "s/^SESSION_SECRET=.*/SESSION_SECRET=$secret/" "$ENV_DIR/.env"
    created_env=1
fi

if [[ ! -x $PREFIX/venv/bin/python ]]; then
    echo "==> Creating the virtualenv"
    python3 -m venv "$PREFIX/venv"
fi

echo "==> Installing systemd units"
for unit in "${UNITS[@]}"; do
    sed "s|@REPO@|$REPO|g" "$DEPLOY_DIR/$unit" >"/etc/systemd/system/$unit"
    chmod 644 "/etc/systemd/system/$unit"
done
TIMERS=(meal-planner-backup.timer meal-planner-ytdlp-update.timer meal-planner-autodeploy.timer)
systemctl daemon-reload
systemctl enable meal-planner.service "${TIMERS[@]}"
systemctl start "${TIMERS[@]}"

if [[ ${created_env:-0} == 1 ]]; then
    cat <<EOF

Almost done. Fill in the settings, then deploy:

    sudo nano $ENV_DIR/.env      # APP_PASSWORD, ANTHROPIC_API_KEY, TRANSCRIBE_API_KEY
    sudo $DEPLOY_DIR/update.sh

(SESSION_SECRET was generated for you. DATA_DIR is set by the service to $DATA_DIR.)
EOF
else
    "$DEPLOY_DIR/update.sh"
fi
