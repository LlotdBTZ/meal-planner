"""Plain-text grocery list for pasting into iPhone Notes (design §6.6).

One line per item, grouped under plain section-name lines, in store-section
order. Items ticked as "already have it" are left out; empty sections are dropped.
In Notes: paste, select all, tap the checklist button.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.grocery import ListLine
from app.recipes import SECTIONS


def to_notes_text(lines: Iterable[ListLine], checked: set[str] | None = None) -> str:
    checked = checked or set()
    by_section: dict[str, list[str]] = {s: [] for s in SECTIONS}
    for line in lines:
        if line.key in checked:
            continue
        section = line.section if line.section in by_section else "Other"
        by_section[section].append(line.text)

    out: list[str] = []
    for section, texts in by_section.items():
        if texts:
            out.append(section)
            out.extend(texts)
    return "\n".join(out)
