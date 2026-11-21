"""The products-page check (her ruling, 2026-11-21): what /products must never say or mark up.

The voice products page is in private preview and sells nothing yet. So the whole rendered page (the words,
the attributes, the head, the links and the structured data, all of it) is held to this list of things it must
not carry:

  claim-words      a waitlist, a beta, "coming soon", a "voice agent", "best", "most accurate", accuracy or a
                   percentage, a price, a rupee or dollar sign, "free", "on sale", voice cloning, a choice of
                   voices, "open source", GitHub, "on-device", "never leaves your machine", "tamper-proof",
                   customers, clients, partners, "trusted by", the name of a rival, "HQ" and "Signet";
  structured-data  an `offers`, `aggregateRating`, `review`, `Offer`, `PreOrder`, `PreSale` or `price` in the
                   JSON-LD.

`check(html, slug)` returns "<rule-id>: <detail>" per finding, each once. A slug other than "/products" has no
findings: the rest of the site keeps its own rules. The build treats a finding as a problem in every build, a
release or a dev one, because the list is a ruling and not a style note. Standard library only.
"""
from __future__ import annotations

import html as htmllib
import re

SLUG = "/products"

# (the label a finding carries, a pattern for it). Whole words, case-insensitive, run on the page's HTML with
# its <style> blocks taken out and its entities decoded, so a word in a label, a link or a meta tag is read too.
_BANNED = (
    ("beta", r"\bbeta\b"),
    ("waitlist", r"\bwait[\s-]?list\b"),
    ("coming soon", r"\bcoming soon\b"),
    ("voice agent", r"\bvoice agents?\b"),
    ("best", r"\bbest\b"),
    ("most accurate", r"\bmost accurate\b"),
    ("accuracy", r"\baccura(?:te|cy)\b|\bWER\b"),
    ("a percentage", r"\d\s*%"),
    ("a price", r"\bpric(?:e|es|ed|ing)\b|[₹$€£]|\bINR\b|\bUSD\b|\brupees?\b|\bper (?:month|year|minute|hour)\b|/(?:month|mo|year)\b"),
    ("free", r"\bfree\b"),
    ("on sale", r"\bon sale\b|\bdiscounts?\b"),
    ("voice cloning", r"\bclon(?:e|es|ed|ing)\b"),
    ("a choice of voices", r"\bvoices\b|\b(?:choose|pick|select) (?:a|your|any) voice\b"),
    ("open source", r"\bopen[\s-]?source\b"),
    ("GitHub", r"\bgit ?hub\b"),
    ("on-device", r"\bon[\s-]?device\b"),
    ("never leaves your machine", r"\bnever leaves your (?:machine|device|phone|computer)\b"),
    ("tamper-proof", r"\btamper[\s-]?(?:proof|evident|resistant)\b"),
    ("customers", r"\bcustomers?\b|\bclients?\b|\bpartners?\b|\bpartnerships?\b|\btrusted by\b"),
    ("a rival", r"\b(?:OpenAI|ChatGPT|Whisper|Deepgram|ElevenLabs|Eleven Labs|Otter|AssemblyAI|Speechify|Murf|Sarvam|Gnani|Google|Microsoft|Azure|Amazon|AWS|Siri|Alexa)\b"),
    ("HQ", r"\bHQ\b"),
    ("Signet", r"\bSignet\b"),
)
_BANNED_COMPILED = tuple((label, re.compile(pattern, re.IGNORECASE if label != "HQ" else 0)) for label, pattern in _BANNED)
_STYLE = re.compile(r"<style\b.*?</style>", re.IGNORECASE | re.DOTALL)
# Structured-data words a JSON-LD block must not carry as a key or a type.
_STRUCTURED = re.compile(r'"(?:offers?|aggregateRating|review|reviews|Offer|AggregateOffer|PreOrder|PreSale|price|priceCurrency|Rating|Review)"')
_JSONLD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)


def check(html: str, slug: str) -> list[str]:
    """Findings for one rendered page, each once. Only /products is held to the list."""
    if slug != SLUG:
        return []
    found: list[str] = []
    text = htmllib.unescape(_STYLE.sub(" ", html))
    for label, pattern in _BANNED_COMPILED:
        match = pattern.search(text)
        if match:
            found.append(f"claim-words: {label}: {match.group(0)!r}")
    for block in _JSONLD.findall(html):
        for match in _STRUCTURED.finditer(block):
            finding = f"structured-data: {match.group(0)}"
            if finding not in found:
                found.append(finding)
    return found
