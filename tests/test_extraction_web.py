import json

import httpx2
import pytest

from app.extraction.schema import ExtractionError
from app.extraction.web import fetch_page, find_jsonld_recipe, parse_page

RECIPE = {
    "@type": "Recipe",
    "name": "Chicken Curry",
    "recipeYield": ["4", "4 servings"],
    "image": [{"url": "https://blog/img.jpg"}],
    "recipeIngredient": ["1 lb chicken thighs", "1 can coconut milk", "2 tbsp curry paste"],
    "recipeInstructions": [
        {"@type": "HowToStep", "text": "Brown the chicken."},
        {"@type": "HowToSection", "itemListElement": [{"text": "Add milk &amp; paste."}]},
    ],
}


def page(jsonld=None, body="<p>Hello</p>", og=None):
    head = ""
    if jsonld is not None:
        head += f'<script type="application/ld+json">{json.dumps(jsonld)}</script>'
    if og:
        head += f'<meta property="og:image" content="{og}">'
    return f"<html><head>{head}</head><body>{body}</body></html>"


def test_jsonld_recipe_becomes_clean_text():
    content = parse_page(page(RECIPE, body="<p>Long life story...</p>"))
    assert content.text == (
        "Recipe: Chicken Curry\n"
        "Yield: 4, 4 servings\n"
        "Ingredients:\n"
        "- 1 lb chicken thighs\n"
        "- 1 can coconut milk\n"
        "- 2 tbsp curry paste\n"
        "Instructions:\n"
        "- Brown the chicken.\n"
        "- Add milk & paste."
    )
    assert content.image_url == "https://blog/img.jpg"
    assert "life story" not in content.text


def test_jsonld_inside_graph_and_type_list():
    graph = {"@graph": [{"@type": "WebPage"}, {**RECIPE, "@type": ["Recipe", "Thing"]}]}
    assert find_jsonld_recipe([json.dumps(graph)])["name"] == "Chicken Curry"
    assert find_jsonld_recipe(["not json", json.dumps([RECIPE])])["name"] == "Chicken Curry"
    assert find_jsonld_recipe([json.dumps({"@type": "Article"})]) is None


def test_without_jsonld_uses_visible_text_and_og_image():
    html = page(
        body="<nav>Menu</nav><h1>Soup</h1><script>var x=1</script>"
        "<ul><li>2 cups stock</li><li>1 onion</li></ul><footer>(c)</footer>",
        og="https://blog/og.jpg",
    )
    content = parse_page(html)
    assert content.text == "Soup\n2 cups stock\n1 onion"
    assert content.image_url == "https://blog/og.jpg"
    assert content.truncated is False


def test_long_pages_are_truncated_and_flagged(monkeypatch):
    from app.extraction import web

    monkeypatch.setattr(web, "MAX_TEXT_CHARS", 10)
    content = parse_page(page(body="<p>" + "x" * 50 + "</p>"))
    assert len(content.text) == 10
    assert content.truncated is True


def client(handler):
    return httpx2.Client(transport=httpx2.MockTransport(handler))


def test_fetch_page():
    def handler(request):
        assert "meal-planner" in request.headers["user-agent"]
        return httpx2.Response(200, text=page(RECIPE), headers={"content-type": "text/html"})

    assert fetch_page("https://blog/x", client(handler)).text.startswith("Recipe: Chicken Curry")


@pytest.mark.parametrize(
    "response, message",
    [
        (httpx2.Response(404, headers={"content-type": "text/html"}), "error \\(404\\)"),
        (
            httpx2.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"}),
            "isn't a web page",
        ),
    ],
)
def test_fetch_page_errors(response, message):
    with pytest.raises(ExtractionError, match=message):
        fetch_page("https://blog/x", client(lambda r: response))


def test_fetch_page_network_error():
    def handler(request):
        raise httpx2.ConnectError("down")

    with pytest.raises(ExtractionError, match="Couldn't load"):
        fetch_page("https://blog/x", client(handler))
