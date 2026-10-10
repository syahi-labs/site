# tests/test_katha_site.py
#
# katha.syahi.sh's index, built from the same pipeline as syahi.sh: its site.yaml, the ported page and
# its parity with today's live page. katha.syahi.sh also serves feed.xml, which Spotify reads; nothing
# here may ever produce one.
import re
from pathlib import Path

import pytest
import yaml

from asset_urls import hashed_file, hashed_url, unhash
from checks import copycheck, htmlcheck
from css_guard import page_css_violations
from parity_helpers import PARITY, apply_allowed, apply_link_moves, link_values, words
from sitebuild.claims import ClaimRegister
from sitebuild.content import load_pages
from sitebuild.schema import jsonld_mismatches
from sitebuild.site import load_site

REPO = Path(__file__).resolve().parents[1]
KATHA = REPO / "katha"
SNAPSHOT = PARITY / "katha-index.html"
EM_DASH = chr(0x2014)

@pytest.fixture(scope="module")
def built(real_site):
    """The shared build of the real inputs: (root, out, result). The main host's own pages are ported
    in Task 9, and a stand-in fills in for any that is not there yet, so only the katha host is under test here."""
    return real_site


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
    assert hashed_file(host, "pages/katha-index.css").is_file()
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


def test_the_page_carries_the_katha_chrome(html, built):
    assert 'class="wordmark wordmark-katha"' in html
    assert 'href="https://syahi.sh/"' in html                       # the Syahi tab
    assert '<a class="cta" href="https://listen.katha.syahi.sh/">Visit the store</a>' in html
    assert '<link rel="canonical" href="https://katha.syahi.sh/">' in html
    assert f'<link rel="stylesheet" href="{hashed_url(built[1] / "katha.syahi.sh", "pages/katha-index.css")}">' in html
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


# ---- the page's own stylesheet ----

# Type roles as on today's page: the labels were IBM Plex Mono, the lead lines Fraunces. A page asks for a
# role by token; tokens.css decides the family.
SERIF = (".devanagari", ".sub", ".roman", ".beat strong", ".spine")
MONO = (".figcap", ".label", ".beat::marker", ".fit-card h2", ".slot-tag")


def rule(css: str, selector: str) -> str:
    match = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert match, f"no rule for {selector}"
    return match.group(1)


@pytest.mark.parametrize("selector, token", [(s, "--font-serif") for s in SERIF] + [(s, "--font-mono") for s in MONO])
def test_the_page_css_gives_each_role_its_family_by_token(selector, token):
    css = (REPO / "tokens" / "pages" / "katha-index.css").read_text(encoding="utf-8")
    assert re.search(r"font-family:\s*var\(" + token + r"\)", rule(css, selector)), selector


def test_the_page_css_passes_the_stricter_guard():
    assert page_css_violations((REPO / "tokens" / "pages" / "katha-index.css").read_text(encoding="utf-8")) == []


# ---- the port: markup-only changes, each one pinned ----

# Launch B2 (2026-10-10) made this page the listener page. The Task 9 port tests that pinned the old publisher body
# word for word (headings, beats, links, text and title parity against katha-index.html) moved to /katha, which kept
# that body (tests/test_parity.py). What this page says is pinned in tests/test_launch_pages.py.

def test_the_page_is_one_h1_and_h2s_below_it(html):
    assert re.findall(r"<h([1-6])\b", html.split("<main", 1)[1].split("</main>")[0]) == ["1", "2", "2"]


def test_the_devanagari_runs_are_marked_hindi(html):
    assert '<span lang="hi">कथा</span>' in html
    assert len(re.findall(r'<span lang="hi">', html)) >= 4


def test_the_hero_image_is_a_file_in_the_katha_hosts_own_output(built):
    host = built[1] / "katha.syahi.sh"
    page = (host / "index.html").read_text(encoding="utf-8")
    # The hero is a picture gated to wide screens: its sources name this host's own variants, the full size among them.
    srcset = re.search(r'<source type="image/webp" srcset="([^"]+)"', page).group(1)
    urls = re.findall(r"(/assets/img/gramophone-\d+w\.[0-9a-f]{10}\.webp) (\d+)w", srcset)
    assert [w for _, w in urls] == ["240", "480", "900"]
    assert all((host / url.lstrip("/")).is_file() for url, _ in urls)


# ---- the old page's allowed diffs (still /katha's), and no remote font or script ----

def test_every_allowed_diff_has_a_reason_and_none_hides_copy():
    entries = yaml.safe_load((PARITY / "allowed_diffs.yaml").read_text(encoding="utf-8"))["katha-index.html"]
    assert all(set(e) == {"text", "reason"} and e["reason"].strip() for e in entries)
    # Only the header strip and the three step numbers. Anything longer is copy.
    assert [e["text"] for e in entries] == ["SYAHI · KATHA AUDIO ENTRY 003 BENGALURU, IN", "01", "02", "03"]
