# tests/test_signet_page.py
#
# Task 9c: the Signet page at /signet, ported word for word from signet-landing a0bb211 (the page that is
# live at signet.syahi.sh today, snapshot tests/parity/signet.html) into the shared base. Its own wordmark
# header and its footer are the shared header and footer now. Copy is not edited. The comparison is
# tests/parity_helpers.py; the only excused differences are in tests/parity/allowed_diffs.yaml, and the only
# moved links are parity_helpers.LINK_MOVES, each with a reason.
#
# What is specific to this page: it carries the D10 sentence and the founding price (both claims, tied to each
# other by tests below), its illustrative scenes are wrapped in data-sample, its seal is the shared partial
# with a name of its own, and the copper accents of today's page are the one action colour.
import datetime
import hashlib
import json
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

import pytest
import yaml

from asset_urls import hashed_file, hashed_url
from checks import copycheck, htmlcheck
from parity_helpers import PARITY, apply_allowed, apply_link_moves, link_values, moves_used, words
from real_site import STAND_INS
from sitebuild.claims import ClaimRegister
from sitebuild.content import load_pages
from sitebuild.render import format_date
from sitebuild.schema import format_rupees, jsonld_mismatches

REPO = Path(__file__).resolve().parents[1]
EM_DASH = chr(0x2014)
APPROVED = datetime.date(2026, 10, 6)
SNAPSHOT = "signet.html"

# The D10 sentence, word for word as 07-SYSTEM/RULINGS.md (2026-10-06) words it.
D10 = ("Live today: every post, outreach email and desk draft our agents make waits for Surabhi's yes in Signet. "
       "Next: the same loop for your business's drafts. No outside customers yet. "
       "Founding users start at ₹1,499 a month, after a demo.")
PRICE_LINE = "₹1,499 a month or ₹14,999 a year, GST included."


@pytest.fixture(scope="module")
def dist(real_site):
    return real_site.out / "syahi.sh"


@pytest.fixture(scope="module")
def register():
    return ClaimRegister.load(REPO / "data" / "claims.yaml")


@pytest.fixture(scope="module")
def html(dist):
    return (dist / "signet.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def main(html):
    return main_of(html)


def main_of(markup):
    return markup.split("<main", 1)[1].split("</main>")[0]


def old_page():
    return (PARITY / SNAPSHOT).read_text(encoding="utf-8")


def old_main():
    return old_page().split("<main>", 1)[1].split("</main>")[0]


def old_footer():
    return old_page().split("<footer>", 1)[1].split("</footer>")[0]


def page():
    return next(p for p in load_pages(REPO / "content") if p.slug == "/signet")


def claim_ids(markup):
    return set(re.findall(r'data-claim="([^"]+)"', markup))


def without_claims(markup):
    return re.sub(r'<span data-claim="[^"]+">.*?</span>', "", markup)


class Tags(HTMLParser):
    """Every start tag of a piece of markup, with its attributes, in order."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, {name: value or "" for name, value in attrs}))

    handle_startendtag = handle_starttag


def tags_of(markup):
    scan = Tags()
    scan.feed(markup)
    return scan.tags


VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())


class Scenes(HTMLParser):
    """The text inside elements marked data-sample and the text outside them."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.inside, self.outside, self.depth, self.stack = [], [], 0, []

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return
        sample = "data-sample" in dict(attrs)
        self.stack.append(sample)
        self.depth += sample

    def handle_endtag(self, tag):
        if tag in VOID or not self.stack:
            return
        self.depth -= self.stack.pop()

    def handle_data(self, data):
        (self.inside if self.depth else self.outside).append(data)


def scenes(markup):
    scan = Scenes()
    scan.feed(markup)
    return " ".join("".join(scan.inside).split()), " ".join("".join(scan.outside).split())


# ---- the build ----

def test_the_whole_build_still_has_no_problem(real_site):
    assert real_site.result.problems == []


def test_the_page_is_built_listed_and_no_stand_in(real_site, dist, html):
    assert (dist / "signet.html").is_file()
    assert "Stand-in" not in html
    assert "<loc>https://syahi.sh/signet</loc>" in (dist / "sitemap.xml").read_text(encoding="utf-8")
    assert '<link rel="canonical" href="https://syahi.sh/signet">' in html
    assert "signet.html" not in STAND_INS                  # the stand-in is retired: the real page exists


def test_the_front_matter_is_the_ports_contract():
    found = page()
    assert found.layout == "page" and found.css == "signet"
    assert found.schema == ("SoftwareApplication",)
    assert found.audience is None                          # not set here: Part B decides
    assert found.draft is False and found.approved == APPROVED and found.updated == datetime.date(2026, 10, 7)   # the battery paragraph changed on 10-07, not yet re-approved
    assert found.og_image == "/assets/brand/og-signet.png"
    assert found.claims and len(set(found.claims)) == len(found.claims)


def test_front_matter_lists_exactly_the_claims_the_main_renders(main):
    assert set(page().claims) == claim_ids(main)


def test_the_page_passes_every_check_on_its_own(html):
    assert htmlcheck.check(html) == []
    assert copycheck.check(html, page().audience) == []
    assert jsonld_mismatches(html) == []


def test_the_buttons_label_gets_its_digits_from_the_claim_and_the_check_proves_it(html, register):
    source = (REPO / "content" / "signet.html").read_text(encoding="utf-8")
    assert "claim_text('booking-call-length', 'short')" in source and 'aria-label="Book a 30-minute' not in source
    assert htmlcheck.check(html, register.renderings()) == []
    # and the proof has teeth: against a register where the claim has moved, the label this page rendered is a finding
    moved = {**register.renderings(), "booking-call-length": ("45 minutes", "45-minute")}
    assert [f for f in htmlcheck.check(html, moved) if "aria-label" in f and '"30"' in f]


def test_the_made_by_line_is_the_approval(html):
    assert f"Checked and approved by Surabhi Pradhan on {format_date(APPROVED)}." in html
    assert "Not yet approved" not in html


def test_the_share_image_is_todays_og_png_and_is_published(dist, html):
    assert '<meta property="og:image" content="https://syahi.sh/assets/brand/og-signet.png">' in html
    published = (dist / "assets" / "brand" / "og-signet.png").read_bytes()
    blob = hashlib.sha1(b"blob %d\0" % len(published) + published).hexdigest()
    assert blob == "4848da2d16aed2ba762e166688b6ff74dacb2420"            # git rev-parse a0bb211:og.png


def test_no_page_in_the_build_repeats_an_id(dist):
    for path in sorted(dist.rglob("*.html")):
        ids = re.findall(r'\bid="([^"]+)"', path.read_text(encoding="utf-8"))
        assert len(ids) == len(set(ids)), (path.name, [i for i in ids if ids.count(i) > 1])


# ---- text parity ----

def test_main_text_is_the_old_pages_text_word_for_word(main):
    old = apply_allowed(words(old_page(), "body"), SNAPSHOT)
    new = words("<main" + main + "</main>", "main")
    assert new == old


SIGNATURE = ("What you approved is what goes out.",
             "Nothing sends that you didn't verifiably see.",
             "One of these is a decision. The other is a reflex.",
             "We ran the battery on ourselves first",
             "Hash mutation, caught", "Veto won the race", "Freeze, from a phone",
             "The seal can travel with the message",
             "Two things this page refuses to fake",
             "A system with customers running it besides us, yet",
             "See it happen on your own draft",
             "after a demo. Book 30 minutes, bring a real email or quote you'd hand an agent")


def test_every_signature_sentence_is_in_the_new_main(html):
    new = words(html, "main")
    assert len(new.split()) > 700
    for phrase in SIGNATURE:
        assert phrase in new, phrase


def test_title_and_description_are_the_old_pages_exactly(html):
    for pattern in (r"<title>(.*?)</title>", r'<meta name="description" content="(.*?)" ?/?>'):
        assert unescape(re.search(pattern, html).group(1)) == unescape(re.search(pattern, old_page()).group(1))


def test_the_headings_are_the_old_pages_in_the_same_levels(main):
    pattern = r"<h([1-6])\b[^>]*>(.*?)</h\1>"
    strip = lambda text: " ".join(re.sub(r"<[^>]+>", "", text).split())
    old = [(int(level), strip(text)) for level, text in re.findall(pattern, old_main(), re.S)]
    new = [(int(level), strip(text)) for level, text in re.findall(pattern, main, re.S)]
    assert new == old
    assert [level for level, _ in new] == [1, 2, 2, 2, 2, 2, 2, 3, 3, 2]       # no level to repair here


def test_each_section_is_labelled_by_a_heading_that_exists(main):
    ids = {attrs["id"] for _, attrs in tags_of(main) if "id" in attrs}
    labels = [attrs["aria-labelledby"] for tag, attrs in tags_of(main) if tag == "section"]
    assert len(labels) == 7 and set(labels) <= ids


# ---- what the port excuses, and what it drops ----

def test_the_snapshot_excuses_the_header_and_the_three_step_numbers_each_with_a_reason():
    entries = yaml.safe_load((PARITY / "allowed_diffs.yaml").read_text(encoding="utf-8"))
    texts = [entry["text"] for entry in entries[SNAPSHOT]]
    assert texts == ["SIGNET by Syahi", "01", "02", "03"]
    for entry in entries[SNAPSHOT]:
        assert set(entry) == {"text", "reason"} and entry["reason"].strip(), entry
    assert "shared header" in entries[SNAPSHOT][0]["reason"]
    for step in entries[SNAPSHOT][1:]:
        assert "counter" in step["reason"] or "Same reason" in step["reason"]


def test_the_snapshot_names_each_element_it_drops_and_the_new_page_holds_none_of_them(html):
    entries = yaml.safe_load((PARITY / "allowed_diffs.yaml").read_text(encoding="utf-8"))["removed_elements"][SNAPSHOT]
    assert [e["match"] for e in entries] == ["<header>", "<footer>", "<script>"]
    for entry in entries:
        assert set(entry) == {"match", "reason"} and entry["reason"].strip(), entry
        assert entry["match"] in old_page(), f"{entry['match']} is not in the old page: remove the entry"
    assert "shared header" in entries[0]["reason"] and "shared footer" in entries[1]["reason"]
    assert "<script>" not in html and html.count('<footer class="site-footer">') == 1
    assert 'class="site-header"' in html and html.count("<header") == 1
    assert "<script" not in html.replace('<script type="application/ld+json">', "")


def test_the_page_pulls_nothing_from_another_host(html):
    assert "fonts.googleapis.com" not in html and "fonts.gstatic.com" not in html
    assert 'rel="stylesheet" href="http' not in html and "preconnect" not in html


def test_the_parity_comparison_skips_nothing_that_is_content():
    # parity_helpers.SKIP hides nav, footer, canvas, noscript, script, style, svg and head from BOTH sides. That is
    # only honest while no content sits inside one of them. This page's content has none: the old main holds one
    # <style> block (the page's own CSS, now tokens/pages/signet.css) and svg that draw and say nothing.
    skipped = {"nav", "footer", "canvas", "noscript", "script", "head"}
    assert {tag for tag, _ in tags_of(old_main())} & skipped == set()
    assert [tag for tag, _ in tags_of(old_main()) if tag == "style"] == ["style"]
    svg_text = {"text", "title", "desc", "tspan", "textpath", "foreignobject"}
    assert {tag for tag, _ in tags_of(old_main())} & svg_text == set()


def test_nothing_in_the_new_main_hides_from_the_comparison(main):
    hidden = {"nav", "footer", "canvas", "noscript", "script", "style", "head", "text", "title", "desc", "tspan", "textpath", "foreignobject"}
    assert {tag for tag, _ in tags_of(main)} & hidden == set()
    # and every svg is a drawing: its only children are shapes
    svg_children = re.findall(r"<svg\b.*?</svg>", main, re.S)
    assert svg_children and all(not re.search(r">[^<\s][^<]*<", svg) for svg in svg_children)


# ---- the step numbers ----

def test_the_step_numbers_are_drawn_by_a_counter_not_written_as_digits(main):
    css = (REPO / "tokens" / "pages" / "signet.css").read_text(encoding="utf-8")
    steps = re.search(r'<ol class="steps">(.*?)</ol>', main, re.S).group(1)
    assert steps.count("<li>") == 3 and not re.search(r"\d", re.sub(r"<[^>]+>", "", steps))
    assert "counter-reset:step" in css and "counter-increment:step" in css
    assert re.search(r"content:counter\(step,\s*zero-padded\)", css)
    assert re.search(r'@counter-style zero-padded\{system:extends decimal;pad:2 "0";suffix:""\}', css)
    # today's three numbers are what the allowed diffs excuse, and they were in the old glyph column
    assert re.findall(r"<em>(\d\d)</em>", old_main()) == ["01", "02", "03"]


# ---- links ----

def test_the_links_are_the_old_pages_exactly_and_no_move_touches_the_content(main):
    old, new = link_values(old_main()), link_values(main)
    assert new == apply_link_moves(old) == old
    assert old == ["https://cal.com/surabhipradhan/30-mins-discussion-about-syahi?overlayCalendar=true"]
    assert moves_used(old) == []                         # the one link in the content is another site's


def test_the_old_footers_links_each_have_a_home_in_the_shared_header_or_footer(html):
    old = link_values(old_footer())
    assert old == ["https://syahi.sh/", "https://syahi.sh/contact", "https://syahi.sh/privacy",
                   "https://syahi.sh/terms", "https://syahi.sh/refund"]
    assert [move.new for move in moves_used(old)] == ["/", "/contact", "/privacy", "/terms", "/refund"]
    chrome = link_values(html.split("<main", 1)[0] + html.split("</main>", 1)[1])
    for moved in apply_link_moves(old):
        assert moved in chrome, moved


def test_the_demo_button_keeps_its_new_tab_and_its_label(main):
    (button,) = [attrs for tag, attrs in tags_of(main) if tag == "a"]
    assert button["class"] == "button" and button["target"] == "_blank" and button["rel"] == "noopener"
    assert button["aria-label"] == "Book a 30-minute demo (opens in a new tab)"
    assert button["data-claims"] == "booking-call-length"       # its digits come from the claim, through claim_text()
    assert re.search(r'>Book a <span data-claim="booking-call-length">30-minute</span> demo</a>', main)


# ---- claims ----

CLAIMS = {
    "signet-name": ("Signet by Syahi", "syahi.sh, 2026-10-06"),
    "signet-d10": (D10, "Ruling D10, 2026-10-06"),
    "signet-price-amount": ("1499", "Decision 2026-09-10, Signet INR price"),
    "signet-price-line": (PRICE_LINE, "Decision 2026-09-10, Signet INR price"),
    "signet-founding-lock": ("Founding price, locked for life while you stay subscribed.", "Decision 2026-09-10, Signet INR price"),
    "signet-pay-after-demo": ("Nothing to pay until after the demo.", "Ruling D10, 2026-10-06"),
    "signet-live-since": ("August 31, 2026", "Ruling D10, 2026-10-06"),
    "signet-battery-date": ("August 31, 2026", "Signet live battery, 2026-08-31"),
    "signet-battery-sent": ("One real email went out", "Signet live battery, 2026-08-31"),
    "signet-battery-refused": ("Two other drafts got past her phone and were still refused at send.", "Signet live battery, 2026-08-31"),
    "signet-battery-refused-why": ("the recipient wasn't on an approved lead list",
                                   "Signet live battery, 2026-08-31"),
}


@pytest.mark.parametrize("id", sorted(CLAIMS))
def test_each_new_claim_has_its_text_and_a_short_public_source(register, id):
    text, source = CLAIMS[id]
    claim = register.get(id)
    assert claim.text == text and claim.source == source
    assert claim.status == "live" and claim.updated == (datetime.date(2026, 10, 7) if id in ("signet-battery-refused", "signet-battery-refused-why") else APPROVED) and len(claim.source) <= 60


def test_the_call_length_claim_has_the_adjective_form_for_the_button(register):
    claim = register.get("booking-call-length")
    assert (claim.text, claim.short) == ("30 minutes", "30-minute")


def test_the_ids_this_page_reuses_exist_once_and_no_id_repeats():
    text = (REPO / "data" / "claims.yaml").read_text(encoding="utf-8")
    ids = re.findall(r"(?m)^- id: (\S+)", text)
    assert len(ids) == len(set(ids))
    assert {"signet-price-monthly", "signet-price-yearly", "booking-call-length"} <= set(ids)


def test_the_d10_sentence_is_on_the_page_exactly_once(html, main):
    assert html.count('data-claim="signet-d10"') == 1
    shown = words(html, "main")
    assert shown.count("Live today: every post, outreach email and desk draft") == 1
    assert shown.count(D10) == 1
    assert shown.count("No outside customers yet") == 1 and shown.count("Founding users start at") == 1
    assert main.count('<p class="lead"><span data-claim="signet-d10">') == 1


def test_d10_is_the_rulings_sentence_word_for_word(register):
    # D10 above is copied from 07-SYSTEM/RULINGS.md (2026-10-06). The corpus is private, so the site's tests never read it.
    assert register.get("signet-d10").text == D10
    assert D10.count("\u20b91,499 a month") == 1 and D10.endswith("after a demo.")


def test_the_price_line_holds_both_founding_prices_the_terms_page_states(register):
    line = register.get("signet-price-line").text
    assert register.get("signet-price-monthly").text in line
    assert register.get("signet-price-yearly").text in line
    assert line.endswith("GST included.")


def test_the_d10_sentence_holds_the_monthly_price_the_terms_page_states(register):
    assert register.get("signet-price-monthly").text in register.get("signet-d10").text


def test_the_structured_amount_is_the_monthly_price(register):
    amount = register.get("signet-price-amount").text
    assert format_rupees(amount) == "₹1,499"
    assert register.get("signet-price-monthly").text == f"{format_rupees(amount)} a month"


def test_the_fine_line_under_the_button_is_three_claims_and_nothing_else(main):
    (fine,) = re.findall(r'<p class="fine">(.*?)</p>', main, re.S)
    ids = re.findall(r'data-claim="([^"]+)"', fine)
    assert ids == ["signet-price-line", "signet-founding-lock", "signet-pay-after-demo"]
    assert re.sub(r"\s+", "", re.sub(r"<span[^>]*>.*?</span>", "", fine, flags=re.S)) == ""


# (figure as the page prints it, the claim that must be the only way it gets there)
FIGURES = [("30-minute", "booking-call-length"), ("30 minutes", "booking-call-length"),
           ("₹1,499", "signet-d10"), ("₹14,999", "signet-price-line"), ("August 31, 2026", "signet-live-since"),
           ("August 31, 2026", "signet-battery-date"), ("One real email went out", "signet-battery-sent"),
           ("Two other drafts got past her phone", "signet-battery-refused"), ("the recipient wasn't on an approved lead list", "signet-battery-refused-why"),
           ("Founding price, locked for life", "signet-founding-lock"), ("Nothing to pay until after", "signet-pay-after-demo")]


def test_each_figure_reaches_the_page_only_through_its_claim(main, register):
    shown = words("<main>" + main + "</main>", "main")
    bare = words("<body>" + without_claims(main) + "</body>", "body")
    for figure, id in FIGURES:
        assert figure in shown, figure
        assert id in claim_ids(main), (figure, id)
        assert figure in register.get(id).text or figure in (register.get(id).short or ""), (id, figure)
        assert figure not in bare, f"{figure!r} is written outside a claim"


def test_the_call_length_is_one_claim_in_two_forms_on_the_page(main):
    assert main.count('data-claim="booking-call-length"') == 2
    assert 'Book <span data-claim="booking-call-length">30 minutes</span>, bring a real email' in main


def test_the_two_dates_are_two_claims_because_they_are_two_facts(main, register):
    assert register.get("signet-live-since").text == register.get("signet-battery-date").text
    assert main.count('data-claim="signet-live-since"') == 1 and main.count('data-claim="signet-battery-date"') == 1
    assert "since <span data-claim=\"signet-live-since\">August 31, 2026</span>" in main
    assert "On <span data-claim=\"signet-battery-date\">August 31, 2026</span>, we put it" in main


def test_the_structured_data_is_a_software_application_priced_as_the_page_says(html, register):
    nodes = [json.loads(block) for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
    (app,) = [node for node in nodes if node["@type"] == "SoftwareApplication"]
    assert app["name"] == register.get("signet-name").text == "Signet by Syahi"
    assert app["offers"]["price"] == "1499" and app["offers"]["priceCurrency"] == "INR"
    assert app["offers"]["description"] == register.get("signet-price-line").text
    assert app["offers"]["description"] in words(html, "main")     # a reader sees what the structured data says
    assert not [node for node in nodes if node["@type"] in ("Organization", "WebSite", "AggregateRating", "Review")]


# ---- the illustrative scenes ----

SAMPLES = ("ledger", "notif", "detail", "outward-sample")


def test_each_scene_is_wrapped_in_data_sample(main):
    scenes_found = {}
    for tag, attrs in tags_of(main):
        first = attrs.get("class", "").split()[:1]
        if first and first[0] in SAMPLES:
            scenes_found[first[0]] = "data-sample" in attrs
    assert scenes_found == dict.fromkeys(SAMPLES, True)


def test_the_scenes_numbers_names_and_ids_are_inside_a_sample_and_nowhere_else(main):
    inside, outside = scenes(main)
    for made_up in ("09:14", "09:15", "a1b2c3d4e5f60718", "cmd_9f2", "2026-09-03", "meena@sharma-furnishings.example",
                    "Agent wants to send 1 email", "3BHK"):
        assert made_up in inside, made_up
        assert made_up not in outside, f"{made_up} is outside every data-sample"


def test_the_made_up_recipient_is_on_a_reserved_domain_and_stays_as_it_is(main):
    recipients = re.findall(r"[\w.+-]+@[\w.-]+", main)
    assert recipients == ["meena@sharma-furnishings.example"]       # an address that can never reach anyone


def test_the_real_facts_are_not_inside_a_sample(main):
    inside, outside = scenes(main)
    for fact in ("August 31, 2026", "One real email went out", "Two other drafts", "Founding users start at"):
        assert fact in outside and fact not in inside, fact


def test_no_digit_sits_outside_a_claim_a_time_or_a_sample(html):
    assert htmlcheck.check(html) == []
    assert not [f for f in htmlcheck.check(html) if f.startswith("numbers-from-claims")]


# ---- the seals ----

def test_the_cta_seal_is_the_shared_partial_with_a_name_and_is_decoration(main):
    source = (REPO / "content" / "signet.html").read_text(encoding="utf-8")
    assert source.count('{% include "partials/signet-seal.html" %}') == 1 and "<svg class=\"signet-mark\"" not in source
    assert '{% with seal_id = "cta", seal_decorative = true %}' in source
    assert main.count('<svg class="signet-mark" viewBox="0 0 512 512" aria-hidden="true">') == 1
    assert main.count('id="signet-seal-carve-cta"') == 1 and main.count('mask="url(#signet-seal-carve-cta)"') == 1
    assert "role=\"img\" aria-label=\"The Signet brand seal" not in main


def test_the_old_headers_and_footers_seals_are_the_shared_chromes_now(html):
    assert html.count('class="signet-mark"') == 1                      # the page's own header and footer seals are gone
    assert html.count("<mask") == 1
    assert "SIGNET" not in html and "ink &middot; seal &middot; parchment" not in html


def test_the_hero_watermark_is_drawn_by_a_class_not_by_a_colour(main):
    mark = re.search(r'<svg class="hero-watermark".*?</svg>', main, re.S).group(0)
    assert 'aria-hidden="true"' in mark and "var(--" not in mark and "stroke=" not in mark.replace("stroke-width", "")
    assert not re.search(r'#[0-9a-fA-F]{3,8}\b', mark)


# ---- the page's stylesheet ----

def css():
    return (REPO / "tokens" / "pages" / "signet.css").read_text(encoding="utf-8")


def test_the_page_names_its_own_sheet_and_the_build_publishes_it(dist, html):
    assert f'<link rel="stylesheet" href="{hashed_url(dist, "pages/signet.css")}">' in html
    assert hashed_file(dist, "pages/signet.css").read_bytes() == (REPO / "tokens" / "pages" / "signet.css").read_bytes()


def test_the_sheet_passes_the_page_css_guard_and_has_no_em_dash():
    from css_guard import page_css_violations
    assert page_css_violations(css()) == []
    assert EM_DASH not in css() and "@import" not in css() and "url(http" not in css()


def test_every_font_size_is_a_step_of_the_scale_and_every_family_a_token():
    sizes = re.findall(r"font-size:([^;}]+)", css())
    assert len(sizes) >= 25
    for size in sizes:
        assert "var(--fs-" in size and not re.search(r"\d(rem|px|em)\b", size), size
    for family in re.findall(r"font-family:([^;}]+)", css()):
        assert re.fullmatch(r"var\(--font-(serif|sans|mono)\)", family.strip()), family


def test_every_custom_property_the_page_reads_is_defined_in_tokens_or_in_the_sheet():
    # A var() of a name nothing defines is silently invalid: the property falls back and no test sees it.
    # Today's page had its own palette (--paper, --territory, --copper-text ...); none of it may be left behind.
    from css_guard import DECLARED_TOKENS
    sheet = re.sub(r"/\*.*?\*/", "", css(), flags=re.S)                       # the header comment names today's palette
    source = (REPO / "content" / "signet.html").read_text(encoding="utf-8")
    own = set(re.findall(r"(--[\w-]+)\s*:", sheet))
    for text, where in ((sheet, "signet.css"), (source, "signet.html")):
        for name in re.findall(r"var\(\s*(--[\w-]+)", text):
            assert name in DECLARED_TOKENS or name in own, f"{where} reads {name}, which nothing defines"
    for old in ("--paper", "--surface", "--territory", "--walnut", "--copper", "--good", "--dock", "--nav-inactive", "--serif", "--sans", "--mono"):
        assert old + ")" not in sheet and old + "," not in sheet and old + "-" not in sheet, old


def test_the_copper_accents_are_the_one_action_colour_and_the_dot_keeps_its_own_token():
    sheet = css()
    for selector in (".eyebrow", ".hero h1 em", ".ledger .status.sealed", ".step-glyph::after", ".receipt-tag",
                     ".outward-footer", ".stamp"):
        body = re.search(r"(?m)^" + re.escape(selector) + r"[^{]*\{([^}]*)\}", sheet)
        assert body and "var(--act)" in body.group(1), selector
    assert "--mark-signet-dot" not in sheet            # the dot is the seal's brand-mark token, set once in base.css


def test_the_panels_and_hairlines_take_the_ground_and_rule_tokens():
    sheet = css()
    for selector in (".ledger", ".outward-sample", ".proof", ".request", ".fit-card"):
        body = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", sheet)
        assert body and "var(--ground-deep)" in body.group(1), selector
    assert "var(--rule)" in sheet


def test_the_ledger_animation_is_css_only_and_off_under_reduced_motion():
    sheet = css()
    assert "@media (prefers-reduced-motion: no-preference)" in sheet and "@keyframes rise" in sheet and "@keyframes stamp" in sheet
    assert re.search(r"(?m)^\s*\.ledger li,\s*\.stamp\s*\{[^}]*opacity:0", sheet)
    head = sheet.split("@media (prefers-reduced-motion: no-preference)", 1)[0]
    assert "opacity:0" not in head                      # content is visible unless the animation that reveals it will run


def media_block(sheet, query):
    """The body of the first @media block with this exact query, braces balanced."""
    start = sheet.index("@media (" + query + ")")
    body_start = sheet.index("{", start) + 1
    depth, i = 1, body_start
    while depth:
        depth += {"{": 1, "}": -1}.get(sheet[i], 0)
        i += 1
    return sheet[body_start:i - 1]


def test_the_stamp_sits_inside_the_content_box_wherever_the_column_fills_it():
    # Measured in a browser at 320, 360, 390, 481, 768 and 816 px (fix round 1): the resting stamp, tilted corner
    # included, is inside the content box, and the page is never wider than the viewport, resting or revealing.
    sheet = css()
    wide = re.search(r"(?m)^\.stamp\{([^}]*)\}", sheet).group(1)
    assert "right:-1rem" in wide                         # where there is room, it overhangs the ledger as today's did
    narrow = media_block(sheet, "max-width:51em")
    assert ".stamp{right:.4rem}" in narrow               # .4rem is more than the tilted corner reaches past the ledger
    assert ".hero{overflow-x:clip}" in narrow            # the reveal's scale-up cannot widen the page
    # the 4.6rem stamp of the narrowest block keeps the inset, so no rule below it puts the stamp back outside
    assert "right:" not in media_block(sheet, "max-width:30em")
    # the tilt: a square w wide, turned 8 degrees, reaches w * (cos8 + sin8 - 1) / 2 past its box on each side
    import math
    reach = lambda rem: rem * (math.cos(math.radians(8)) + math.sin(math.radians(8)) - 1) / 2
    assert reach(5.2) < 0.4 and reach(4.6) < 0.4


def test_the_page_has_no_script_hook_in_its_sheet():
    assert ".js " not in css() and "html.js" not in css()


# ---- no em dash ----

def test_no_em_dash_in_the_page_source_its_output_or_its_snapshot_diff(html):
    assert EM_DASH not in (REPO / "content" / "signet.html").read_text(encoding="utf-8")
    assert EM_DASH not in html
    assert EM_DASH not in (REPO / "data" / "claims.yaml").read_text(encoding="utf-8")
