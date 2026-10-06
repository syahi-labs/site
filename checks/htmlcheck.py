"""The HTML checks (spec section 7): the markup rules a rendered page must keep.

`check(html, claims=None)` returns one finding per problem as "<rule-id>: <detail>". No findings means
the page passes. Rules: one-h1, one-main, heading-order, lang-hi, numbers-from-claims and balanced.

`numbers-from-claims` covers the attributes a person reads or hears (aria-label, alt, title, placeholder) as
well as the text. A digit in one of those, inside `<main>`, is a finding unless the element names the claims it
took its digits from, `data-claims="id,id"` (the template helper `claim_text()` writes the claim's text into
an attribute, and the element carries that marker). The marker alone only says "a claim supplied this"; with
`claims` (a map of claim id to the texts it renders as, see ClaimRegister.renderings) the check proves it: the
listed ids must exist, and once each listed claim's text is taken out of the attribute no digit may be left. A
typed figure that agreed with its claim yesterday therefore fails the day the claim changes.

`one-main` matters beyond markup: the copy check and numbers-from-claims read `<main>` only, so a
page without one would pass both unread.

`balanced` is the spec's HTML validity check. It is strict on purpose: every element that is not
void must be closed with its own end tag, in order, and a stray end tag fails. Closing tags the HTML
spec lets a page leave out (</p>, </li>) are required here, so the markup reads one way everywhere.

Standard library only.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser

HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
FOREIGN = frozenset({"svg", "math"})   # inside these, <x/> really does close the element
RAW_TEXT = frozenset({"script", "style", "title"})   # text that is not page copy
HEAD_ONLY = frozenset({"meta", "link", "base"})   # attributes here are metadata: exempt from lang-hi
# The attributes people read or hear, so a Devanagari run in one needs lang="hi" like body text does.
VISIBLE_ATTRS = ("alt", "title", "aria-label", "placeholder")
DEVANAGARI = re.compile(r"[ऀ-ॿ]+(?:\s+[ऀ-ॿ]+)*")
NUMBER = re.compile(r"\d+(?:[.,:/]\d+)*")


@dataclass(frozen=True)
class _Open:
    """One open element, with what it passes down to everything inside it."""
    tag: str
    hindi: bool        # the nearest lang attribute at or above it is Hindi
    in_main: bool
    exempt: bool       # inside a claim, a sample, <time>, <svg> or <code>
    foreign: bool
    raw: bool


_ROOT = _Open("", hindi=False, in_main=False, exempt=False, foreign=False, raw=False)


class _Scan(HTMLParser):
    """One pass over the page that collects what every rule needs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[_Open] = []
        self.h1 = 0
        self.mains = 0
        self.levels: list[int] = []
        self.hindi: list[str] = []
        self.numbers: list[str] = []
        self.claimed: list[tuple[str, str, list[str]]] = []   # (attribute, value, ids) a data-claims element holds digits in
        self.balance: list[str] = []

    @property
    def _top(self) -> _Open:
        return self.stack[-1] if self.stack else _ROOT

    def handle_starttag(self, tag, attrs):
        self._open(tag, attrs, self_closed=False)

    def handle_startendtag(self, tag, attrs):
        self._open(tag, attrs, self_closed=True)

    def handle_endtag(self, tag):
        if tag in VOID:
            self.balance.append(f"balanced: stray </{tag}>, a void element has no end tag")
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i].tag == tag:
                for left_open in self.stack[i + 1:]:
                    self.balance.append(f"balanced: <{left_open.tag}> is not closed before </{tag}>")
                del self.stack[i:]
                return
        self.balance.append(f"balanced: stray </{tag}>, nothing is open to close")

    def handle_data(self, data):
        top = self._top
        if top.raw:
            return
        if not top.hindi:
            self.hindi += [run.group(0) for run in DEVANAGARI.finditer(data)]
        if top.in_main and not top.exempt:
            text = " ".join(data.split())
            self.numbers += [f'"{n.group(0)}" is outside a claim (in "{_shorten(text)}")' for n in NUMBER.finditer(text)]

    def _attribute_numbers(self, attrs: dict) -> None:
        """Digits in the attributes people read or hear: bare ones are findings, claimed ones are kept for check()."""
        ids = [name.strip() for name in attrs.get("data-claims", "").split(",") if name.strip()]
        for name in VISIBLE_ATTRS:
            value = attrs.get(name, "")
            if not NUMBER.search(value):
                continue
            if ids:
                self.claimed.append((name, value, ids))
            else:
                self.numbers += [f'"{n.group(0)}" is outside a claim (in {name}="{_shorten(value)}")' for n in NUMBER.finditer(value)]

    def close(self):
        super().close()
        for left_open in self.stack:
            self.balance.append(f"balanced: <{left_open.tag}> is never closed")
        self.stack.clear()

    def _open(self, tag: str, attrs, self_closed: bool) -> None:
        attrs = {name: (value or "") for name, value in attrs}
        parent = self._top
        node = _Open(
            tag=tag,
            hindi=_is_hindi(attrs["lang"]) if "lang" in attrs else parent.hindi,
            in_main=parent.in_main or tag == "main",
            exempt=parent.exempt or tag in ("time", "svg", "code") or "data-claim" in attrs or "data-sample" in attrs,
            foreign=parent.foreign or tag in FOREIGN,
            raw=tag in RAW_TEXT,
        )
        if tag == "main":
            self.mains += 1
        if tag in HEADINGS:
            self.levels.append(HEADINGS[tag])
            if tag == "h1":
                self.h1 += 1
        if not node.hindi and tag not in HEAD_ONLY:
            for name in VISIBLE_ATTRS:
                self.hindi += [run.group(0) for run in DEVANAGARI.finditer(attrs.get(name, ""))]
        if node.in_main and not node.exempt:
            self._attribute_numbers(attrs)
        # HTML ignores a slash on a non-void element outside svg and math, so `<div/>` opens a div.
        if tag in VOID or (self_closed and node.foreign):
            return
        self.stack.append(node)


def _is_hindi(lang: str) -> bool:
    return lang.strip().lower().split("-")[0] == "hi"


def _shorten(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def check(html: str, claims: Mapping[str, Sequence[str]] | None = None) -> list[str]:
    """Findings for one rendered page, each "<rule-id>: <detail>", each reported once.

    `claims` maps each live claim id to the texts it renders as. Without it, a `data-claims` marker is taken on
    trust; with it, the marker is proved (see the module docstring).
    """
    scan = _Scan()
    scan.feed(html)
    scan.close()
    found: list[str] = []
    if scan.h1 != 1:
        found.append(f"one-h1: found {scan.h1} h1 elements, expected exactly 1")
    if scan.mains != 1:
        found.append(f"one-main: found {scan.mains} main elements, expected exactly 1")
    for before, after in zip(scan.levels, scan.levels[1:]):
        if after > before + 1:
            found.append(f"heading-order: h{after} follows h{before}, skipping h{before + 1}")
    found += [f'lang-hi: "{run}" is not inside an element with lang="hi"' for run in scan.hindi]
    found += [f"numbers-from-claims: {number}" for number in scan.numbers]
    if claims is not None:
        found += [f"numbers-from-claims: {problem}" for problem in _unproven(scan.claimed, claims)]
    found += scan.balance
    return list(dict.fromkeys(found))


def _unproven(claimed: list[tuple[str, str, list[str]]], claims: Mapping[str, Sequence[str]]) -> list[str]:
    """What the `data-claims` markers fail to prove: an id the register lacks, and a digit no listed claim supplies."""
    found = []
    for name, value, ids in claimed:
        found += [f'data-claims names "{id}", which is not a live claim (in {name}="{_shorten(value)}")' for id in ids if id not in claims]
        remaining = value
        for text in sorted((text for id in ids for text in claims.get(id, ())), key=len, reverse=True):
            remaining = remaining.replace(text, " ")
        found += [f'"{n.group(0)}" is not in the text of {", ".join(ids)} (in {name}="{_shorten(value)}")' for n in NUMBER.finditer(remaining)]
    return found
