"""Text parity between a snapshot of today's live page and the new page's <main>.

Every ported page is compared the same way, so the comparison lives here once:

  words(markup, scope)       the text a reader sees inside <body> (the old page) or <main> (the new page)
  apply_allowed(old, key)    the old text with each excused difference taken out, once
  link_values(markup)        every href and src, in order

"The text a reader sees" is text nodes joined the way a browser lays them out: an inline element
(a, b, span, time, small, ...) is transparent, so `by <span>day 30</span>, you` reads "by day 30, you",
and a block element (p, li, dt, h1, div, br, ...) is a break, so two paragraphs never glue into one
word. Script, style, svg, the head, and the old page's own footer, nav and canvas are not text. A tag
this module does not know counts as a block: a stray break can only make the comparison stricter.

Excused differences live in tests/parity/allowed_diffs.yaml, keyed by snapshot file name, one entry per
difference with its reason. They are the only way a word may differ. Never use one to excuse a change
of copy.
"""
import re
from html.parser import HTMLParser
from pathlib import Path

import yaml

PARITY = Path(__file__).parent / "parity"
ALLOWED_DIFFS = PARITY / "allowed_diffs.yaml"

SKIP = frozenset({"script", "style", "footer", "nav", "noscript", "canvas", "svg", "head"})
INLINE = frozenset(
    "a abbr b bdi bdo cite code data dfn em i kbd mark q s samp small span strong sub sup time u var".split()
)


class _Text(HTMLParser):
    """The text of one scope: everything inside the first <scope> element's tag, outside what SKIP holds."""

    def __init__(self, scope: str):
        super().__init__(convert_charrefs=True)
        self.scope, self.depth, self.inside, self.out = scope, 0, False, []

    def handle_starttag(self, tag, attrs):
        if tag == self.scope:
            self.inside = True
        if tag in SKIP:
            self.depth += 1
        elif tag not in INLINE:
            self.out.append(" ")

    def handle_endtag(self, tag):
        if tag in SKIP and self.depth:
            self.depth -= 1
        elif tag not in INLINE:
            self.out.append(" ")
        if tag == self.scope and self.scope == "main":
            self.inside = False

    def handle_data(self, data):
        if self.inside and not self.depth:
            self.out.append(data)


def words(markup: str, scope: str) -> str:
    """The reader's text of `scope` ("body" or "main") in `markup`, whitespace collapsed to single spaces."""
    parser = _Text(scope)
    parser.feed(markup)
    parser.close()
    return re.sub(r"\s+", " ", "".join(parser.out)).strip()


def apply_allowed(old: str, key: str, diffs: Path = ALLOWED_DIFFS) -> str:
    """`old` with each allowed difference for snapshot `key` removed, once, as a whole run of words.

    Every entry needs a reason, and an entry whose text is no longer in the old page fails: a stale
    exception must go, so the list never grows into a place copy can hide.
    """
    entries = yaml.safe_load(diffs.read_text(encoding="utf-8")) or {}
    for entry in entries.get(key, []):
        assert entry.get("reason", "").strip(), f"allowed diff {entry['text']!r} has no reason"
        pattern = r"(?<!\S)" + re.escape(entry["text"]) + r"(?!\S)"
        old, removed = re.subn(pattern, "", old, count=1)
        assert removed == 1, f"allowed diff {entry['text']!r} is not in the old page: remove the entry"
    return re.sub(r"\s+", " ", old).strip()


def link_values(markup: str) -> list[str]:
    """Every href and src value in `markup`, in document order."""
    return re.findall(r'(?:href|src)="([^"]+)"', markup)
