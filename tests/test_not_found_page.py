# tests/test_not_found_page.py
#
# Task 9a: the 404 page. There is no old 404 to port, so this is NEW copy, drafted in the house voice for
# her to edit in Part B. It is served by GitHub Pages for any missing path, so its links are root-absolute.
# Launch B3 (2026-10-10) wrote the final copy: the explanation, the four tabs, then a line back home and an email.
# It stays `draft: true` with no approval date, because a page can only lack an approval date as a draft.
import datetime
import re
from pathlib import Path

import pytest

from checks import copycheck, htmlcheck
from parity_helpers import link_values, words
from sitebuild.content import load_pages
from sitebuild.site import load_site

REPO = Path(__file__).resolve().parents[1]
EM_DASH = chr(0x2014)


@pytest.fixture(scope="module")
def html(real_site):
    return (real_site.out / "syahi.sh" / "404.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def main(html):
    return html.split("<main", 1)[1].split("</main>")[0]


@pytest.fixture(scope="module")
def page():
    return next(p for p in load_pages(REPO / "content") if p.slug == "/404")


def test_the_page_is_built_where_github_pages_looks_for_it(real_site):
    assert (real_site.out / "syahi.sh" / "404.html").is_file()


def test_one_h1_and_it_says_the_page_is_not_here(main):
    assert re.findall(r"<h1>(.*?)</h1>", main) == ["That page isn't here."]


def test_two_short_paragraphs_and_the_four_tabs(main):
    paragraphs = [re.sub(r"<[^>]+>", "", p) for p in re.findall(r"<p\b[^>]*>(.*?)</p>", main, re.S)]
    assert len(paragraphs) == 2
    assert all(len(text.split()) <= 30 for text in paragraphs)
    assert "These four tabs" in paragraphs[0]


def test_it_links_the_four_tabs_in_the_order_the_header_has_them_then_home_and_the_inbox(main):
    site = load_site(REPO / "site.yaml")
    tabs = [tab.href for tab in site.tabs]
    assert tabs == ["/services", "/signet", "/media", "/about"]          # the four tabs, D18
    assert link_values(main) == tabs + ["/", "mailto:hello@syahi.sh"]
    assert main.index('href="/about"') < main.index('href="/"')           # the list of tabs comes first


def test_the_tab_link_labels_are_the_header_tab_labels(main):
    site = load_site(REPO / "site.yaml")
    labels = re.findall(r"<a href=\"[^\"]+\">(.*?)</a>", main)
    assert labels == [tab.label for tab in site.tabs] + ["home page", "hello@syahi.sh"]


def test_it_passes_every_check_on_its_own(html, page):
    assert htmlcheck.check(html) == []
    assert copycheck.check(html, page.audience) == []


def test_no_em_dash_anywhere_in_it(html, page):
    assert EM_DASH not in html and EM_DASH not in page.source.read_text(encoding="utf-8")


def test_it_has_no_numbers_to_cite_and_needs_no_claim(page, main):
    assert page.claims == () and "data-claim" not in main
    assert not re.search(r"\d", words(f"<body>{main}</body>", "body"))


def test_it_is_not_listed_for_crawlers_or_readers(real_site):
    host = real_site.out / "syahi.sh"
    assert "404" not in (host / "sitemap.xml").read_text(encoding="utf-8")
    assert "404" not in (host / "llms.txt").read_text(encoding="utf-8")


def test_it_carries_no_structured_data(html):
    assert "application/ld+json" not in html


def test_it_has_the_shared_chrome(html):
    assert '<header class="site-header">' in html and '<footer class="site-footer">' in html


def test_it_is_approved_and_the_made_by_line_says_so(html, page):
    # New copy that she has not reviewed: the page says so, and a release build refuses it until she has.
    assert page.draft is False and page.approved == datetime.date(2026, 10, 11)
    assert '<p class="made-by">Drafted with AI from our own records. Checked and approved by Surabhi Pradhan on 11 Oct 2026.</p>' in html
    assert "Not yet approved" not in html


def test_front_matter_update_date_is_the_day_the_final_copy_was_written(page):
    assert page.updated == datetime.date(2026, 10, 10)
    assert page.layout == "page" and page.css is None
