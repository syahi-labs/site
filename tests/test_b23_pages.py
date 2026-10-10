# tests/test_b23_pages.py
#
# Launch B2 and B3 (2026-10-10): the katha.syahi.sh listener page and the listed fixes on ported pages. Every page
# touched here is a draft with no approval date (it needs her yes on Sunday) and `updated` 2026-10-10.
import datetime
import json
import re
from html import unescape
from pathlib import Path

import pytest

from checks import copycheck, d10check, htmlcheck
from sitebuild.claims import ClaimRegister
from sitebuild.content import load_pages
from sitebuild.render import format_long_date
from sitebuild.schema import jsonld_mismatches

REPO = Path(__file__).resolve().parents[1]
EM_DASH, EN_DASH = chr(0x2014), chr(0x2013)
DAY = datetime.date(2026, 10, 10)
D20 = ("syahi.sh sets no cookies and runs no tracking scripts. Our host counts visits in aggregate (which pages, which countries, "
       "which campaign link), never who you are. Raw server logs are kept short and never joined to anything else.")


@pytest.fixture(scope="module")
def dist(real_site):
    return real_site.out / "syahi.sh"


@pytest.fixture(scope="module")
def register():
    return ClaimRegister.load(REPO / "data" / "claims.yaml")


def built(dist, name):
    return (dist / name).read_text(encoding="utf-8")


def main_of(html):
    return html.split("<main", 1)[1].split("</main>")[0]


def visible(markup):
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)\b.*?</\1>", "", markup, flags=re.S))).split())


def page(host, slug):
    folder = REPO / "content" if host == "main" else REPO / "katha" / "content"
    return next(p for p in load_pages(folder) if p.slug == slug)


def ld(html):
    return [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


CHANGED = [("main", "/"), ("main", "/404"), ("main", "/contact"), ("main", "/privacy"), ("main", "/terms"), ("main", "/refund"),
           ("main", "/signet"), ("main", "/services/quote"), ("main", "/katha"), ("katha", "/")]


@pytest.mark.parametrize("host, slug", CHANGED)
def test_every_changed_page_is_a_draft_with_no_approval_updated_today(host, slug):
    found = page(host, slug)
    assert found.draft is True and found.approved is None and found.updated == DAY


# ---- B2: the listener page ----

@pytest.fixture(scope="module")
def listener(real_site):
    return (real_site.out / "katha.syahi.sh" / "index.html").read_text(encoding="utf-8")


def test_the_listener_page_passes_every_check(listener):
    assert htmlcheck.check(listener) == [] and copycheck.check(listener, None) == []
    assert jsonld_mismatches(listener) == [] and d10check.check(listener, "/") == []
    assert EM_DASH not in listener and EN_DASH not in main_of(listener)


def test_the_listener_page_names_the_show_the_title_the_store_and_the_clip(listener, register):
    main = main_of(listener)
    assert register.get("media-dahshat-line").text == "A free Hinglish horror fiction podcast with an AI cast."
    for needle in ("Dahshat", "अधूरे हिसाब", register.get("media-dahshat-line").text, register.get("katha-title-price").text,
                   register.get("katha-sample-length").text):
        assert needle in visible(main), needle
    assert 'href="https://listen.katha.syahi.sh/shows/dahshat"' in main and 'href="https://listen.katha.syahi.sh/t/adhoore-hisab"' in main
    assert '<source src="https://media.katha.syahi.sh/samples/adhoore-hisaab.mp3"' in main
    assert 'href="https://syahi.sh/katha"' in main                      # the pointer to the publisher pitch


def test_the_listener_page_has_no_spotify_link_because_the_corpus_has_no_url(listener):
    assert "spotify" not in listener.lower()


def test_the_listener_page_carries_a_podcast_series_and_an_audiobook_from_claims(listener, register):
    nodes = {n["@type"]: n for n in ld(listener)}
    series, book = nodes["PodcastSeries"], nodes["Audiobook"]
    assert series["name"] == register.get("katha-show-name").text and series["url"] == register.get("katha-show-url").text
    assert book["name"] == register.get("katha-title-name").text and book["url"] == register.get("katha-title-url").text
    assert book["offers"]["price"] == register.get("katha-title-price-amount").text == "116.82"
    assert register.get("katha-title-price-amount").text in register.get("katha-title-price").text
    assert f'href="{series["url"]}"' in listener and f'href="{book["url"]}"' in listener   # the structured data's urls are the page's links


def test_the_two_katha_pages_have_one_self_canonical_each_and_no_shared_sentences(listener, dist):
    assert listener.count('<link rel="canonical" href="https://katha.syahi.sh/">') == 1
    publisher = built(dist, "katha.html")
    assert publisher.count('<link rel="canonical" href="https://syahi.sh/katha">') == 1
    a, b = visible(main_of(listener)), visible(main_of(publisher))
    sentences = lambda text: {s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) >= 6}
    assert sentences(a) & sentences(b) == set()
    assert "Dahshat" not in b and "Forty-five seconds" not in b


def test_every_dahshat_description_says_the_same_thing(dist, listener, register):
    line = register.get("media-dahshat-line").text
    assert line in visible(main_of(built(dist, "media.html"))) and line in visible(main_of(listener))
    assert "Hinglish horror" in unescape(re.search(r'<meta name="description" content="(.*?)">', listener).group(1))
    assert "Hindi fiction podcast" not in listener and "Hindi audio fiction" not in listener


def test_no_feed_or_cname_is_built(real_site):
    assert not list(real_site.out.rglob("feed.xml")) and not list(real_site.out.rglob("CNAME"))


# ---- B3.1 privacy ----

def test_privacy_carries_the_d20_line_verbatim_and_no_google_and_no_moving_ink(dist):
    text = visible(main_of(built(dist, "privacy.html")))
    assert D20 in text
    assert "Google" not in text and "moving ink" not in text and "analytics" not in text
    assert "served from syahi.sh itself" in text and "No third-party font host" in text


def test_privacy_links_line_names_only_services_the_built_site_links_to(dist):
    text = visible(main_of(built(dist, "privacy.html")))
    line = re.search(r"Links to (.*?) take you to those services", text).group(1)
    named = {"WhatsApp": "wa.me", "Cal.com": "cal.com", "YouTube": "youtube.com", "GitHub": "github.com",
             "LinkedIn": "linkedin.com", "Instagram": "instagram.com", "Threads": "threads.com", "X": "x.com"}
    assert set(re.split(r", | and ", line)) == set(named)
    every_link = "".join(p.read_text(encoding="utf-8") for p in dist.glob("*.html"))
    for host in named.values():
        assert re.search(r'href="https://(www\.)?' + re.escape(host), every_link), host


# ---- B3.2 the 404 ----

def test_404_is_final_copy_with_the_four_tabs_as_links(dist):
    main = main_of(built(dist, "404.html"))
    assert re.findall(r"<h1>(.*?)</h1>", main) == ["That page isn't here."]
    for href in ("/services", "/signet", "/media", "/about"):
        assert f'<a href="{href}">' in main
    assert "placeholder" not in main.lower() and "TODO" not in main
    assert len(visible(main).split()) < 60


# ---- B3.3 Signet ----

def test_signet_has_no_d10_finding_and_the_old_lines_are_gone(dist):
    html = built(dist, "signet.html")
    assert d10check.check(html, "/signet") == []
    text = visible(main_of(html))
    assert "A self-serve app you start on your own today" in text and "A system with years of outside use behind it" in text
    assert "sign up for today" not in text and "customers running it" not in text


# ---- B3.4 the quote page ----

def test_quote_faq_says_a_quick_look_and_the_signet_line_is_the_d10_first_beat(dist, register):
    main = main_of(built(dist, "services/quote.html"))
    assert "A wrong draft costs you a quick look, not a customer." in visible(main)
    assert "ten seconds" not in main and "qtm-check-time" not in main
    first_beat = register.get("signet-d10-first").text
    assert first_beat in visible(main) and "Every draft our agents make" not in main
    assert register.get("signet-d10").text not in visible(main)           # the full sentence stays off the services pages
    assert register.claims["qtm-check-time"].status == "retired"


# ---- B3.5 the home ----

def test_home_thesis_and_the_card_head_claim_no_total(dist, register):
    main = main_of(built(dist, "index.html"))
    text = visible(main)
    assert ("We take the repeat work off your desk, so your business can operate efficiently, analyze deeply and grow immensely.") in text
    assert "an owner's desk" not in text
    assert '<span class="roman"><span data-claim="home-card-count">4</span></span>' in main
    assert "Ventures to start with" in text and "4 Ventures Pick" not in text
    assert text.count("<") == 0 and len(re.findall(r'class="card"', main)) == int(register.get("home-card-count").short)
    assert register.claims["venture-count"].status == "retired"


# ---- B3.6 the dated lines ----

@pytest.mark.parametrize("name", ["contact", "privacy", "terms", "refund"])
def test_last_updated_is_the_front_matter_date_and_never_typed(dist, name):
    found = page("main", f"/{name}")
    source = found.source.read_text(encoding="utf-8")
    assert not re.search(r'<time datetime="\d{4}', source) and "{{ page.updated" in source
    expected = f'<p class="updated">Last updated <time datetime="{found.updated.isoformat()}">{format_long_date(found.updated)}</time></p>'
    assert expected in main_of(built(dist, f"{name}.html"))


def test_the_date_follows_the_front_matter_when_it_changes(tmp_path):
    from sitebuild.render import make_env
    from sitebuild.site import load_site
    env = make_env(REPO, load_site(REPO / "site.yaml"), ClaimRegister.load(REPO / "data" / "claims.yaml"))
    template = env.from_string('<time datetime="{{ page.updated }}">{{ page.updated|long_date }}</time>')
    for day, shown in ((datetime.date(2026, 10, 10), "10 October 2026"), (datetime.date(2027, 1, 3), "3 January 2027")):
        assert template.render(page=type("P", (), {"updated": day})()) == f'<time datetime="{day.isoformat()}">{shown}</time>'
    with pytest.raises(TypeError):
        format_long_date("2026-10-10")
