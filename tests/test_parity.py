# tests/test_parity.py
#
# Task 9a: the four policy pages (contact, privacy, terms, refund) ported word for word from the live
# site at 446f625, parity-tested against byte-for-byte snapshots in tests/parity/. Part 9b adds the home
# page (snapshot site-index.html, the same site commit) and /katha, the publisher pitch (katha-feed 71e0a6d,
# the snapshot katha.syahi.sh's index is tested against); 9c and 9d add their own pairs. The comparison
# is tests/parity_helpers.py; the only excused differences are in tests/parity/allowed_diffs.yaml and the
# only moved links are parity_helpers.LINK_MOVES, each with a reason.
import datetime
import json
import re
from html import unescape
from pathlib import Path

import pytest
import yaml

from asset_urls import hashed_file, hashed_url, unhash
from checks import copycheck, htmlcheck
from parity_helpers import PARITY, apply_allowed, apply_link_moves, link_values, moves_used, words
from sitebuild.claims import ClaimRegister
from sitebuild.content import load_pages
from sitebuild.render import format_date
from sitebuild.schema import jsonld_mismatches

REPO = Path(__file__).resolve().parents[1]
EM_DASH = chr(0x2014)
APPROVED = datetime.date(2026, 10, 6)
# Her call 2026-10-10 (quiz item 8): the date each policy page says it was last updated. Only privacy has a text change
# (10 October); the other three keep the dates they had. All four stay drafts: the build says "re-approve" for the three
# whose Last updated line now renders from `updated`.
POLICY_UPDATED = {"contact.html": datetime.date(2026, 9, 10), "terms.html": datetime.date(2026, 9, 12),
                  "refund.html": datetime.date(2026, 9, 12), "privacy.html": datetime.date(2026, 10, 10)}
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")

# (snapshot, built page, slug, the date the page says it was last updated, its heading levels below the h1)
PAGES = [
    ("site-contact.html", "contact.html", "/contact", "2026-09-10", []),
    ("site-privacy.html", "privacy.html", "/privacy", "2026-09-10", []),
    ("site-terms.html", "terms.html", "/terms", "2026-09-12", [2, 2, 2]),
    ("site-refund.html", "refund.html", "/refund", "2026-09-12", [2]),
]
IDS = [pair[0] for pair in PAGES]
# Sentences that must be in each page's new <main>, so a comparison cannot pass by both sides being empty.
SIGNATURE = {
    "site-contact.html": ("One inbox, one number, one person answering.", "Say what it's about and it reaches the right place",
                          "Complaints are acknowledged within 48 hours and resolved within one month."),
    "site-privacy.html": ("Short, because there isn't much.", "We never see or store them.", "Nothing here is aimed at anyone under 18"),
    "site-terms.html": ("Two lines of business, one set of rules.", "Keep It Running, the retainer", "The courts at Bengaluru have exclusive jurisdiction."),
    "site-refund.html": ("Nothing ships in a box.", "you don't pay for the build", "Razorpay typically shows it in your account"),
}


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


def old_content(snapshot):
    """What the old page said that is not its own strip, footer or styling: from its devanagari line to </main>."""
    old = (PARITY / snapshot).read_text(encoding="utf-8")
    return old.split('<div class="devanagari">', 1)[1].split("</main>")[0]


def claim_ids(markup):
    return set(re.findall(r'data-claim="([^"]+)"', markup))


# ---- the build ----

def test_the_whole_build_has_no_problem(real_site):
    assert real_site.result.problems == []


@pytest.mark.parametrize("snapshot, name, slug, updated, levels", PAGES, ids=IDS)
def test_the_page_is_built_and_names_the_policy_stylesheet(real_site, dist, snapshot, name, slug, updated, levels):
    assert (dist / name).is_file()
    html = built(dist, name)
    assert f'<link rel="stylesheet" href="{hashed_url(dist, "pages/policy.css")}">' in html
    assert hashed_file(dist, "pages/policy.css").read_bytes() == (REPO / "tokens" / "pages" / "policy.css").read_bytes()
    assert f'<link rel="canonical" href="https://syahi.sh{slug}">' in html


@pytest.mark.parametrize("snapshot, name, slug, updated, levels", PAGES, ids=IDS)
def test_the_page_passes_every_check_on_its_own(dist, snapshot, name, slug, updated, levels):
    html = built(dist, name)
    page = next(p for p in load_pages(REPO / "content") if p.slug == slug)
    assert htmlcheck.check(html) == []
    assert copycheck.check(html, page.audience) == []
    assert jsonld_mismatches(html) == []


# Launch B3 (2026-10-10): all four policy pages changed (the "Last updated" line now renders from `updated`, and the
# privacy page has its listed edits), so each is a draft again until she approves it on Sunday.
DRAFTS = {"contact.html", "privacy.html", "terms.html", "refund.html"}
DRAFT_LINE = "Drafted with AI from our own records. Not yet approved."


@pytest.mark.parametrize("snapshot, name, slug, updated, levels", PAGES, ids=IDS)
def test_front_matter_is_the_ports_contract(snapshot, name, slug, updated, levels):
    page = next(p for p in load_pages(REPO / "content") if p.slug == slug)
    assert page.layout == "page" and page.css == "policy"
    assert page.audience is None and page.schema == ()
    assert page.claims and len(set(page.claims)) == len(page.claims)
    if name in DRAFTS:
        assert page.draft is True and page.approved is None   # no approval date: nobody has approved the launch B3 version
        assert page.updated == POLICY_UPDATED[name]
    else:
        assert page.draft is False and page.approved == APPROVED   # the live page was last approved and shipped on 6 Oct 2026


@pytest.mark.parametrize("snapshot, name, slug, updated, levels", PAGES, ids=IDS)
def test_the_made_by_line_says_what_is_true_of_the_page(dist, snapshot, name, slug, updated, levels):
    html = built(dist, name)
    if name in DRAFTS:
        assert f'<p class="made-by">{DRAFT_LINE}</p>' in html and "Checked and approved" not in html
    else:
        assert f"Checked and approved by Surabhi Pradhan on {format_date(APPROVED)}." in html


def test_privacy_has_made_the_three_edits_it_waited_for():
    # Launch B3 replaced the three statements that were untrue on the new site; the comment in the front matter
    # says so, and the old statements are gone from the body.
    source = (REPO / "content" / "privacy.html").read_text(encoding="utf-8")
    front = source.split("\n---\n", 1)[0]
    comment = "\n".join(line for line in front.splitlines() if line.lstrip().startswith("#"))
    assert "B3" in comment and "D20" in comment and "D21" in comment
    body = source.split("\n---\n", 1)[1]
    assert "Google Fonts" not in body and "moving ink" not in body and "runs no analytics" not in body
    assert "Links to WhatsApp, Cal.com, X, GitHub and YouTube" not in body


# Launch B3, the sentences that changed on the policy pages, old as the live page has them and new as the page says
# them now (each is listed old and new in the B2/B3 report). Applied to the old page's words before the comparison,
# so every other word of every policy page is still held to the live page. One entry is the date line, which now
# renders from the page's own `updated`.
B3_TEXT_EDITS = {
    "site-contact.html": [],     # quiz item 8: no text change, date stays 10 September 2026
    "site-terms.html": [],       # likewise 12 September 2026
    "site-refund.html": [],      # likewise 12 September 2026
    "site-privacy.html": [
        ("Last updated 10 September 2026", "Last updated 10 October 2026"),
        ("syahi.sh sets no cookies. It runs no analytics. It has no contact form, so the site itself collects nothing you type. "
         "The moving ink is drawn inside your browser and sends nothing anywhere. Two things do leave your browser when the page loads:",
         "syahi.sh sets no cookies and runs no tracking scripts. Our host counts visits in aggregate (which pages, which countries, "
         "which campaign link), never who you are. Raw server logs are kept short and never joined to anything else. "
         "syahi.sh has no contact form, so the site itself collects nothing you type. Two things happen when the page loads:"),
        ("Fonts. The typefaces come from Google Fonts. Google's servers receive that request, which carries your IP address and "
         "browser details. Google's privacy policy covers what they do with it.",
         "Fonts. The typefaces are served from syahi.sh itself. No third-party font host receives a request from your browser."),
        ("Links to WhatsApp, Cal.com, X, GitHub and YouTube take you to those services.",
         "Links to WhatsApp, Cal.com, YouTube, GitHub, LinkedIn, Instagram and Threads take you to those services."),   # X dropped 2026-10-10 (quiz item 1): no personal profile is linked
        ("Hosting. The site is served by GitHub Pages. GitHub keeps ordinary server logs: IP address, page requested, time. "
         "We don't see visitor-level logs.",
         "Hosting. syahi.sh is served by Cloudflare, and katha.syahi.sh by GitHub Pages. Each keeps ordinary server logs to "
         "deliver the pages: IP address, page requested, time. We see only the aggregate counts above, never visitor-level logs."),
    ],
}


def old_words_with_b3_edits(snapshot):
    old = apply_allowed(words((PARITY / snapshot).read_text(encoding="utf-8"), "body"), snapshot)
    for before, after in B3_TEXT_EDITS.get(snapshot, []):
        assert old.count(before) == 1, before          # a stale edit (text the live page no longer has) fails
        old = old.replace(before, after)
    return old


# ---- text parity ----

@pytest.mark.parametrize("snapshot, name, slug, updated, levels", PAGES, ids=IDS)
def test_main_text_is_the_old_pages_text_word_for_word(dist, snapshot, name, slug, updated, levels):
    new = words(built(dist, name), "main")
    assert new == old_words_with_b3_edits(snapshot)


@pytest.mark.parametrize("snapshot, name, slug, updated, levels", PAGES, ids=IDS)
def test_every_signature_sentence_is_in_the_new_main(dist, snapshot, name, slug, updated, levels):
    new = words(built(dist, name), "main")
    assert len(new.split()) > 150
    for phrase in SIGNATURE[snapshot]:
        assert phrase in new, phrase


@pytest.mark.parametrize("snapshot, name, slug, updated, levels", PAGES, ids=IDS)
def test_title_and_description_are_the_old_pages_exactly(dist, snapshot, name, slug, updated, levels):
    # Compared as the browser reads them: the template escapes an apostrophe as &#39;, the old page did not.
    old = (PARITY / snapshot).read_text(encoding="utf-8")
    html = built(dist, name)
    for pattern in (r"<title>(.*?)</title>", r'<meta name="description" content="(.*?)">'):
        assert unescape(re.search(pattern, html).group(1)) == unescape(re.search(pattern, old).group(1))
    assert "Syahi's products" in unescape(re.search(r'<meta name="description" content="(.*?)">', built(dist, "privacy.html")).group(1))


@pytest.mark.parametrize("snapshot, name, slug, updated, levels", PAGES, ids=IDS)
def test_links_are_the_old_pages_exactly_and_in_order(dist, snapshot, name, slug, updated, levels):
    old, new = link_values(old_content(snapshot)), link_values(main_of(built(dist, name)))
    assert new == old
    assert old                                          # the comparison cannot pass by both sides being empty


def test_only_the_header_strips_are_excused():
    entries = yaml.safe_load((PARITY / "allowed_diffs.yaml").read_text(encoding="utf-8"))
    for snapshot, strip in (("site-contact.html", "P-04"), ("site-privacy.html", "P-01"),
                            ("site-terms.html", "P-02"), ("site-refund.html", "P-03")):
        (entry,) = entries[snapshot]
        assert entry["text"] == f"ENTRY {strip} LEDGER SYAHI.SH PLACE BENGALURU, IN EST 2026"
        assert entry["reason"].strip()


# ---- the port's markup-only changes, each pinned ----

@pytest.mark.parametrize("snapshot, name, slug, updated, levels", PAGES, ids=IDS)
def test_headings_below_the_h1_are_h2_with_their_words_kept(dist, snapshot, name, slug, updated, levels):
    # Today's terms and refund pages go h1 straight to h3. Fixed by the level, not the words.
    found = [int(level) for level in re.findall(r"<h([1-6])\b", main_of(built(dist, name)))]
    assert found == [1] + levels


def test_the_h2s_are_the_old_h3s(dist):
    assert re.findall(r"<h2>(.*?)</h2>", built(dist, "terms.html")) == [
        "Keep It Running, the retainer", "Your part", "What's yours and what's ours"]
    assert re.findall(r"<h2>(.*?)</h2>", built(dist, "refund.html")) == ["If your purchase won't play"]
    assert re.findall(r"<h3>(.*?)</h3>", (PARITY / "site-terms.html").read_text(encoding="utf-8")) == [
        "Keep It Running, the retainer", "Your part", "What's yours and what's ours"]


@pytest.mark.parametrize("snapshot, name, slug, updated, levels", PAGES, ids=IDS)
def test_the_devanagari_wordmark_line_is_marked_hindi(dist, snapshot, name, slug, updated, levels):
    assert '<p class="devanagari"><span lang="hi">स्याही</span> &nbsp;·&nbsp; ink</p>' in main_of(built(dist, name))


@pytest.mark.parametrize("snapshot, name, slug, updated, levels", PAGES, ids=IDS)
def test_the_last_updated_date_is_a_time_element_rendered_from_the_pages_updated_date(dist, snapshot, name, slug, updated, levels):
    # Launch B3: the line is no longer typed by hand. It is the page's front-matter `updated`, so it cannot disagree with it.
    page = next(p for p in load_pages(REPO / "content") if p.slug == slug)
    when = page.updated
    long_form = f"{when.day} {MONTHS[when.month - 1]} {when.year}"
    assert f'<p class="updated">Last updated <time datetime="{when.isoformat()}">{long_form}</time></p>' in main_of(built(dist, name))
    assert f"Last updated {datetime.date.fromisoformat(updated).day}" in (PARITY / snapshot).read_text(encoding="utf-8")   # the live page typed its own
    source = page.source.read_text(encoding="utf-8")
    assert "{{ page.updated" in source and f'datetime="{updated}"' not in source     # no hand-typed date left in the source


def test_every_section_is_a_section_with_its_head_and_its_prose(dist):
    for name, sections in (("contact.html", 4), ("privacy.html", 8), ("terms.html", 8), ("refund.html", 6)):
        main = main_of(built(dist, name))
        assert main.count("<section>") == main.count("</section>") == sections, name
        assert main.count('class="section-head"') == sections, name


def test_the_terms_pricing_plate_keeps_its_anchor(dist):
    assert '<div class="plate" id="pricing">' in built(dist, "terms.html")


# ---- numbers are claims ----

# (figure as the page prints it, the claim that must be the only way it gets there)
FIGURES = {
    "contact.html": [("+91 89514 49537", "whatsapp-number"), ("30 minutes", "booking-call-length"),
                     ("ADB-1993", "org-llpin"), ("560076", "org-registered-address"),
                     ("2020", "law-ecommerce-rules"), ("48 hours", "grievance-ack-window"),
                     ("three working days", "reply-window"), ("one month", "grievance-resolve-window")],
    "privacy.html": [("ADB-1993", "org-llpin"), ("2023", "law-dpdp-act"), ("30 days", "signet-deletion-window"),
                     ("under 18", "minor-age-limit"), ("seven working days", "privacy-request-window")],
    "terms.html": [("ADB-1993", "org-llpin"), ("₹1,499 a month", "signet-price-monthly"),
                   ("₹14,999 a year", "signet-price-yearly"), ("day 30", "qtm-guarantee-day"),
                   ("four hours a month", "retainer-hours"), ("ten months for twelve", "signet-yearly-ratio")],
    "refund.html": [("14 days", "signet-annual-refund-window"), ("day 30", "qtm-guarantee-day"),
                    ("18% under SAC 998432", "katha-gst-treatment"), ("48 hours", "grievance-ack-window"),
                    ("30 days", "katha-refund-resolve-window"), ("5 to 7 working days", "razorpay-refund-timing"),
                    ("+91 89514 49537", "whatsapp-number"), ("three working days", "reply-window"),
                    ("seven working days", "refund-initiate-window")],
    # the home page: the count of ventures in both its forms, the quote and install promises, the founder's years
    "index.html": [("four", "home-card-count"), ("4", "home-card-count"), ("ten minutes", "qtm-quote-time"),
                   ("two weeks", "qtm-live-time"), ("eleven years", "founder-years")],
}


def without_claims(main):
    """The page's main with every claim span emptied, so what is left is text no claim supplies."""
    return re.sub(r'<span data-claim="[^"]+">.*?</span>', "", main)


@pytest.mark.parametrize("name", sorted(FIGURES))
def test_each_figure_reaches_the_page_only_through_its_claim(dist, register, name):
    main = main_of(built(dist, name))
    bare = words("<body>" + without_claims(main) + "</body>", "body")
    for figure, id in FIGURES[name]:
        assert id in claim_ids(main), (name, id)
        assert figure in register.get(id).text or figure in (register.get(id).short or ""), (id, figure)
        assert figure not in bare, f"{name}: {figure!r} is written outside a claim"


@pytest.mark.parametrize("snapshot, name, slug, updated, levels", PAGES, ids=IDS)
def test_front_matter_lists_exactly_the_claims_the_main_renders(dist, snapshot, name, slug, updated, levels):
    page = next(p for p in load_pages(REPO / "content") if p.slug == slug)
    assert set(page.claims) == claim_ids(main_of(built(dist, name)))


def test_a_fact_two_pages_state_comes_from_one_claim(dist):
    terms, refund = main_of(built(dist, "terms.html")), main_of(built(dist, "refund.html"))
    # the Quote in Ten Minutes guarantee day: terms and refund can never disagree
    assert terms.count('data-claim="qtm-guarantee-day"') == 2 and refund.count('data-claim="qtm-guarantee-day"') == 3
    contact = main_of(built(dist, "contact.html"))
    assert contact.count('data-claim="whatsapp-number"') == 2 and refund.count('data-claim="whatsapp-number"') == 1
    assert 'data-claim="grievance-ack-window"' in contact and 'data-claim="grievance-ack-window"' in refund


def test_the_two_pages_that_promise_three_working_days_use_one_id(dist):
    contact, refund = main_of(built(dist, "contact.html")), main_of(built(dist, "refund.html"))
    assert contact.count('data-claim="reply-window"') == 1 and refund.count('data-claim="reply-window"') == 1
    assert claim_ids(contact) & claim_ids(refund) >= {"reply-window", "whatsapp-number", "grievance-ack-window"}
    # no other id carries the phrase, so no third place can say it differently
    for id, claim in ClaimRegister.load(REPO / "data" / "claims.yaml").claims.items():
        assert ("three working days" in claim.text) == (id == "reply-window"), id


def test_the_two_seven_working_day_promises_are_two_claims_with_their_own_ids(dist, register):
    # Initiating an approved refund and confirming a privacy request are different promises that happen to match.
    assert register.get("refund-initiate-window").text == register.get("privacy-request-window").text == "seven working days"
    privacy, refund = main_of(built(dist, "privacy.html")), main_of(built(dist, "refund.html"))
    assert claim_ids(privacy) >= {"privacy-request-window"} and "refund-initiate-window" not in claim_ids(privacy)
    assert claim_ids(refund) >= {"refund-initiate-window"} and "privacy-request-window" not in claim_ids(refund)


def test_the_grievance_clock_is_not_the_katha_refund_window(register):
    assert register.get("grievance-resolve-window").text == "one month"
    assert register.get("katha-refund-resolve-window").text == "30 days"


def test_every_wa_me_link_dials_the_whatsapp_claim(dist, register):
    digits = re.sub(r"\D", "", register.get("whatsapp-number").text)
    links = [href for name in ("contact.html", "refund.html") for href in link_values(main_of(built(dist, name))) if "wa.me" in href]
    assert len(links) == 3 and set(links) == {f"https://wa.me/{digits}"}


def test_the_contact_description_names_the_whatsapp_claim_number(register):
    page = next(p for p in load_pages(REPO / "content") if p.slug == "/contact")
    assert register.get("whatsapp-number").text in page.description


def test_the_llpin_claim_has_a_short_form_for_the_company_table(dist, register):
    assert register.get("org-llpin").text == "LLPIN ADB-1993"
    assert register.get("org-llpin").short == "ADB-1993"
    assert '<dt>LLPIN</dt><dd><span data-claim="org-llpin">ADB-1993</span></dd>' in main_of(built(dist, "contact.html"))


# ---- the claims this part adds: pinned, each with a short public source ----

CLAIMS = {
    # the organisation: the footer, structured data, llms.txt (org-legal-name and org-llpin were Task 10's)
    "org-name": ("Syahi", None),
    "org-alternate-name": ("\u0938\u094d\u092f\u093e\u0939\u0940", None),
    "org-founding-date": ("2026-08-13", "MCA record"),
    "org-locality": ("Bengaluru", "MCA record"),
    "org-registered-address": ("E-313, Nandi Meraki, Phase 1 Yelenahalli, Reliable Residency Phase 2, Off Bannerghatta Road, "
                               "Bangalore 560076", "MCA record"),
    # contact
    "whatsapp-number": ("+91 89514 49537", "Contact page, 2026-09-10"),
    "booking-call-length": ("30 minutes", None),
    "grievance-ack-window": ("48 hours", "Contact page, 2026-09-10"),
    "grievance-resolve-window": ("one month", "Contact page, 2026-09-10"),
    "reply-window": ("three working days", "Contact page, 2026-09-10"),
    "law-ecommerce-rules": ("Consumer Protection (E-Commerce) Rules, 2020", "Gazette of India"),
    # privacy
    "law-dpdp-act": ("Digital Personal Data Protection Act, 2023", "Gazette of India"),
    "signet-deletion-window": ("30 days", "Privacy policy, 2026-09-10"),
    "minor-age-limit": ("under 18", "Privacy policy, 2026-09-10"),
    "privacy-request-window": ("seven working days", "Privacy policy, 2026-09-10"),
    # terms
    "signet-price-monthly": ("\u20b91,499 a month", "Terms of service, 2026-09-12"),
    "signet-price-yearly": ("\u20b914,999 a year", "Terms of service, 2026-09-12"),
    "signet-yearly-ratio": ("ten months for twelve", "Terms of service, 2026-09-12"),
    "retainer-hours": ("four hours a month", "Terms of service, 2026-09-12"),
    "qtm-guarantee-day": ("day 30", "Terms of service, 2026-09-12"),
    # refund
    "signet-annual-refund-window": ("14 days", "Refund policy, 2026-09-12"),
    "katha-gst-treatment": ("18% under SAC 998432", "Refund policy, 2026-09-12"),
    "katha-refund-resolve-window": ("30 days", "Refund policy, 2026-09-12"),
    "razorpay-refund-timing": ("5 to 7 working days", "Refund policy, 2026-09-12"),
    "refund-initiate-window": ("seven working days", "Refund policy, 2026-09-12"),
    # home (Task 9b)
    # (home-card-count replaced venture-count on 2026-10-10: its test is test_the_count_of_cards_is_one_claim_in_two_forms)
    "qtm-quote-time": ("ten minutes", "Services page, 2026-10-06"),
    "qtm-live-time": ("two weeks", "Services page, 2026-10-06"),
    "founder-years": ("eleven years", "syahi.sh home page, 2026-10-06"),
}


@pytest.mark.parametrize("id", sorted(CLAIMS))
def test_each_new_claim_has_its_text_and_a_short_public_source(register, id):
    text, source = CLAIMS[id]
    claim = register.get(id)
    assert claim.text == text
    assert claim.status == "live" and claim.updated == APPROVED
    assert claim.source.strip() and len(claim.source) <= 60
    if source:
        assert claim.source == source


def test_org_summary_is_one_plain_sentence_pair_for_llms_txt(register, real_site):
    summary = register.get("org-summary")
    assert summary.text.startswith("Syahi (")
    assert "operate efficiently, analyze deeply and grow immensely" in summary.text
    llms = (real_site.out / "syahi.sh" / "llms.txt").read_text(encoding="utf-8")
    assert f"> {summary.text}" in llms


def test_the_org_claims_exist_once_each(register):
    for id in ("org-name", "org-alternate-name", "org-legal-name", "org-llpin", "org-founding-date",
               "org-locality", "org-summary"):
        assert register.get(id)
    text = (REPO / "data" / "claims.yaml").read_text(encoding="utf-8")
    ids = re.findall(r"(?m)^- id: (\S+)", text)
    assert len(ids) == len(set(ids))


# ---- the registered street address: /contact only, never structured data ----

ADDRESS_MARKERS = ("Nandi Meraki", "560076", "Yelenahalli", "Bannerghatta")


def test_the_registered_address_is_a_claim_used_on_contact_only(dist, register):
    text = register.get("org-registered-address").text
    assert all(marker in text for marker in ADDRESS_MARKERS)
    assert "Bangalore 560076" in text and text.startswith("E-313")
    assert register.get("org-registered-address").source == "MCA record"
    assert 'data-claim="org-registered-address"' in main_of(built(dist, "contact.html"))


def test_the_address_is_nowhere_else_in_either_host(real_site):
    holders = set()
    for path in sorted(real_site.out.rglob("*")):
        if path.is_file() and path.suffix in (".html", ".txt", ".xml", ".css"):
            body = path.read_text(encoding="utf-8")
            if any(marker in body for marker in ADDRESS_MARKERS):
                holders.add(path.relative_to(real_site.out).as_posix())
    assert holders == {"syahi.sh/contact.html"}


def test_the_address_never_reaches_json_ld(real_site):
    blocks = []
    for path in sorted(real_site.out.rglob("*.html")):
        blocks += re.findall(r'<script type="application/ld\+json">(.*?)</script>', path.read_text(encoding="utf-8"), re.S)
    assert blocks                                       # the pages do carry structured data
    for block in blocks:
        assert not any(marker in block for marker in ADDRESS_MARKERS)
        json.loads(block)


# ---- no em dash, no remote anything ----

@pytest.mark.parametrize("snapshot, name, slug, updated, levels", PAGES, ids=IDS)
def test_no_em_dash_in_the_page_source_or_its_output(dist, snapshot, name, slug, updated, levels):
    source = REPO / "content" / name
    assert EM_DASH not in source.read_text(encoding="utf-8")
    assert EM_DASH not in built(dist, name)


def test_no_em_dash_in_the_policy_stylesheet_or_the_new_claims():
    assert EM_DASH not in (REPO / "tokens" / "pages" / "policy.css").read_text(encoding="utf-8")
    assert EM_DASH not in (REPO / "data" / "claims.yaml").read_text(encoding="utf-8")


@pytest.mark.parametrize("snapshot, name, slug, updated, levels", PAGES, ids=IDS)
def test_the_page_pulls_nothing_from_another_host(dist, snapshot, name, slug, updated, levels):
    html = built(dist, name)
    assert "fonts.googleapis.com" not in html and "fonts.gstatic.com" not in html
    assert "<script" not in html.replace('<script type="application/ld+json">', "")
    assert 'rel="stylesheet" href="http' not in html


# ---- the snapshots are today's live pages, untouched ----

PINNED = {   # git rev-parse 446f625:<file> in the live site repo
    "site-contact.html": "445b5f66d470c91b0396abd5ce5473333d553b33",
    "site-privacy.html": "e9cd067b3dd67449887967ec6b405f7c75a5ee45",
    "site-terms.html": "9ffa4417540b742e9c6342a051c550651dbc1802",
    "site-refund.html": "ef70727071518d639d26fc9b51e573026c4fd3e9",
}


PINNED["site-index.html"] = "965a18a0a06ed3df2c10aa7054b74964464a0a01"     # git rev-parse 446f625:index.html (site)
PINNED["katha-index.html"] = "8ebde0c01f978766bac5b5e604ec9356efba089d"     # git rev-parse 71e0a6d:index.html (katha-feed)
PINNED["signet.html"] = "dfe791c3f6706de85dcc1774bebacb5c1d2b9631"          # git rev-parse c069f92:index.html (signet-landing)
PINNED["services.html"] = "fb5a87159727fbe0c63880b173fb8a8af4c6850d"        # git rev-parse c66925f:index.html (studioservices-landing)


@pytest.mark.parametrize("snapshot", sorted(PINNED))
def test_the_snapshot_is_the_pinned_blob_byte_for_byte(snapshot):
    import hashlib
    data = (PARITY / snapshot).read_bytes()
    blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()   # git's own object id
    assert blob == PINNED[snapshot]


# ---- /katha, the publisher pitch (Task 9b, split by launch B2) ----
# Task 9b ported the page katha.syahi.sh served at its root (katha-feed 71e0a6d) as /katha too, from one shared partial.
# Launch B2 (2026-10-10) split them: katha.syahi.sh `/` is now the listener page (tests/test_launch_pages.py), and /katha
# keeps the publisher pitch. The listen line and the sample section moved to the listener page, so word for word holds
# for the rest, with the three named edits below.

KATHA = "katha-index.html"
KATHA_SIGNATURE = ("Every sentence verified against the source.", "A human signs off",
                   "Bring a catalog, or one title you care about.", "No checkout, no commitment.")
# (old words, new words, why): the only places /katha differs from the live page's words
KATHA_B2_EDITS = [
    ("Here to listen? Buy अधूरे हिसाब in our store, or play Dahshat, our free Hinglish horror show.",
     "Here to listen, or to hear a sample first? Head to katha.syahi.sh.",
     "the listen line now points at the listener page instead of repeating its titles"),
    ("III The sample अधूरे हिसाब · chapter one Forty-five seconds from a title already out on Spotify and Google Play. "
     "Synthetic narration, every sentence checked against the printed text, a human signed off before it shipped. IV The ask",
     "III Hear the quality अधूरे हिसाब · chapter one Forty-five seconds of chapter one, right here. "
     "Every title has a free sample chapter. IV The ask",
     "quiz item 9: the sample clip is back on the pitch, worded from the claims katha-sample-length and media-store-sample"),
    ("IV The ask",
     "IV Our voices Every voice reads the same opening of अधूरे हिसाब, chapter one, so you can compare. Every voice is synthetic, "
     "invented rather than cloned from a real person, and watermarked. "
     "Neha नेहा narrator Kabir कबीर podcast host Aarav आरव Sameer समीर Sarla सरला character voice V The ask",
     "Our voices: five synthetic narrator voices on one passage, worded from the katha-voice-* claims (Katha voice samples, 2026-10-10)"),
]


def ld_nodes(html):
    return [json.loads(block) for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


def old_katha_content():
    """What the old page said that is not its own strip or footer: from the hero grid to </main>."""
    return (PARITY / KATHA).read_text(encoding="utf-8").split('<div class="hero-grid">', 1)[1].split("</main>")[0]


def test_the_katha_page_is_built_and_the_main_host_lists_it(real_site, dist):
    assert (dist / "katha.html").is_file()
    assert "<loc>https://syahi.sh/katha</loc>" in (dist / "sitemap.xml").read_text(encoding="utf-8")
    assert "https://syahi.sh/katha)" in (dist / "llms.txt").read_text(encoding="utf-8")


def test_the_katha_page_front_matter_is_the_publisher_pitch_draft():
    page = next(p for p in load_pages(REPO / "content") if p.slug == "/katha")
    assert page.layout == "page" and page.css == "katha-index"     # the one sheet both pages share
    assert page.schema == ("Service",) and page.audience is None
    assert page.draft is True and page.approved is None and page.updated == datetime.date(2026, 10, 10)
    assert page.claims[:3] == ("katha-sample-length", "media-store-sample", "katha-title-name")   # the sample clip is back (quiz item 9)
    assert page.claims[3:] and all(c.startswith("katha-voice-") for c in page.claims[3:])         # Our voices


def test_the_two_katha_pages_share_no_body_and_the_shared_partial_is_gone():
    publisher = (REPO / "content" / "katha.html").read_text(encoding="utf-8").split("\n---\n", 1)[1]
    listener = (REPO / "katha" / "content" / "index.html").read_text(encoding="utf-8").split("\n---\n", 1)[1]
    assert "{% include" not in publisher and "{% include" not in listener
    assert not (REPO / "templates" / "partials" / "katha-publishers.html").exists()
    for phrase in KATHA_SIGNATURE:
        assert phrase in publisher and phrase not in listener, phrase
    assert "<audio" in listener and "<audio" in publisher      # the clip is on both pages (quiz item 9)


def test_the_two_hosts_render_different_mains(real_site, dist):
    on_katha_host = (real_site.out / "katha.syahi.sh" / "index.html").read_text(encoding="utf-8")
    assert main_of(built(dist, "katha.html")) != main_of(on_katha_host)


def test_the_katha_main_text_is_the_old_pages_text_but_for_the_two_b2_edits(dist):
    old = apply_allowed(words((PARITY / KATHA).read_text(encoding="utf-8"), "body"), KATHA)
    for before, after, why in KATHA_B2_EDITS:
        assert why and old.count(before) == 1, before
        old = old.replace(before, after)
    new = words(built(dist, "katha.html"), "main")
    assert new == old
    for phrase in KATHA_SIGNATURE:                      # the comparison cannot pass by both sides being empty
        assert phrase in new


def test_the_katha_title_and_description_are_the_old_pages_exactly(dist):
    old = (PARITY / KATHA).read_text(encoding="utf-8")
    html = built(dist, "katha.html")
    for pattern in (r"<title>(.*?)</title>", r'<meta name="description" content="(.*?)">'):
        assert unescape(re.search(pattern, html).group(1)) == unescape(re.search(pattern, old).group(1))


def test_the_katha_links_are_the_old_pages_with_each_move_applied_in_order_less_the_listener_links(dist):
    old, new = link_values(old_katha_content()), link_values(unhash(main_of(built(dist, "katha.html"))))
    # launch B2: the two store links left with the listener copy (the sample clip is back, quiz item 9); one pointer to katha.syahi.sh came in
    moved = [v for v in old if v not in (
        "https://listen.katha.syahi.sh/t/adhoore-hisab", "https://listen.katha.syahi.sh/shows/dahshat")]
    expected = apply_link_moves(moved)
    expected.insert(1, "https://katha.syahi.sh/")      # inserted after the moves: the helper's own move table would rewrite it
    # Our voices: five mp3 sources (narrator first) sit between the sample section and the ask, so before the ask's two links
    voices = [f"https://media.katha.syahi.sh/samples/voices/{v}-01.mp3" for v in ("neha", "kabir", "aarav", "sameer", "sarla")]
    expected[-2:-2] = voices
    assert new == expected
    assert len(old) == 6                                # the comparison cannot pass by both sides being empty
    assert [move.old for move in moves_used(old)] == ["https://syahi.sh/art/gramophone.webp"]
    assert "/assets/img/gramophone.webp" in new and not [v for v in new if "syahi.sh/art/" in v]


def test_the_katha_page_passes_every_check_and_names_the_shared_sheet(real_site, dist):
    html = built(dist, "katha.html")
    page = next(p for p in load_pages(REPO / "content") if p.slug == "/katha")
    assert htmlcheck.check(html) == [] and copycheck.check(html, page.audience) == [] and jsonld_mismatches(html) == []
    assert '<link rel="canonical" href="https://syahi.sh/katha">' in html
    assert f'<link rel="stylesheet" href="{hashed_url(dist, "pages/katha-index.css")}">' in html
    assert hashed_file(dist, "pages/katha-index.css").read_bytes() == (REPO / "tokens" / "pages" / "katha-index.css").read_bytes()
    assert list((dist / "assets" / "img").glob("gramophone-900w.*.webp"))


def test_the_katha_structured_data_is_a_service_the_organization_provides(dist):
    html = built(dist, "katha.html")
    (service,) = [node for node in ld_nodes(html) if node["@type"] == "Service"]
    title = unescape(re.search(r"<title>(.*?)</title>", html).group(1))
    assert service["name"] == title and service["provider"] == {"@id": "https://syahi.sh/#org"}
    assert not [node for node in ld_nodes(html) if node["@type"] in ("Organization", "WebSite")]   # the home page defines those once


def test_the_katha_page_has_no_script_no_remote_font_and_no_em_dash(dist):
    html = built(dist, "katha.html")
    assert "<script" not in html.replace('<script type="application/ld+json">', "")
    assert "fonts.googleapis.com" not in html and 'rel="stylesheet" href="http' not in html
    assert EM_DASH not in html and EM_DASH not in (REPO / "content" / "katha.html").read_text(encoding="utf-8")


# ---- the home page (Task 9b) ----
# Today's home (site 446f625) without the moving ink: no canvas, no script, no fluid.js (D21). Its own
# strip and footer are the shared header and footer now. Launch B1 rewrote the top of it (the owner pitch, her
# triad as three beats, one action), so word for word now holds from the ventures section to the end: the four
# cards, the house mark and the colophon. The rewritten top has its own tests in tests/test_launch_pages.py.

HOME = "site-index.html"
HOME_CARDS = ("Signet by Syahi", "Quote in Ten Minutes", "Katha Audio", "Paper Machine")
HOME_SIGNATURE = ("Nothing sends that you didn't verifiably see.",
                  "Live on your number in two weeks.",
                  "Plates, not thumbnails.",
                  "Ink is how intent becomes record.",
                  "Surabhi Pradhan signs everything that leaves here, eleven years into AI, ML and analytics.")


def old_home():
    return (PARITY / HOME).read_text(encoding="utf-8")


def old_home_content():
    """What the old home said that is not its own strip or footer: from the hero grid to </main>."""
    return old_home().split('<div class="hero-grid">', 1)[1].split("</main>")[0]


def old_home_cards_on():
    """The old home from the ventures section head to the end of its main: the part launch B1 kept word for word."""
    return '<div class="section-head">' + old_home().split('<div class="section-head">', 1)[1].split("</main>")[0]


def new_home_cards_on(dist):
    main = main_of(built(dist, "index.html"))
    return '<div class="section-head">' + main.split('<div class="section-head">', 1)[1]


def home_page():
    return next(p for p in load_pages(REPO / "content") if p.slug == "/")


def test_the_home_is_built_and_is_no_stand_in(dist):
    html = built(dist, "index.html")
    assert "Stand-in" not in html
    assert "<loc>https://syahi.sh/</loc>" in (dist / "sitemap.xml").read_text(encoding="utf-8")
    assert '<link rel="canonical" href="https://syahi.sh/">' in html


def test_the_home_front_matter_is_the_rewrites_contract(dist):
    page = home_page()
    assert page.layout == "page" and page.css == "home"
    assert page.audience == "owner"         # launch B1: an owner reads it, so the first line stays free of agents and AI
    assert page.schema == ()                # the Organization and WebSite nodes come with the main host's home page
    assert page.draft is True and page.approved is None     # her Sunday edit and yes
    assert page.updated == datetime.date(2026, 10, 10)
    assert page.claims and len(set(page.claims)) == len(page.claims)
    assert set(page.claims) == claim_ids(main_of(built(dist, "index.html")))
    assert "Not yet approved" in built(dist, "index.html")


def test_the_home_passes_every_check_on_its_own(dist):
    html = built(dist, "index.html")
    assert htmlcheck.check(html) == []
    assert copycheck.check(html, home_page().audience) == []
    assert jsonld_mismatches(html) == []


def test_the_home_carries_the_organization_and_the_website_once(dist):
    nodes = ld_nodes(built(dist, "index.html"))
    (org,) = [n for n in nodes if n["@type"] == "Organization"]
    (site,) = [n for n in nodes if n["@type"] == "WebSite"]
    assert org["@id"] == "https://syahi.sh/#org" and org["name"] == "Syahi" and org["alternateName"] == "स्याही"
    assert site["@id"] == "https://syahi.sh/#site" and site["publisher"] == {"@id": "https://syahi.sh/#org"}


# ---- text parity ----

# Launch B3: the section head said "4 Ventures" and Syahi has six, so the label now says what the four cards are.
# Quiz items 12, 4 and 5 (her answers, 2026-10-10): the head reads "Where to start"; card IV goes to /paper-machine as
# "see the plates"; the colophon paragraph is two sentences.
HOME_B3_EDITS = [
    ("Ventures Pick the one you came for.", "Where to start Pick the one you came for."),
    ("watch on YouTube", "see the plates"),
    ("Every venture here runs on the same loop: agents draft, a human approves, the decision gets written down. "
     "We think that loop, not the models, is what the next decade of small companies is made of.",
     "Every piece of work that reaches you has a person's yes behind it, and a dated record that shows it."),
]


def test_the_home_cards_and_colophon_are_the_old_pages_text_word_for_word(dist):
    old = words("<main>" + old_home_cards_on() + "</main>", "main")
    for before, after in HOME_B3_EDITS:
        assert old.count(before) == 1, before
        old = old.replace(before, after)
    new = words("<main>" + new_home_cards_on(dist) + "</main>", "main")
    assert new == old
    assert len(old.split()) > 150                       # the comparison cannot pass by both sides being empty


def test_every_signature_sentence_is_in_the_new_home_main(dist):
    new = words(built(dist, "index.html"), "main")
    assert len(new.split()) > 200
    for phrase in HOME_SIGNATURE + HOME_CARDS:
        assert phrase in new, phrase
    assert "An AI venture studio run by one human and her agents." not in new      # the old thesis went with the rewrite


def test_the_home_title_and_description_are_the_rewrites_not_the_old_pages(dist):
    html = built(dist, "index.html")
    title = unescape(re.search(r"<title>(.*?)</title>", html).group(1))
    description = unescape(re.search(r'<meta name="description" content="(.*?)">', html).group(1))
    assert title == "Syahi · AI and automation for owner-run businesses in India"
    assert "owner" in description and description != unescape(re.search(r'<meta name="description" content="(.*?)">', old_home()).group(1))


def test_the_home_excuses_the_header_strip_and_names_each_element_it_drops():
    entries = yaml.safe_load((PARITY / "allowed_diffs.yaml").read_text(encoding="utf-8"))
    (strip,) = entries[HOME]
    assert strip["text"] == "ENTRY 001 LEDGER SYAHI.SH PLACE BENGALURU, IN EST 2026" and strip["reason"].strip()
    dropped = entries["removed_elements"][HOME]
    assert [e["match"] for e in dropped] == ['<canvas id="fluidlayer"', '<canvas id="inklayer"', '<svg class="grain"',
                                              "<script>", "<footer>"]
    for entry in dropped:
        assert set(entry) == {"match", "reason"} and entry["reason"].strip(), entry
        assert entry["match"] in old_home(), f"{entry['match']} is not in the old home: remove the entry"
    assert "D21" in dropped[0]["reason"] and "no text" in dropped[0]["reason"]
    assert "shared footer" in dropped[-1]["reason"]


def test_what_the_home_drops_is_not_in_the_new_page(dist):
    html = built(dist, "index.html")
    assert "<canvas" not in html and 'class="grain"' not in html and "<footer>" not in html
    assert "<script" not in html.replace('<script type="application/ld+json">', "")
    assert "fluid" not in html and not (dist / "fluid.js").exists()
    assert "fonts.googleapis.com" not in html and 'rel="stylesheet" href="http' not in html
    assert html.count('<footer class="site-footer">') == 1


# ---- links and media ----

def test_the_home_card_links_are_the_old_pages_with_each_move_applied_in_order(dist):
    old, new = link_values(old_home_cards_on()), link_values(unhash(new_home_cards_on(dist)))
    # quiz item 4: card IV's link goes to the plates page, so the old YouTube link is replaced in place
    assert new == ["/paper-machine" if v == "https://youtube.com/@papermachine07" else v for v in apply_link_moves(old)]
    assert len(old) == 7                                # the comparison cannot pass by both sides being empty
    assert [move.old for move in moves_used(old)] == [
        "https://signet.syahi.sh", "https://services.syahi.sh", "https://katha.syahi.sh/",
        "art/loom.webp", "art/gramophone.webp", "art/cube.webp"]
    hero = unhash(main_of(built(dist, "index.html")).split('<div class="section-head">')[0])
    assert "inkpot" in hero                         # the house mark's art is still the hero's


def test_the_four_cards_keep_their_anchors_and_go_where_the_controller_ruled(dist):
    cards = re.findall(r'<a class="card" id="([a-z]+)" href="([^"]+)"', main_of(built(dist, "index.html")))
    assert cards == [("signet", "/signet"), ("studio", "/services/quote"), ("katha", "/katha"),
                     ("papermachine", "/paper-machine")]      # quiz item 4
    assert [id for id, _ in re.findall(r'<a class="card" id="([a-z]+)" href="([^"]+)"', old_home())] == [id for id, _ in cards]


def test_the_home_alt_text_and_labels_are_the_old_pages_exactly(dist):
    pattern = r'(?:alt|aria-label)="([^"]*)"'
    old, new = re.findall(pattern, old_home_content()), re.findall(pattern, main_of(built(dist, "index.html")))
    assert new == old and len(old) == 5                 # the four plates' alt text and the seal's label (the drop is hidden)


def test_each_art_file_the_home_names_is_in_the_output(dist):
    page = built(dist, "index.html")
    for name in ("inkpot", "loom", "gramophone", "cube"):
        urls = re.findall(rf"(/assets/img/{name}-\d+w\.[0-9a-f]{{10}}\.webp) \d+w", page)
        assert len(urls) == 3, name                                         # shown through picture(): 240, 480, 900
        assert all((dist / url.lstrip("/")).is_file() for url in urls), name


# ---- the port's markup-only changes, each pinned ----

def test_the_card_titles_are_h2_with_their_words_kept(dist):
    # Today's page goes h1 straight to h3. Fixed by the level, not the words.
    main = main_of(built(dist, "index.html"))
    assert [int(level) for level in re.findall(r"<h([1-6])\b", main)] == [1, 2, 2, 2, 2, 2, 2, 2]   # h1, three beats, four cards
    assert tuple(re.findall(r"<h2>(.*?)</h2>", main))[3:] == HOME_CARDS
    assert tuple(re.findall(r"<h3>(.*?)</h3>", old_home())) == HOME_CARDS


def test_the_home_devanagari_wordmark_line_is_marked_hindi(dist):
    main = main_of(built(dist, "index.html"))
    assert '<p class="devanagari"><span lang="hi">स्याही</span> &nbsp;·&nbsp; ink</p>' in main
    assert main.count('lang="hi"') == 1


def test_the_drop_stays_in_the_h1_as_a_hidden_decoration(dist):
    main = main_of(built(dist, "index.html"))
    assert re.search(r'<h1>Syahi<svg class="drop" viewBox="20 8 60 84" aria-hidden="true"><path d="[^"]+"/></svg></h1>', main)


def test_the_seal_comes_from_the_shared_partial_and_is_drawn_by_classes(dist):
    source = (REPO / "content" / "index.html").read_text(encoding="utf-8")
    assert source.count('{% include "partials/signet-seal.html" %}') == 1 and "<svg class=\"signet-mark\"" not in source
    main = main_of(built(dist, "index.html"))
    assert main.count('<svg class="signet-mark"') == 1 and main.count('id="signet-seal-carve"') == 1
    assert main.count('class="seal-ring"') == 2 and main.count('class="seal-core"') == 1 and main.count('class="seal-dot"') == 1
    assert "#221A0E" not in main and "#B06325" not in main            # the ink and the copper are tokens now
    assert main.count("#") == main.count("#fff") + main.count("#000") + main.count("url(#") + main.count('href="#')   # only the mask's


def test_the_hero_art_keeps_its_words_and_the_old_ventures_line_went_with_the_old_thesis(dist):
    main = main_of(built(dist, "index.html"))
    assert '<figcaption class="hero-mark-cap">the house mark · dawat &amp; qalam</figcaption>' in main
    assert "hero-ventures" not in main and "&middot; signet" not in main
    assert '<span class="roman"><span data-claim="home-card-count">4</span></span>' in main


def test_the_count_of_cards_is_one_claim_in_two_forms_and_the_old_venture_count_is_retired(register):
    # Launch B3: Syahi has six ventures, so "4 Ventures" claimed a total. The head counts the cards on the page instead.
    claim = register.get("home-card-count")
    assert (claim.text, claim.short) == ("four", "4")
    assert register.claims["venture-count"].status == "retired"


def test_the_sections_are_sections_with_their_heads(dist):
    main = main_of(built(dist, "index.html"))
    assert main.count("<section") == main.count("</section>") == 4        # hero, the three beats, the ventures, the colophon
    assert main.count('class="section-head"') == 1
    assert 'inview-target' not in main                                     # a hook for the script that is gone


def test_the_untouched_note_about_the_numbers_strip_is_a_template_comment_not_published(dist):
    source = (REPO / "content" / "index.html").read_text(encoding="utf-8")
    assert "{# machine-counted strip lands here once she picks the public numbers #}" in source
    assert "machine-counted" not in built(dist, "index.html")


# ---- the page's stylesheet ----

HOME_SERIF = (".devanagari", ".thesis", ".roman", ".card h2", ".colophon p", ".lede")
HOME_MONO = (".hero-ventures", ".hero-mark-cap", ".label", ".card .for", ".card .act")


def rule(css, selector):
    match = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert match, f"no rule for {selector}"
    return match.group(1)


def home_css():
    return (REPO / "tokens" / "pages" / "home.css").read_text(encoding="utf-8")


def test_the_home_names_its_own_sheet_and_the_build_publishes_it(dist):
    assert f'<link rel="stylesheet" href="{hashed_url(dist, "pages/home.css")}">' in built(dist, "index.html")
    assert hashed_file(dist, "pages/home.css").read_bytes() == (REPO / "tokens" / "pages" / "home.css").read_bytes()


@pytest.mark.parametrize("selector, token", [(s, "--font-serif") for s in HOME_SERIF] + [(s, "--font-mono") for s in HOME_MONO])
def test_the_home_css_gives_each_role_its_family_by_token(selector, token):
    assert re.search(r"font-family:\s*var\(" + token + r"\)", rule(home_css(), selector)), selector


def test_the_wordmark_sits_between_the_hero_steps_and_every_other_size_is_a_step_of_the_scale():
    css = home_css()
    assert "font-size:clamp(var(--fs-hero-min),14vw,var(--fs-hero))" in rule(css, ".hero h1")
    sizes = re.findall(r"font-size:([^;}]+)", css)
    assert len(sizes) >= 15
    for size in sizes:
        assert "var(--fs-" in size and not re.search(r"\d(rem|px|em)\b", size), size


def test_the_home_css_has_no_script_hook_and_no_em_dash():
    css = home_css()
    assert EM_DASH not in css and "@import" not in css and "url(http" not in css
    assert ".inview" not in css and "html.fx" not in css and "#inklayer" not in css and "#fluidlayer" not in css


def test_the_torn_paper_plates_are_kept_without_a_raw_colour_in_the_sheet():
    from css_guard import page_css_violations
    css = home_css()
    assert page_css_violations(css) == []
    for name in ("a", "b", "c", "d"):
        assert f".torn-{name}" in css
    # the rim is the page's ground, lighter than the tan print, where today's was a raw near-white
    assert re.search(r"background:var\(--ground\)[;}\s]", rule(css, ".torn") + ";")
