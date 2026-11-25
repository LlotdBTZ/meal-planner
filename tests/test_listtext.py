from app.grocery import ListLine
from app.listtext import to_notes_text


def line(item, section, *amounts):
    return ListLine(key=item, item=item, section=section, amounts=list(amounts))


LINES = [
    line("beef chuck", "Meat & Seafood", "2 lb"),
    line("onion", "Produce", "1½"),
    line("salt", "Spices"),
    line("garlic", "Produce", "6 cloves"),
    line("mystery", "Not a section", "1"),
]


def test_format_matches_design():
    assert to_notes_text(LINES) == (
        "Produce\n"
        "1½ onion\n"
        "6 cloves garlic\n"
        "Meat & Seafood\n"
        "2 lb beef chuck\n"
        "Spices\n"
        "salt\n"
        "Other\n"
        "1 mystery"
    )


def test_checked_items_are_left_out_and_empty_sections_dropped():
    text = to_notes_text(LINES, checked={"beef chuck", "salt", "onion"})
    assert text == "Produce\n6 cloves garlic\nOther\n1 mystery"


def test_lines_keep_their_order_within_a_section():
    lines = [line("b", "Produce", "1"), line("a", "Produce", "1")]
    assert to_notes_text(lines) == "Produce\n1 b\n1 a"


def test_nothing_to_buy():
    assert to_notes_text([]) == ""
    assert to_notes_text(LINES, checked={ln.key for ln in LINES}) == ""
