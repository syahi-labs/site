"""The D10 placement check (spec 5.3, ruling D10): what a page may say about Signet's customers, and where.

The full D10 sentence (claim `signet-d10`) appears once wherever Signet is offered. Elsewhere the page
says nothing about customers, users or sign-ups beyond it. This check holds both halves:

  d10-count     a page that renders the Signet price line (claim `signet-price-line`) or offers a Signet demo
                or booking link inside <main> must carry exactly one `data-claim="signet-d10"` span;
  d10-sentence  inside <main>, a sentence that mentions customers, users or signing up, and either names
                Signet or sits on a page whose subject is Signet, is a finding unless it is inside the
                `signet-d10` span.

A page's subject is Signet when its path is /signet or its h1 names Signet. A booking link is an anchor in
<main> to cal.com that is on a Signet-subject page, or whose text or label says Signet or demo.

`check(html, slug)` returns "<rule-id>: <detail>" per finding, each once. The build treats a finding as a
problem in a release build and a warning in a dev build. It reads the rendered page, so it cannot be
satisfied by a different spelling of the claim. Standard library only.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

from checks.copycheck import BLOCK_TAGS, SKIPPED_TAGS, _clean

D10 = "signet-d10"
PRICE_LINE = "signet-price-line"
CUSTOMER_WORDS = re.compile(
    r"\b(?:customers?|users?|sign(?:s|ed|ing)?[\s-]*up)\b|\bsignups?\b", re.IGNORECASE)
SIGNET = re.compile(r"\bSignet\b")
BOOKING_HOST = "https://cal.com/"
_BREAK = "\x00"     # where the d10 span sat: a sentence never runs across it


class _Scan(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.d10_spans = 0
        self.price_lines = 0
        self.h1: list[str] = []
        self.blocks: list[str] = []
        self.booking_links: list[tuple[str, str]] = []     # (href, text and label) of cal.com anchors in <main>
        self._main = 0
        self._skip = 0
        self._d10_depth = 0            # >0 while inside the d10 span (span nesting counted)
        self._block: list[str] = []
        self._in_h1 = False
        self._h1_text: list[str] = []
        self._anchor: dict | None = None

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if tag == "span":
            if self._d10_depth:
                self._d10_depth += 1
            elif fields.get("data-claim") == D10:
                self.d10_spans += 1
                self._d10_depth = 1
                self._block.append(_BREAK)
            elif fields.get("data-claim") == PRICE_LINE:
                self.price_lines += 1
        if tag == "main":
            self._flush()
            self._main += 1
            return
        if not self._main:
            return
        if tag in SKIPPED_TAGS:
            self._skip += 1
        elif tag in BLOCK_TAGS:
            self._flush()
            self._in_h1 = tag == "h1"
        elif tag == "br":
            self._block.append(" ")
        if tag == "a" and (fields.get("href") or "").startswith(BOOKING_HOST):
            self._anchor = {"href": fields["href"], "text": [fields.get("aria-label") or ""]}

    def handle_endtag(self, tag):
        if tag == "span" and self._d10_depth:
            self._d10_depth -= 1
            if not self._d10_depth:
                self._block.append(_BREAK)
        if not self._main:
            return
        if tag == "main":
            self._flush()
            self._main -= 1
        elif tag in SKIPPED_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in BLOCK_TAGS:
            self._flush()
            self._in_h1 = False
        elif tag == "a" and self._anchor is not None:
            self.booking_links.append((self._anchor["href"], _clean(" ".join(self._anchor["text"]))))
            self._anchor = None

    def handle_data(self, data):
        if self._main and not self._skip:
            if self._anchor is not None:
                self._anchor["text"].append(data)
            if not self._d10_depth:
                self._block.append(data)
            if self._in_h1:
                self._h1_text.append(data)

    def close(self):
        super().close()
        self._flush()

    def _flush(self) -> None:
        text = "".join(self._block)
        self._block = []
        if text.replace(_BREAK, "").strip():
            self.blocks.append(text)
        if self._h1_text:
            self.h1.append(_clean("".join(self._h1_text)))
            self._h1_text = []


def _sentences(block: str) -> list[str]:
    out = []
    for piece in block.split(_BREAK):
        for sentence in re.split(r"(?<=[.!?])\s+", _clean(piece)):
            if sentence:
                out.append(sentence)
    return out


def check(html: str, slug: str | None = None) -> list[str]:
    page = _Scan()
    page.feed(html)
    page.close()
    signet_page = slug == "/signet" or any(SIGNET.search(h) for h in page.h1)
    found: list[str] = []

    offers = []
    if page.price_lines:
        offers.append("the Signet price line")
    if any(signet_page or re.search(r"signet|demo", text, re.IGNORECASE) for _, text in page.booking_links):
        offers.append("a Signet demo or booking link")
    if offers and page.d10_spans != 1:
        found.append(f"d10-count: the page shows {' and '.join(offers)} but carries {page.d10_spans} "
                     f"data-claim=\"{D10}\" spans, not exactly one")

    for block in page.blocks:
        for sentence in _sentences(block):
            if CUSTOMER_WORDS.search(sentence) and (signet_page or SIGNET.search(sentence)):
                found.append(f"d10-sentence: a sentence about customers, users or sign-ups outside the {D10} span: {sentence!r}")
    return list(dict.fromkeys(found))
