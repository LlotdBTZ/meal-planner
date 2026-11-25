import json

import pytest
from fastapi.testclient import TestClient

from app import db, jobs, recipes
from app.config import get_settings
from app.extraction.schema import RecipeDraft
from app.main import create_app
from app.recipes import Ingredient, Recipe
from app.templating import ingredient_line, qty_input

THUMB = "0123456789abcdef0123456789abcdef.jpg"


def no_runner(source, on_stage):
    raise AssertionError("not used")


@pytest.fixture
def settings(tmp_path):
    return get_settings({"DATA_DIR": str(tmp_path), "APP_PASSWORD": "pw", "SESSION_SECRET": "s"})


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings, runner=no_runner), follow_redirects=False) as c:
        c.post("/login", data={"password": "pw"})
        yield c


@pytest.fixture
def conn(settings, client):
    c = db.connect(settings.db_path)
    yield c
    c.close()


def make_recipe(conn, name="Birria Tacos", thumb=None, **kw):
    return recipes.create_recipe(
        conn,
        Recipe(
            name=name,
            servings=4,
            source_url="https://www.tiktok.com/@c/video/1",
            platform="tiktok",
            thumbnail_path=thumb,
            steps=["Braise the beef"],
            ingredients=[
                Ingredient(item="beef chuck", quantity=2, unit="lb", section="Meat & Seafood"),
                Ingredient(item="onion", quantity=0.5, note="diced", section="Produce"),
            ],
            **kw,
        ),
    )


def editor_form(**overrides):
    form = {
        "name": "Garlic Shrimp",
        "servings": "2",
        "qty": ["1", "1 1/2", ""],
        "unit": ["lb", "tbsp", ""],
        "item": ["Shrimp", "butter", ""],
        "note": ["peeled", "", ""],
        "section": ["Meat & Seafood", "Dairy & Eggs", "Other"],
        "raw": ["1 lb shrimp, peeled", "", ""],
        "notes": "",
    }
    form.update(overrides)
    return form


# --- filters -------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected", [(None, ""), (2.0, "2"), (1.5, "1½"), (0.6, "0.6"), (1 / 3, "⅓")]
)
def test_qty_input(value, expected):
    assert qty_input(value) == expected


def test_ingredient_line():
    assert ingredient_line(Ingredient(item="onion", quantity=0.5, note="diced")) == "½ onion, diced"
    assert ingredient_line(Ingredient(item="beef", quantity=2, unit="lb")) == "2 lb beef"
    assert ingredient_line(Ingredient(item="salt")) == "salt"


# --- home ----------------------------------------------------------------------


def test_home_empty_state(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "No recipes yet" in resp.text
    assert 'href="/add"' in resp.text


def test_home_lists_recipes_and_searches(client, conn):
    make_recipe(conn, "Birria Tacos")
    make_recipe(conn, "Chicken Curry")
    body = client.get("/").text
    assert "Birria Tacos" in body and "Chicken Curry" in body
    body = client.get("/?q=curry").text
    assert "Chicken Curry" in body and "Birria Tacos" not in body
    assert "No recipes match" in client.get("/?q=zzz").text


def test_home_escapes_names(client, conn):
    make_recipe(conn, "<script>alert(1)</script>")
    body = client.get("/").text
    assert "<script>alert(1)" not in body
    assert "&lt;script&gt;" in body


def test_week_toggle_from_home(client, conn):
    rid = make_recipe(conn)
    resp = client.post(f"/week/add/{rid}?next=/")
    assert resp.status_code == 303 and resp.headers["location"] == "/"
    body = client.get("/").text
    assert "in-week" in body
    assert "data-week-count>1<" in body
    resp = client.post(f"/week/remove/{rid}", headers={"X-Requested-With": "fetch"})
    assert resp.status_code == 204
    assert recipes.week_recipe_ids(conn) == []


def test_week_add_unknown_recipe_404(client):
    assert client.post("/week/add/999").status_code == 404


def test_next_param_must_be_local(client, conn):
    rid = make_recipe(conn)
    resp = client.post(f"/week/add/{rid}?next=https://evil.example")
    assert resp.headers["location"] == "/"


# --- recipe view / edit / delete ------------------------------------------------


def test_recipe_view(client, conn):
    rid = make_recipe(conn)
    body = client.get(f"/recipe/{rid}").text
    assert "Birria Tacos" in body
    assert "2 lb beef chuck" in body
    assert "½ onion, diced" in body
    assert "Serves 4" in body
    assert "open the original on TikTok" in body
    assert "Braise the beef" in body
    assert "Add to this week" in body


def test_recipe_missing_is_404(client):
    assert client.get("/recipe/999").status_code == 404
    assert client.get("/recipe/999/edit").status_code == 404


def test_edit_form_prefilled(client, conn):
    rid = make_recipe(conn)
    body = client.get(f"/recipe/{rid}/edit").text
    assert 'value="Birria Tacos"' in body
    assert 'value="½"' in body
    assert "<option selected>Meat &amp; Seafood</option>" in body


def test_edit_saves_and_keeps_source(client, conn):
    rid = make_recipe(conn, thumb=THUMB)
    resp = client.post(
        f"/recipe/{rid}/edit",
        data=editor_form(source_url="https://evil", thumbnail_path="../../etc/passwd"),
    )
    assert resp.status_code == 303 and resp.headers["location"] == f"/recipe/{rid}"
    r = recipes.get_recipe(conn, rid)
    assert r.name == "Garlic Shrimp" and r.servings == 2
    assert [(i.item, i.quantity, i.unit, i.note, i.section) for i in r.ingredients] == [
        ("shrimp", 1.0, "lb", "peeled", "Meat & Seafood"),
        ("butter", 1.5, "tbsp", None, "Dairy & Eggs"),
    ]
    assert r.source_url == "https://www.tiktok.com/@c/video/1"
    assert r.thumbnail_path == THUMB
    assert r.steps == ["Braise the beef"]


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"name": "  "}, "Give the recipe a name"),
        ({"servings": "lots"}, "whole number"),
        ({"item": ["", "", ""]}, "at least one ingredient"),
        ({"qty": ["a few", "", ""]}, "isn&#39;t an amount"),
        ({"item": ["Shrimp", "", ""], "qty": ["1", "2", ""]}, "Row 2 has an amount"),
    ],
)
def test_edit_validation_errors_keep_input(client, conn, overrides, message):
    rid = make_recipe(conn)
    resp = client.post(f"/recipe/{rid}/edit", data=editor_form(**overrides))
    assert resp.status_code == 400
    assert message in resp.text
    assert recipes.get_recipe(conn, rid).name == "Birria Tacos"


def test_delete_recipe_and_thumbnail(client, conn, settings):
    settings.thumbnails_dir.mkdir(parents=True, exist_ok=True)
    (settings.thumbnails_dir / THUMB).write_bytes(b"jpg")
    rid = make_recipe(conn, thumb=THUMB)
    resp = client.post(f"/recipe/{rid}/delete")
    assert resp.status_code == 303 and resp.headers["location"] == "/"
    assert recipes.get_recipe(conn, rid) is None
    assert not (settings.thumbnails_dir / THUMB).exists()


# --- thumbnails ------------------------------------------------------------------


def test_thumbnail_served_only_for_safe_names(client, settings):
    settings.thumbnails_dir.mkdir(parents=True, exist_ok=True)
    (settings.thumbnails_dir / THUMB).write_bytes(b"jpg")
    resp = client.get(f"/thumbs/{THUMB}")
    assert resp.status_code == 200 and resp.content == b"jpg"
    assert client.get("/thumbs/..%2F..%2Fmeal-planner.db").status_code == 404
    assert client.get("/thumbs/meal-planner.db").status_code == 404
    assert client.get("/thumbs/ffffffffffffffffffffffffffffffff.jpg").status_code == 404


def test_pages_require_login(settings):
    with TestClient(create_app(settings, runner=no_runner), follow_redirects=False) as c:
        for path in ["/", "/week", "/recipe/1", f"/thumbs/{THUMB}", "/review/1"]:
            assert c.get(path).status_code == 303, path
        assert c.post("/week/clear").status_code == 303


# --- add and review -----------------------------------------------------------------


def test_add_page(client):
    body = client.get("/add").text
    assert "data-add-form" in body and "data-autostart" not in body
    body = client.get("/add?url=https%3A%2F%2Fwww.tiktok.com%2Fx").text
    assert "data-autostart" in body
    assert "https://www.tiktok.com/x</textarea>" in body


def done_job(conn, draft):
    jid = jobs.create_job(conn, "https://www.tiktok.com/x")
    conn.execute(
        "UPDATE extraction_jobs SET status='done', result_json=? WHERE id=?",
        (json.dumps(draft.to_dict()), jid),
    )
    return jid


DRAFT = RecipeDraft(
    found_recipe=True,
    name="Garlic Shrimp",
    servings=2,
    ingredients=[Ingredient(item="shrimp", quantity=1, unit="lb", raw_text="1lb shrimp!!")],
    steps=["Cook it"],
    warnings=["Amounts weren't given for salt"],
    source_url="https://www.tiktok.com/x",
    platform="tiktok",
    thumbnail_path=THUMB,
)


def test_review_shows_draft_and_warnings(client, conn):
    jid = done_job(conn, DRAFT)
    body = client.get(f"/review/{jid}").text
    assert "Check the recipe" in body
    assert 'value="Garlic Shrimp"' in body
    assert "Amounts weren&#39;t given for salt" in body
    assert "Originally: 1lb shrimp!!" in body
    assert f'value="{THUMB}"' in body


def test_review_unfinished_job_goes_back_to_add(client, conn):
    jid = jobs.create_job(conn, "x")
    assert client.get(f"/review/{jid}").headers["location"] == "/add"
    assert client.get("/review/999").headers["location"] == "/add"


def test_review_save_creates_recipe(client, conn):
    jid = done_job(conn, DRAFT)
    form = editor_form(
        source_url=DRAFT.source_url,
        platform="tiktok",
        thumbnail_path=THUMB,
        step=["Cook it"],
    )
    resp = client.post(f"/review/{jid}", data=form)
    assert resp.status_code == 303
    rid = int(resp.headers["location"].rsplit("/", 1)[1])
    r = recipes.get_recipe(conn, rid)
    assert r.name == "Garlic Shrimp"
    assert (r.source_url, r.platform, r.thumbnail_path, r.steps) == (
        DRAFT.source_url,
        "tiktok",
        THUMB,
        ["Cook it"],
    )
    assert r.ingredients[0].raw_text == "1 lb shrimp, peeled"


def test_review_save_rejects_unsafe_fields(client, conn):
    jid = done_job(conn, DRAFT)
    form = editor_form(source_url="javascript:alert(1)", platform="evil", thumbnail_path="../x.jpg")
    rid = int(client.post(f"/review/{jid}", data=form).headers["location"].rsplit("/", 1)[1])
    r = recipes.get_recipe(conn, rid)
    assert (r.source_url, r.platform, r.thumbnail_path) == (None, None, None)


def test_review_save_with_errors_rerenders(client, conn):
    jid = done_job(conn, DRAFT)
    resp = client.post(f"/review/{jid}", data=editor_form(name=""))
    assert resp.status_code == 400
    assert "Give the recipe a name" in resp.text
    assert recipes.list_recipes(conn) == []


# --- this week --------------------------------------------------------------------------


def test_week_empty_state(client):
    assert "No meals picked yet" in client.get("/week").text


def test_week_list_combines_and_ticks(client, conn):
    a = make_recipe(conn, "Tacos")
    b = recipes.create_recipe(
        conn,
        Recipe(
            name="Soup",
            ingredients=[
                Ingredient(item="onion", quantity=1, section="Produce"),
                Ingredient(item="salt", section="Spices"),
            ],
        ),
    )
    recipes.add_to_week(conn, a)
    recipes.add_to_week(conn, b)
    body = client.get("/week").text
    assert "1½ onion" in body
    assert "2 lb beef chuck" in body
    assert "Produce\n1½ onion\nMeat &amp; Seafood\n2 lb beef chuck\nSpices\nsalt" in body

    resp = client.post("/week/check", data={"item_key": "salt", "checked": "1"})
    assert resp.status_code == 303
    body = client.get("/week").text
    assert 'aria-checked="true"' in body
    assert "Spices\nsalt" not in body  # ticked items aren't copied

    client.post("/week/check", data={"item_key": "salt", "checked": ""})
    assert recipes.checked_items(conn) == set()


def test_clear_week(client, conn):
    rid = make_recipe(conn)
    recipes.add_to_week(conn, rid)
    recipes.set_checked(conn, "onion", True)
    resp = client.post("/week/clear?next=/week")
    assert resp.headers["location"] == "/week"
    assert recipes.week_recipe_ids(conn) == [] and recipes.checked_items(conn) == set()
    assert recipes.get_recipe(conn, rid) is not None


def test_static_assets(client):
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


# --- home-screen app ----------------------------------------------------------------


def test_manifest_and_icons_are_public(settings):
    # iOS and Android fetch these without the session cookie.
    with TestClient(create_app(settings, runner=no_runner), follow_redirects=False) as c:
        resp = c.get("/static/manifest.json")
        assert resp.status_code == 200
        manifest = json.loads(resp.content)
        assert manifest["start_url"] == "/" and manifest["display"] == "standalone"
        sizes = {icon["sizes"] for icon in manifest["icons"]}
        assert {"192x192", "512x512"} <= sizes
        for icon in manifest["icons"]:
            png = c.get(icon["src"])
            assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n", icon
            assert png.headers["content-type"] == "image/png"
        touch = c.get("/static/icons/apple-touch-icon.png")
        assert touch.status_code == 200 and touch.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_pages_link_manifest_and_apple_tags(client):
    for path in ["/", "/week", "/add", "/login"]:
        body = client.get(path).text
        assert '<link rel="manifest" href="/static/manifest.json">' in body, path
        assert 'rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png"' in body, path
        assert '<meta name="apple-mobile-web-app-capable" content="yes">' in body, path
        assert '<meta name="apple-mobile-web-app-title" content="Meals">' in body, path
