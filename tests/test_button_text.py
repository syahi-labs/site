"""A link button whose label holds a claim span must not be a flex box: flex drops the spaces around the span
("Book a30-minutecall", 2026-10-11). Every button-like rule in the stylesheets is held to it."""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUTTONS = (".cta", ".btn")


def rules(css, selector):
    return [body for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
            if selector in [s.strip() for s in sel.split(",")]]


def test_button_rules_are_not_flex_boxes():
    for sheet in sorted((REPO / "tokens").rglob("*.css")):
        css = sheet.read_text(encoding="utf-8")
        for selector in BUTTONS:
            for body in rules(css, selector):
                assert not re.search(r"display\s*:\s*(inline-)?(flex|grid)", body), (sheet.name, selector)
