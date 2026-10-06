"""The copy check (spec section 7): the rules that keep AI-sounding copy off the site.

`check(html, audience)` returns one finding per problem as "<rule-id>: <detail>". No findings means
the copy is clean. The copy is the text of `<main>`, plus the page `<title>` and the
`<meta name="description">`, which are copy too. A finding from the title or description reads
"<rule-id>: title: ..." or "<rule-id>: description: ...". Header, footer and the rest of the head
are not read.

Rules: em-dash, contrast-framing, throat-clearing, buzzword and intangible run over all three.
stacked-threes (per paragraph) and owner-first-line (for the owner audience) are about the page body.

Standard library only. This file never holds the em dash itself; it is built from its code point.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

EM_DASH = chr(0x2014)

# "It's not X, it's Y" and its cousins. Case-insensitive, run on text whose curly apostrophes are
# straight and whose blocks are joined as sentences, so one spelling covers both and a heading plus
# the line under it reads as one frame.
#
# The same-subject frame ("We don't X, we Y") must start a sentence: the start of the text, after
# . ! or ? (and any closing quote or bracket) plus space, or at a block boundary (blocks are joined by
# a newline). That alone rules out a clause a conjunction introduces ("If we don't hear back, we call
# you.": if, when, unless, once, until, because, since, although, while, whether), which is a
# condition and not a contrast. Opening quotes and brackets may sit between the start and the subject.
_SENTENCE_START = r"""(?:^|(?:(?<=[.!?])|(?<=[.!?]["')\]\u201d]))\s+|(?<=\n))["'(\[\u201c]*"""
_SEP = r"(?:\s*[,;:]\s*|\s+-{1,2}\s+|\s*[\u2013\u2014]\s*)"   # , ; : - -- en dash, em dash
_JUST = r"(?:(?:just|only|merely) )?"
_X = r"[^.,;:]{1,40}"
_THING = r"(?:it|this|that)"
_THING_IS = rf"{_THING}(?:'?s| is)\b"                         # it's, its, it is, this is, that's
_RESTATED = rf"(?:but\b|{_THING_IS})"
_DO_NOT = r"(?:(?:do|does|did|will|would|can|could) not|(?:don|doesn|didn|won|wouldn|can|couldn)'?t|cannot)"
CONTRAST_FRAMING = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    # not X, but Y / not X, it's Y: the brief's first form, with every separator
    rf"\bnot {_JUST}{_X}{_SEP}{_RESTATED}",
    # isn't X, it's Y
    rf"\b(?:isn|aren|wasn|weren)'?t {_JUST}{_X}{_SEP}{_RESTATED}",
    # It's not X. It's Y: the brief's second form; a full stop is a separator only between these pronouns
    rf"\b{_THING}(?:'?s not| is not| isn'?t) [^.]{{1,40}}\.\s+{_THING_IS}",
    # We don't X, we Y: the same subject says no and then yes. Not "I": "I don't know, I guess so" is a
    # hedge, not a pitch, and no wording tells the two apart.
    rf"{_SENTENCE_START}(?P<subject>we|you|they|it|he|she) {_DO_NOT} {_X}{_SEP}(?P=subject)\b",
))
THROAT_CLEARING = (
    "in today's", "it's worth noting", "let's dive", "in a world where", "at the end of the day",
    "needless to say", "simply put",
)
INTANGIBLE = ("peace of mind", "take your business to the next level", "transform your business", "the power of ai")


def _verb(base: str, past: bool = True) -> list[str]:
    """The base, its s form, ing form and, unless `past` is False, its d or ed form."""
    stem = base[:-1] if base.endswith("e") else base
    forms = [base, base + "s", stem + "ing"]
    if past:
        forms.append(base + ("d" if base.endswith("e") else "ed"))
    return forms


# Whole words only. Every inflection fires except "leveraged": a leveraged buyout is finance, not a pitch.
BUZZ_WORDS = (
    ["synergy", "synergies", "seamless", "seamlessly", "robust", "holistic"]
    + _verb("leverage", past=False)
    + _verb("unlock") + _verb("empower") + _verb("elevate")
    + _verb("revolutionize") + _verb("revolutionise") + _verb("supercharge")
)
# Compounds match hyphenated or spaced: "world-class", "world class". Parts are regex fragments.
BUZZ_COMPOUNDS = (
    ("cutting", "edge"), ("game", "changers?"), ("game", "changing"), ("world", "class"),
    ("best", "in", "class"), ("next", "level"),
)
_JOIN = r"[\s\u2010\u2011-]+"
BUZZWORDS = re.compile(
    r"(?<!\w)(?:" + "|".join(BUZZ_WORDS + [_JOIN.join(parts) for parts in BUZZ_COMPOUNDS]) + r")(?!\w)",
    re.IGNORECASE,
)

# A triad is "A, B and C" or "A, B, and C": three short runs with no sentence punctuation inside them.
_ITEM = r"[^\s,;:.!?][^,;:.!?]{0,39}"
TRIAD = re.compile(rf"{_ITEM}, {_ITEM},? and {_ITEM}")
# Her own triad is the house voice and never counts.
HER_TRIAD = re.compile(r"operate efficiently, analyze deeply,? and grow immensely", re.IGNORECASE)

# agent, agents, agentic; AI and A.I. with its dot (the initialism is upper case only, so "Ai" and "said" are not it)
OWNER_FIRST_LINE_WORDS = re.compile(r"\bagent(?:s|ic)?\b|(?-i:\bA\.I\b\.?|\bAI\b)", re.IGNORECASE)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

# Elements that end a sentence and a block of text. Inline elements (b, a, span, ...) do not.
BLOCK_TAGS = frozenset(
    "address article aside blockquote dd details div dl dt fieldset figcaption figure footer form "
    "h1 h2 h3 h4 h5 h6 header hr li main nav ol p pre section summary table tbody td tfoot th thead tr ul".split()
)
SKIPPED_TAGS = frozenset({"script", "style"})
CURLY = str.maketrans({"\u2018": "'", "\u2019": "'"})


class _Page(HTMLParser):
    """What the rules read: the text of `<main>` in `blocks` (and each `<p>`, each `<h1>`), the title, the description."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self.paragraphs: list[str] = []
        self.h1: list[str] = []
        self.title = ""
        self.description = ""
        self._main = 0
        self._skip = 0
        self._svg = 0
        self._block: list[str] = []
        self._para: list[str] | None = None
        self._in_h1 = False
        self._title: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "svg":
            self._svg += 1
        elif tag == "title" and not self._main and not self._svg:   # the page's, not an svg's
            self._title = []
        elif tag == "meta" and not self.description:
            fields = dict(attrs)
            if (fields.get("name") or "").lower() == "description":
                self.description = _clean(fields.get("content") or "")
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
            self._in_h1 = tag == "h1"
            if tag == "p":
                self._para = []

    def handle_endtag(self, tag):
        if tag == "svg":
            self._svg = max(0, self._svg - 1)
        elif tag == "title" and self._title is not None:
            self.title = _clean("".join(self._title))
            self._title = None
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

    def handle_data(self, data):
        if self._title is not None:
            self._title.append(data)
        if self._main and not self._skip:
            self._text(data)

    def close(self):
        super().close()
        self._flush()

    def _text(self, text: str) -> None:
        self._block.append(text)
        if self._para is not None:
            self._para.append(text)

    def _flush(self) -> None:
        if self._block:
            text = _clean("".join(self._block))
            if text:
                self.blocks.append(text)
                if self._in_h1:
                    self.h1.append(text)
            self._block = []
        if self._para is not None:
            text = _clean("".join(self._para))
            if text:
                self.paragraphs.append(text)
            self._para = None


def _clean(text: str) -> str:
    """Straight apostrophes and single spaces, so a phrase matches however the source spelled it."""
    return " ".join(text.translate(CURLY).split())


def _sentences(blocks: list[str]) -> str:
    """The blocks as running text, one per line: a block that does not end its sentence gets a full stop."""
    return "\n".join(block if block[-1] in ".!?:;," else block + "." for block in blocks)


def _phrase(words: str) -> re.Pattern:
    """A phrase as a case-insensitive pattern: any run of spaces between words, and whole words at both ends."""
    body = r"\s+".join(re.escape(word) for word in words.split())
    return re.compile(rf"(?<!\w){body}(?!\w)", re.IGNORECASE)


_THROAT = [(phrase, _phrase(phrase)) for phrase in THROAT_CLEARING]
_INTANGIBLE = [(phrase, _phrase(phrase)) for phrase in INTANGIBLE]


def check(html: str, audience: str | None) -> list[str]:
    """Findings for the page copy, each "<rule-id>: <detail>", each reported once."""
    page = _Page()
    page.feed(html)
    page.close()
    found = (
        _copy_rules(_sentences(page.blocks), "")
        + _copy_rules(page.title, "title")
        + _copy_rules(page.description, "description")
        + _stacked_threes(page.paragraphs)
    )
    if audience == "owner":
        found += _owner_first_line(page.blocks, page.h1)
    return list(dict.fromkeys(found))


def _copy_rules(text: str, where: str) -> list[str]:
    """The rules every piece of copy gets. `where` is "" for the body, else "title" or "description"."""
    if not text:
        return []
    found = (
        [("em-dash", f'em dash (U+2014) in "{_around(text, m)}"'.replace(EM_DASH, "[U+2014]"))
         for m in re.finditer(EM_DASH, text)]   # shown as a code point, so a build log never carries the character
        + [("contrast-framing", f'"{m.group(0).strip()}"') for pattern in CONTRAST_FRAMING for m in pattern.finditer(text)]
        + [("throat-clearing", f'"{phrase}"') for phrase, pattern in _THROAT if pattern.search(text)]
        + [("buzzword", f'"{m.group(0).lower()}"') for m in BUZZWORDS.finditer(text)]
        + [("intangible", f'"{phrase}"') for phrase, pattern in _INTANGIBLE if pattern.search(text)]
    )
    label = f"{where}: " if where else ""
    return [f"{rule}: {label}{detail}" for rule, detail in found]


def _stacked_threes(paragraphs: list[str]) -> list[str]:
    found = []
    for paragraph in paragraphs:
        triads = [m.group(0).strip() for m in TRIAD.finditer(HER_TRIAD.sub("X", paragraph))]
        if len(triads) >= 2:
            shown = "; ".join(f'"{t}"' for t in triads)
            found.append(f"stacked-threes: {len(triads)} triads in one paragraph: {shown}")
    return found


def _owner_first_line(blocks: list[str], h1: list[str]) -> list[str]:
    """What an owner reads first must not lead with the machinery.

    Two places count: the first sentence of the page (a block boundary ends a sentence) and the h1,
    read whole, so an eyebrow line above the h1 cannot hide it.
    """
    openings = []
    if blocks:
        openings.append(SENTENCE_END.split(blocks[0], maxsplit=1)[0])
    if h1:
        openings.append(h1[0])
    found = []
    for opening in dict.fromkeys(openings):
        word = OWNER_FIRST_LINE_WORDS.search(opening)
        if word:
            found.append(f'owner-first-line: the opening says "{word.group(0)}": "{opening}"')
    return found


def _around(text: str, match: re.Match, reach: int = 24) -> str:
    return " ".join(text[max(0, match.start() - reach): match.end() + reach].split())
