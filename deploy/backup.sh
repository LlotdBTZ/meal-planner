#!/usr/bin/env bash
# Back up the Meal Planner database now (the timer also does this nightly).
# Backups go to /var/lib/meal-planner/backups; the newest 14 are kept.
#
#   sudo deploy/backup.sh
#
# Restore: sudo systemctl stop meal-planner
#          sudo -u mealplanner cp /var/lib/meal-planner/backups/meal-planner-YYYY-MM-DD.db \
#              /var/lib/meal-planner/meal-planner.db
#          sudo rm -f /var/lib/meal-planner/meal-planner.db-wal /var/lib/meal-planner/meal-planner.db-shm
#          sudo systemctl start meal-planner
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "error: run with sudo" >&2; exit 1; }
status=0
systemctl start meal-planner-backup.service || status=$?
journalctl -u meal-planner-backup.service -n 3 --no-pager -o cat
exit "$status"
