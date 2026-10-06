"""Text parity between a snapshot of today's live page and the new page's <main>.

Every ported page is compared the same way, so the comparison lives here once:

  words(markup, scope)       the text a reader sees inside <body> (the old page) or <main> (the new page)
  apply_allowed(old, key)    the old text with each excused difference taken out, once
  link_values(markup)        every href and src, in order
  apply_link_moves(values)   the old page's links with each deliberate move applied (LINK_MOVES)
  moves_used(values)         which moves matched, so a stale move can be found

"The text a reader sees" is text nodes joined the way a browser lays them out: an inline element
(a, b, span, time, small, ...) is transparent, so `by <span>day 30</span>, you` reads "by day 30, you",
and a block element (p, li, dt, h1, div, br, ...) is a break, so two paragraphs never glue into one
word. Script, style, svg, the head, and the old page's own footer, nav and canvas are not text. A tag
this module does not know counts as a block: a stray break can only make the comparison stricter.

Excused differences live in tests/parity/allowed_diffs.yaml, keyed by snapshot file name, one entry per
difference with its reason. They are the only way a word may differ. Never use one to excuse a change
of copy.

Links are compared the same way: a ported page's links are the old page's, in order, except for the
moves in LINK_MOVES, each with its reason. They are the only way a link may differ.
"""
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import NamedTuple

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


class LinkMove(NamedTuple):
    """One deliberate change of a link between today's page and its port, and why.

    `old` is matched exactly, or, when `host` is true, as a whole origin: the origin itself or any path,
    query or fragment under it, and nothing on a different host (`https://a.example` is not
    `https://a.example.other.example`).
    """
    old: str
    new: str
    reason: str
    host: bool = False


LINK_MOVES = (
    LinkMove("https://signet.syahi.sh", "/signet", host=True, reason=(
        "Signet's page moves into the one site at /signet, so a link to it points there and skips a redirect hop.")),
    LinkMove("https://services.syahi.sh", "/services/quote", host=True, reason=(
        "The Quote in Ten Minutes page moves into the one site at /services/quote, so any link to the old host points there.")),
    LinkMove("https://katha.syahi.sh/", "/katha", reason=(
        "The Katha card goes to the publisher pitch, which is now also a page of the one site at /katha.")),
    LinkMove("art/inkpot.webp", "/assets/img/inkpot.webp", reason=(
        "Same file bytes; the shared assets tree replaces the old art folder, which the new build does not serve.")),
    LinkMove("art/loom.webp", "/assets/img/loom.webp", reason=(
        "Same file bytes; the shared assets tree replaces the old art folder, which the new build does not serve.")),
    LinkMove("art/gramophone.webp", "/assets/img/gramophone.webp", reason=(
        "Same file bytes; the shared assets tree replaces the old art folder, which the new build does not serve.")),
    LinkMove("art/cube.webp", "/assets/img/cube.webp", reason=(
        "Same file bytes; the shared assets tree replaces the old art folder, which the new build does not serve.")),
    LinkMove("https://syahi.sh/art/gramophone.webp", "/assets/img/gramophone.webp", reason=(
        "Same file bytes; the katha pitch no longer hotlinks the other host, each host serves its own copy from /assets/img.")),
    # Signet's and the services page's own footers linked the main site by its full address, because they lived on
    # another host. In the one site the same pages are linked by path. Each lands in the shared header or footer,
    # which replace that nav.
    LinkMove("https://syahi.sh/", "/", reason=(
        "Signet's page moves into the one site, so its footer's link to the main site is the shared wordmark's link to the home page.")),
    LinkMove("https://syahi.sh", "/", reason=(
        "The services page's own footer linked the main site by its bare address, because it lived on another host. "
        "In the one site that link is the shared wordmark's link to the home page.")),
    LinkMove("https://syahi.sh/contact", "/contact", reason=(
        "Signet's page moves into the one site, so a link to the contact page is a path; the shared footer's policy row carries it.")),
    LinkMove("https://syahi.sh/privacy", "/privacy", reason=(
        "Signet's page moves into the one site, so a link to the privacy page is a path; the shared footer's policy row carries it.")),
    LinkMove("https://syahi.sh/terms", "/terms", reason=(
        "Signet's page moves into the one site, so a link to the terms page is a path; the shared footer's policy row carries it.")),
    LinkMove("https://syahi.sh/refund", "/refund", reason=(
        "Signet's page moves into the one site, so a link to the refund page is a path; the shared footer's policy row carries it.")),
)


def _origin_matches(value: str, origin: str) -> bool:
    return value == origin or value.startswith((origin + "/", origin + "?", origin + "#"))


def _move_for(value: str, moves) -> LinkMove | None:
    return next((m for m in moves if (_origin_matches(value, m.old) if m.host else value == m.old)), None)


def apply_link_moves(values: list[str], moves=LINK_MOVES) -> list[str]:
    """`values` with each deliberate move applied. Same length, same order; anything no move names is untouched."""
    return [m.new if (m := _move_for(value, moves)) else value for value in values]


def moves_used(values: list[str], moves=LINK_MOVES) -> list[LinkMove]:
    """The moves that matched at least one of `values`, in the order the moves are listed."""
    matched = {_move_for(value, moves) for value in values} - {None}
    return [m for m in moves if m in matched]
