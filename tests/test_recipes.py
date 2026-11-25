import pytest

from app import db, recipes
from app.recipes import Ingredient, Recipe


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.migrate(c)
    yield c
    c.close()


def tacos() -> Recipe:
    return Recipe(
        name="Birria Tacos",
        servings=4,
        source_url="https://www.tiktok.com/@chef/video/1",
        platform="tiktok",
        steps=["Braise beef", "Fry tortillas"],
        ingredients=[
            Ingredient(item="beef chuck", quantity=2, unit="lb", section="Meat & Seafood"),
            Ingredient(item="onion", quantity=1, note="diced", section="Produce"),
            Ingredient(item="salt", section="Spices", raw_text="salt to taste"),
        ],
    )


def test_create_and_get_round_trip(conn):
    rid = recipes.create_recipe(conn, tacos())
    r = recipes.get_recipe(conn, rid)
    assert r is not None
    assert r.id == rid
    assert r.name == "Birria Tacos"
    assert r.servings == 4
    assert r.platform == "tiktok"
    assert r.steps == ["Braise beef", "Fry tortillas"]
    assert r.created_at and r.updated_at
    assert [i.item for i in r.ingredients] == ["beef chuck", "onion", "salt"]
    onion = r.ingredients[1]
    assert (onion.quantity, onion.unit, onion.note, onion.section) == (1, None, "diced", "Produce")
    assert r.ingredients[2].quantity is None
    assert r.ingredients[2].raw_text == "salt to taste"


def test_get_missing_returns_none(conn):
    assert recipes.get_recipe(conn, 999) is None


def test_unknown_section_becomes_other(conn):
    r = Recipe(name="X", ingredients=[Ingredient(item="thing", section="Aisle 9")])
    rid = recipes.create_recipe(conn, r)
    assert recipes.get_recipe(conn, rid).ingredients[0].section == "Other"


def test_create_requires_name(conn):
    with pytest.raises(ValueError):
        recipes.create_recipe(conn, Recipe(name="  ", ingredients=[]))


def test_list_newest_first_and_search(conn):
    recipes.create_recipe(conn, Recipe(name="Chicken Curry", ingredients=[]))
    recipes.create_recipe(conn, Recipe(name="Beef Stew", ingredients=[]))
    recipes.create_recipe(conn, Recipe(name="chicken soup", ingredients=[]))
    assert [r.name for r in recipes.list_recipes(conn)] == [
        "chicken soup",
        "Beef Stew",
        "Chicken Curry",
    ]
    assert [r.name for r in recipes.list_recipes(conn, search="CHICKEN")] == [
        "chicken soup",
        "Chicken Curry",
    ]


def test_search_treats_wildcards_literally(conn):
    recipes.create_recipe(conn, Recipe(name="100% Rye Bread", ingredients=[]))
    recipes.create_recipe(conn, Recipe(name="Rye Bread", ingredients=[]))
    assert [r.name for r in recipes.list_recipes(conn, search="100%")] == ["100% Rye Bread"]
    assert recipes.list_recipes(conn, search="_") == []


def test_list_shows_week_flag(conn):
    a = recipes.create_recipe(conn, Recipe(name="A", ingredients=[]))
    recipes.create_recipe(conn, Recipe(name="B", ingredients=[]))
    recipes.add_to_week(conn, a)
    flags = {r.name: r.in_week for r in recipes.list_recipes(conn)}
    assert flags == {"A": True, "B": False}


def test_update_replaces_fields_and_ingredients(conn):
    rid = recipes.create_recipe(conn, tacos())
    before = recipes.get_recipe(conn, rid)
    edited = Recipe(
        name="Better Tacos",
        servings=6,
        source_url=before.source_url,
        platform="tiktok",
        ingredients=[Ingredient(item="beef chuck", quantity=3, unit="lb")],
    )
    assert recipes.update_recipe(conn, rid, edited) is True
    after = recipes.get_recipe(conn, rid)
    assert after.name == "Better Tacos"
    assert after.servings == 6
    assert after.created_at == before.created_at
    assert [(i.item, i.quantity) for i in after.ingredients] == [("beef chuck", 3)]
    assert conn.execute("SELECT COUNT(*) FROM ingredients").fetchone()[0] == 1


def test_update_missing_returns_false(conn):
    assert recipes.update_recipe(conn, 999, Recipe(name="X", ingredients=[])) is False


def test_delete_cascades(conn):
    rid = recipes.create_recipe(conn, tacos())
    recipes.add_to_week(conn, rid)
    assert recipes.delete_recipe(conn, rid) is True
    assert recipes.get_recipe(conn, rid) is None
    assert conn.execute("SELECT COUNT(*) FROM ingredients").fetchone()[0] == 0
    assert recipes.week_recipe_ids(conn) == []
    assert recipes.delete_recipe(conn, rid) is False


def test_week_add_remove_is_idempotent(conn):
    a = recipes.create_recipe(conn, Recipe(name="A", ingredients=[]))
    b = recipes.create_recipe(conn, Recipe(name="B", ingredients=[]))
    recipes.add_to_week(conn, a)
    recipes.add_to_week(conn, a)
    recipes.add_to_week(conn, b)
    assert recipes.week_recipe_ids(conn) == [a, b]
    recipes.remove_from_week(conn, a)
    recipes.remove_from_week(conn, a)
    assert recipes.week_recipe_ids(conn) == [b]


def test_add_missing_recipe_to_week_returns_false(conn):
    assert recipes.add_to_week(conn, 999) is False
    assert recipes.week_recipe_ids(conn) == []


def test_week_recipes_include_ingredients(conn):
    rid = recipes.create_recipe(conn, tacos())
    recipes.add_to_week(conn, rid)
    [r] = recipes.week_recipes(conn)
    assert r.name == "Birria Tacos"
    assert len(r.ingredients) == 3


def test_list_checks_and_clear_week(conn):
    rid = recipes.create_recipe(conn, tacos())
    recipes.add_to_week(conn, rid)
    recipes.set_checked(conn, "onion", True)
    recipes.set_checked(conn, "salt", True)
    recipes.set_checked(conn, "salt", True)
    recipes.set_checked(conn, "onion", False)
    assert recipes.checked_items(conn) == {"salt"}
    recipes.clear_week(conn)
    assert recipes.week_recipe_ids(conn) == []
    assert recipes.checked_items(conn) == set()
    assert recipes.get_recipe(conn, rid) is not None
