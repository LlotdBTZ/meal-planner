import pytest

from app.extraction.schema import (
    EXTRACTION_SCHEMA,
    ExtractionError,
    RecipeDraft,
    parse_draft,
    parse_quantity,
)
from app.recipes import SECTIONS


def valid():
    return {
        "found_recipe": True,
        "name": "Birria Tacos",
        "servings": 4,
        "ingredients": [
            {
                "quantity": 2,
                "unit": "lb",
                "item": "Beef Chuck",
                "note": None,
                "section": "Meat & Seafood",
                "raw_text": "2lb chuck roast",
            },
            {
                "quantity": None,
                "unit": None,
                "item": "salt",
                "note": "to taste",
                "section": "Spices",
                "raw_text": "salt to taste",
            },
        ],
        "steps": ["Braise", "  Fry  "],
        "warnings": ["Amounts not stated for salt"],
    }


def test_valid_draft():
    d = parse_draft(valid())
    assert d.found_recipe is True
    assert d.name == "Birria Tacos"
    assert d.servings == 4
    assert [(i.item, i.quantity, i.unit, i.section) for i in d.ingredients] == [
        ("beef chuck", 2.0, "lb", "Meat & Seafood"),
        ("salt", None, None, "Spices"),
    ]
    assert d.ingredients[1].note == "to taste"
    assert d.ingredients[0].raw_text == "2lb chuck roast"
    assert d.steps == ["Braise", "Fry"]
    assert d.warnings == ["Amounts not stated for salt"]


def test_missing_fields_are_tolerated():
    d = parse_draft({"found_recipe": True, "ingredients": [{"item": "egg"}]})
    assert d.name == ""
    assert d.servings is None
    assert d.ingredients[0].section == "Other"
    assert d.steps == [] and d.warnings == []


def test_bad_section_becomes_other_and_blank_items_dropped():
    data = valid()
    data["ingredients"][0]["section"] = "Aisle 9"
    data["ingredients"].append({"item": "  ", "section": "Produce"})
    data["ingredients"].append("not a dict")
    d = parse_draft(data)
    assert d.ingredients[0].section == "Other"
    assert len(d.ingredients) == 2


def test_found_recipe_false_without_ingredients():
    data = valid()
    data["ingredients"] = []
    assert parse_draft(data).found_recipe is False


def test_bad_servings_ignored():
    for bad in ["4", -1, 0, True]:
        data = valid()
        data["servings"] = bad
        assert parse_draft(data).servings is None


def test_not_a_dict_raises_friendly_error():
    with pytest.raises(ExtractionError):
        parse_draft(["nope"])


@pytest.mark.parametrize(
    "value, expected",
    [
        (2, 2.0),
        (0.5, 0.5),
        ("1/2", 0.5),
        ("1 1/2", 1.5),
        ("1½", 1.5),
        ("½", 0.5),
        ("2-3", 3.0),
        ("2 to 3", 3.0),
        ("", None),
        ("a few", None),
        (None, None),
        (0, None),
        ("1/0", None),
        (True, None),
    ],
)
def test_parse_quantity(value, expected):
    result = parse_quantity(value)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


def test_draft_round_trips_through_dict():
    d = parse_draft(valid())
    d.source_url = "https://x"
    assert RecipeDraft.from_dict(d.to_dict()) == d


def test_schema_sections_match_app_sections():
    item_schema = EXTRACTION_SCHEMA["properties"]["ingredients"]["items"]
    assert item_schema["properties"]["section"]["enum"] == list(SECTIONS)
    assert item_schema["additionalProperties"] is False
    assert set(item_schema["required"]) == set(item_schema["properties"])
    assert set(EXTRACTION_SCHEMA["required"]) == set(EXTRACTION_SCHEMA["properties"])
