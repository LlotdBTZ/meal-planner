# Meal Planner — Build Plan

Design: [../specs/2026-11-24-meal-planner-design.md](../specs/2026-11-24-meal-planner-design.md)
Date: 2026-11-24

Each task ends with its tests passing and a commit. Logic that can be tested
without a network (units, combining, parsing, the database, auth) is written
test-first. Network pieces (yt-dlp, Claude, transcription) sit behind small
interfaces, so the pipeline can be tested with fakes. Each one also gets a
manual smoke test against real links.

## Target layout

```
meal-planner/
  pyproject.toml          # Python >=3.11 (Pi OS Bookworm ships 3.11)
  .env.example
  app/
    main.py               # FastAPI app, routes wiring, static/templates
    config.py             # settings from env / .env
    db.py                 # sqlite3 connection, schema, migrations (PRAGMA user_version)
    auth.py               # password login, signed session cookie, require_login dependency
    recipes.py            # recipe + ingredient CRUD, week selection, list checks
    grocery.py            # unit normalization, combining, friendly amounts
    listtext.py           # plain-text output for Notes
    jobs.py               # single-worker background extraction queue + job table
    extraction/
      schema.py           # RecipeDraft dataclasses, validation of Claude JSON
      llm.py              # Claude client: text -> RecipeDraft
      transcribe.py       # audio file -> transcript (swappable interface)
      fetch.py            # yt-dlp metadata, audio download, thumbnail save
      web.py              # non-social pages: JSON-LD Recipe, else main text
      pipeline.py         # orchestration: platform detect, caption pass, audio pass, fallbacks
    routes/               # pages.py, api.py
    templates/            # base, login, home, add, review, recipe, week
    static/               # css, js (copy, polling), manifest.json, icons
  tests/
  deploy/
    meal-planner.service
    meal-planner-ytdlp-update.service / .timer
    meal-planner-backup.service / .timer
    install.sh, update.sh, backup.sh
  README.md
```

## Tasks

### 0. Repo and GitHub
- `git init`, `.gitignore` (venv, `.env`, `data/`, `__pycache__`), commit the
  design and this plan.
- Create the `meal-planner` repo on GitHub (owner LlotdBTZ) and push `main`.

### 1. Skeleton
- `pyproject.toml` with fastapi, uvicorn, jinja2, python-multipart,
  itsdangerous, anthropic, yt-dlp, httpx; dev: pytest.
- `config.py` reads `APP_PASSWORD`, `SESSION_SECRET`, `ANTHROPIC_API_KEY`,
  `TRANSCRIBE_API_KEY`, `YTDLP_COOKIES`, `DATA_DIR`, `PORT` (default 8080).
- `main.py` with `/health`. Test: health returns 200.

### 2. Database
- Schema from design §6.3. Migrations are run in order based on `user_version`.
- `recipes.py`: create recipe with ingredients (one transaction), get, list +
  name search, update (replace ingredient rows), delete (cascades), week
  add/remove/list/clear, list-check toggle/clear.
- Tests use a temporary SQLite file: round-trip, cascade delete, search,
  week behaviour, and clear-week also clears the checks.

### 3. Units and combining (`grocery.py`), test-first
- Normalize unit aliases (tablespoon/Tbsp/T → tbsp, lbs → lb, …).
- Families: volume (tsp, tbsp, cup, ml, l), weight (oz, lb, g, kg), count
  (no unit), and named count units (clove, can, pinch, …) that only add when
  the unit matches.
- `combine(ingredients) -> list[ListLine]`: group by normalized item, sum
  within each family, and keep incompatible parts as `1 + 2 cup` on one line.
  Items with no quantity stay without an amount. Section = most common
  section among the parts (ties go to the first seen).
- Friendly amounts: fractions (½ ⅓ ¼ ⅔ ¾ ⅛), pick the display unit
  (e.g. 12 tsp → ¼ cup), metric stays metric, imperial stays imperial.
- Tests: the onion example, tbsp+cup, oz+lb, g+kg, mixed volume+count,
  salt with no amount, and section ties.

### 4. Notes text (`listtext.py`), test-first
- Sections in a fixed order; skip empty ones and checked items.
  Format as in design §6.6. Test the exact output.

### 5. Login (`auth.py`)
- Login form compares against `APP_PASSWORD` in constant time and sets a signed
  cookie (itsdangerous) that lasts 1 year. `require_login` dependency redirects
  to `/login?next=…` (so the Shortcut's `/add?url=` survives login).
  Simple in-memory rate limit on failed attempts.
- Tests: protected page redirects, wrong password rejected, right password
  sets cookie, `next` is honoured and only allows local paths.

### 6. Extraction
- `schema.py`: dataclasses plus a validator for the JSON in design §6.4.
  Covers `found_recipe`, the multi-recipe warning, and section values limited
  to the fixed list. Tests: valid, missing fields, bad section → Other,
  string quantities ("1/2") → 0.5.
- `llm.py`: Claude call with a JSON-schema / tool-use structured output,
  prompt covering the normalization rules in §6.4, and a small current
  model. Load the `claude-api` skill before writing it to confirm the model
  ID and the structured-output API. Test with a recorded response.
- `transcribe.py`: `Transcriber` protocol plus an OpenAI speech-to-text
  implementation. Reject files over the API size limit with a clear error.
- `fetch.py`: `get_metadata(url)`, `download_audio(url, dir)` (audio-only,
  no ffmpeg), `save_thumbnail`. Pass cookies when configured. Map yt-dlp
  errors to friendly messages (private, login required, not found).
- `web.py`: fetch with httpx, find JSON-LD `Recipe` (including inside
  `@graph`), and otherwise strip HTML to text. Tests with saved HTML fixtures.
- `pipeline.py`: detect platform, then run the caption pass, then the audio
  pass if nothing was found. Use the web path for other sites and the text
  path for pasted text. Report a stage label for progress and delete temporary
  audio. Tests use fakes for fetch, llm and transcriber to cover every branch.

### 7. Jobs (`jobs.py`)
- An `extraction_jobs` row per request, processed by a single worker thread
  from a queue, so only one runs at a time. Jobs still running at startup are
  marked failed. `GET /api/jobs/{id}` returns status, stage, result or error.
- Tests: queued → done with a fake pipeline; an error is recorded; restart
  recovery works.

### 8. Pages
- `home`: recipe cards with thumbnails, search, a week toggle (form POST plus
  a small JS enhancement), and a week count badge.
- `add`: link/text form. `/add?url=` starts the job automatically. The page
  polls the job, then goes to review.
- `review` (new) and `recipe/{id}/edit` share one ingredient-table form: add,
  remove and reorder rows, a section dropdown, and warnings shown at the top.
  Save validates that there is a name and at least one ingredient.
- `recipe/{id}`: view, open the source, edit, and delete (with confirmation).
- `week`: chosen meals with remove buttons, the combined list with
  "have it" checkboxes, Copy list, and Clear week.
- Mobile-first CSS. Route tests with TestClient for each page and form POST.

### 9. Copy and home-screen app
- `copy.js`: use `navigator.clipboard` when in a secure context. Otherwise
  fall back to a hidden textarea plus `execCommand('copy')`, and as a last
  resort show a select-all text box. Show a "Copied" toast.
- `manifest.json`, icons (180/192/512), and Apple meta tags.
- Manual check on the iPhone over LAN HTTP.

### 10. Deployment
- `install.sh` (run on the Pi): apt install python3-venv, create a
  `mealplanner` user, put the code in /opt/meal-planner and data in
  /var/lib/meal-planner, create the venv, copy `.env.example`, and install
  and enable the units.
- Service: uvicorn on 0.0.0.0:8080 with 1 worker, `MemoryMax=300M`,
  `Restart=on-failure`.
- Weekly timer: `pip install -U yt-dlp`, then restart the service.
- Nightly timer: `sqlite3 .backup` into `backups/`, keeping the last 14.
- `update.sh`: git pull, pip install, restart.

### 11. README
- What it is, setup on the Pi, `.env` keys and where to get them, the iOS
  Shortcut steps (share sheet → open `/add?url=`), adding it to the Home
  Screen, Instagram cookies, optional Tailscale + `tailscale serve`, and
  backups and restore.

### 12. Try it for real
- Deploy to the Pi. Test 3 TikToks (recipe in the caption, recipe only spoken,
  no recipe), 2 Instagram reels, and 1 blog. Plan a week of 3 meals and paste
  the list into Notes.
- Check memory use (`systemctl status`) and that Pi-hole still answers DNS
  during an extraction.
- Write down anything that needs fixing as follow-up issues.
