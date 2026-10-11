"""The files a crawler or the edge reads: sitemap.xml, robots.txt, llms.txt, _headers.

Each function returns text and decides nothing about which pages exist. The
pipeline passes `sitemap_xml` exactly the entries that belong in it. `llms_txt`
is given every page and leaves out the pending ones and /404 itself, because a
page list for readers must never name a page that is not live.
"""
from __future__ import annotations

import datetime
import re
from typing import Iterable
from xml.sax.saxutils import escape

from sitebuild.claims import ClaimRegister
from sitebuild.content import Page
from sitebuild.schema import page_url
from sitebuild.site import SiteConfig

NOT_FOUND_SLUG = "/404"
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
LLMS_TITLE = "Syahi"
SUMMARY_CLAIM = "org-summary"


def sitemap_xml(entries: Iterable[tuple[str, datetime.date]], base_url: str) -> str:
    """A sitemaps.org 0.9 urlset: one `url` per (slug, date), sorted by slug, clean URLs.

    Raises ValueError for the /404 page or a slug given twice: both are mistakes in the caller.
    """
    entries = list(entries)  # read once: a generator would be spent by the slug checks
    slugs = [slug for slug, _ in entries]
    if NOT_FOUND_SLUG in slugs:
        raise ValueError(f"{NOT_FOUND_SLUG} does not belong in a sitemap")
    repeated = sorted({slug for slug in slugs if slugs.count(slug) > 1})
    if repeated:
        raise ValueError(f"slug listed more than once in the sitemap: {', '.join(repeated)}")
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', f'<urlset xmlns="{SITEMAP_NS}">']
    for slug, date in sorted(entries, key=lambda entry: entry[0]):
        lines += [
            "  <url>",
            f"    <loc>{escape(page_url(base_url, slug))}</loc>",
            f"    <lastmod>{date.isoformat()}</lastmod>",
            "  </url>",
        ]
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def robots_txt(base_url: str) -> str:
    """Every crawler allowed (D7), and where the sitemap is."""
    return f"User-agent: *\nAllow: /\n\nSitemap: {base_url}/sitemap.xml\n"


def llms_txt(site: SiteConfig, pages: list[Page], claims: ClaimRegister) -> str:
    """A plain-text guide for answer engines: who we are, then each live page with its description."""
    # claims.get, not claims.text: the register's `used` set records what pages render, not what generators read.
    summary = _one_line(claims.get(SUMMARY_CLAIM).text)
    listed = sorted(
        (page for page in pages if page.slug != NOT_FOUND_SLUG and page.slug not in site.pending_pages),
        key=lambda page: page.slug,
    )
    lines = [f"# {LLMS_TITLE}", "", f"> {summary}", "", "## Pages"]
    if listed:
        lines.append("")
    for page in listed:
        lines.append(f"- [{_one_line(page.title)}]({page_url(site.base_url, page.slug)}): {_one_line(page.description)}")
    return "\n".join(lines) + "\n"


def _one_line(text: str) -> str:
    """Whitespace runs, newlines included, become one space: a folded YAML value must not split a list line."""
    return re.sub(r"\s+", " ", text).strip()


IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
SHORT_CACHE = "public, max-age=3600"


def headers_txt(stable_assets: Iterable[str]) -> str:
    """Cloudflare Workers static-assets `_headers`: a hashed asset never changes under its name, so it is cached for a year.

    `stable_assets` are the paths under assets/ that keep a name whose bytes can change (the share images, the
    favicons, the marks): each gets a short cache instead. The edge adds up every rule a path matches, so the
    stable rule first detaches the Cache-Control the /assets/* rule set, then sets its own.
    """
    lines = ["/assets/*", f"  Cache-Control: {IMMUTABLE_CACHE}"]
    for key in sorted(set(stable_assets)):
        lines += ["", f"/assets/{key}", "  ! Cache-Control", f"  Cache-Control: {SHORT_CACHE}"]
    return "\n".join(lines) + "\n"
