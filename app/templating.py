"""Shared Jinja2 templates (autoescape on) and display filters."""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.grocery import format_quantity
from app.recipes import SECTIONS

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=TEMPLATES_DIR)

_EXACT_FRACTIONS = (0.0, 0.125, 0.25, 1 / 3, 0.5, 2 / 3, 0.75)


def qty_input(value: float | None) -> str:
    """A quantity for an editable field: "1½" when exact, else a plain decimal."""
    if value is None:
        return ""
    whole, frac = divmod(value, 1)
    if any(abs(frac - f) < 1e-6 for f in _EXACT_FRACTIONS):
        return format_quantity(value)
    return f"{value:g}"


def ingredient_line(ing) -> str:
    """'2 lb beef chuck, cubed' for the recipe view."""
    parts = [qty_input(ing.quantity), ing.unit or "", ing.item]
    text = " ".join(p for p in parts if p)
    return f"{text}, {ing.note}" if ing.note else text


templates.env.filters["qty_input"] = qty_input
templates.env.filters["ingredient_line"] = ingredient_line
templates.env.globals["SECTIONS"] = SECTIONS
