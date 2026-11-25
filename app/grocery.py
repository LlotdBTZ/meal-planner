"""Combine ingredients from the week's recipes into one grocery list.

Rules (design §6.5):
- Ingredients are grouped by item name (case/space-insensitive).
- Within an item, compatible units are converted and added: volume
  (tsp/tbsp/cup/fl oz/ml/l/...), weight (oz/lb/g/kg), plain counts, and
  named units (clove, can, ...) which only add up when the unit matches.
- Incompatible amounts for the same item go on one line: "onion — 1 + 2 cups".
- Amounts are shown in friendly units and fractions, rounded *up* so you buy enough.
- Metric amounts stay metric unless mixed with imperial, in which case imperial wins.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.recipes import SECTIONS, Ingredient

# Base units: volume in ml, weight in g.
VOLUME_ML: dict[str, float] = {
    "tsp": 4.92892,
    "tbsp": 14.7868,
    "fl oz": 29.5735,
    "cup": 236.588,
    "pint": 473.176,
    "quart": 946.353,
    "gallon": 3785.41,
    "ml": 1.0,
    "l": 1000.0,
}
WEIGHT_G: dict[str, float] = {"oz": 28.3495, "lb": 453.592, "g": 1.0, "kg": 1000.0}
METRIC = {"ml", "l", "g", "kg"}

_ALIASES: dict[str, str] = {}
for _canonical, _names in {
    "tsp": ["tsp", "tsps", "teaspoon", "teaspoons"],
    "tbsp": ["tbsp", "tbsps", "tbs", "tbl", "tablespoon", "tablespoons"],
    "cup": ["cup", "cups", "c"],
    "fl oz": ["fl oz", "fl. oz", "floz", "fluid ounce", "fluid ounces"],
    "pint": ["pint", "pints", "pt"],
    "quart": ["quart", "quarts", "qt"],
    "gallon": ["gallon", "gallons", "gal"],
    "ml": ["ml", "milliliter", "milliliters", "millilitre", "millilitres"],
    "l": ["l", "liter", "liters", "litre", "litres"],
    "oz": ["oz", "ounce", "ounces"],
    "lb": ["lb", "lbs", "pound", "pounds"],
    "g": ["g", "gr", "gram", "grams"],
    "kg": ["kg", "kgs", "kilogram", "kilograms"],
}.items():
    for _name in _names:
        _ALIASES[_name] = _canonical

# Nice fractions, in ascending order, with their display characters.
_FRACTIONS: list[tuple[float, str]] = [
    (0.0, ""),
    (1 / 8, "⅛"),
    (1 / 4, "¼"),
    (1 / 3, "⅓"),
    (1 / 2, "½"),
    (2 / 3, "⅔"),
    (3 / 4, "¾"),
    (1.0, ""),
]
_TOLERANCE = 0.01  # how far a value may sit above a nice fraction and still round down to it


def normalize_unit(unit: str | None) -> str | None:
    """Map unit spellings to one canonical form; unknown units are lowercased and singular."""
    if unit is None or not unit.strip():
        return None
    raw = unit.strip().rstrip(".")
    if raw == "T":
        return "tbsp"
    if raw == "t":
        return "tsp"
    lowered = " ".join(raw.lower().split())
    if lowered in _ALIASES:
        return _ALIASES[lowered]
    return _singular(lowered)


def _singular(word: str) -> str:
    if word.endswith("es") and word[:-2].endswith(("ch", "sh", "s", "x", "z")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _plural(word: str) -> str:
    if word.endswith(("ch", "sh", "s", "x", "z")):
        return word + "es"
    return word + "s"


def format_quantity(value: float) -> str:
    """1.5 → "1½", rounding *up* to the next nice fraction (within a small tolerance)."""
    whole = math.floor(value)
    remainder = value - whole
    for fraction, symbol in _FRACTIONS:
        if fraction >= remainder - _TOLERANCE:
            if fraction == 1.0:
                whole, symbol = whole + 1, ""
            break
    if whole == 0 and not symbol:
        return "⅛" if value > 0 else "0"
    return f"{whole if whole else ''}{symbol}"


def _format_decimal(value: float) -> str:
    text = f"{math.ceil(value * 100 - 1e-6) / 100:.2f}".rstrip("0").rstrip(".")
    return text


def _with_unit(quantity_text: str, unit: str, value: float, pluralize: bool) -> str:
    if pluralize and value > 1 + _TOLERANCE:
        unit = _plural(unit)
    return f"{quantity_text} {unit}"


def _format_volume(ml: float, metric: bool) -> str:
    if metric:
        if ml >= 1000 * (1 - _TOLERANCE):
            return f"{_format_decimal(ml / 1000)} l"
        return f"{math.ceil(ml - 1e-6)} ml"
    cups = ml / VOLUME_ML["cup"]
    if cups >= 0.25 * (1 - _TOLERANCE):
        return _with_unit(format_quantity(cups), "cup", cups, pluralize=True)
    tbsp = ml / VOLUME_ML["tbsp"]
    if tbsp >= 1 - _TOLERANCE:
        return f"{format_quantity(tbsp)} tbsp"
    return f"{format_quantity(ml / VOLUME_ML['tsp'])} tsp"


def _format_weight(g: float, metric: bool) -> str:
    if metric:
        if g >= 1000 * (1 - _TOLERANCE):
            return f"{_format_decimal(g / 1000)} kg"
        return f"{math.ceil(g - 1e-6)} g"
    lb = g / WEIGHT_G["lb"]
    if lb >= 1 - _TOLERANCE:
        return f"{format_quantity(lb)} lb"
    return f"{format_quantity(g / WEIGHT_G['oz'])} oz"


@dataclass
class _Bucket:
    total: float = 0.0
    metric: bool = True


@dataclass
class ListLine:
    key: str
    item: str
    section: str
    amounts: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        if not self.amounts:
            return self.item
        if len(self.amounts) == 1:
            return f"{self.amounts[0]} {self.item}"
        return f"{self.item} — {' + '.join(self.amounts)}"


@dataclass
class _Group:
    key: str
    buckets: dict[tuple[str, str | None], _Bucket] = field(default_factory=dict)
    sections: list[str] = field(default_factory=list)


def item_key(item: str) -> str:
    return " ".join(item.lower().split())


def _bucket_key(unit: str | None) -> tuple[str, str | None]:
    if unit in VOLUME_ML:
        return ("volume", None)
    if unit in WEIGHT_G:
        return ("weight", None)
    return ("count", unit)


def _format_bucket(kind: str, unit: str | None, bucket: _Bucket) -> str:
    if kind == "volume":
        return _format_volume(bucket.total, bucket.metric)
    if kind == "weight":
        return _format_weight(bucket.total, bucket.metric)
    text = format_quantity(bucket.total)
    return _with_unit(text, unit, bucket.total, pluralize=True) if unit else text


def _pick_section(sections: list[str]) -> str:
    cleaned = [s if s in SECTIONS else "Other" for s in sections] or ["Other"]
    return max(cleaned, key=lambda s: (cleaned.count(s), -cleaned.index(s)))


def combine(ingredients: Iterable[Ingredient]) -> list[ListLine]:
    """Merge ingredients into grocery-list lines, sorted by store section then name."""
    groups: dict[str, _Group] = {}
    for ing in ingredients:
        key = item_key(ing.item)
        if not key:
            continue
        group = groups.setdefault(key, _Group(key=key))
        group.sections.append(ing.section)
        if ing.quantity is None:
            continue
        unit = normalize_unit(ing.unit)
        bucket = group.buckets.setdefault(_bucket_key(unit), _Bucket())
        if unit in VOLUME_ML:
            bucket.total += ing.quantity * VOLUME_ML[unit]
        elif unit in WEIGHT_G:
            bucket.total += ing.quantity * WEIGHT_G[unit]
        else:
            bucket.total += ing.quantity
        if unit not in METRIC:
            bucket.metric = False

    lines = [
        ListLine(
            key=g.key,
            item=g.key,
            section=_pick_section(g.sections),
            amounts=[_format_bucket(kind, unit, b) for (kind, unit), b in g.buckets.items()],
        )
        for g in groups.values()
    ]
    lines.sort(key=lambda line: (SECTIONS.index(line.section), line.item))
    return lines
