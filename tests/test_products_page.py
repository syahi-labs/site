# tests/test_products_page.py: the voice products page at /products, and the retirement of /signet (her rulings,
# 2026-11-21). The words are hers and are pinned exactly. Read the built output, not the source.
import datetime
import json
import re
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path

import pytest

from checks import copycheck, htmlcheck, productscheck
from sitebuild.claims import ClaimRegister
from sitebuild.content import load_pages
from sitebuild.schema import jsonld_mismatches, visible_text
from sitebuild.site import load_site

REPO = Path(__file__).resolve().parents[1]
EM_DASH = chr(0x2014)

TITLE = "Voice AI for English, Hindi and Hinglish | Syahi"
DESCRIPTION = ("Syahi Dictate, Voice and Talk: speech to text, text to speech and live voice conversation for English, "
               "Hindi and Hinglish. Built in-house, in private preview.")
H1 = "Voice AI for English, Hindi and Hinglish"
UNDER_H1 = "In private preview, built in-house."
PRODUCTS = [
    ("Syahi Dictate", "Speech to text for Hinglish",
     "Speak in Hinglish, get clean text back. Hindi in Devanagari, English stays in English. Runs on our own servers, nothing is kept."),
    ("Syahi Voice", "Text to speech",
     "Turn text into speech in English, Hindi or Hinglish. Every clip carries a watermark that marks it as made by Syahi Voice."),
    ("Syahi Talk", "Live voice conversation",
     "Talk to AI out loud in English, Hindi or Hinglish, and hear it answer."),
]
NOTE = "Private preview, by request only. We read every request."
FAQ = [
    ("What are Syahi Dictate, Voice and Talk?",
     "Voice AI built in-house for English, Hindi and Hinglish: speech to text, text to speech and live voice conversation. "
     "All three are in private preview."),
    ("Can I use them today?", "Not yet. They're in private preview, by request only."),
    ("Is my audio kept?", "No. Dictate runs on our own servers and keeps no audio or text."),
    ("Who builds them?", "Syahi, an AI venture studio in Bengaluru."),
]


@pytest.fixture(scope="module")
def dist(real_site):
    return real_site.out / "syahi.sh"


@pytest.fixture(scope="module")
def html(dist):
    return (dist / "products.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def main(html):
    return html.split("<main", 1)[1].split("</main>")[0]


@pytest.fixture(scope="module")
def graph(html):
    blocks = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
    assert len(blocks) == 1 and blocks[0]["@context"] == "https://schema.org"
    return blocks[0]["@graph"]


def text_of(markup):
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def meta(html, key):
    return unescape(re.search(rf'<meta (?:name|property)="{re.escape(key)}" content="([^"]*)">', html).group(1))


def test_the_real_build_has_no_problems(real_site):
    assert real_site.result.problems == []


# ---- the approved words, exactly ----

def test_title_description_and_open_graph_words(html):
    assert unescape(re.search(r"<title>(.*?)</title>", html).group(1)) == TITLE
    assert meta(html, "description") == DESCRIPTION
    assert meta(html, "og:description") == DESCRIPTION
    assert meta(html, "og:title") == TITLE
    assert '<link rel="canonical" href="https://syahi.sh/products">' in html


def test_h1_and_the_line_under_it(main):
    assert re.findall(r"<h1>(.*?)</h1>", main) == [H1]
    assert f'<p class="thesis">{UNDER_H1}</p>' in main


def test_three_product_blocks_in_order_each_with_a_chip_a_line_and_a_button(main):
    blocks = re.findall(r'<li class="product" id="\w+">(.*?)</li>', main, re.S)
    assert len(blocks) == 3
    for block, (name, category, line) in zip(blocks, PRODUCTS):
        assert text_of(re.search(r"<h3>(.*?)</h3>", block).group(1)) == name
        assert text_of(re.search(r'<p class="category">(.*?)</p>', block).group(1)) == category
        assert text_of(re.search(r'<span class="chip">(.*?)</span>', block).group(1)) == "Private preview"
        assert text_of(re.search(r'<p class="line">(.*?)</p>', block).group(1)) == line
        assert text_of(re.search(r'<a class="cta"[^>]*>(.*?)</a>', block).group(1)) == "Request access"


def test_the_note_sits_under_the_buttons(main):
    assert text_of(re.search(r'<p class="request-note">(.*?)</p>', main).group(1)) == NOTE
    assert main.rindex('class="cta"') < main.index('class="request-note"') < main.index('id="faq-head"')


def test_the_four_questions_are_visible_headings_with_their_answers_and_only_those(main):
    section = main.split('id="faq-head"', 1)[1]
    pairs = [(text_of(q), text_of(a)) for q, a in re.findall(r"<h3>(.*?)</h3>\s*<p>(.*?)</p>", section, re.S)]
    assert pairs == FAQ


def test_no_other_words_on_the_page_beyond_the_pinned_ones_and_small_structural_labels(main):
    known = [H1, UNDER_H1, NOTE, "Private preview", "Request access", "Products", "Questions", "स्याही · ink"]
    for name, category, line in PRODUCTS:
        known += [name, category, line]
    for q, a in FAQ:
        known += [q, a]
    text = text_of(main.split(">", 1)[1])
    for piece in sorted(known, key=len, reverse=True):
        text = text.replace(piece, " ")
    assert " ".join(text.split()) == ""


# ---- the request mechanism: no backend, so a mailto to the address /contact publishes ----

def test_each_button_is_a_mailto_to_the_published_address_with_the_subject(main, dist):
    contact = (dist / "contact.html").read_text(encoding="utf-8")
    assert 'href="mailto:hello@syahi.sh"' in contact
    links = re.findall(r'<a class="cta" href="(mailto:[^"]+)"', main)
    assert links == [f"mailto:hello@syahi.sh?subject=Request%20access%3A%20{name.replace(' ', '%20')}" for name, _, _ in PRODUCTS]


def test_no_form_field_script_or_endpoint_on_the_page(html):
    assert not re.search(r"<(form|input|textarea|select|script(?![^>]*ld\+json))\b", html)
    assert "action=" not in html and "fetch(" not in html


# ---- structured data ----

def test_graph_holds_the_org_the_page_three_apps_and_the_faq(graph):
    assert [n["@type"] for n in graph] == ["Organization", "WebPage", "BreadcrumbList", "SoftwareApplication",
                                           "SoftwareApplication", "SoftwareApplication", "FAQPage"]
    org, page = graph[0], graph[1]
    assert org["@id"] == "https://syahi.sh/#org" and org["name"] == "Syahi" and org["legalName"] == "SYAHI TECHNOLOGIES LLP"
    assert page["url"] == "https://syahi.sh/products" and page["name"] == TITLE and page["dateModified"] == "2026-11-21"
    assert page["publisher"] == {"@id": "https://syahi.sh/#org"}


def test_the_org_node_matches_the_home_pages_apart_from_the_github_profile(graph, dist):
    home = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                                              (dist / "index.html").read_text(encoding="utf-8"), re.S)]
    home_org = next(n for n in home if n["@type"] == "Organization")
    org = graph[0]
    assert "github.com/syahi-labs" in json.dumps(home_org["sameAs"])         # the home keeps it: not this page's call
    assert not any("github" in link for link in org["sameAs"])
    assert {k: v for k, v in org.items() if k != "sameAs"} == {k: v for k, v in home_org.items() if k != "sameAs"}
    assert org["sameAs"] == [link for link in home_org["sameAs"] if "github" not in link]


def test_the_three_apps_carry_the_name_the_category_the_line_and_the_org_as_publisher(graph):
    apps = [n for n in graph if n["@type"] == "SoftwareApplication"]
    assert [(a["name"], a["applicationCategory"], a["description"]) for a in apps] == [
        ("Syahi Dictate", "Speech to text", PRODUCTS[0][2]),
        ("Syahi Voice", "Text to speech", PRODUCTS[1][2]),
        ("Syahi Talk", "Live voice conversation", PRODUCTS[2][2])]
    for app in apps:
        assert app["publisher"] == {"@id": "https://syahi.sh/#org"}
        assert set(app) == {"@id", "@type", "name", "applicationCategory", "description", "publisher"}


def test_the_faq_markup_is_the_visible_faq_word_for_word(graph):
    faq = graph[-1]
    assert [(q["name"], q["acceptedAnswer"]["text"]) for q in faq["mainEntity"]] == FAQ


def keys_and_types(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            if key == "@type":
                yield from (value if isinstance(value, list) else [value])
            yield from keys_and_types(value)
    elif isinstance(node, list):
        for item in node:
            yield from keys_and_types(item)


def test_no_offer_rating_review_or_price_anywhere_in_the_structured_data(html, graph):
    banned = {"offers", "offer", "Offer", "AggregateOffer", "aggregateRating", "AggregateRating", "Rating", "review", "reviews",
              "Review", "price", "priceCurrency", "availability"}
    assert banned.isdisjoint(keys_and_types(graph))
    for raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        for word in ("PreOrder", "PreSale", "1499", "1,499", "Signet"):
            assert word not in raw, word
    assert jsonld_mismatches(html) == []


def test_no_priced_signet_node_is_in_any_built_page(real_site):
    for page in (real_site.out / "syahi.sh").rglob("*.html"):
        raw = page.read_text(encoding="utf-8")
        assert "Signet by Syahi" not in "".join(re.findall(r'<script type="application/ld\+json">(.*?)</script>', raw, re.S)), page.name
        assert '"priceCurrency"' not in raw or page.name in {"katha.html"}, page.name     # the Katha store's own audiobook price


# ---- her list of things the page must not say ----

def test_the_page_passes_its_claims_check_and_the_copy_and_html_checks(html):
    assert productscheck.check(html, "/products") == []
    assert copycheck.check(html, None) == []
    assert htmlcheck.check(html) == []
    assert EM_DASH not in html


def test_github_is_not_in_the_footer_of_this_page_only(html, dist):
    assert "github" not in html.lower()
    assert "github.com/syahi-labs" in (dist / "about.html").read_text(encoding="utf-8")


def test_the_page_is_mobile_first_one_column_then_three_from_48em(real_site):
    css = next((real_site.out / "syahi.sh" / "assets" / "pages").glob("products.*.css")).read_text(encoding="utf-8")
    assert re.search(r"\.products\{[^}]*grid-template-columns:minmax\(0,1fr\)", css)
    assert re.search(r"@media \(min-width:48em\)\{\s*\.products\{[^}]*repeat\(3,", css)


# ---- navigation, sitemap, llms.txt ----

def test_the_nav_products_link_points_to_products_on_every_page(real_site):
    site = load_site(REPO / "site.yaml")
    assert ("Products", "/products") in [(t.label, t.href) for t in site.tabs]
    for page in (real_site.out / "syahi.sh").rglob("*.html"):
        assert '<a href="/products"' in page.read_text(encoding="utf-8"), page.name


def test_the_sitemap_and_llms_txt_list_products_with_the_h1_and_the_line_under_it(dist):
    locs = [e.text for e in ET.parse(dist / "sitemap.xml").getroot().iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    assert "https://syahi.sh/products" in locs
    assert f"- [{H1}](https://syahi.sh/products): {UNDER_H1}\n" in (dist / "llms.txt").read_text(encoding="utf-8")


def test_the_page_is_approved_on_her_a_after_the_screenshots():
    page = next(p for p in load_pages(REPO / "content") if p.slug == "/products")
    assert page.schema == ("VoiceProducts",) and page.omit_profiles == ("GitHub",) and page.css == "products"
    assert page.draft is False and page.approved == datetime.date(2026, 11, 21)   # her A on desktop and phone screenshots, 21 Nov 2026


# ---- /signet is retired ----

def test_signet_has_no_page_no_sitemap_line_no_llms_line_and_no_link(real_site):
    out = real_site.out / "syahi.sh"
    assert not (out / "signet.html").exists() and not (REPO / "content" / "signet.html").exists()
    assert "/signet" not in (out / "sitemap.xml").read_text(encoding="utf-8")
    assert "/signet" not in (out / "llms.txt").read_text(encoding="utf-8") and "signet.syahi.sh" not in (out / "llms.txt").read_text(encoding="utf-8")
    for page in sorted(real_site.out.rglob("*.html")):
        raw = page.read_text(encoding="utf-8")
        assert not re.search(r'(?:href|src|action)="(?:https://(?:syahi\.sh|signet\.syahi\.sh))?/signet\b', raw), page
        assert "signet.syahi.sh" not in raw, page
    assert "/signet" not in (REPO / "site.yaml").read_text(encoding="utf-8")


def test_the_worker_answers_410_for_signet_and_keeps_the_subdomain_301():
    src = (REPO / "worker" / "src" / "lib.js").read_text(encoding="utf-8")
    index = (REPO / "worker" / "src" / "index.js").read_text(encoding="utf-8")
    assert 'new Set(["/signet"])' in src and "status: 410" in src and "x-robots-tag" in src and "noindex" in src
    assert "isGone(url)" in index
    assert 'if (host === "signet.syahi.sh") return `https://syahi.sh/${url.search}`;' in src      # unchanged
