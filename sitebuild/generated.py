"""The files a crawler reads: sitemap.xml, robots.txt, llms.txt.

Each function returns text and decides nothing about which pages exist. The
pipeline passes `sitemap_xml` exactly the entries that belong in it. `llms_txt`
is given every page and leaves out the pending ones and /404 itself, because a
page list for readers must never name a page that is not live.
"""
from __future__ import annotations

import datetime
import re
from xml.sax.saxutils import escape

from sitebuild.claims import ClaimRegister
from sitebuild.content import Page
from sitebuild.schema import page_url
from sitebuild.site import SiteConfig

NOT_FOUND_SLUG = "/404"
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
LLMS_TITLE = "Syahi"
SUMMARY_CLAIM = "org-summary"


def sitemap_xml(entries: list[tuple[str, datetime.date]], base_url: str) -> str:
    """A sitemaps.org 0.9 urlset: one `url` per (slug, date), sorted by slug, clean URLs.

    Raises ValueError for the /404 page or a slug given twice: both are mistakes in the caller.
    """
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
