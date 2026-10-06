"""Structured data for a page, built from claims, and the check that none of it is invisible.

`build_jsonld` returns the JSON-LD nodes for one page. Every string in them comes
from a claim or from the page's own title (the claims are read without marking them
used: that record belongs to what a page renders), so what search and answer engines read
is what a person reads. `jsonld_mismatches` proves it on the rendered HTML: any
string in a JSON-LD block that does not appear in the page's visible text is a
problem. URLs, ids, dates and enumerations are exempt.

The Organization, WebSite and Person ids live on the main host. A second host
(katha) points at them and never redefines them.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser

from sitebuild.claims import ClaimError, ClaimRegister
from sitebuild.content import Page
from sitebuild.site import SiteConfig

MAIN_URL = "https://syahi.sh"
MAIN_HEADER = "syahi"  # SiteConfig.header of the main host; any other header is a second host

LOGO_PATH = "/assets/brand/mark-512.png"
REGION = "Karnataka"
COUNTRY = "IN"
CURRENCY = "INR"
RUPEE = "\u20b9"
# A plain amount: ASCII digits, no grouping, no sign, an optional decimal part. "1499", "116.82".
AMOUNT = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")
APPLICATION_CATEGORY = "BusinessApplication"
CONTACT_TYPE = "sales"

# Keys whose values are URLs, ids, dates or enumerations: they need not appear in the page.
# The first eighteen are the plan's list (Phase 1 plan, Task 4). `applicationCategory` and
# `contactType` are enumerations of the same kind as `priceCurrency` and `areaServed`, and the
# nodes emit them, so without them every /signet and home build would fail the check.
EXEMPT_KEYS = frozenset({
    "@context", "@type", "@id", "url", "logo", "image", "sameAs", "item", "priceCurrency",
    "areaServed", "addressCountry", "addressRegion", "inLanguage", "foundingDate",
    "datePublished", "dateModified", "contentUrl", "embedUrl",
    "applicationCategory", "contactType",
})
ISO_DATE = re.compile(
    r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?"
)
PLAIN_NUMBER = re.compile(r"\d+(?:\.\d+)?")
HIDDEN_TAGS = frozenset({"script", "style", "template", "noscript"})
REFUSED_TYPES = frozenset({"Review", "AggregateRating", "Rating"})
JSONLD_TYPE = "application/ld+json"


class SchemaError(Exception):
    """A page asks for structured data we cannot or will not emit. The message names the page file."""


def page_url(base_url: str, slug: str) -> str:
    """The clean URL of a page: no .html, no trailing slash, except the root. The one place the rule lives."""
    return base_url + slug


@dataclass(frozen=True)
class _Context:
    page: Page
    site: SiteConfig
    claims: ClaimRegister

    @property
    def entity_base(self) -> str:
        return self.site.base_url if self.site.header == MAIN_HEADER else MAIN_URL

    @property
    def is_main_home(self) -> bool:
        return self.page.slug == "/" and self.site.header == MAIN_HEADER

    @property
    def page_url(self) -> str:
        return page_url(self.site.base_url, self.page.slug)

    def entity(self, fragment: str, path: str = "/") -> str:
        return f"{self.entity_base}{path}#{fragment}"

    def ref(self, fragment: str, path: str = "/") -> dict:
        return {"@id": self.entity(fragment, path)}

    def claim(self, id: str) -> str:
        """A claim's full text. Reads through `get`, so a retired or unknown id fails as it does in
        a page, but the id is not marked used: that record is for what a page renders."""
        return self.claims.get(id).text

    def url_claim(self, id: str) -> str:
        value = self.claim(id)
        if not value.startswith("https://"):
            raise SchemaError(f"{self.page.source}: claim '{id}' must be an https:// URL for structured data, got {value!r}")
        return value

    def amount(self, amount_id: str, line_id: str) -> str:
        """The amount in claim `amount_id`, once claim `line_id` is proven to show it.

        An Offer's price is a number no reader sees, so it must be the number they do see:
        the line claim has to contain the amount written as rupees, as the page writes it.
        """
        value = self.claim(amount_id)
        try:
            shown = format_rupees(value)
        except ValueError:
            raise SchemaError(
                f"{self.page.source}: claim '{amount_id}' must be a plain amount such as 1499 or 116.82, got {value!r}"
            ) from None
        line = self.claim(line_id)
        if not re.search(re.escape(shown) + r"(?![0-9]|[.,][0-9])", line):
            raise SchemaError(
                f"{self.page.source}: claim '{amount_id}' is {value}, so claim '{line_id}' must show {shown}, "
                f"but it says {line!r}"
            )
        return value


def format_rupees(amount: str) -> str:
    """A plain amount as the page writes rupees, with Indian grouping: 1499 -> ₹1,499, 150000 -> ₹1,50,000.

    Raises ValueError for anything that is not a plain amount (see AMOUNT).
    """
    if not AMOUNT.fullmatch(amount):
        raise ValueError(f"{amount!r} is not a plain amount")
    whole, dot, fraction = amount.partition(".")
    head, tail = whole[:-3], whole[-3:]
    groups = [head[max(0, end - 2):end] for end in range(len(head), 0, -2)][::-1]
    return RUPEE + ",".join(groups + [tail]) + dot + fraction


def build_jsonld(page: Page, site: SiteConfig, claims: ClaimRegister) -> list[dict]:
    """The JSON-LD nodes for one page: `WebPage` and `BreadcrumbList` always, the rest by page.

    The main host's home page adds the full Organization and the WebSite. A page adds a node
    for each type its `schema` front matter lists. An unsupported type fails the build, so a
    typo cannot quietly drop structured data. Review and AggregateRating are never emitted.
    """
    kinds = list(dict.fromkeys(page.schema))
    for kind in kinds:
        if kind in REFUSED_TYPES:
            raise SchemaError(f"{page.source}: schema type {kind!r} is never emitted, this site carries no reviews or ratings")
        if kind not in _BUILDERS:
            raise SchemaError(f"{page.source}: schema type {kind!r} is not supported (supported: {', '.join(sorted(_BUILDERS))})")
    ctx = _Context(page, site, claims)
    try:
        nodes = []
        if ctx.is_main_home:
            nodes += [_organization(ctx), _website(ctx)]
        nodes += [_webpage(ctx), _breadcrumbs(ctx)]
        nodes += [_BUILDERS[kind](ctx) for kind in kinds]
        return nodes
    except ClaimError as err:
        raise ClaimError(f"{page.source}: structured data: {err}") from err


def _organization(ctx: _Context) -> dict:
    org = {
        "@type": "Organization",
        "@id": ctx.entity("org"),
        "name": ctx.claim("org-name"),
        "alternateName": ctx.claim("org-alternate-name"),
        "legalName": ctx.claim("org-legal-name"),
        "url": ctx.site.base_url + "/",
        "logo": ctx.site.base_url + LOGO_PATH,
        "foundingDate": ctx.claim("org-founding-date"),
        "founder": ctx.ref("surabhi", "/about"),
        # Locality only. The registered street address lives on /contact and goes nowhere else.
        "address": {
            "@type": "PostalAddress",
            "addressLocality": ctx.claim("org-locality"),
            "addressRegion": REGION,
            "addressCountry": COUNTRY,
        },
        "contactPoint": {"@type": "ContactPoint", "contactType": CONTACT_TYPE, "url": ctx.site.base_url + "/contact"},
    }
    if ctx.site.profiles:
        org["sameAs"] = [link.href for link in ctx.site.profiles]
    return org


def _website(ctx: _Context) -> dict:
    return {
        "@type": "WebSite",
        "@id": ctx.entity("site"),
        "url": ctx.site.base_url + "/",
        "name": ctx.claim("org-name"),
        "publisher": ctx.ref("org"),
    }


def _webpage(ctx: _Context) -> dict:
    return {
        "@type": "WebPage",
        "url": ctx.page_url,
        "name": ctx.page.title,
        "isPartOf": ctx.ref("site"),
        "publisher": ctx.ref("org"),
    }


def _breadcrumbs(ctx: _Context) -> dict:
    """Home, then each level of the path that has a name: a tab's label, or the page's own title.

    A level with no name is left out. Inventing one would put a string on the page's structured
    data that no reader can see.
    """
    site, page = ctx.site, ctx.page
    tab_labels = {tab.href: tab.label for tab in site.tabs if tab.href.startswith("/")}
    trail = [(site.name, site.base_url + "/")]
    parts = [part for part in page.slug.split("/") if part]
    for depth in range(1, len(parts) + 1):
        path = "/" + "/".join(parts[:depth])
        name = tab_labels.get(path) or (page.title if path == page.slug else None)
        if name:
            trail.append((name, site.base_url + path))
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": position, "name": name, "item": url}
            for position, (name, url) in enumerate(trail, start=1)
        ],
    }


def _service(ctx: _Context) -> dict:
    return {"@type": "Service", "name": ctx.page.title, "provider": ctx.ref("org"), "areaServed": COUNTRY}


def _software_application(ctx: _Context) -> dict:
    return {
        "@type": "SoftwareApplication",
        "name": ctx.claim("signet-name"),
        "applicationCategory": APPLICATION_CATEGORY,
        "offers": {
            "@type": "Offer",
            "price": ctx.amount("signet-price-amount", "signet-price-line"),
            "priceCurrency": CURRENCY,
            "description": ctx.claim("signet-price-line"),
        },
    }


def _profile_page(ctx: _Context) -> dict:
    person = {
        "@type": "Person",
        "@id": ctx.entity("surabhi", "/about"),
        "name": ctx.claim("founder-name"),
        "description": ctx.claim("founder-line"),
        "worksFor": ctx.ref("org"),
    }
    if ctx.site.founder_profiles:
        person["sameAs"] = [link.href for link in ctx.site.founder_profiles]
    return {"@type": "ProfilePage", "url": ctx.page_url, "mainEntity": person}


def _podcast_series(ctx: _Context) -> dict:
    return {
        "@type": "PodcastSeries",
        "name": ctx.claim("katha-show-name"),
        "url": ctx.url_claim("katha-show-url"),
        "inLanguage": "hi",
    }


def _audiobook(ctx: _Context) -> dict:
    return {
        "@type": "Audiobook",
        "name": ctx.claim("katha-title-name"),
        "url": ctx.url_claim("katha-title-url"),
        "inLanguage": "hi",
        "offers": {
            "@type": "Offer",
            "price": ctx.amount("katha-title-price-amount", "katha-title-price"),
            "priceCurrency": CURRENCY,
        },
    }


_BUILDERS = {
    "Audiobook": _audiobook,
    "PodcastSeries": _podcast_series,
    "ProfilePage": _profile_page,
    "Service": _service,
    "SoftwareApplication": _software_application,
}


# ---- the check -------------------------------------------------------------------------


class _Scan(HTMLParser):
    """One pass over a page: the text a reader can see, and the raw text of each JSON-LD block."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text: list[str] = []
        self.blocks: list[str] = []
        self._hidden = 0
        self._block: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "script" and (dict(attrs).get("type") or "").strip().lower() == JSONLD_TYPE:
            self._block = []
        if tag in HIDDEN_TAGS:
            self._hidden += 1

    def handle_endtag(self, tag):
        if tag == "script" and self._block is not None:
            self.blocks.append("".join(self._block))
            self._block = None
        if tag in HIDDEN_TAGS and self._hidden:
            self._hidden -= 1

    def handle_data(self, data):
        if self._block is not None:
            self._block.append(data)
        elif not self._hidden:
            self.text.append(data)

    def finish(self) -> _Scan:
        self.close()
        if self._block is not None:  # a JSON-LD script that was never closed
            self.blocks.append("".join(self._block))
            self._block = None
        return self


def _scan(html: str) -> _Scan:
    scan = _Scan()
    scan.feed(html)
    return scan.finish()


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def visible_text(html: str) -> str:
    """The text of the page outside script, style, template and noscript, whitespace collapsed.

    Entities are decoded. The text of `<title>` counts, as a reader sees it in the tab.
    CSS is not evaluated, so text hidden by a stylesheet still counts as visible.
    """
    return _collapse("".join(_scan(html).text))


def jsonld_mismatches(html: str) -> list[str]:
    """Every JSON-LD string, at any depth, that the page does not show, as "<key>: <value>".

    Exempt: the values under EXEMPT_KEYS, ISO dates, and a numeric `price` (build_jsonld has
    already tied each one to a price the page shows). A block that is not
    valid JSON is reported as "json-ld: block N is not valid JSON (...)" rather than skipped.
    """
    scan = _scan(html)
    shown = _collapse("".join(scan.text))
    problems = []
    for number, raw in enumerate(scan.blocks, start=1):
        try:
            data = json.loads(raw)
        except ValueError as err:
            problems.append(f"json-ld: block {number} is not valid JSON ({err})")
            continue
        for key, value in _strings(data, "(root)"):
            if _exempt(key, value) or _collapse(value) in shown:
                continue
            problems.append(f"{key}: {value}")
    return problems


def _strings(node: object, key: str):
    """(key, string) for every string under node. A list's items take the key of the list."""
    if isinstance(node, dict):
        for child_key, child in node.items():
            if child_key not in EXEMPT_KEYS:
                yield from _strings(child, child_key)
    elif isinstance(node, list):
        for item in node:
            yield from _strings(item, key)
    elif isinstance(node, str):
        yield key, node


def _exempt(key: str, value: str) -> bool:
    if ISO_DATE.fullmatch(value):
        return True
    return key == "price" and bool(PLAIN_NUMBER.fullmatch(value))
