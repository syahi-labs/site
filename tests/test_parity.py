# tests/test_parity.py
#
# Task 9a: the four policy pages (contact, privacy, terms, refund) ported word for word from the live
# site at 446f625, parity-tested against byte-for-byte snapshots in tests/parity/. Parts 9b to 9d add
# their own pairs. The comparison is tests/parity_helpers.py; the only excused differences are in
# tests/parity/allowed_diffs.yaml, each with a reason.
import datetime
import json
import re
from html import unescape
from pathlib import Path

import pytest
import yaml

from checks import copycheck, htmlcheck
from parity_helpers import PARITY, apply_allowed, link_values, words
from sitebuild.claims import ClaimRegister
from sitebuild.content import load_pages
from sitebuild.render import format_date
from sitebuild.schema import jsonld_mismatches

REPO = Path(__file__).resolve().parents[1]
EM_DASH = chr(0x2014)
APPROVED = datetime.date(2026, 10, 6)
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
    assert '<link rel="stylesheet" href="/assets/pages/policy.css">' in html
    assert (dist / "assets" / "pages" / "policy.css").read_bytes() == (REPO / "tokens" / "pages" / "policy.css").read_bytes()
    assert f'<link rel="canonical" href="https://syahi.sh{slug}">' in html


@pytest.mark.parametrize("snapshot, name, slug, updated, levels", PAGES, ids=IDS)
def test_the_page_passes_every_check_on_its_own(dist, snapshot, name, slug, updated, levels):
    html = built(dist, name)
    page = next(p for p in load_pages(REPO / "content") if p.slug == slug)
    assert htmlcheck.check(html) == []
    assert copycheck.check(html, page.audience) == []
    assert jsonld_mismatches(html) == []


@pytest.mark.parametrize("snapshot, name, slug, updated, levels", PAGES, ids=IDS)
def test_front_matter_is_the_ports_contract(snapshot, name, slug, updated, levels):
    page = next(p for p in load_pages(REPO / "content") if p.slug == slug)
    assert page.approved == APPROVED                 # the live page was last approved and shipped on 6 Oct 2026
    assert page.layout == "page" and page.css == "policy"
    assert page.audience is None and page.schema == ()
    assert page.claims and len(set(page.claims)) == len(page.claims)


@pytest.mark.parametrize("snapshot, name, slug, updated, levels", PAGES, ids=IDS)
def test_the_made_by_line_carries_the_approval_date(dist, snapshot, name, slug, updated, levels):
    assert f"Checked and approved by Surabhi Pradhan on {format_date(APPROVED)}." in built(dist, name)


# ---- text parity ----

@pytest.mark.parametrize("snapshot, name, slug, updated, levels", PAGES, ids=IDS)
def test_main_text_is_the_old_pages_text_word_for_word(dist, snapshot, name, slug, updated, levels):
    old = apply_allowed(words((PARITY / snapshot).read_text(encoding="utf-8"), "body"), snapshot)
    new = words(built(dist, name), "main")
    assert new == old


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
def test_the_last_updated_date_is_a_time_element(dist, snapshot, name, slug, updated, levels):
    when = datetime.date.fromisoformat(updated)
    long_form = f"{when.day} {MONTHS[when.month - 1]} {when.year}"
    assert f'<p class="updated">Last updated <time datetime="{updated}">{long_form}</time></p>' in main_of(built(dist, name))
    assert f"Last updated {long_form}" in (PARITY / snapshot).read_text(encoding="utf-8")


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
                     ("2020", "law-ecommerce-rules"), ("48 hours", "grievance-ack-window")],
    "privacy.html": [("ADB-1993", "org-llpin"), ("2023", "law-dpdp-act"), ("30 days", "signet-deletion-window"),
                     ("under 18", "minor-age-limit")],
    "terms.html": [("ADB-1993", "org-llpin"), ("₹1,499 a month", "signet-price-monthly"),
                   ("₹14,999 a year", "signet-price-yearly"), ("day 30", "qtm-guarantee-day")],
    "refund.html": [("14 days", "signet-annual-refund-window"), ("day 30", "qtm-guarantee-day"),
                    ("18% under SAC 998432", "katha-gst-treatment"), ("48 hours", "grievance-ack-window"),
                    ("30 days", "katha-refund-resolve-window"), ("5 to 7 working days", "razorpay-refund-timing"),
                    ("+91 89514 49537", "whatsapp-number")],
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
    "law-ecommerce-rules": ("Consumer Protection (E-Commerce) Rules, 2020", "Gazette of India"),
    # privacy
    "law-dpdp-act": ("Digital Personal Data Protection Act, 2023", "Gazette of India"),
    "signet-deletion-window": ("30 days", "Privacy policy, 2026-09-10"),
    "minor-age-limit": ("under 18", "Privacy policy, 2026-09-10"),
    # terms
    "signet-price-monthly": ("\u20b91,499 a month", "Terms of service, 2026-09-12"),
    "signet-price-yearly": ("\u20b914,999 a year", "Terms of service, 2026-09-12"),
    "qtm-guarantee-day": ("day 30", "Terms of service, 2026-09-12"),
    # refund
    "signet-annual-refund-window": ("14 days", "Refund policy, 2026-09-12"),
    "katha-gst-treatment": ("18% under SAC 998432", "Refund policy, 2026-09-12"),
    "katha-refund-resolve-window": ("30 days", "Refund policy, 2026-09-12"),
    "razorpay-refund-timing": ("5 to 7 working days", "Refund policy, 2026-09-12"),
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


@pytest.mark.parametrize("snapshot", sorted(PINNED))
def test_the_snapshot_is_the_pinned_blob_byte_for_byte(snapshot):
    import hashlib
    data = (PARITY / snapshot).read_bytes()
    blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()   # git's own object id
    assert blob == PINNED[snapshot]
