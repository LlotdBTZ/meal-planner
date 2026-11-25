"""Recipe blogs and other pages: JSON-LD Recipe data, or the page's visible text.

JSON-LD gives clean ingredient lines, which are still sent to Claude to split
into quantity/unit/item/section (cheap, because the text is short).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Any

import httpx2

from app.extraction.schema import ExtractionError

MAX_PAGE_BYTES = 3 * 1024 * 1024
MAX_TEXT_CHARS = 60_000
USER_AGENT = "Mozilla/5.0 (compatible; meal-planner/0.1; personal recipe saver)"


@dataclass
class PageContent:
    text: str
    image_url: str | None = None
    truncated: bool = False


class _PageParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "nav", "header", "footer", "svg", "form", "aside"}
    BLOCK = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "tr", "section", "article"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.jsonld: list[str] = []
        self.og_image: str | None = None
        self.text_parts: list[str] = []
        self._skip_depth = 0
        self._in_jsonld = False
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
            self._in_jsonld, self._buf = True, []
        if tag == "meta" and a.get("property") == "og:image" and a.get("content"):
            self.og_image = self.og_image or a["content"]
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag in self.BLOCK:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_jsonld:
            self.jsonld.append("".join(self._buf))
            self._in_jsonld = False
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self._buf.append(data)
        elif not self._skip_depth:
            self.text_parts.append(data)

    @property
    def text(self) -> str:
        lines = (" ".join(line.split()) for line in "".join(self.text_parts).splitlines())
        return "\n".join(line for line in lines if line)


def _is_recipe(node: Any) -> bool:
    t = node.get("@type") if isinstance(node, dict) else None
    return t == "Recipe" or (isinstance(t, list) and "Recipe" in t)


def _walk(node: Any):
    if isinstance(node, list):
        for n in node:
            yield from _walk(n)
    elif isinstance(node, dict):
        yield node
        if "@graph" in node:
            yield from _walk(node["@graph"])


def find_jsonld_recipe(blocks: list[str]) -> dict[str, Any] | None:
    for raw in blocks:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for node in _walk(data):
            if _is_recipe(node):
                return node
    return None


def _as_text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(_as_text(v) for v in value)
    if isinstance(value, dict):
        return _as_text(value.get("text") or value.get("name") or "")
    return unescape(str(value or "")).strip()


def _image_url(value: Any) -> str | None:
    if isinstance(value, list):
        return _image_url(value[0]) if value else None
    if isinstance(value, dict):
        return value.get("url")
    return value or None


def recipe_to_text(recipe: dict[str, Any]) -> str:
    lines = [f"Recipe: {_as_text(recipe.get('name'))}"]
    if recipe.get("recipeYield"):
        lines.append(f"Yield: {_as_text(recipe['recipeYield'])}")
    lines.append("Ingredients:")
    lines += [f"- {_as_text(i)}" for i in recipe.get("recipeIngredient") or []]
    steps = recipe.get("recipeInstructions") or []
    if isinstance(steps, str):
        steps = [steps]
    if steps:
        lines.append("Instructions:")
        for step in steps:
            if isinstance(step, dict) and step.get("itemListElement"):
                lines += [f"- {_as_text(s)}" for s in step["itemListElement"]]
            else:
                lines.append(f"- {_as_text(step)}")
    return "\n".join(lines)


def parse_page(html: str) -> PageContent:
    parser = _PageParser()
    parser.feed(html)
    parser.close()
    recipe = find_jsonld_recipe(parser.jsonld)
    if recipe:
        return PageContent(
            text=recipe_to_text(recipe),
            image_url=_image_url(recipe.get("image")) or parser.og_image,
        )
    text = parser.text
    truncated = len(text) > MAX_TEXT_CHARS
    return PageContent(text=text[:MAX_TEXT_CHARS], image_url=parser.og_image, truncated=truncated)


def fetch_page(url: str, http: httpx2.Client) -> PageContent:
    try:
        resp = http.get(url, headers={"User-Agent": USER_AGENT})
    except httpx2.HTTPError as e:
        raise ExtractionError("Couldn't load that page.") from e
    if resp.status_code >= 400:
        raise ExtractionError(f"That page returned an error ({resp.status_code}).")
    if "html" not in resp.headers.get("content-type", "html"):
        raise ExtractionError("That link isn't a web page.")
    if len(resp.content) > MAX_PAGE_BYTES:
        raise ExtractionError("That page is too large to read.")
    return parse_page(resp.text)
