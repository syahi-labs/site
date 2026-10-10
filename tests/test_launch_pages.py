# tests/test_launch_pages.py
#
# Launch Part B1: the five drafted pages, home (rewritten), /services, /about, /media and /paper-machine. They are
# drafts (draft: true, approved empty) until she approves them on Sunday, so the build warns and a release refuses.
# What these tests hold: each page is built, has one h1, passes the copy, HTML and D10 checks and its structured
# data matches what it shows; every figure and named fact is a claim; the rules she set for these pages
# (no price on services, no agent or AI in the first line of home and services, her personal profiles only on
# /about, Chhavi Films never, Signet's customers only in the D10 sentence) hold on what the build wrote.
import datetime
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from checks import copycheck, d10check, htmlcheck
from sitebuild.claims import ClaimRegister
from sitebuild.content import load_pages
from sitebuild.schema import jsonld_mismatches
from sitebuild.site import load_site

REPO = Path(__file__).resolve().parents[1]
EM_DASH, EN_DASH = chr(0x2014), chr(0x2013)
DRAFTED = datetime.date(2026, 10, 10)

# slug -> (built file, audience). Home and /services are for an owner, so "agent" and "AI" stay out of their first line.
PAGES = {
    "/": ("index.html", "owner"),
    "/services": ("services.html", "owner"),
    "/about": ("about.html", None),
    "/media": ("media.html", None),
    "/paper-machine": ("paper-machine.html", None),
}
NEW = [slug for slug in PAGES if slug != "/"]

# The five plates of the Field Guide that the channel's own playlist lists as published (read through the YouTube API
# 2026-10-10, 10-SYAHI/org/published/catalogue.md). Plate six is not published and must not be listed.
PUBLISHED_VIDEOS = ["JsBHFsB8WlA", "VwmYaB2SweM", "WFLsJqOxOnE", "sI27VV4OR3A", "PlgCc5JFUHw"]


@pytest.fixture(scope="module")
def dist(real_site):
    return real_site.out / "syahi.sh"


@pytest.fixture(scope="module")
def register():
    return ClaimRegister.load(REPO / "data" / "claims.yaml")


@pytest.fixture(scope="module")
def site():
    return load_site(REPO / "site.yaml")


def source(slug):
    return next(page for page in load_pages(REPO / "content") if page.slug == slug)


def built(dist, slug):
    return (dist / PAGES[slug][0]).read_text(encoding="utf-8")


def main_of(html):
    return html.split("<main", 1)[1].split("</main>")[0]


def text_of(markup):
    class Text(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts = []

        def handle_data(self, data):
            self.parts.append(data)

    scan = Text()
    scan.feed(markup)
    return " ".join("".join(scan.parts).split())


def jsonld(html):
    return [json.loads(block) for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


# ---- built, drafted, and clean ----

def test_the_whole_build_has_no_problem_and_no_page_is_pending(real_site, site):
    assert real_site.result.problems == []
    assert site.pending_pages == frozenset()


@pytest.mark.parametrize("slug", PAGES)
def test_each_page_is_built_listed_and_canonical(dist, slug):
    html = built(dist, slug)
    assert "Stand-in" not in html
    url = "https://syahi.sh" + slug
    assert f'<link rel="canonical" href="{url}">' in html
    assert f"<loc>{url}</loc>" in (dist / "sitemap.xml").read_text(encoding="utf-8")


@pytest.mark.parametrize("slug", PAGES)
def test_each_page_has_exactly_one_h1(dist, slug):
    assert len(re.findall(r"<h1[ >]", built(dist, slug))) == 1


@pytest.mark.parametrize("slug", PAGES)
def test_each_page_is_a_draft_awaiting_her_approval(dist, slug):
    page = source(slug)
    assert page.draft is True and page.approved is None
    assert page.updated == DRAFTED
    assert page.layout == "page"
    assert "Not yet approved" in built(dist, slug)


@pytest.mark.parametrize("slug", PAGES)
def test_each_page_passes_the_copy_html_and_d10_checks(dist, register, slug):
    html = built(dist, slug)
    audience = PAGES[slug][1]
    assert source(slug).audience == audience
    assert copycheck.check(html, audience) == []
    assert htmlcheck.check(html, register.renderings()) == []
    assert d10check.check(html, slug) == []
    assert jsonld_mismatches(html) == []


@pytest.mark.parametrize("slug", PAGES)
def test_the_source_has_no_em_or_en_dash(slug):
    page = source(slug)
    text = page.source.read_text(encoding="utf-8")
    assert EM_DASH not in text and EN_DASH not in text


@pytest.mark.parametrize("slug", PAGES)
def test_every_claim_the_page_renders_is_in_its_front_matter(dist, slug):
    page = source(slug)
    spans = set(re.findall(r'data-claim="([^"]+)"', main_of(built(dist, slug))))   # the footer's legal line is the layout's
    assert spans <= set(page.claims)
    # a claim in front matter that shows no span is used in an attribute (a link), which only the plate URLs do
    assert all(id.startswith("pm-plate-") and id.endswith("-url") for id in set(page.claims) - spans)


@pytest.mark.parametrize("slug", NEW)
def test_the_new_pages_use_the_story_sheet_and_every_claim_they_list_is_live(slug, register):
    page = source(slug)
    assert page.css == "story"
    for id in page.claims:
        assert register.get(id).status == "live"      # get() refuses a retired claim, so this proves it is in the register


# ---- the rules she set ----

@pytest.mark.parametrize("slug", ["/", "/services"])
def test_the_first_line_names_neither_agents_nor_ai(dist, slug):
    main = main_of(built(dist, slug))
    first_block = re.search(r"<(?:p|h1)[^>]*>(.*?)</(?:p|h1)>", main, re.S).group(1)
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", main, re.S).group(1)
    for opening in (text_of(first_block), text_of(h1)):
        assert not re.search(r"\bagents?\b|\bAI\b", opening, re.I), opening


@pytest.mark.parametrize("slug", ["/", "/services"])
def test_no_price_on_the_owner_pages(dist, slug):
    text = text_of(main_of(built(dist, slug)))
    assert not re.search(r"₹|\bRs\.?\s?\d|\bINR\b|\$\s?\d|\blakh\b|\bper month\b|\ba month\b.*\d", text)


def test_the_services_item_that_says_hours_a_month_is_keep_it_running_and_no_price(dist):
    text = text_of(main_of(built(dist, "/services")))
    assert "four hours a month" in text and "Every price is said on the call." in text
    assert not re.search(r"\d", text.replace("30-minute", "").replace("30 days", ""))


def test_her_personal_profiles_are_on_about_and_nowhere_else(dist, site):
    links = [link.href for link in site.founder_profiles]
    assert links == ["https://x.com/surabhipradhan", "https://github.com/surpradhan"]
    for path in sorted(dist.rglob("*.html")):
        html = path.read_text(encoding="utf-8")
        for href in links:
            assert (href in html) == (path.name == "about.html"), (path.name, href)


def test_chhavi_films_never_appears(dist):
    for path in dist.rglob("*"):
        if path.is_file() and path.suffix in (".html", ".txt", ".xml"):
            assert "chhavi" not in path.read_text(encoding="utf-8").lower(), path.name


def test_signets_customers_are_only_in_the_d10_sentence(dist):
    full = "Next: the same loop for your business's drafts."
    first_beat = "Live today: every post, outreach email and desk draft our agents make waits for Surabhi's yes in Signet."
    for slug in PAGES:
        html = built(dist, slug)
        text = text_of(main_of(html))
        assert full not in text and "No outside customers yet" not in text and "Founding users" not in text, slug
        assert text.count(first_beat) == (1 if slug == "/about" else 0), slug
        assert 'data-claim="signet-d10"' not in html, slug


def test_the_header_has_no_link_to_a_page_that_is_not_built(dist, site):
    for link in (*site.tabs, *site.policies):
        file = dist / ("index.html" if link.href == "/" else link.href.lstrip("/") + ".html")
        assert file.is_file(), link.href


# ---- home ----

def test_home_keeps_the_four_cards_and_the_house_mark(dist):
    main = main_of(built(dist, "/"))
    cards = re.findall(r'<a class="card" id="(\w+)" href="([^"]+)"', main)
    assert cards == [("signet", "/signet"), ("studio", "/services/quote"), ("katha", "/katha"),
                     ("papermachine", "https://youtube.com/@papermachine07")]
    assert "inkpot" in main and "the house mark" in main and "partials" not in main
    assert re.search(r"<h1>Syahi<svg", main)


def test_home_sells_with_her_triad_as_three_beats_and_one_action(dist):
    main = main_of(built(dist, "/"))
    assert "operate efficiently, analyze deeply and grow" in main.replace("&nbsp;", " ")
    assert re.findall(r"<h2>(.*?)</h2>", main)[:3] == ["Operate efficiently", "Analyze deeply", "Grow immensely"]
    hero = main.split('<div class="beats">')[0]
    actions = re.findall(r'<a class="cta" href="([^"]+)"', hero)
    assert actions == ["https://cal.com/surabhipradhan/30-mins-discussion-about-syahi"]
    assert "Book a call" in hero


# ---- /services ----

def test_services_is_the_closed_list_of_five_with_for_and_you_end_up_with(dist, register):
    main = main_of(built(dist, "/services"))
    items = main.split('<li class="item">')[1:]
    assert len(items) == 5
    for item in items:
        assert "<dt>For</dt>" in item and "<dt>You end up with</dt>" in item
    names = [text_of(re.search(r"<h3>(.*?)</h3>", item, re.S).group(1)) for item in items]
    assert names[0] == "A free 30-minute call" and names[1] == "The assessment" and names[2] == "Named builds"
    assert names[3] == register.get("agent-os-name").text and names[4] == "Keep It Running"
    assert 'href="/services/quote"' in items[2]                      # the worked example


# ---- /about ----

def test_about_is_a_profile_page_whose_person_matches_the_page(dist, register, site):
    html = built(dist, "/about")
    nodes = jsonld(html)
    (profile,) = [node for node in nodes if node["@type"] == "ProfilePage"]
    person = profile["mainEntity"]
    assert person["@type"] == "Person" and person["@id"] == "https://syahi.sh/about#surabhi"
    assert person["name"] == register.get("founder-name").text
    assert person["description"] == register.get("founder-line").text
    assert person["worksFor"] == {"@id": "https://syahi.sh/#org"}
    assert person["sameAs"] == [link.href for link in site.founder_profiles]
    shown = text_of(html)
    assert person["name"] in shown and person["description"] in shown
    for link in site.founder_profiles:
        assert f'<a href="{link.href}">{link.label}</a>' in html
    assert jsonld_mismatches(html) == []
    assert [node["@type"] for node in nodes if node["@type"] in ("Review", "AggregateRating")] == []


def test_the_home_organization_names_her_as_founder(dist):
    nodes = jsonld(built(dist, "/"))
    (org,) = [node for node in nodes if node["@type"] == "Organization"]
    assert org["founder"] == {"@id": "https://syahi.sh/about#surabhi"}


def test_about_says_who_how_and_the_company_in_the_agreed_order(dist):
    main = main_of(built(dist, "/about"))
    assert re.findall(r'<h2 class="label"[^>]*>(.*?)</h2>', main) == ["The founder", "The company", "How we work"]
    assert "SYAHI TECHNOLOGIES LLP" in main and "LLPIN ADB-1993" in main


# ---- /media and /paper-machine ----

def test_media_is_three_cards(dist):
    main = main_of(built(dist, "/media"))
    assert re.findall(r'<a class="media-card" href="([^"]+)"', main) == [
        "/paper-machine", "https://katha.syahi.sh", "https://listen.katha.syahi.sh"]
    assert [text_of(h) for h in re.findall(r'<h3>(.*?)</h3>', main)] == ["Paper Machine", "Dahshat", "The Katha store"]


def test_paper_machine_lists_only_the_published_plates_each_linked_to_its_video(dist):
    main = main_of(built(dist, "/paper-machine"))
    plates = re.findall(r'<li><a href="(https://www\.youtube\.com/watch\?v=[^"]+)">', main)
    assert plates == [f"https://www.youtube.com/watch?v={id}" for id in PUBLISHED_VIDEOS]
    assert len(re.findall(r"<li>", main)) == 5


def test_the_launch_claims_are_in_the_register_with_a_public_source(register):
    wanted = ["call-is-free", "assessment-length", "build-live-time", "build-running-period", "build-scope-in-writing",
              "qtm-name", "keep-running-name", "agent-os-name", "agent-os-runs-syahi", "founder-name", "founder-line",
              "org-one-person", "org-founded-month", "signet-d10-first", "media-dahshat-name", "media-dahshat-line",
              "media-adhoore-name", "media-store-sample", "pm-series-name"]
    wanted += [f"pm-plate-{n}-{part}" for n in range(1, 6) for part in ("title", "url")]
    for id in wanted:
        claim = register.get(id)
        assert claim.source and claim.status == "live" and claim.updated == DRAFTED
        assert EM_DASH not in claim.text and EN_DASH not in claim.text


# ---- the rewritten home's link preview (its old snapshot is no longer its contract) ----

def test_the_home_link_preview_is_the_rewrites_own_and_has_no_image_alt(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert '<meta property="og:title" content="Syahi · the repeat work off your desk">' in html
    assert "owner-run businesses" in re.search(r'<meta property="og:description" content="([^"]*)">', html).group(1)
    assert "og:image:alt" not in html
