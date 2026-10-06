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

def test_numbers_in_attributes_scripts_and_styles_are_not_visible_text():
    html = doc('<h1>a</h1><a href="/page-2" aria-label="page 2">go</a><script>var n = 5;</script><style>p{margin:4px}</style>')
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
