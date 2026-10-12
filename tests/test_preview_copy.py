# tests/test_preview_copy.py
#
# Task 9c fix round 1: a ported page keeps today's link preview. Today's pages said one thing to a person reading
# the page (title, description) and another to the card a shared link unfurls into (og:title, og:description,
# og:image:alt and the twitter pair). The base now emits the preview's own words from the optional front matter
# `og_title`, `og_description` and `og_image_alt`, and falls back on the title and description. This compares
# what each ported page emits with what its snapshot (tests/parity/) said, tag by tag, so no preview can drift.
# Task 9d adds the services page: today's preview was its title and description, so it carries no preview front matter.
import re
from html import unescape
from pathlib import Path

import pytest

from checks import copycheck
from parity_helpers import PARITY
from sitebuild.content import load_pages

REPO = Path(__file__).resolve().parents[1]
EM_DASH = chr(0x2014)

# (snapshot, host, built file, page source under that host's content folder)
PAGES = [
    # The home is not here: launch B1 rewrote it, so no snapshot's preview is its contract (tests/test_launch_pages.py).
    ("site-contact.html", "syahi.sh", "contact.html", "content/contact.html"),
    ("site-privacy.html", "syahi.sh", "privacy.html", "content/privacy.html"),
    ("site-terms.html", "syahi.sh", "terms.html", "content/terms.html"),
    ("site-refund.html", "syahi.sh", "refund.html", "content/refund.html"),
    ("signet.html", "syahi.sh", "signet.html", "content/signet.html"),
    ("katha-index.html", "syahi.sh", "katha.html", "content/katha.html"),
    ("services.html", "syahi.sh", "services/quote.html", "content/services/quote.html"),
    # katha.syahi.sh `/` is not here: launch B2 made it the listener page, so no snapshot's preview is its contract.
    # Its preview words are pinned in tests/test_launch_pages.py.
]
IDS = [f"{host}/{built}" for _, host, built, _ in PAGES]
# the pages whose preview says something other than their title and description: today's values, kept
OWN_PREVIEW = {"content/signet.html", "content/katha.html"}

TAG = re.compile(r'<meta\s+(?:property|name)="([^"]+)"\s+content="([^"]*)"\s*/?>')


def metas(markup):
    """Every meta tag's name or property and its content, as the browser reads it (entities decoded)."""
    head = markup.split("</head>")[0]
    return {name: unescape(content) for name, content in TAG.findall(head)}


def snapshot(name):
    return metas((PARITY / name).read_text(encoding="utf-8"))


def built(real_site, host, name):
    return metas((real_site.out / host / name).read_text(encoding="utf-8"))


def page_at(source):
    pages = [*load_pages(REPO / "content"), *load_pages(REPO / "katha" / "content")]
    return next(p for p in pages if p.source == REPO / source)


@pytest.mark.parametrize("snap, host, name, source", PAGES, ids=IDS)
def test_the_open_graph_title_description_and_alt_are_todays(real_site, snap, host, name, source):
    old, new = snapshot(snap), built(real_site, host, name)
    assert new["og:title"] == old["og:title"]
    assert new["og:description"] == old["og:description"]
    assert new.get("og:image:alt") == old.get("og:image:alt")


@pytest.mark.parametrize("snap, host, name, source", PAGES, ids=IDS)
def test_the_twitter_title_description_and_alt_are_todays_or_the_open_graph_ones_where_today_had_none(real_site, snap, host, name, source):
    old, new = snapshot(snap), built(real_site, host, name)
    assert new["twitter:title"] == old.get("twitter:title", old["og:title"])
    assert new["twitter:description"] == old.get("twitter:description", old["og:description"])
    assert new.get("twitter:image:alt") == old.get("twitter:image:alt", old.get("og:image:alt"))


# Descriptions she changed on purpose after the snapshot, page by page, with her words in the site's tests.
CHANGED_DESCRIPTIONS = {
    # her A, 2026-10-12: the old one ran 179 characters and Google cut it
    "katha.html": "Indian-language audiobooks for rights-holders whose catalog has no audio. "
                  "Every sentence checked against the printed text, and a human signs off.",
}


@pytest.mark.parametrize("snap, host, name, source", PAGES, ids=IDS)
def test_the_title_and_the_description_are_still_the_pages_own(real_site, snap, host, name, source):
    old, new = snapshot(snap), built(real_site, host, name)
    assert new["description"] == CHANGED_DESCRIPTIONS.get(name if host == "syahi.sh" else None, old["description"])
    html = (real_site.out / host / name).read_text(encoding="utf-8")
    assert unescape(re.search(r"<title>(.*?)</title>", html).group(1)) == unescape(
        re.search(r"<title>(.*?)</title>", (PARITY / snap).read_text(encoding="utf-8"), re.S).group(1).strip())


@pytest.mark.parametrize("snap, host, name, source", PAGES, ids=IDS)
def test_a_page_carries_front_matter_for_its_preview_only_where_today_differed(snap, host, name, source):
    found = page_at(source)
    old = snapshot(snap)
    differs = old["og:title"] != unescape(found.title) or old["og:description"] != unescape(found.description)
    assert differs is (source in OWN_PREVIEW), source
    if differs:
        assert found.og_title == old["og:title"] and found.og_description == old["og:description"]
    else:
        assert found.og_title is None and found.og_description is None
    assert found.og_image_alt == old.get("og:image:alt")


def test_signets_preview_is_the_wording_tap_1_shipped(real_site):
    new = built(real_site, "syahi.sh", "signet.html")
    assert new["og:title"] == "Signet by Syahi: the decision ledger for AI that talks to your customers"
    assert new["og:description"].startswith("The decision ledger for AI that talks to your customers.")
    assert new["og:description"].endswith("Veto always wins. Every decision leaves a receipt.")
    assert new["og:image:alt"] == ("The Signet seal above the words: Agents do the work. You keep the say-so. "
                                   "Signet by Syahi, a decision ledger.")
    assert new["og:title"] == new["twitter:title"] and new["og:image:alt"] == new["twitter:image:alt"]


def test_every_other_page_has_no_image_alt_because_today_had_none(real_site):
    for snap, host, name, _ in PAGES:
        if snap != "signet.html":
            assert "og:image:alt" not in built(real_site, host, name), (host, name)


@pytest.mark.parametrize("snap, host, name, source", PAGES, ids=IDS)
def test_the_preview_copy_passes_the_copy_check_and_has_no_em_dash(real_site, snap, host, name, source):
    html = (real_site.out / host / name).read_text(encoding="utf-8")
    found = page_at(source)
    assert copycheck.check(html, found.audience) == []
    for value in (found.og_title, found.og_description, found.og_image_alt):
        assert value is None or EM_DASH not in value
    assert EM_DASH not in html


def test_the_copy_check_reads_the_preview_copy_of_the_pages_that_have_it(real_site):
    # Signet's preview words are different from its title, so they are what the check must have read.
    html = (real_site.out / "syahi.sh" / "signet.html").read_text(encoding="utf-8")
    broken = html.replace("Every decision leaves a receipt.", "We leverage every decision.")
    assert [f for f in copycheck.check(broken, None) if "og:description" in f and "leverage" in f]
