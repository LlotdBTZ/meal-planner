"""Recipes, ingredients, this week's meals, and grocery-list ticks."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.db import transaction

SECTIONS: tuple[str, ...] = (
    "Produce",
    "Meat & Seafood",
    "Dairy & Eggs",
    "Bakery",
    "Pantry",
    "Spices",
    "Frozen",
    "Other",
)


@dataclass
class Ingredient:
    item: str
    quantity: float | None = None
    unit: str | None = None
    note: str | None = None
    section: str = "Other"
    raw_text: str | None = None
    id: int | None = None
    position: int = 0


@dataclass
class Recipe:
    name: str
    ingredients: list[Ingredient] = field(default_factory=list)
    servings: int | None = None
    source_url: str | None = None
    platform: str | None = None
    thumbnail_path: str | None = None
    notes: str | None = None
    steps: list[str] | None = None
    id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class RecipeSummary:
    id: int
    name: str
    thumbnail_path: str | None
    in_week: bool
    created_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _clean_section(section: str | None) -> str:
    return section if section in SECTIONS else "Other"


def _recipe_values(recipe: Recipe) -> dict:
    name = (recipe.name or "").strip()
    if not name:
        raise ValueError("Recipe name is required")
    return {
        "name": name,
        "servings": recipe.servings,
        "source_url": recipe.source_url,
        "platform": recipe.platform,
        "thumbnail_path": recipe.thumbnail_path,
        "notes": recipe.notes,
        "steps": json.dumps(recipe.steps) if recipe.steps is not None else None,
    }


def _insert_ingredients(
    conn: sqlite3.Connection, recipe_id: int, ingredients: list[Ingredient]
) -> None:
    conn.executemany(
        """INSERT INTO ingredients
           (recipe_id, position, quantity, unit, item, note, section, raw_text)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                recipe_id,
                pos,
                ing.quantity,
                ing.unit,
                ing.item.strip(),
                ing.note,
                _clean_section(ing.section),
                ing.raw_text,
            )
            for pos, ing in enumerate(ingredients)
        ],
    )


def create_recipe(conn: sqlite3.Connection, recipe: Recipe) -> int:
    values = _recipe_values(recipe)
    now = _now()
    with transaction(conn):
        cur = conn.execute(
            """INSERT INTO recipes
               (name, servings, source_url, platform, thumbnail_path, notes, steps,
                created_at, updated_at)
               VALUES (:name, :servings, :source_url, :platform, :thumbnail_path, :notes,
                       :steps, :now, :now)""",
            {**values, "now": now},
        )
        recipe_id = cur.lastrowid
        _insert_ingredients(conn, recipe_id, recipe.ingredients)
    return recipe_id


def _ingredients_for(conn: sqlite3.Connection, recipe_id: int) -> list[Ingredient]:
    rows = conn.execute(
        "SELECT * FROM ingredients WHERE recipe_id = ? ORDER BY position", (recipe_id,)
    )
    return [
        Ingredient(
            id=r["id"],
            position=r["position"],
            quantity=r["quantity"],
            unit=r["unit"],
            item=r["item"],
            note=r["note"],
            section=r["section"],
            raw_text=r["raw_text"],
        )
        for r in rows
    ]


def _row_to_recipe(conn: sqlite3.Connection, row: sqlite3.Row) -> Recipe:
    return Recipe(
        id=row["id"],
        name=row["name"],
        servings=row["servings"],
        source_url=row["source_url"],
        platform=row["platform"],
        thumbnail_path=row["thumbnail_path"],
        notes=row["notes"],
        steps=json.loads(row["steps"]) if row["steps"] is not None else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        ingredients=_ingredients_for(conn, row["id"]),
    )


def get_recipe(conn: sqlite3.Connection, recipe_id: int) -> Recipe | None:
    row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    return _row_to_recipe(conn, row) if row else None


def list_recipes(conn: sqlite3.Connection, search: str | None = None) -> list[RecipeSummary]:
    sql = """SELECT r.id, r.name, r.thumbnail_path, r.created_at,
                    (w.recipe_id IS NOT NULL) AS in_week
             FROM recipes r LEFT JOIN week_selection w ON w.recipe_id = r.id"""
    params: list = []
    if search and search.strip():
        escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        sql += " WHERE r.name LIKE ? ESCAPE '\\'"
        params.append(f"%{escaped}%")
    sql += " ORDER BY r.created_at DESC, r.id DESC"
    return [
        RecipeSummary(
            id=r["id"],
            name=r["name"],
            thumbnail_path=r["thumbnail_path"],
            in_week=bool(r["in_week"]),
            created_at=r["created_at"],
        )
        for r in conn.execute(sql, params)
    ]


def update_recipe(conn: sqlite3.Connection, recipe_id: int, recipe: Recipe) -> bool:
    values = _recipe_values(recipe)
    with transaction(conn):
        cur = conn.execute(
            """UPDATE recipes SET name = :name, servings = :servings,
                   source_url = :source_url, platform = :platform,
                   thumbnail_path = :thumbnail_path, notes = :notes, steps = :steps,
                   updated_at = :now
               WHERE id = :id""",
            {**values, "now": _now(), "id": recipe_id},
        )
        if cur.rowcount == 0:
            return False
        conn.execute("DELETE FROM ingredients WHERE recipe_id = ?", (recipe_id,))
        _insert_ingredients(conn, recipe_id, recipe.ingredients)
    return True


def delete_recipe(conn: sqlite3.Connection, recipe_id: int) -> bool:
    cur = conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
    return cur.rowcount > 0


# --- This week -------------------------------------------------------------


def add_to_week(conn: sqlite3.Connection, recipe_id: int) -> bool:
    if not conn.execute("SELECT 1 FROM recipes WHERE id = ?", (recipe_id,)).fetchone():
        return False
    conn.execute(
        "INSERT OR IGNORE INTO week_selection (recipe_id, added_at) VALUES (?, ?)",
        (recipe_id, _now()),
    )
    return True


def remove_from_week(conn: sqlite3.Connection, recipe_id: int) -> None:
    conn.execute("DELETE FROM week_selection WHERE recipe_id = ?", (recipe_id,))


def week_recipe_ids(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute("SELECT recipe_id FROM week_selection ORDER BY added_at, recipe_id")
    return [r["recipe_id"] for r in rows]


def week_recipes(conn: sqlite3.Connection) -> list[Recipe]:
    return [r for rid in week_recipe_ids(conn) if (r := get_recipe(conn, rid))]


def clear_week(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        conn.execute("DELETE FROM week_selection")
        conn.execute("DELETE FROM list_checks")


# --- "Already have it" ticks on the grocery list ----------------------------


def set_checked(conn: sqlite3.Connection, item_key: str, checked: bool) -> None:
    if checked:
        conn.execute("INSERT OR IGNORE INTO list_checks (item_key) VALUES (?)", (item_key,))
    else:
        conn.execute("DELETE FROM list_checks WHERE item_key = ?", (item_key,))


def checked_items(conn: sqlite3.Connection) -> set[str]:
    return {r["item_key"] for r in conn.execute("SELECT item_key FROM list_checks")}
