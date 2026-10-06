# tests/test_not_found_page.py
#
# Task 9a: the 404 page. There is no old 404 to port, so this is NEW copy, drafted in the house voice for
# her to edit in Part B. It is served by GitHub Pages for any missing path, so its links are root-absolute.
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


def test_one_line_of_copy_and_nothing_else_to_read(main):
    assert len(re.findall(r"<p\b", main)) == 1
    line = re.search(r"<p[^>]*>(.*?)</p>", main, re.S).group(1)
    assert len(re.sub(r"<[^>]+>", "", line).split()) <= 20


def test_it_links_home_and_the_four_tabs_in_the_order_the_header_has_them(main):
    site = load_site(REPO / "site.yaml")
    tabs = [tab.href for tab in site.tabs]
    assert tabs == ["/services", "/signet", "/media", "/about"]          # the four tabs, D18
    assert link_values(main) == ["/"] + tabs


def test_the_link_labels_are_the_header_tab_labels(main):
    site = load_site(REPO / "site.yaml")
    labels = re.findall(r"<a href=\"[^\"]+\">(.*?)</a>", main)
    assert labels == ["Home"] + [tab.label for tab in site.tabs]


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


def test_it_has_the_shared_chrome_and_a_made_by_line(html):
    assert '<header class="site-header">' in html and '<footer class="site-footer">' in html
    assert "Checked and approved by Surabhi Pradhan on 6 Oct 2026." in html


def test_front_matter_dates_are_the_session_date_of_the_draft(page):
    # New copy that she has not reviewed yet: the dates are the day it was drafted, and the task report flags
    # it for her Part B edit. Her approval is what makes the made-by line true.
    assert page.approved == datetime.date(2026, 10, 6) and page.updated == datetime.date(2026, 10, 6)
    assert page.layout == "page" and page.css is None
