# tests/test_katha_site.py
#
# katha.syahi.sh's index, built from the same pipeline as syahi.sh: its site.yaml, the ported page and
# its parity with today's live page. katha.syahi.sh also serves feed.xml, which Spotify reads; nothing
# here may ever produce one.
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path

import pytest
import yaml

from checks import copycheck, htmlcheck
from sitebuild.claims import ClaimRegister
from sitebuild.content import load_pages
from sitebuild.pipeline import build
from sitebuild.schema import jsonld_mismatches
from sitebuild.site import load_site

REPO = Path(__file__).resolve().parents[1]
PARITY = Path(__file__).parent / "parity"
KATHA = REPO / "katha"
SNAPSHOT = PARITY / "katha-index.html"
EM_DASH = chr(0x2014)

# The real inputs the build reads, copied to a throwaway root. The main host's own pages are ported in
# Task 9, so until they exist a stub stands in for them: only the katha host is under test here.
REAL_INPUTS = ("katha", "data", "templates", "tokens", "assets", "content")
STUB = """---
title: Stand-in
description: A stand-in for the main host's pages, which are ported separately.
updated: 2026-10-06
approved: 2026-10-06
layout: page
---
<h1>Stand-in</h1>
"""


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("site")
    for name in REAL_INPUTS:
        if (REPO / name).is_dir():
            shutil.copytree(REPO / name, root / name)
    shutil.copy(REPO / "site.yaml", root / "site.yaml")
    if not (root / "content").is_dir():
        (root / "content").mkdir()
        (root / "content" / "index.html").write_text(STUB, encoding="utf-8")
    out = tmp_path_factory.mktemp("out") / "dist"
    result = build(root, out)
    return root, out, result


KATHA_PREFIXES = ("katha.syahi.sh", "katha/")   # its output (sitecheck, sitemap) and its source files


def own(built):
    """The katha host's problems and warnings: what names its output or its source, paths made relative.

    Until the main host's pages are ported its own problems (no org-summary for llms.txt) are expected
    and are not this test's business, so each message is attributed by where it points.
    """
    root, out, result = built
    relative = lambda item: item.replace(str(out), "").replace(str(root), "").lstrip("/")
    mine = lambda items: [relative(i) for i in items if relative(i).startswith(KATHA_PREFIXES)]
    return mine(result.problems), mine(result.warnings)


@pytest.fixture(scope="module")
def html(built):
    return (built[1] / "katha.syahi.sh" / "index.html").read_text(encoding="utf-8")


# ---- katha/site.yaml ----

def test_site_yaml_is_the_katha_chrome():
    site = load_site(KATHA / "site.yaml")
    assert site.header == "katha"
    assert site.base_url == "https://katha.syahi.sh"
    assert [(t.label, t.href) for t in site.tabs] == [("Listen", "/"), ("Syahi", "https://syahi.sh/")]
    assert (site.cta.label, site.cta.href) == ("Visit the store", "https://listen.katha.syahi.sh/")
    assert site.pending_pages == frozenset()


def test_site_yaml_policies_are_syahi_shs_by_absolute_url():
    site = load_site(KATHA / "site.yaml")
    main = load_site(REPO / "site.yaml")
    assert [link.label for link in site.policies] == [link.label for link in main.policies]
    assert [link.href for link in site.policies] == ["https://syahi.sh" + link.href for link in main.policies]
    assert all(link.href.startswith("https://syahi.sh/") for link in site.policies)


def test_site_yaml_has_the_same_company_profiles_as_syahi_sh():
    assert load_site(KATHA / "site.yaml").profiles == load_site(REPO / "site.yaml").profiles


# ---- the build ----

def test_the_katha_host_builds_with_no_problem_of_its_own(built):
    problems, _ = own(built)
    assert problems == []


def test_the_katha_host_has_no_warning_of_its_own(built):
    _, warnings = own(built)
    assert warnings == []


def test_the_output_is_what_the_publish_step_copies_and_never_a_feed(built):
    host = built[1] / "katha.syahi.sh"
    for name in ("index.html", "robots.txt", "sitemap.xml"):
        assert (host / name).is_file(), name
    assert (host / "assets" / "pages" / "katha-index.css").is_file()
    assert not list((built[1]).rglob("feed.xml")) and not list(built[1].rglob("CNAME"))


def test_sitemap_and_robots_name_the_katha_host(built):
    host = built[1] / "katha.syahi.sh"
    assert "<loc>https://katha.syahi.sh/</loc>" in (host / "sitemap.xml").read_text(encoding="utf-8")
    assert "Sitemap: https://katha.syahi.sh/sitemap.xml" in (host / "robots.txt").read_text(encoding="utf-8")


def test_the_page_passes_every_check_on_its_own(html):
    page = next(p for p in load_pages(KATHA / "content") if p.slug == "/")
    assert htmlcheck.check(html) == []
    assert copycheck.check(html, page.audience) == []
    assert jsonld_mismatches(html) == []


def test_the_page_carries_the_katha_chrome(html):
    assert 'class="wordmark wordmark-katha"' in html
    assert 'href="https://syahi.sh/"' in html                       # the Syahi tab
    assert '<a class="cta" href="https://listen.katha.syahi.sh/">Visit the store</a>' in html
    assert '<link rel="canonical" href="https://katha.syahi.sh/">' in html
    assert '<link rel="stylesheet" href="/assets/pages/katha-index.css">' in html
    for href in ("https://syahi.sh/privacy", "https://syahi.sh/terms", "https://syahi.sh/refund", "https://syahi.sh/contact"):
        assert f'href="{href}"' in html
    assert '<span data-claim="org-legal-name">' in html and '<span data-claim="org-llpin">' in html


def test_no_em_dash_in_the_page_its_css_or_its_site_yaml():
    for path in (KATHA / "content" / "index.html", KATHA / "site.yaml", REPO / "tokens" / "pages" / "katha-index.css"):
        assert EM_DASH not in path.read_text(encoding="utf-8"), path


def test_the_claims_register_loads_and_every_claim_has_a_public_source():
    register = ClaimRegister.load(REPO / "data" / "claims.yaml")
    for claim in register.claims.values():
        assert claim.source.strip(), claim.id
    for id in ("org-legal-name", "org-llpin", "katha-sample-length"):
        assert register.get(id)
    assert register.get("org-llpin").text.startswith("LLPIN ")   # the footer adds no label of its own


# ---- the port: markup-only changes, each one pinned ----

def test_the_one_heading_below_the_h1_is_an_h2_with_its_words_kept(html):
    # Today's page jumps from h1 to h3. Fixed by changing the level, not the words.
    assert re.findall(r"<h([1-6])\b", html.split("<main", 1)[1].split("</main>")[0]) == ["1", "2"]
    assert re.search(r"<h2[^>]*>For</h2>", html)


def test_both_devanagari_runs_are_marked_hindi(html):
    assert len(re.findall(r'<span lang="hi">अधूरे हिसाब</span>', html)) == 2     # the listen line and the sample
    assert '<span lang="hi">कथा</span>' in html


def test_the_beats_are_an_ordered_list_of_three(html):
    block = re.search(r'<ol class="beats">(.*?)</ol>', html, re.S).group(1)
    assert len(re.findall(r"<li\b", block)) == 3
    assert [t.strip() for t in re.findall(r"<strong>(.*?)</strong>", block)] == [
        "Agents produce", "Every sentence checked", "A human signs off"]


def test_links_and_media_are_the_old_pages_exactly(html):
    # The same set of href and src values in the page's own content, compared whole, not as substrings.
    attrs = lambda markup: set(re.findall(r'(?:href|src)="([^"]+)"', markup))
    old = SNAPSHOT.read_text(encoding="utf-8").split('<div class="hero-grid">', 1)[1].split("</main>")[0]
    new = html.split("<main", 1)[1].split("</main>")[0]
    assert attrs(new) == attrs(old)
    assert len(attrs(old)) == 6      # the guard cannot pass by both sides being empty


# ---- parity with today's live page ----

class Text(HTMLParser):
    """The words a reader sees: body text minus the old page's footer, scripts, styles and svg."""

    SKIP = frozenset({"script", "style", "footer", "nav", "noscript", "canvas", "svg", "head"})

    def __init__(self, scope: str):
        super().__init__(convert_charrefs=True)
        self.scope, self.depth, self.inside, self.out = scope, 0, False, []

    def handle_starttag(self, tag, attrs):
        if tag == self.scope:
            self.inside = True
        if tag in self.SKIP:
            self.depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth:
            self.depth -= 1
        if tag == self.scope and self.scope == "main":
            self.inside = False

    def handle_data(self, data):
        if self.inside and not self.depth:
            self.out.append(data)


def words(markup: str, scope: str) -> str:
    parser = Text(scope)
    parser.feed(markup)
    return re.sub(r"\s+", " ", " ".join(parser.out)).strip()


def apply_allowed(old: str, key: str) -> str:
    """Remove each allowed difference from the old text, once. A stale entry is an error."""
    entries = yaml.safe_load((PARITY / "allowed_diffs.yaml").read_text(encoding="utf-8")) or {}
    for entry in entries.get(key, []):
        assert entry.get("reason", "").strip(), f"allowed diff {entry['text']!r} has no reason"
        pattern = r"(?<!\S)" + re.escape(entry["text"]) + r"(?!\S)"
        old, removed = re.subn(pattern, "", old, count=1)
        assert removed == 1, f"allowed diff {entry['text']!r} is not in the old page: remove the entry"
    return re.sub(r"\s+", " ", old).strip()


def test_main_text_is_the_old_pages_text_word_for_word(html):
    old = apply_allowed(words(SNAPSHOT.read_text(encoding="utf-8"), "body"), "katha-index.html")
    new = words(html, "main")
    assert new == old


def test_every_old_sentence_survives_in_the_new_main(html):
    # A guard on the guard: the comparison above cannot pass by both sides being empty.
    new = words(html, "main")
    for phrase in ("Every sentence verified against the source.", "A human signs off",
                   "Bring a catalog, or one title you care about.", "No checkout, no commitment."):
        assert phrase in new


def test_title_and_description_are_the_old_pages_exactly(html):
    old = SNAPSHOT.read_text(encoding="utf-8")
    title = re.search(r"<title>(.*?)</title>", old).group(1)
    description = re.search(r'<meta name="description" content="(.*?)">', old).group(1)
    assert f"<title>{title}</title>" in html
    assert f'<meta name="description" content="{description}">' in html


def test_every_allowed_diff_has_a_reason_and_none_hides_copy():
    entries = yaml.safe_load((PARITY / "allowed_diffs.yaml").read_text(encoding="utf-8"))["katha-index.html"]
    assert all(set(e) == {"text", "reason"} and e["reason"].strip() for e in entries)
    # Only the header strip and the three step numbers. Anything longer is copy.
    assert [e["text"] for e in entries] == ["SYAHI · KATHA AUDIO ENTRY 003 BENGALURU, IN", "01", "02", "03"]
