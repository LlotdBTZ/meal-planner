# Meal Planner — Design

Date: 2026-11-24
Status: Approved by owner 2026-11-24

## 1. Intent

The user finds recipes on TikTok and Instagram. Today, turning one of those videos
into a grocery list is manual. Meal Planner removes that work:

1. Paste (or share) a TikTok/Instagram link.
2. The app pulls the recipe name and ingredients out of the post.
3. The user reviews and corrects the ingredients, then saves the recipe.
4. Each week the user picks which saved meals to make.
5. The app combines the ingredients of those meals into one grocery list.
6. One tap copies the list so it can be pasted into iPhone Notes.

It is a personal tool for one person. Sharing with others may come later, so
the design should not block that, but nothing is built for it now.

Similar in spirit to apps like KartChef, but built for this one workflow,
without grocery-store integration.

## 2. Goals, non-goals, anti-goals

**Goals**
- Turning a link into a saved recipe takes about a minute, most of it reviewing.
- Extraction works for the common cases: the recipe is written in the
  caption, or it is spoken in the video.
- The weekly list combines duplicates sensibly ("1 onion" + "½ onion" →
  "1½ onion") and is grouped by store section.
- The list pastes cleanly into iPhone Notes.
- Runs on the user's Raspberry Pi 3 B+ (1GB RAM) next to Pi-hole without hurting it.
- Running cost is a few cents per recipe at most.

**Non-goals (for now)**
- Multiple users, sign-up, or accounts.
- Ordering groceries or connecting to stores.
- Cooking steps/instructions. Only name and ingredients are required; steps
  may be stored if extraction gets them for free, but no UI work goes into them.
- A native iOS app or App Store listing.
- Nutrition, cost estimates, or a pantry inventory.
- Meal calendar by day. The plan is "this week's meals," not Monday/Tuesday slots.

**Anti-goals (failure even if it "works")**
- Saving ingredients the user didn't see. Every extracted recipe goes through
  the review screen before it is saved.
- Slowing down or destabilising Pi-hole (DNS for the whole house).
- Silent failure: if extraction can't find a recipe, the user is told and can
  paste the caption/ingredients by hand instead.
- Fiddly maintenance. Routine breakage (e.g. yt-dlp falling behind TikTok)
  should be fixed by an automatic update, not by the user SSH-ing in.

## 3. Constraints

- **Hardware:** Raspberry Pi 3 B+, 1GB RAM, already running Pi-hole (which owns
  port 80 and 53). No heavy builds on the Pi.
- **Network:** LAN-only by default. Optional Tailscale for remote access/HTTPS.
- **Owner's machine:** Linux (Fedora). No Mac, so no Xcode/native iOS.
- **Client:** iPhone Safari, used as a home-screen web app.
- **Cost:** free hosting; pay-per-use APIs only (Claude, transcription).

## 4. Approaches considered

1. **Installable website on Vercel (Next.js + hosted DB).** Free and
   reachable anywhere, but Instagram/TikTok often block cloud IPs, and
   yt-dlp doesn't run well on serverless. Rejected.
2. **Native iPhone app (Swift).** Real share-sheet support, but needs a Mac,
   a $99/yr developer account, and App Store review to share later. Rejected.
3. **Self-hosted web app on the Pi (chosen).** Residential IP gets through to
   TikTok/Instagram far more reliably; yt-dlp runs natively; free.
   Originally sketched as Next.js in Docker, then made lighter because the Pi
   3 B+ has only 1GB RAM: **Python + FastAPI, server-rendered pages, SQLite,
   no Docker, systemd service.** The owner picked this.

## 5. Decided

- Host: the Raspberry Pi 3 B+, alongside Pi-hole.
- Backend: Python 3, FastAPI, served by uvicorn (single worker).
- Pages: server-rendered HTML (Jinja2 templates), plain CSS, small amounts of
  vanilla JavaScript. No frontend build step.
- Database: SQLite, single file on the Pi.
- No Docker. A Python virtualenv + a systemd service that starts on boot.
- Fetching posts: yt-dlp, used as a Python library.
- Reading recipes: Claude API.
- Transcribing audio: an external speech-to-text API (not run on the Pi).
- Access: one shared password; LAN by default; Tailscale as an optional last step.
- Repo: GitHub, named `meal-planner`.

## 6. How it works

### 6.1 Screens

```
┌ Recipes (home) ───────────────┐   ┌ Add recipe ───────────────────┐
│ [+ Add]          [This week 3]│   │ Link: [ https://tiktok...  ]  │
│ ┌──────┐ ┌──────┐ ┌──────┐    │   │ [Get recipe]                  │
│ │ img  │ │ img  │ │ img  │    │   │ ─ or ─ paste caption/text:    │
│ │Tacos✓│ │Pasta │ │Curry✓│    │   │ [                          ]  │
│ └──────┘ └──────┘ └──────┘    │   └───────────────────────────────┘
│ search: [        ]            │
└───────────────────────────────┘
┌ Review (before save) ─────────┐   ┌ This week ────────────────────┐
│ Name: [Birria Tacos        ]  │   │ Tacos ✕   Curry ✕   Soup ✕     │
│ Servings: [4]   source: link  │   │ PRODUCE                       │
│ qty  unit  item        note   │   │ ☐ 1½ onion                    │
│ [2 ] [lb ] [beef chuck] [   ] │   │ ☐ 6 garlic cloves             │
│ [1 ] [   ] [onion     ] [diced]│  │ MEAT                          │
│ [+ add row]  (rows deletable) │   │ ☐ 2 lb beef chuck             │
│ ⚠ "No amounts in video for 2" │   │ ...                           │
│ [Save]  [Cancel]              │   │ [Copy list]  [Clear week]     │
└───────────────────────────────┘   └───────────────────────────────┘
```

- **Recipes (home):** cards with thumbnail and name, searchable by name. Tap a
  card's check to add/remove it from this week. Tap the card body to open the
  recipe (view, edit, delete, open original link).
- **Add recipe:** paste a link, or paste raw text (caption, recipe from
  anywhere). Shows progress while extracting ("Reading caption…",
  "Listening to video…"), which can take ~10–60s on the Pi.
- **Review:** editable form. Each ingredient row: quantity, unit, item, note,
  plus a store-section dropdown. Warnings from extraction shown at the top
  (e.g. "amounts weren't stated for 2 ingredients"). Nothing is saved until
  Save is pressed.
- **This week:** chosen meals at the top (removable), then the combined list
  grouped by store section. Each line can be ticked to mean "already have it";
  ticked lines are left out of the copy. **Copy list** puts the remaining
  lines on the clipboard. **Clear week** empties the selection.

### 6.2 Getting a recipe from a link

1. Detect platform from the URL (TikTok, Instagram, other).
2. **Metadata:** yt-dlp `extract_info(download=False)` → caption/description,
   title, uploader, thumbnail URL. Save the thumbnail image locally so cards
   don't break when the CDN link expires.
3. **Caption pass:** send the caption to Claude with a structured-output
   request (schema in 6.4). Claude also reports whether the caption actually
   contained an ingredient list.
4. **Audio pass (only if step 3 found no ingredients):** yt-dlp downloads the
   audio-only stream (no ffmpeg conversion; m4a/mp4 audio is accepted by
   transcription APIs). Send to the transcription API. Send caption +
   transcript to Claude again. Delete the audio file afterwards.
5. **Non-social links (recipe blogs):** fetch the page; if it has a
   schema.org `Recipe` JSON-LD block, use it directly; otherwise send the
   page's main text to Claude. Nice-to-have, cheap to include.
6. **Failure:** if yt-dlp can't fetch the post (private, login wall, blocked),
   show a clear message and keep the paste-text box ready. Instagram
   sometimes requires login; support an optional cookies file path in config
   (`YTDLP_COOKIES`) for yt-dlp, documented in the README.

Extraction runs in a background task; the Add page polls a status endpoint.
Only one extraction runs at a time (Pi memory).

### 6.3 Data

```
recipes
  id, name, servings (int, nullable), source_url, platform,
  thumbnail_path, notes, steps (text, nullable), created_at, updated_at
ingredients
  id, recipe_id → recipes, position,
  quantity (real, nullable), unit (text, nullable), item (text),
  note (text, nullable), section (text), raw_text (original line)
week_selection
  recipe_id → recipes (one row per chosen meal)
list_checks
  item_key (text)  -- "already have" ticks for the current week
extraction_jobs
  id, url_or_text, status, stage, result_json, error, created_at
```

Sections (fixed list): Produce, Meat & Seafood, Dairy & Eggs, Bakery,
Pantry, Spices, Frozen, Other.

`item` is stored in a normalized form (lowercase, singular, without prep words:
"onion", not "Diced Onions"); prep words go in `note`. Claude produces this
form; the user can edit it on the review screen.

### 6.4 Claude extraction output (per recipe)

```json
{
  "found_recipe": true,
  "name": "Birria Tacos",
  "servings": 4,
  "ingredients": [
    {"quantity": 2, "unit": "lb", "item": "beef chuck",
     "note": null, "section": "Meat & Seafood", "raw_text": "2lb chuck roast"}
  ],
  "steps": ["..."],
  "warnings": ["Amounts not stated for salt and pepper"]
}
```

One recipe per post in v1 (Claude's call, not the owner's): if a post holds
several recipes (e.g. "3 meal-prep ideas"), Claude extracts the first/main one
and adds a warning naming the others, so the user can paste their text in
separately. Splitting one post into several recipes can come later.

Fractions become decimals ("½" → 0.5). "Salt to taste" → quantity null,
unit null. Units normalized to a known set where possible (tsp, tbsp, cup,
oz, lb, g, kg, ml, l, clove, can, pinch, …), otherwise kept as written.

### 6.5 Combining the weekly list

- Group ingredients from all chosen recipes by `item`.
- Within an item, convert compatible units to a common one and add:
  - volume: tsp/tbsp/cup/ml/l
  - weight: oz/lb/g/kg
  - count: no unit, or same count-unit (clove, can)
- Incompatible units for the same item are listed together on one line:
  "onion — 1 + 2 cups chopped".
- Items with no quantity appear once with no amount ("salt").
- Display amounts in friendly form (0.5 → ½, 1.333 cup → 1⅓ cup; 4 tbsp →
  ¼ cup when cleaner).
- No scaling by servings in v1 — each recipe is used as saved.

### 6.6 Copy to Notes

Copied text is one line per item, grouped by section, with section names as
plain lines:

```
Produce
1½ onion
6 garlic clove
Meat & Seafood
2 lb beef chuck
```

In Notes, select all → tap the checklist button to turn it into a checklist.

**Clipboard caveat:** `navigator.clipboard` only works over HTTPS. On plain
LAN HTTP, fall back to selecting a hidden textarea + `document.execCommand
('copy')`, and as a last resort show the text in a box with "Select all" so
the user can copy manually. With Tailscale HTTPS the modern API works.

### 6.7 Sharing from TikTok/Instagram on iPhone

A website can't appear in the iOS share sheet, so the README includes steps
to build an iOS Shortcut: accepts URLs from the share sheet → opens
`http://<pi>:8080/add?url=<encoded>` in Safari, which starts extraction
immediately (after login, if needed).

### 6.8 Login

- One password, set in config (`APP_PASSWORD`). Login page sets a long-lived
  signed session cookie (~1 year), so the user logs in once per device.
- Keep auth in one place (a dependency/middleware) so real accounts can
  replace it later.

### 6.9 Running on the Pi

- Port **8080** (Pi-hole uses 80).
- Config in a `.env` file on the Pi (not committed): `APP_PASSWORD`,
  `SESSION_SECRET`, `ANTHROPIC_API_KEY`, transcription API key,
  `YTDLP_COOKIES` (optional), `DATA_DIR`.
- systemd service: starts on boot, restarts on crash, `MemoryMax` around
  300MB so the app can never starve Pi-hole.
- A weekly systemd timer upgrades yt-dlp in the virtualenv and restarts the
  service (TikTok/Instagram changes break yt-dlp often).
- An `install.sh` that sets up the venv, service, and timer on a fresh Pi;
  an `update.sh` that deploys a release tag (`vX.Y.Z` on `main`), backs up the
  database first, checks `/health`, and rolls back to the previous release if
  the check fails.
- Releases deploy themselves: a systemd timer on the Pi checks GitHub every
  15 minutes and runs `update.sh` for a new tag. The Pi pulls; GitHub holds no
  deploy secrets and can't reach the Pi. A tag that failed is not retried
  automatically. (Chosen over GitHub Actions deploying through Tailscale/SSH
  or a self-hosted runner, because the repo is public.)
- Nightly backup: copy the SQLite file to a dated file in `DATA_DIR/backups`,
  keep the last 14.
- Optional final step (documented): Tailscale on the Pi and iPhone,
  `tailscale serve` for HTTPS, giving remote access and a full home-screen app.

### 6.10 Home-screen app

Web app manifest + icons + `apple-mobile-web-app-capable` meta, so Add to
Home Screen launches full-screen with its own icon. Mobile-first layout;
desktop just needs to be usable.

## 7. Left to the builder

- Exact Claude model (start with a small, cheap current model; move up if
  extraction quality is poor) and prompt wording.
- Which transcription API (e.g. OpenAI's speech-to-text); keep it behind a
  small interface so it can be swapped.
- Library choices for migrations, session cookies, and HTTP fetching.
- Visual styling, beyond: mobile-first, clean, readable in the kitchen.
- Test strategy. At minimum, unit tests for unit conversion/combining and
  for parsing Claude's output, plus recorded fixtures for extraction.
- Whether to support both 32-bit and 64-bit Raspberry Pi OS (check what the
  Pi runs; Python and yt-dlp work on both).
