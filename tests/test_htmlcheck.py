# tests/test_htmlcheck.py
import re

import pytest

from checks.htmlcheck import check

def ids(f): return {x.split(":")[0] for x in f}
def doc(m): return f"<html><head><title>स्याही</title></head><body><main>{m}</main></body></html>"

def test_one_h1():
    assert "one-h1" in ids(check(doc("<h1>a</h1><h1>b</h1>")))
    assert "one-h1" not in ids(check(doc("<h1>a</h1>")))

def test_heading_order():
    assert "heading-order" in ids(check(doc("<h1>a</h1><h3>b</h3>")))
    assert "heading-order" not in ids(check(doc("<h1>a</h1><h2>b</h2><h3>c</h3><h2>d</h2>")))

def test_lang_hi_required_but_title_exempt():
    assert "lang-hi" in ids(check(doc("<h1>a</h1><p>स्याही</p>")))
    assert "lang-hi" not in ids(check(doc('<h1>a</h1><p><span lang="hi">स्याही</span></p>')))

def test_balanced():
    assert "balanced" in ids(check(doc("<h1>a</h1><p><b>x</p></b>")))
    assert "balanced" not in ids(check(doc("<h1>a</h1><p>x<br>y</p>")))

def test_numbers_from_claims():
    assert "numbers-from-claims" in ids(check(doc("<h1>a</h1><p>Only 5 owners.</p>")))
    ok = ('<h1>a</h1><p><span data-claim="x">₹1,499</span> <time datetime="2026-08-31">31 Aug</time></p>'
          '<div data-sample><p>09:14 draft</p></div>')
    assert "numbers-from-claims" not in ids(check(doc(ok)))

# ---- beyond the brief: the rules in prose, edges and the output shape ----

CLEAN = '<h1>a</h1><h2>b</h2><p>Plain words.<br>More.</p>'

def test_a_clean_document_has_no_findings():
    assert check(doc(CLEAN)) == []

def test_every_finding_reads_rule_id_colon_detail():
    findings = check(doc("<h1>a</h1><h1>b</h1><h4>c</h4><p>5 <b>x</p></b>स्याही"))
    assert findings and all(re.fullmatch(r"[a-z0-9-]+: .+", f) for f in findings)

def test_no_h1_at_all_fails_one_h1():
    assert "one-h1" in ids(check(doc("<h2>a</h2>")))

def test_the_h1_count_covers_the_whole_page_not_only_main():
    html = "<html><head><title>t</title></head><body><header><h1>a</h1></header><main><h1>b</h1></main></body></html>"
    assert "one-h1" in ids(check(html))

@pytest.mark.parametrize("body, bad", [
    ("<h1>a</h1><h2>b</h2><h4>c</h4>", True),
    ("<h1>a</h1><h3>b</h3>", True),
    ("<h1>a</h1><h2>b</h2><h3>c</h3><h4>d</h4><h2>e</h2><h3>f</h3>", False),
    ("<h1>a</h1><h2>b</h2><h3>c</h3><h1>d</h1>", False),
    ("<h1>a</h1><h4>b</h4><h2>c</h2>", True),
])
def test_heading_order_cases(body, bad):
    assert ("heading-order" in ids(check(doc(body)))) is bad

def test_heading_order_names_the_levels():
    (finding,) = [f for f in check(doc("<h1>a</h1><h3>b</h3>")) if f.startswith("heading-order")]
    assert "h1" in finding and "h3" in finding

def test_devanagari_in_the_title_and_meta_content_is_exempt():
    html = ('<html><head><title>स्याही</title><meta name="description" content="स्याही हिंदी">'
            '<meta property="og:title" content="स्याही"></head><body><main><h1>a</h1></main></body></html>')
    assert "lang-hi" not in ids(check(html))

def test_devanagari_in_a_script_or_style_is_not_text():
    html = doc('<h1>a</h1><script type="application/ld+json">{"alternateName": "स्याही"}</script>')
    assert "lang-hi" not in ids(check(html))

def test_lang_hi_is_inherited_from_an_ancestor():
    assert "lang-hi" not in ids(check(doc('<h1>a</h1><div lang="hi"><p><b>स्याही</b></p></div>')))

@pytest.mark.parametrize("lang", ["hi", "HI", "hi-IN", "hi-Deva"])
def test_lang_hi_accepts_the_hindi_forms(lang):
    assert "lang-hi" not in ids(check(doc(f'<h1>a</h1><p lang="{lang}">स्याही</p>')))

@pytest.mark.parametrize("lang", ["en", "", "hindi", "his"])
def test_another_language_does_not_cover_devanagari(lang):
    assert "lang-hi" in ids(check(doc(f'<h1>a</h1><p lang="{lang}">स्याही</p>')))

def test_the_nearest_lang_wins():
    html = doc('<h1>a</h1><p lang="hi">स्याही <span lang="en">सियाही</span></p>')
    findings = [f for f in check(html) if f.startswith("lang-hi")]
    assert len(findings) == 1 and "सियाही" in findings[0]

def test_html_lang_hi_covers_the_whole_page():
    html = '<html lang="hi"><head><title>t</title></head><body><main><h1>स्याही</h1></main></body></html>'
    assert "lang-hi" not in ids(check(html))

def test_devanagari_in_a_visible_attribute_needs_lang_hi_too():
    assert "lang-hi" in ids(check(doc('<h1>a</h1><img src="/x.png" alt="स्याही">')))
    assert "lang-hi" not in ids(check(doc('<h1>a</h1><img src="/x.png" alt="स्याही" lang="hi">')))

def test_devanagari_outside_main_is_checked_as_well():
    html = "<html><head><title>t</title></head><body><footer>स्याही</footer><main><h1>a</h1></main></body></html>"
    assert "lang-hi" in ids(check(html))

def test_the_lang_hi_finding_shows_the_text():
    (finding,) = [f for f in check(doc("<h1>a</h1><p>नमस्ते दुनिया</p>")) if f.startswith("lang-hi")]
    assert "नमस्ते" in finding

@pytest.mark.parametrize("fragment", [
    '<span data-claim="price">2,999</span>',
    '<span data-claim="">2,999</span>',
    '<b><span data-claim="price">2,999</span></b>',
    '<div data-sample><p>Quote 14 for 09:14</p></div>',
    '<time datetime="2026-10-06">6 Oct 2026</time>',
    '<svg viewBox="0 0 10 10"><text>5</text></svg>',
    '<p>Run <code>build 2</code>.</p>',
])
def test_numbers_inside_the_allowed_elements_pass(fragment):
    assert "numbers-from-claims" not in ids(check(doc("<h1>a</h1>" + fragment)))

@pytest.mark.parametrize("fragment", [
    "<p>5 owners</p>",
    "<h2>Step 1</h2>",
    "<p>Call 0 800</p>",
    "<p>Pay <b>3</b>x</p>",
    '<p><span class="claim">2,999</span></p>',
    '<p data-claim="x">2,999</p> <p>and 4</p>',
    "<p>१२ owners</p>",
])
def test_numbers_outside_them_fail(fragment):
    body = "<h1>a</h1>" + ("<h2>x</h2>" if "<h2>" in fragment else "") + fragment
    assert "numbers-from-claims" in ids(check(doc(body)))

def test_numbers_are_judged_in_main_only():
    html = ("<html><head><title>t 2026</title></head><body><header>Menu 1</header><main><h1>a</h1></main>"
            "<footer>approved on 6 Oct 2026</footer></body></html>")
    assert "numbers-from-claims" not in ids(check(html))

def test_numbers_in_scripts_styles_and_attributes_nobody_reads_are_not_visible_text():
    # (an aria-label, alt, title or placeholder IS read or heard: see the attribute rules at the end of this file)
    html = doc('<h1>a</h1><a href="/page-2" class="p2" data-n="2">go</a><script>var n = 5;</script><style>p{margin:4px}</style>')
    assert "numbers-from-claims" not in ids(check(html))

def test_a_number_beside_a_claim_still_fails_and_is_named():
    (finding,) = [f for f in check(doc('<h1>a</h1><p><span data-claim="x">9</span> and 7 more</p>')) if f.startswith("numbers-from-claims")]
    assert "7" in finding and "9" not in finding.split("(")[0]

def test_an_allowed_element_that_closed_does_not_exempt_the_text_after_it():
    assert "numbers-from-claims" in ids(check(doc('<h1>a</h1><p><time datetime="2026-10-06">today</time> and 5 more</p>')))

@pytest.mark.parametrize("body", [
    "<h1>a</h1><p>x</p><p>y</p>",
    "<h1>a</h1><ul><li>x</li><li>y</li></ul>",
    '<h1>a</h1><img src="/a.png" alt="a"><hr><input type="text"><br>',
    '<h1>a</h1><svg viewBox="0 0 1 1"><path d="M0 0"/><circle r="1"></circle></svg>',
    "<h1>a</h1><!-- <p> in a comment --><p>x</p>",
])
def test_balanced_markup_passes(body):
    assert "balanced" not in ids(check(doc(body)))

@pytest.mark.parametrize("body", [
    "<h1>a</h1><p>never closed",
    "<h1>a</h1><div><p>x</p>",
    "<h1>a</h1><p>x</p></p>",
    "<h1>a</h1><p>x</div></p>",
    "<h1>a</h1><p><b>x</p></b>",
    "<h1>a</h1></section>",
    "<h1>a</h1><p>x</br></p>",
    "<h1>a</h1><div/><p>x</p>",
])
def test_unbalanced_markup_fails(body):
    assert "balanced" in ids(check(doc(body)))

def test_an_unclosed_element_is_named():
    findings = [f for f in check(doc("<h1>a</h1><section><p>x</p>")) if f.startswith("balanced")]
    assert any("section" in f for f in findings)

def test_a_stray_closing_tag_is_named():
    findings = [f for f in check(doc("<h1>a</h1><p>x</p></em>")) if f.startswith("balanced")]
    assert any("</em>" in f for f in findings)

def test_the_same_finding_is_reported_once():
    findings = check(doc("<h1>a</h1><p>7 and 7</p>"))
    assert len(findings) == len(set(findings))

# ---- fix round 1, ruling 3: one main per page ----

BARE = "<html><head><title>t</title></head><body>{}</body></html>"

def test_one_main():
    assert "one-main" not in ids(check(doc("<h1>a</h1>")))
    assert "one-main" in ids(check(BARE.format("<h1>a</h1><p>no main</p>")))
    two = BARE.format("<main><h1>a</h1></main><main><p>x</p></main>")
    assert "one-main" in ids(check(two))

def test_a_main_inside_a_main_is_two():
    assert "one-main" in ids(check(BARE.format("<main><h1>a</h1><main><p>x</p></main></main>")))

def test_the_one_main_finding_counts_them():
    (zero,) = [f for f in check(BARE.format("<h1>a</h1>")) if f.startswith("one-main")]
    (two,) = [f for f in check(BARE.format("<main><h1>a</h1></main><main></main>")) if f.startswith("one-main")]
    assert "0" in zero and "2" in two

def test_a_page_with_no_main_still_gets_the_other_rules():
    findings = check(BARE.format("<h1>a</h1><h1>b</h1>"))
    assert ids(findings) == {"one-main", "one-h1"}


# ---- numbers in the attributes people read or hear: aria-label, alt, title, placeholder ----
# A reader hears an aria-label and sees an alt when the image fails, so a digit there is as much a figure as
# a digit in a paragraph and comes from a claim too. The helper `claim_text()` puts a claim's text into an
# attribute; the element then says which claims it took its digits from, `data-claims="id,id"`. With the
# register at hand the check goes further and proves the digits are the claims' current text.

REGISTER = {"booking-call-length": ("30 minutes", "30-minute"), "plate-count": ("4 plates",)}
VISIBLE = ("aria-label", "alt", "title", "placeholder")


def one(markup, claims=None):
    return check(doc(markup), claims)


def numbers(found):
    return [f for f in found if f.startswith("numbers-from-claims")]


@pytest.mark.parametrize("attr", VISIBLE)
def test_a_digit_in_a_visible_attribute_is_a_finding(attr):
    (finding,) = numbers(one(f'<h1>a</h1><a href="/x" {attr}="Book a 30-minute demo">x</a>'))
    assert '"30"' in finding and attr in finding and "outside a claim" in finding


def test_the_finding_names_each_number_and_shows_the_attribute():
    found = numbers(one('<h1>a</h1><img src="/i.webp" alt="Plate 4 of 12">'))
    assert len(found) == 2 and any('"4"' in f for f in found) and any('"12"' in f for f in found)
    assert all('alt="Plate 4 of 12"' in f for f in found)


@pytest.mark.parametrize("attr", VISIBLE)
def test_an_element_that_names_its_claims_may_carry_digits_in_its_attribute(attr):
    assert numbers(one(f'<h1>a</h1><a href="/x" {attr}="Book a 30-minute demo" data-claims="booking-call-length">x</a>')) == []


def test_attributes_that_are_not_read_or_heard_may_hold_digits():
    ok = '<h1>a</h1><a href="/signet2" class="c3" id="x1" data-n="5" style="top:4px" width="22">x</a><img src="/a1.webp" width="900" height="900" alt="">'
    assert numbers(one(ok)) == []


def test_a_head_meta_with_digits_is_not_checked_here():
    html = '<html><head><title>t</title><meta name="description" content="30 minutes"><meta property="og:title" content="4 plates"></head><body><main><h1>a</h1></main></body></html>'
    assert numbers(check(html)) == []


def test_the_header_and_footer_outside_main_are_not_checked():
    html = '<html><head><title>t</title></head><body><header><a href="/" aria-label="Home 2">x</a></header><main><h1>a</h1></main></body></html>'
    assert numbers(check(html)) == []


@pytest.mark.parametrize("wrapper", ['<div data-sample aria-label="Ledger at 09:14">x</div>', '<svg aria-label="Plate 4"></svg>',
                                     '<span data-claim="x" title="30 minutes">y</span>', '<time datetime="2026-08-31" title="31 Aug">z</time>',
                                     '<div data-sample><img src="/s.webp" alt="Meena at 09:15"></div>'])
def test_a_scene_a_drawing_a_claim_or_a_time_may_carry_digits_in_its_attributes(wrapper):
    assert numbers(one("<h1>a</h1>" + wrapper)) == []


def test_digits_in_the_text_of_an_element_that_names_claims_are_still_checked():
    found = numbers(one('<h1>a</h1><a href="/x" aria-label="Book a 30-minute demo" data-claims="booking-call-length">Only 5 left</a>'))
    assert len(found) == 1 and '"5"' in found[0]


# ---- with the register: the digits must be the listed claims' current text ----

def test_the_digits_come_from_the_listed_claims_text_full_or_short():
    for label in ("Book a 30-minute demo", "A call of 30 minutes", "Book 30 minutes or a 30-minute demo"):
        assert numbers(one(f'<h1>a</h1><a href="/x" aria-label="{label}" data-claims="booking-call-length">x</a>', REGISTER)) == []


def test_a_digit_the_listed_claims_do_not_supply_is_a_finding():
    (finding,) = numbers(one('<h1>a</h1><a href="/x" aria-label="Book a 30-minute demo in 5 days" data-claims="booking-call-length">x</a>', REGISTER))
    assert '"5"' in finding and "booking-call-length" in finding


def test_a_claim_whose_text_has_changed_no_longer_covers_a_typed_digit():
    # The attribute was written with 30 in it; the claim now says 45, so the build must say so.
    changed = {"booking-call-length": ("45 minutes", "45-minute")}
    found = numbers(one('<h1>a</h1><a href="/x" aria-label="Book a 30-minute demo" data-claims="booking-call-length">x</a>', changed))
    assert len(found) == 1 and '"30"' in found[0]


def test_a_listed_id_the_register_does_not_have_is_a_finding():
    found = numbers(one('<h1>a</h1><a href="/x" aria-label="Book a 30-minute demo" data-claims="no-such-claim">x</a>', REGISTER))
    assert any("no-such-claim" in f and "not a live claim" in f for f in found)


def test_several_ids_may_be_listed_and_each_supplies_its_own_digits():
    ok = '<h1>a</h1><img src="/i.webp" alt="A 30-minute call and 4 plates" data-claims="booking-call-length, plate-count">'
    assert numbers(one(ok, REGISTER)) == []
    assert numbers(one(ok.replace("data-claims=\"booking-call-length, plate-count\"", 'data-claims="plate-count"'), REGISTER))


def test_a_claim_may_not_excuse_digits_it_does_not_contain_by_being_listed_on_an_unrelated_element():
    assert numbers(one('<h1>a</h1><a href="/x" aria-label="Open 24 hours" data-claims="booking-call-length">x</a>', REGISTER))


def test_without_a_register_the_listed_ids_are_taken_on_trust():
    assert numbers(one('<h1>a</h1><a href="/x" aria-label="Book a 30-minute demo" data-claims="anything">x</a>')) == []
