# tests/test_quote_page.py
#
# Task 9d: Quote in Ten Minutes at /services/quote, ported word for word from studioservices-landing c66925f (the
# page that is live at services.syahi.sh today, snapshot tests/parity/services.html) into the shared base. Its own
# footer is the shared footer now. Copy is not edited. The comparison is tests/parity_helpers.py; the only excused
# differences are in tests/parity/allowed_diffs.yaml, and the only moved links are parity_helpers.LINK_MOVES, each
# with a reason.
#
# What is specific to this page: it is the owner-facing offer (audience: owner), its figures are claims (the two
# promises the home card already registers, reused, and three more), its drawn scene is wrapped in data-sample,
# its WhatsApp links are today's, byte for byte, and its dark brass and WhatsApp green are the shared tokens: the
# ground, the ink and the one action colour. The sticky thumb button of today's page stays, drawn by CSS alone.
import datetime
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

import pytest
import yaml

from checks import copycheck, htmlcheck
from parity_helpers import PARITY, apply_allowed, apply_link_moves, link_values, moves_used, words
from real_site import STAND_INS
from sitebuild.claims import ClaimRegister
from sitebuild.content import load_pages
from sitebuild.render import format_date
from sitebuild.schema import jsonld_mismatches

REPO = Path(__file__).resolve().parents[1]
EM_DASH = chr(0x2014)
APPROVED = datetime.date(2026, 10, 6)
SNAPSHOT = "services.html"
BUILT = "services/quote.html"
# today's WhatsApp link, byte for byte: the Worker stamps campaigns onto it later, so it must not drift
WA = "https://wa.me/918951449537?text=Hi%2C%20I%20quote%20custom%20work%20and%20want%20to%20know%20more%20about%20Quote%20in%20Ten%20Minutes."


@pytest.fixture(scope="module")
def dist(real_site):
    return real_site.out / "syahi.sh"


@pytest.fixture(scope="module")
def register():
    return ClaimRegister.load(REPO / "data" / "claims.yaml")


@pytest.fixture(scope="module")
def html(dist):
    return (dist / BUILT).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def main(html):
    return main_of(html)


def main_of(markup):
    return markup.split("<main", 1)[1].split("</main>")[0]


def old_page():
    return (PARITY / SNAPSHOT).read_text(encoding="utf-8")


def old_footer():
    return old_page().split("<footer>", 1)[1].split("</footer>")[0]


def old_content():
    """Everything the old page says in its body that its own footer and its one script do not: the content."""
    body = old_page().split("<body>", 1)[1].split("</body>")[0]
    body = re.sub(r"<footer>.*?</footer>", "", body, flags=re.S)
    return re.sub(r"<script>.*?</script>", "", body, flags=re.S)


def page():
    return next(p for p in load_pages(REPO / "content") if p.slug == "/services/quote")


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
    assert (dist / BUILT).is_file()
    assert "Stand-in" not in html
    assert "<loc>https://syahi.sh/services/quote</loc>" in (dist / "sitemap.xml").read_text(encoding="utf-8")
    assert '<link rel="canonical" href="https://syahi.sh/services/quote">' in html
    assert STAND_INS == ()                                   # the last stand-in is retired: every page of Task 9 exists


def test_the_front_matter_is_the_ports_contract():
    found = page()
    assert found.layout == "page" and found.css == "quote"
    assert found.schema == ("Service",)
    assert found.audience == "owner"                         # the plan's contract: an owner reads this page
    assert found.draft is False and found.approved == found.updated == APPROVED
    assert found.og_image is None                            # today's page named no share image: the site default
    assert found.og_title is None and found.og_description is None and found.og_image_alt is None   # today's equal title and description
    assert found.claims and len(set(found.claims)) == len(found.claims)


def test_front_matter_lists_exactly_the_claims_the_main_renders(main):
    assert set(page().claims) == claim_ids(main)


def test_the_page_passes_every_check_on_its_own(html, register):
    assert htmlcheck.check(html, register.renderings()) == []
    assert copycheck.check(html, page().audience) == []     # includes owner-first-line: not reworded to satisfy it
    assert jsonld_mismatches(html) == []


def test_the_made_by_line_is_the_approval(html):
    assert f"Checked and approved by Surabhi Pradhan on {format_date(APPROVED)}." in html
    assert "Not yet approved" not in html


def test_the_page_names_no_share_image_of_its_own_so_it_carries_the_sites_default(dist, html):
    assert '<meta property="og:image" content="https://syahi.sh/assets/brand/og-default.png">' in html
    assert '<meta name="twitter:image" content="https://syahi.sh/assets/brand/og-default.png">' in html
    assert "og:image:alt" not in html                        # today's page said none


def test_the_structured_data_is_a_service_the_organization_provides(html):
    import json
    nodes = [json.loads(block) for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
    (service,) = [node for node in nodes if node["@type"] == "Service"]
    assert service["name"] == "Quote in Ten Minutes · Syahi" and service["provider"] == {"@id": "https://syahi.sh/#org"}
    assert not [node for node in nodes if node["@type"] in ("Organization", "WebSite", "AggregateRating", "Review", "Offer")]


# ---- text parity ----

def test_main_text_is_the_old_pages_text_word_for_word(main):
    old = apply_allowed(words(old_page(), "body"), SNAPSHOT)
    new = words("<main" + main + "</main>", "main")
    assert new == old


SIGNATURE = ("Quote in Ten Minutes.",
             "Buyers pick a vendor within hours. Most quotes take a day. We close that gap.",
             "How it looks on your phone", "The enquiry arrives", "The draft comes back",
             "Priced off your rate card. Rates stay yours.", "You check it. You send it.",
             "The draft waits for you. Nothing goes out on its own.",
             "Fixed price.", "Guarantee in writing before the build starts.", "Amounts on the first call.",
             "The system drafts. You send. Every quote, every time.",
             "The quote is the first desk we take over.",
             "Agents draft, she signs", "Every draft our agents make waits for her yes in Signet",
             "What if it quotes wrong?", "Do I need new software?", "Hindi or English enquiries?",
             "The next enquiry decides in hours. Answer it in ten minutes.")


def test_every_signature_sentence_is_in_the_new_main(html):
    new = words(html, "main")
    assert len(new.split()) > 330
    for phrase in SIGNATURE:
        assert phrase in new, phrase


def test_title_and_description_are_the_old_pages_exactly(html):
    for pattern in (r"<title>(.*?)</title>", r'<meta name="description" content="(.*?)" ?/?>'):
        assert unescape(re.search(pattern, html).group(1)) == unescape(re.search(pattern, old_page()).group(1))


def test_the_headings_are_the_old_pages_in_the_same_levels(main):
    pattern = r"<h([1-6])\b[^>]*>(.*?)</h\1>"
    strip = lambda text: " ".join(re.sub(r"<[^>]+>", "", re.sub(r"<br[^>]*>", " ", text)).split())
    old = [(int(level), strip(text)) for level, text in re.findall(pattern, old_content(), re.S)]
    new = [(int(level), strip(text)) for level, text in re.findall(pattern, main, re.S)]
    assert new == old
    assert [level for level, _ in new] == [1, 2, 2, 2, 2, 2, 2]       # no level to repair here
    assert new[0] == (1, "Quote in Ten Minutes.")


def test_the_h1_keeps_its_line_break(main):
    assert "<h1>Quote in<br>Ten Minutes.</h1>" in main


def test_the_devanagari_wordmark_is_marked_hindi(main):
    assert '<span lang="hi">स्याही</span>' in main and main.count("स्याही") == 1


# ---- what the port excuses, and what it drops ----

def test_the_snapshot_excuses_no_text_and_names_the_two_elements_it_drops_each_with_a_reason(html):
    entries = yaml.safe_load((PARITY / "allowed_diffs.yaml").read_text(encoding="utf-8"))
    assert SNAPSHOT not in entries                      # no word of the old page is excused: its footer is the helper's SKIP, its hero is content
    dropped = entries["removed_elements"][SNAPSHOT]
    assert [e["match"] for e in dropped] == ["<footer>", "<script>"]
    for entry in dropped:
        assert set(entry) == {"match", "reason"} and entry["reason"].strip(), entry
        assert entry["match"] in old_page(), f"{entry['match']} is not in the old page: remove the entry"
    assert "shared footer" in dropped[0]["reason"] and "sticky" in dropped[1]["reason"]
    # and the new page holds neither: one footer (the shared one) and no script except structured data
    assert html.count('<footer class="site-footer">') == 1 and "<footer>" not in html
    assert "<script" not in html.replace('<script type="application/ld+json">', "")


def test_the_hero_is_content_inside_main_and_the_shared_header_is_the_only_header(html, main):
    # today's hero was a <header>; it is a <div class="hero"> so the shared header is the page's one banner
    assert html.count("<header") == 1 and 'class="site-header"' in html
    assert '<div class="hero">' in main and "<header" not in main
    assert '<header class="hero">' in old_page()


def test_the_page_pulls_nothing_from_another_host(html):
    assert "fonts.googleapis.com" not in html and "fonts.gstatic.com" not in html
    assert 'rel="stylesheet" href="http' not in html and "preconnect" not in html and "data:image" not in html


def test_the_parity_comparison_skips_nothing_that_is_content():
    # parity_helpers.SKIP hides nav, footer, canvas, noscript, script, style, svg and head from BOTH sides. That is
    # only honest while no content sits inside one of them. The old page's content (its body without its footer and
    # its one script) holds none, and neither does the new main.
    skipped = {"nav", "footer", "canvas", "noscript", "script", "style", "svg", "head"}
    assert {tag for tag, _ in tags_of(old_content())} & skipped == set()


def test_nothing_in_the_new_main_hides_from_the_comparison(main):
    hidden = {"nav", "footer", "canvas", "noscript", "script", "style", "svg", "head"}
    assert {tag for tag, _ in tags_of(main)} & hidden == set()


def test_no_page_in_the_build_repeats_an_id(html):
    ids = re.findall(r'\bid="([^"]+)"', html)
    assert len(ids) == len(set(ids))


# ---- links ----

def test_the_links_are_the_old_pages_exactly_and_in_order(main):
    old, new = link_values(old_content()), link_values(main)
    assert new == apply_link_moves(old) == old
    assert old == [WA, "mailto:hello@syahi.sh", WA, WA]  # the hero button, the quiet email, the closing button, the sticky one
    assert moves_used(old) == []                         # no link in the content moves: the old footer's do


def test_every_whatsapp_link_is_todays_prefill_byte_for_byte_and_dials_the_claimed_number(main, register):
    digits = re.sub(r"\D", "", register.get("whatsapp-number").text)
    links = [href for href in link_values(main) if "wa.me" in href]
    assert links == [WA] * 3
    assert all(href.startswith(f"https://wa.me/{digits}?text=") for href in links)


def test_the_old_footers_links_each_have_a_home_in_the_page_or_the_shared_chrome(html, main):
    old = link_values(old_footer())
    assert old == ["https://syahi.sh", WA, "mailto:hello@syahi.sh", "https://syahi.sh/contact", "https://syahi.sh/privacy",
                   "https://syahi.sh/terms", "https://syahi.sh/refund"]
    assert [move.new for move in moves_used(old)] == ["/", "/contact", "/privacy", "/terms", "/refund"]
    chrome = link_values(html.split("<main", 1)[0] + html.split("</main>", 1)[1])
    for moved in apply_link_moves(old):
        assert moved in chrome or moved in link_values(main), moved       # the number's and the email's homes are the hero's links


def test_the_buttons_and_the_quiet_link_keep_their_classes_and_text(main):
    anchors = re.findall(r'<a class="([^"]+)"[^>]*>(.*?)</a>', main, re.S)
    assert anchors == [("cta", "Message us on WhatsApp"), ("quiet-link", "or write to hello@syahi.sh"),
                       ("cta", "Message us on WhatsApp"), ("cta cta-sticky", "Message us on WhatsApp")]


# ---- claims ----

# (id, text, short, source): the claims this page adds, extends or reuses
CLAIMS = {
    "qtm-firm-size": ("5 to 50 people", None, "Services page, 2026-10-06"),
    "qtm-check-time": ("ten seconds", None, "Services page, 2026-10-06"),
    "qtm-quote-time": ("ten minutes", None, "Services page, 2026-10-06"),
    "qtm-live-time": ("two weeks", "Two-week", "Services page, 2026-10-06"),
    "qtm-running-period": ("30 days", None, "Offer doc, 2026-08-24"),
    "org-locality": ("Bengaluru", None, "MCA record"),
}


@pytest.mark.parametrize("id", sorted(CLAIMS))
def test_each_claim_has_its_text_and_a_short_public_source(register, id):
    text, short, source = CLAIMS[id]
    claim = register.get(id)
    assert (claim.text, claim.short, claim.source) == (text, short, source)
    assert claim.status == "live" and claim.updated == APPROVED and len(claim.source) <= 60


def test_no_id_repeats_and_the_ids_this_page_reuses_exist_once():
    text = (REPO / "data" / "claims.yaml").read_text(encoding="utf-8")
    ids = re.findall(r"(?m)^- id: (\S+)", text)
    assert len(ids) == len(set(ids))
    assert {"qtm-quote-time", "qtm-live-time", "qtm-guarantee-day", "org-locality", "whatsapp-number"} <= set(ids)


# (figure as the page prints it, the claim that must be the only way it gets there)
FIGURES = [("5 to 50 people", "qtm-firm-size"), ("ten minutes", "qtm-quote-time"), ("Two-week", "qtm-live-time"),
           ("30 days", "qtm-running-period"), ("ten seconds", "qtm-check-time"), ("Bengaluru", "org-locality")]


def test_each_figure_reaches_the_page_only_through_its_claim(main, register):
    shown = words("<main>" + main + "</main>", "main")
    bare = words("<body>" + without_claims(main) + "</body>", "body")
    for figure, id in FIGURES:
        assert figure in shown, figure
        assert id in claim_ids(main), (figure, id)
        claim = register.get(id)
        assert figure == claim.text or figure == claim.short, (id, figure)
        assert figure not in bare, f"{figure!r} is written outside a claim"


def test_the_two_promises_the_home_card_registers_are_reused_here_not_restated(main):
    assert main.count('data-claim="qtm-quote-time"') == 2          # the offer's "back in ten minutes" and the closing line
    assert main.count('data-claim="qtm-live-time"') == 1
    assert "A draft quote back in <span data-claim=\"qtm-quote-time\">ten minutes</span> on every enquiry" in main
    assert "Answer it in <span data-claim=\"qtm-quote-time\">ten minutes</span>." in main
    assert 'Fixed price. <span data-claim="qtm-live-time">Two-week</span> install.<br>' in main
    home = (REPO / "content" / "index.html").read_text(encoding="utf-8")
    assert 'claim("qtm-quote-time")' in home and 'claim("qtm-live-time")' in home      # the one id each, on the home too


def test_the_running_period_and_the_guarantee_day_are_two_claims_because_they_are_two_facts(main, register):
    # "What happens after the first 30 days?" is the included running period (offer doc: 30 days of running it with
    # weekly receipts, then the retainer). The guarantee day is when the turnaround guarantee is measured (terms,
    # refund). Both are 30 today; either can move alone (a longer first run does not move the guarantee), so each
    # has its own id, and neither has a form that stands in for the other.
    running, guarantee = register.get("qtm-running-period"), register.get("qtm-guarantee-day")
    assert running.id != guarantee.id and running.text == "30 days" and guarantee.text == "day 30"
    assert running.short is None and guarantee.short is None
    assert running.source != guarantee.source
    assert 'What happens after the first <span data-claim="qtm-running-period">30 days</span>?' in main
    assert "qtm-guarantee-day" not in claim_ids(main) and "qtm-guarantee-day" not in page().claims
    # and the two are not the same id by accident of spelling in the register's source
    text = (REPO / "data" / "claims.yaml").read_text(encoding="utf-8")
    assert len(re.findall(r"(?m)^- id: qtm-(?:running-period|guarantee-day)$", text)) == 2


def test_the_firm_size_and_the_check_time_sit_in_their_sentences(main):
    assert 'Owner-run firms, roughly <span data-claim="qtm-firm-size">5 to 50 people</span>, quoting custom work' in main
    assert 'A wrong draft costs you <span data-claim="qtm-check-time">ten seconds</span>, not a customer.' in main
    assert '<summary>What happens after the first <span data-claim="qtm-running-period">30 days</span>?</summary>' in main


def test_the_description_states_the_quote_time_the_claim_registers(register):
    assert register.get("qtm-quote-time").text in page().description


# ---- the illustrative scene ----

SAMPLES = ("bubble", "scene-arrow", "quote-card")


def test_each_piece_of_the_drawn_scene_is_wrapped_in_data_sample(main):
    found = {}
    for tag, attrs in tags_of(main):
        classes = attrs.get("class", "").split()
        for name in SAMPLES:
            if name in classes:
                found[name] = "data-sample" in attrs
    assert found == dict.fromkeys(SAMPLES, True)


def test_the_scenes_made_up_figures_are_inside_a_sample_and_nowhere_else(main):
    inside, outside = scenes(main)
    for made_up in ("2BHK", "10:42 am", "10 min", "7 ft", "10:52 am", "Marathahalli"):
        assert made_up in inside, made_up
        assert made_up not in outside, f"{made_up} is outside every data-sample"


def test_the_real_figures_are_not_inside_a_sample(main):
    inside, outside = scenes(main)
    for fact in ("5 to 50 people", "ten minutes", "Two-week", "30 days", "ten seconds", "Bengaluru"):
        assert fact in outside and fact not in inside, fact


def test_the_sample_rate_card_has_no_amounts_only_redacted_blocks(main):
    card = re.search(r'<div class="quote-card".*?</table>', main, re.S).group(0)
    assert card.count('<span class="redact"></span>') == 4 and card.count('<span class="redact wide"></span>') == 1
    assert not re.search(r"[₹$]|\bRs\b|\bINR\b", card)


def test_the_scenes_clock_says_ten_minutes_and_so_does_the_claim(main, register):
    # 10:42 to 10:52, and the arrow between them says 10 min: the drawing and the promise must agree
    stamps = re.findall(r"\b(\d\d):(\d\d) am\b", main)
    assert stamps == [("10", "42"), ("10", "52")]
    assert int(stamps[1][1]) - int(stamps[0][1]) == 10 and ">10 min<" in main
    assert register.get("qtm-quote-time").text == "ten minutes"


def test_no_digit_sits_outside_a_claim_a_time_or_a_sample(html, register):
    assert htmlcheck.check(html, register.renderings()) == []
    assert not [f for f in htmlcheck.check(html) if f.startswith("numbers-from-claims")]


# ---- the sticky thumb button ----

def test_the_sticky_button_is_the_last_thing_in_main_and_carries_no_script_hook(html, main):
    last = [(tag, attrs) for tag, attrs in tags_of(main) if tag == "a"][-1]
    assert last[1]["class"] == "cta cta-sticky" and last[1]["href"] == WA
    assert main.rstrip().removesuffix("</div>").rstrip().endswith("Message us on WhatsApp</a>")   # the layout's wrap closes after it
    assert main.index('class="closing"') < main.index("cta-sticky")
    assert "is-hidden" not in html and "IntersectionObserver" not in html and "<script" not in main


# ---- the page's stylesheet ----

def css():
    return (REPO / "tokens" / "pages" / "quote.css").read_text(encoding="utf-8")


def rule(selector, sheet=None):
    """The declarations of the first top-level rule whose selector list is exactly `selector`."""
    found = re.search(r"(?m)^\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", sheet if sheet is not None else css())
    assert found, f"{selector} has no rule"
    return found.group(1)


def media_block(sheet, query):
    """The body of the first @media or @supports block whose prelude is exactly this, braces balanced."""
    start = sheet.index(query)
    body_start = sheet.index("{", start) + 1
    depth, i = 1, body_start
    while depth:
        depth += {"{": 1, "}": -1}.get(sheet[i], 0)
        i += 1
    return sheet[body_start:i - 1]


def test_the_page_names_its_own_sheet_and_the_build_publishes_it(dist, html):
    assert '<link rel="stylesheet" href="/assets/pages/quote.css">' in html
    assert (dist / "assets" / "pages" / "quote.css").read_text(encoding="utf-8") == css()


def test_the_sheet_names_no_hex_colour_even_in_its_comments():
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css())     # the header names today's colours by their token roles, not their values


def test_the_sheet_uses_no_remote_url_no_import_and_no_script_hook():
    assert "@import" not in css() and "url(http" not in css() and "url(data" not in css()
    assert ".js " not in css() and "html.js" not in css() and ".is-hidden" not in css()


def test_every_font_size_is_a_step_of_the_scale_and_every_family_a_token():
    sizes = re.findall(r"font-size:([^;}]+)", css())
    assert len(sizes) >= 20
    for size in sizes:
        assert "var(--fs-" in size and not re.search(r"\d(rem|px|em)\b", size), size
    for family in re.findall(r"font-family:([^;}]+)", css()):
        assert re.fullmatch(r"var\(--font-(serif|sans|mono)\)", family.strip()), family


def test_every_custom_property_the_page_reads_is_defined_in_tokens_or_in_the_sheet():
    # A var() of a name nothing defines is silently invalid. Today's page had its own palette (--paper, --brass,
    # --wa ...); none of it may be left behind, and the ones it shared by name with tokens.css (--ink, --serif
    # became --font-serif) are tokens.css's values now.
    from css_guard import DECLARED_TOKENS
    sheet = re.sub(r"/\*.*?\*/", "", css(), flags=re.S)                       # the header comment names today's palette
    source = (REPO / "content" / "services" / "quote.html").read_text(encoding="utf-8")
    own = set(re.findall(r"(--[\w-]+)\s*:", sheet))
    for text, where in ((sheet, "quote.css"), (source, "quote.html")):
        for name in re.findall(r"var\(\s*(--[\w-]+)", text):
            assert name in DECLARED_TOKENS or name in own, f"{where} reads {name}, which nothing defines"
    for old in ("--ink-raised", "--paper", "--paper-dim", "--brass", "--brass-deep", "--hairline", "--wa", "--serif", "--sans", "--mono"):
        assert old + ")" not in sheet and old + "," not in sheet and old + ":" not in sheet and old + " " not in sheet, old


def test_the_brass_accents_are_the_one_action_colour():
    for selector in (".section-label", ".arrow-label", ".draft-stamp", ".approve-check", ".offer-shape p", ".faq summary::after"):
        assert "var(--act)" in rule(selector), selector
    assert "var(--act)" in rule(".hero-thesis::after") and "var(--act)" in rule(".offer-shape")
    assert "var(--act)" in rule(".approve-step")


def test_the_panels_take_the_ground_and_rule_tokens_and_the_text_the_ink_and_muted():
    for selector in (".bubble", ".quote-card"):
        assert "var(--ground-deep)" in rule(selector), selector
    assert "var(--rule)" in css()
    assert "var(--muted)" in rule(".scene-step") and "var(--muted)" in rule(".plate-mark") and "var(--muted)" in rule(".fact-strip")


def test_the_whatsapp_green_is_the_shared_act_button_not_a_colour_of_this_sheet():
    sheet = css()
    # the call buttons are the base's .cta; the sheet lays the sticky one out and never colours a button
    assert not re.search(r"(?m)^\.cta\s*[,{:]", sheet) and not re.search(r"(?m)^\.cta:hover", sheet)
    sticky = rule(".cta-sticky")
    assert "background" not in sticky and "color:" not in sticky.replace("box-shadow", "")
    assert "12833f" not in re.sub(r"/\*.*?\*/", "", sheet, flags=re.S).lower() and "var(--wa)" not in sheet


def test_the_grain_is_gone_and_nothing_paints_over_the_page():
    sheet = re.sub(r"/\*.*?\*/", "", css(), flags=re.S)                       # the header comment names the grain it dropped
    assert "body::before" not in sheet and "radial-gradient" not in sheet


def test_the_hatched_amounts_are_drawn_from_tokens():
    sheet = re.sub(r"/\*.*?\*/", "", css(), flags=re.S)
    redact = rule(".redact", sheet)
    assert "repeating-linear-gradient" in redact and "var(--muted)" in redact and "transparent" in redact


def test_the_sticky_button_is_hidden_on_wide_screens_and_fixed_at_the_bottom_on_narrow_ones():
    sheet = css()
    assert "display:none" in rule(".cta-sticky")
    narrow = media_block(sheet, "@media (max-width:39.99em)")
    block = rule(".cta-sticky", narrow)
    assert "position:fixed" in block and "bottom:var(--space-4)" in block
    assert "left:var(--space-4)" in block and "right:var(--space-4)" in block and "display:" in block and "display:none" not in block


def test_the_footers_last_line_clears_the_sticky_button_on_narrow_screens():
    narrow = media_block(css(), "@media (max-width:39.99em)")
    footer = rule(".site-footer", narrow)
    assert "padding-bottom:calc(var(--space-7) + var(--tap))" in footer       # 92px below the made-by line; the button takes 60


def test_focus_scrolled_into_view_stops_above_the_sticky_button(register):
    # WCAG 2.2 SC 2.4.11: a fixed bar must not fully cover a focused control. The browser keeps a scrolled-to control
    # inside the scrollport minus its scroll-padding, so the padding is the bar's whole footprint: the gap under it,
    # its height (the base .cta's --tap) and a gap above it.
    narrow = media_block(css(), "@media (max-width:39.99em)")
    bar = rule(".cta-sticky", narrow)
    assert "bottom:var(--space-4)" in bar and "padding-bottom" not in bar
    assert "scroll-padding-bottom:calc(var(--space-4) + var(--tap) + var(--space-4))" in rule("html", narrow)
    assert "scroll-padding" not in css().replace(narrow, "")      # wide screens have no bar, so nothing is reserved for it


def test_the_sticky_button_steps_aside_while_the_closing_one_is_on_screen_where_the_browser_can_say_so():
    # today's script hid it while .closing intersected; a scroll-driven animation does the same with no script,
    # and a browser without them simply keeps the button (the @supports guard)
    block = media_block(css(), "@supports (animation-timeline:view())")
    narrow = media_block(block, "@media (max-width:39.99em)")
    assert "timeline-scope:--closing" in rule(".page", narrow)
    assert "view-timeline:--closing" in rule(".closing", narrow)
    sticky = rule(".cta-sticky", narrow)
    assert "animation-timeline:--closing" in sticky and "animation-range:cover" in sticky
    assert re.search(r"@keyframes hide-sticky\{from,to\{opacity:0;visibility:hidden\}\}", css())


def test_the_wide_only_break_is_a_break_only_on_wide_screens():
    assert "display:none" in rule(".wide-only")
    assert ".wide-only{display:inline}" in media_block(css(), "@media (min-width:40em)")


# ---- no em dash ----

def test_no_em_dash_in_the_page_source_its_output_its_sheet_or_its_claims(html):
    assert EM_DASH not in (REPO / "content" / "services" / "quote.html").read_text(encoding="utf-8")
    assert EM_DASH not in html and EM_DASH not in css()
    assert EM_DASH not in (REPO / "data" / "claims.yaml").read_text(encoding="utf-8")
