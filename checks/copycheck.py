"""The copy check (spec section 7): the rules that keep AI-sounding copy off the site.

`check(html, audience)` reads the text of `<main>` only, never the header, footer or head, and
returns one finding per problem as "<rule-id>: <detail>". No findings means the copy is clean.

Rules: em-dash, contrast-framing, throat-clearing, buzzword, intangible, stacked-threes and,
for the owner audience, owner-first-line.

Standard library only. This file never holds the em dash itself; it is built from its code point.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

EM_DASH = chr(0x2014)

# "It's not X, it's Y" and its cousins. The patterns are case-insensitive and run on text
# whose curly apostrophes are straight, so one spelling covers both.
CONTRAST_FRAMING = (
    re.compile(r"\bnot (just |only )?[^.,;:]{1,40}, (but|it'?s|it is)\b", re.IGNORECASE),
    re.compile(r"\bit'?s not [^.]{1,40}\. it'?s\b", re.IGNORECASE),
)
THROAT_CLEARING = (
    "in today's", "it's worth noting", "let's dive", "in a world where", "at the end of the day",
    "needless to say", "simply put",
)
# Whole words only, so "a leveraged buyout" is not "leverage". The list is the spec's: no inflections.
BUZZWORDS = (
    "leverage", "synergy", "cutting-edge", "game-changer", "game-changing", "revolutionize", "revolutionise",
    "seamless", "seamlessly", "unlock", "empower", "robust", "holistic", "next-level", "supercharge", "elevate",
    "world-class", "best-in-class",
)
INTANGIBLE = ("peace of mind", "take your business to the next level", "transform your business", "the power of ai")

# A triad is "A, B and C" or "A, B, and C": three short runs with no sentence punctuation inside them.
_ITEM = r"[^\s,;:.!?][^,;:.!?]{0,39}"
TRIAD = re.compile(rf"{_ITEM}, {_ITEM},? and {_ITEM}")
# Her own triad is the house voice and never counts.
HER_TRIAD = re.compile(r"operate efficiently, analyze deeply,? and grow immensely", re.IGNORECASE)

OWNER_FIRST_LINE_WORDS = re.compile(r"\bagents?\b|(?-i:\bAI\b)", re.IGNORECASE)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

# Elements that end a sentence and a block of text. Inline elements (b, a, span, ...) do not.
BLOCK_TAGS = frozenset(
    "address article aside blockquote dd details div dl dt fieldset figcaption figure footer form "
    "h1 h2 h3 h4 h5 h6 header hr li main nav ol p pre section summary table tbody td tfoot th thead tr ul".split()
)
SKIPPED_TAGS = frozenset({"script", "style"})
CURLY = str.maketrans({"\u2018": "'", "\u2019": "'"})


class _MainText(HTMLParser):
    """The text of `<main>`: `blocks` in reading order, `paragraphs` for each `<p>`."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self.paragraphs: list[str] = []
        self._main = 0
        self._skip = 0
        self._block: list[str] = []
        self._para: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "main":
            self._flush()
            self._main += 1
        elif not self._main:
            return
        elif tag in SKIPPED_TAGS:
            self._skip += 1
        elif tag == "br":
            self._text(" ")
        elif tag in BLOCK_TAGS:
            self._flush()
            if tag == "p":
                self._para = []

    def handle_endtag(self, tag):
        if not self._main:
            return
        if tag == "main":
            self._flush()
            self._main -= 1
        elif tag in SKIPPED_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in BLOCK_TAGS:
            self._flush()

    def handle_data(self, data):
        if self._main and not self._skip:
            self._text(data)

    def _text(self, text: str) -> None:
        self._block.append(text)
        if self._para is not None:
            self._para.append(text)

    def _flush(self) -> None:
        if self._block:
            text = _clean("".join(self._block))
            if text:
                self.blocks.append(text)
            self._block = []
        if self._para is not None:
            text = _clean("".join(self._para))
            if text:
                self.paragraphs.append(text)
            self._para = None


def _clean(text: str) -> str:
    """Straight apostrophes and single spaces, so a phrase matches however the source spelled it."""
    return " ".join(text.translate(CURLY).split())


def _phrase(words: str) -> re.Pattern:
    """A phrase as a case-insensitive pattern: any run of spaces between words, and whole words at both ends."""
    body = r"\s+".join(re.escape(word) for word in words.split())
    return re.compile(rf"(?<!\w){body}(?!\w)", re.IGNORECASE)


def _words(words: tuple[str, ...]) -> re.Pattern:
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(word) for word in words) + r")(?!\w)", re.IGNORECASE)


_THROAT = [(phrase, _phrase(phrase)) for phrase in THROAT_CLEARING]
_INTANGIBLE = [(phrase, _phrase(phrase)) for phrase in INTANGIBLE]
_BUZZ = _words(BUZZWORDS)


def check(html: str, audience: str | None) -> list[str]:
    """Findings for the copy in `<main>`, each "<rule-id>: <detail>", each reported once."""
    main = _MainText()
    main.feed(html)
    main.close()
    main._flush()
    text = " ".join(main.blocks)
    found: list[str] = []
    found += _em_dashes(text)
    found += _contrast_framing(text)
    found += _phrases("throat-clearing", _THROAT, text)
    found += _buzzwords(text)
    found += _phrases("intangible", _INTANGIBLE, text)
    found += _stacked_threes(main.paragraphs)
    if audience == "owner":
        found += _owner_first_line(main.blocks)
    return list(dict.fromkeys(found))


def _em_dashes(text: str) -> list[str]:
    # The finding shows the dash as its code point, so a build log never carries the character itself.
    return [f'em-dash: em dash (U+2014) in "{_around(text, m)}"'.replace(EM_DASH, "[U+2014]")
            for m in re.finditer(EM_DASH, text)]


def _contrast_framing(text: str) -> list[str]:
    return [f'contrast-framing: "{m.group(0)}"' for pattern in CONTRAST_FRAMING for m in pattern.finditer(text)]


def _phrases(rule: str, phrases: list[tuple[str, re.Pattern]], text: str) -> list[str]:
    return [f'{rule}: "{phrase}"' for phrase, pattern in phrases if pattern.search(text)]


def _buzzwords(text: str) -> list[str]:
    return [f'buzzword: "{m.group(0).lower()}"' for m in _BUZZ.finditer(text)]


def _stacked_threes(paragraphs: list[str]) -> list[str]:
    found = []
    for paragraph in paragraphs:
        triads = [m.group(0).strip() for m in TRIAD.finditer(HER_TRIAD.sub("X", paragraph))]
        if len(triads) >= 2:
            shown = "; ".join(f'"{t}"' for t in triads)
            found.append(f"stacked-threes: {len(triads)} triads in one paragraph: {shown}")
    return found


def _owner_first_line(blocks: list[str]) -> list[str]:
    """The first sentence of the page must not lead with the machinery. A block boundary ends a sentence."""
    if not blocks:
        return []
    first = SENTENCE_END.split(blocks[0], maxsplit=1)[0]
    word = OWNER_FIRST_LINE_WORDS.search(first)
    if not word:
        return []
    return [f'owner-first-line: the first sentence says "{word.group(0)}": "{first}"']


def _around(text: str, match: re.Match, reach: int = 24) -> str:
    return text[max(0, match.start() - reach): match.end() + reach].strip()
