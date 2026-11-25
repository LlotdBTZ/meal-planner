"""The recipe draft produced by extraction, its JSON schema, and validation.

A draft is what the review screen shows; nothing is saved until the user
confirms it (design §2 anti-goals).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from app.recipes import SECTIONS, Ingredient


class ExtractionError(Exception):
    """A failure with a plain-English message that can be shown to the user."""


@dataclass
class RecipeDraft:
    found_recipe: bool
    name: str = ""
    servings: int | None = None
    ingredients: list[Ingredient] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_url: str | None = None
    platform: str | None = None
    thumbnail_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecipeDraft:
        data = dict(data)
        data["ingredients"] = [Ingredient(**i) for i in data.get("ingredients", [])]
        return cls(**data)


_NULLABLE_STRING = {"type": ["string", "null"]}

# JSON schema sent to Claude as a structured-output format (design §6.4).
EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "found_recipe": {"type": "boolean"},
        "name": {"type": "string"},
        "servings": {"type": ["integer", "null"]},
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quantity": {"type": ["number", "null"]},
                    "unit": _NULLABLE_STRING,
                    "item": {"type": "string"},
                    "note": _NULLABLE_STRING,
                    "section": {"type": "string", "enum": list(SECTIONS)},
                    "raw_text": {"type": "string"},
                },
                "required": ["quantity", "unit", "item", "note", "section", "raw_text"],
                "additionalProperties": False,
            },
        },
        "steps": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["found_recipe", "name", "servings", "ingredients", "steps", "warnings"],
    "additionalProperties": False,
}

_UNICODE_FRACTIONS = {
    "½": 0.5,
    "⅓": 1 / 3,
    "⅔": 2 / 3,
    "¼": 0.25,
    "¾": 0.75,
    "⅛": 0.125,
    "⅜": 0.375,
    "⅝": 0.625,
    "⅞": 0.875,
}


def parse_quantity(value: Any) -> float | None:
    """Accept numbers or strings like "2", "1/2", "1 1/2", "1½", "2-3" (upper bound)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value) if value > 0 else None
    text = str(value).strip()
    if not text:
        return None
    for ch, frac in _UNICODE_FRACTIONS.items():
        text = text.replace(ch, f" {frac}")
    # ranges: buy enough for the upper end
    parts = re.split(r"\s*(?:-|–|to)\s*", text)
    text = parts[-1].strip()
    total = 0.0
    for token in text.split():
        try:
            if "/" in token:
                num, den = token.split("/", 1)
                total += float(num) / float(den)
            else:
                total += float(token)
        except (ValueError, ZeroDivisionError):
            return None
    return total if total > 0 else None


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def parse_draft(data: Any) -> RecipeDraft:
    """Validate Claude's JSON leniently; never trust it to be perfectly shaped."""
    if not isinstance(data, dict):
        raise ExtractionError("The recipe reader returned something unexpected. Try again.")

    ingredients: list[Ingredient] = []
    for raw in data.get("ingredients") or []:
        if not isinstance(raw, dict):
            continue
        item = _clean_str(raw.get("item"))
        if not item:
            continue
        section = raw.get("section")
        ingredients.append(
            Ingredient(
                item=item.lower(),
                quantity=parse_quantity(raw.get("quantity")),
                unit=_clean_str(raw.get("unit")),
                note=_clean_str(raw.get("note")),
                section=section if section in SECTIONS else "Other",
                raw_text=_clean_str(raw.get("raw_text")),
                position=len(ingredients),
            )
        )

    servings = data.get("servings")
    if isinstance(servings, bool) or not isinstance(servings, int | float) or servings <= 0:
        servings = None

    def str_list(key: str) -> list[str]:
        return [s for v in (data.get(key) or []) if (s := _clean_str(v))]

    return RecipeDraft(
        found_recipe=bool(data.get("found_recipe")) and bool(ingredients),
        name=_clean_str(data.get("name")) or "",
        servings=int(servings) if servings else None,
        ingredients=ingredients,
        steps=str_list("steps"),
        warnings=str_list("warnings"),
    )
