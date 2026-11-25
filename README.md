# Meal Planner

Save recipes from TikTok/Instagram links, pick meals for the week, and copy a combined grocery list into iPhone Notes. Self-hosted on a Raspberry Pi.

See [the design](docs/superpowers/specs/2026-11-24-meal-planner-design.md) and [the build plan](docs/superpowers/plans/2026-11-24-meal-planner-plan.md).

## Deploy on the Raspberry Pi

Needs Raspberry Pi OS Bookworm or later (Python 3.11+). From a clone on the Pi:

```bash
sudo deploy/install.sh            # one time: packages, user, venv, systemd units, /etc/meal-planner/.env
sudo nano /etc/meal-planner/.env  # set APP_PASSWORD, ANTHROPIC_API_KEY, TRANSCRIBE_API_KEY
sudo deploy/update.sh             # deploy the newest vX.Y.Z tag on main
```

The app then runs at `http://<pi-address>:8080`.

- **Update:** `git fetch --tags origin && sudo deploy/update.sh` (or `sudo deploy/update.sh v0.2.0`;
  the same command rolls back to an older tag). It backs up the database first and checks `/health`.
- **Where things live:** code in `/opt/meal-planner/current`, data in `/var/lib/meal-planner`,
  settings in `/etc/meal-planner/.env`. Logs: `journalctl -u meal-planner -f`.
- **Backups:** nightly to `/var/lib/meal-planner/backups` (newest 14 kept); `sudo deploy/backup.sh`
  runs one now. Restore steps are in `deploy/backup.sh`.
- **yt-dlp** updates itself weekly (`meal-planner-ytdlp-update.timer`) and restarts the app.
- The service is capped at 300 MB of RAM so it can't starve Pi-hole.
