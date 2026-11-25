import pytest

from app.grocery import combine, format_quantity, normalize_unit
from app.recipes import Ingredient


def ing(item, quantity=None, unit=None, section="Other", note=None):
    return Ingredient(item=item, quantity=quantity, unit=unit, section=section, note=note)


def texts(lines):
    return [line.text for line in lines]


# --- normalize_unit ----------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, None),
        ("", None),
        ("  ", None),
        ("Tablespoons", "tbsp"),
        ("tbs", "tbsp"),
        ("T", "tbsp"),
        ("t", "tsp"),
        ("teaspoon", "tsp"),
        ("Cups", "cup"),
        ("c", "cup"),
        ("lbs", "lb"),
        ("pound", "lb"),
        ("ounces", "oz"),
        ("grams", "g"),
        ("kilogram", "kg"),
        ("mL", "ml"),
        ("liters", "l"),
        ("fl oz", "fl oz"),
        ("Cloves", "clove"),
        ("pinches", "pinch"),
        ("bunches", "bunch"),
        ("cans", "can"),
        ("sprigs", "sprig"),
        ("Handful", "handful"),
        ("dollop", "dollop"),  # unknown units are kept, lowercased
    ],
)
def test_normalize_unit(raw, expected):
    assert normalize_unit(raw) == expected


# --- format_quantity -----------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        (1, "1"),
        (2.0, "2"),
        (0.5, "½"),
        (1.5, "1½"),
        (0.25, "¼"),
        (0.75, "¾"),
        (1 / 3, "⅓"),
        (2 + 2 / 3, "2⅔"),
        (0.125, "⅛"),
        (1.0625, "1⅛"),  # rounds up so you buy enough
        (0.9, "1"),
        (0.01, "⅛"),
        (12, "12"),
    ],
)
def test_format_quantity(value, expected):
    assert format_quantity(value) == expected


# --- combine -------------------------------------------------------------------


def test_onion_example_from_design():
    lines = combine(
        [
            ing("onion", 1, section="Produce"),
            ing("onion", 0.5, note="diced", section="Produce"),
        ]
    )
    assert texts(lines) == ["1½ onion"]
    assert lines[0].section == "Produce"
    assert lines[0].key == "onion"


def test_item_matching_ignores_case_and_spaces():
    lines = combine([ing("Garlic", 2, "cloves"), ing(" garlic ", 4, "clove")])
    assert texts(lines) == ["6 cloves garlic"]


def test_tbsp_and_cup_add_up():
    assert texts(combine([ing("olive oil", 2, "tbsp"), ing("olive oil", 2, "tbsp")])) == [
        "¼ cup olive oil"
    ]
    assert texts(combine([ing("milk", 1, "cup"), ing("milk", 0.5, "cups")])) == ["1½ cups milk"]


def test_small_volumes_stay_in_spoons():
    assert texts(combine([ing("cumin", 1, "tbsp"), ing("cumin", 2, "tbsp")])) == ["3 tbsp cumin"]
    assert texts(combine([ing("paprika", 2, "tsp"), ing("paprika", 1, "tsp")])) == [
        "1 tbsp paprika"
    ]
    assert texts(combine([ing("salt", 1, "tsp")])) == ["1 tsp salt"]
    assert texts(combine([ing("pepper", 0.5, "tsp")])) == ["½ tsp pepper"]


def test_oz_and_lb_add_up():
    assert texts(combine([ing("beef", 2, "lb"), ing("beef", 8, "oz")])) == ["2½ lb beef"]
    assert texts(combine([ing("cheese", 4, "oz"), ing("cheese", 4, "oz")])) == ["8 oz cheese"]


def test_metric_stays_metric():
    assert texts(combine([ing("rice", 500, "g"), ing("rice", 0.75, "kg")])) == ["1.25 kg rice"]
    assert texts(combine([ing("flour", 200, "g"), ing("flour", 150, "grams")])) == ["350 g flour"]
    assert texts(combine([ing("stock", 500, "ml"), ing("stock", 250, "ml")])) == ["750 ml stock"]


def test_mixed_metric_and_imperial_uses_imperial():
    assert texts(combine([ing("butter", 8, "oz"), ing("butter", 227, "g")])) == ["1 lb butter"]


def test_incompatible_units_listed_together():
    lines = combine([ing("onion", 1, section="Produce"), ing("onion", 2, "cups")])
    assert texts(lines) == ["onion — 1 + 2 cups"]


def test_no_amount_items():
    assert texts(combine([ing("salt"), ing("salt")])) == ["salt"]
    # an amount elsewhere wins over "to taste"
    assert texts(combine([ing("salt"), ing("salt", 1, "tsp")])) == ["1 tsp salt"]


def test_unknown_units_only_add_when_they_match():
    lines = combine([ing("yogurt", 1, "dollop"), ing("yogurt", 2, "dollops"), ing("yogurt", 1)])
    assert texts(lines) == ["yogurt — 3 dollops + 1"]


def test_count_units_pluralize():
    assert texts(combine([ing("tomatoes", 1, "can")])) == ["1 can tomatoes"]
    assert texts(combine([ing("tomatoes", 2, "can")])) == ["2 cans tomatoes"]
    assert texts(combine([ing("salt", 2, "pinch")])) == ["2 pinches salt"]


def test_section_is_most_common_then_first_seen():
    lines = combine(
        [
            ing("garlic", 1, section="Produce"),
            ing("garlic", 1, section="Spices"),
            ing("garlic", 1, section="Spices"),
        ]
    )
    assert lines[0].section == "Spices"
    tie = combine([ing("lime", 1, section="Produce"), ing("lime", 1, section="Other")])
    assert tie[0].section == "Produce"


def test_lines_sorted_by_store_section_then_name():
    lines = combine(
        [
            ing("salt", section="Spices"),
            ing("onion", 1, section="Produce"),
            ing("beef", 1, "lb", section="Meat & Seafood"),
            ing("garlic", 2, section="Produce"),
            ing("mystery", 1, section="Not a section"),
        ]
    )
    assert [(line.section, line.item) for line in lines] == [
        ("Produce", "garlic"),
        ("Produce", "onion"),
        ("Meat & Seafood", "beef"),
        ("Spices", "salt"),
        ("Other", "mystery"),
    ]


def test_empty_input():
    assert combine([]) == []
