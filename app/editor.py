"""Parse and validate the recipe editor form (shared by Review and Edit)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from starlette.datastructures import FormData

from app.extraction.schema import parse_quantity
from app.recipes import SECTIONS, Ingredient, Recipe

_THUMBNAIL_NAME = re.compile(r"^[0-9a-f]{32}\.(?:jpg|png|webp)$")
_PLATFORMS = {"tiktok", "instagram", "youtube", "web"}


def safe_thumbnail(name: str | None) -> str | None:
    """Only accept thumbnail names the app itself generates (no paths)."""
    return name if name and _THUMBNAIL_NAME.match(name) else None


def _text(form: FormData, key: str, limit: int = 500) -> str | None:
    value = " ".join(str(form.get(key) or "").split())[:limit]
    return value or None


@dataclass
class EditorResult:
    recipe: Recipe
    errors: list[str] = field(default_factory=list)


def parse_editor_form(form: FormData) -> EditorResult:
    errors: list[str] = []
    name = _text(form, "name", 200) or ""
    if not name:
        errors.append("Give the recipe a name.")

    servings_raw = _text(form, "servings", 10)
    servings = None
    if servings_raw:
        if servings_raw.isdigit() and 0 < int(servings_raw) <= 100:
            servings = int(servings_raw)
        else:
            errors.append("Servings should be a whole number.")

    columns = {k: form.getlist(k) for k in ("qty", "unit", "item", "note", "section", "raw")}
    rows = max((len(v) for v in columns.values()), default=0)
    ingredients: list[Ingredient] = []
    for i in range(rows):

        def cell(key: str, limit: int = 200, i: int = i) -> str | None:
            values = columns[key]
            value = " ".join(str(values[i]).split())[:limit] if i < len(values) else ""
            return value or None

        item, qty_text = cell("item"), cell("qty", 20)
        if not item:
            if qty_text or cell("unit") or cell("note"):
                errors.append(f"Row {i + 1} has an amount but no ingredient.")
            continue
        quantity = parse_quantity(qty_text) if qty_text else None
        if qty_text and quantity is None:
            errors.append(
                f"“{qty_text}” for {item} isn't an amount. Use numbers like 2, ½, or 1 1/2."
            )
        section = cell("section")
        ingredients.append(
            Ingredient(
                item=item.lower(),
                quantity=quantity,
                unit=cell("unit", 30),
                note=cell("note"),
                section=section if section in SECTIONS else "Other",
                raw_text=cell("raw", 300),
                position=len(ingredients),
            )
        )
    if not ingredients:
        errors.append("Add at least one ingredient.")

    platform = _text(form, "platform", 20)
    source_url = _text(form, "source_url", 2000)
    if source_url and not source_url.startswith(("http://", "https://")):
        source_url = None
    steps = [s for s in (" ".join(x.split()) for x in form.getlist("step")) if s]

    recipe = Recipe(
        name=name,
        servings=servings,
        ingredients=ingredients,
        source_url=source_url,
        platform=platform if platform in _PLATFORMS else None,
        thumbnail_path=safe_thumbnail(_text(form, "thumbnail_path", 60)),
        notes=_text(form, "notes", 2000),
        steps=steps or None,
    )
    return EditorResult(recipe=recipe, errors=errors)
