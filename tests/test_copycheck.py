# tests/test_copycheck.py
import re

import pytest

from checks.copycheck import check

EM = chr(0x2014)


def ids(findings): return {f.split(":")[0] for f in findings}

def main(p): return f"<html><body><main>{p}</main></body></html>"

def test_em_dash():
    assert "em-dash" in ids(check(main("<p>a " + chr(0x2014) + " b</p>"), None))

def test_contrast_framing():
    assert "contrast-framing" in ids(check(main("<p>It's not a tool, it's a teammate.</p>"), None))

def test_buzzword_whole_word_only():
    assert "buzzword" in ids(check(main("<p>We leverage data.</p>"), None))
    assert "buzzword" not in ids(check(main("<p>A leveraged buyout.</p>"), None))

def test_her_triad_is_exempt_but_two_triads_fail():
    ok = "<p>We help you operate efficiently, analyze deeply and grow immensely.</p>"
    assert "stacked-threes" not in ids(check(main(ok), None))
    bad = "<p>Fast, cheap and simple. Quotes, replies and follow-ups.</p>"
    assert "stacked-threes" in ids(check(main(bad), None))

def test_owner_first_line():
    assert "owner-first-line" in ids(check(main("<h1>AI that answers enquiries</h1><p>x</p>"), "owner"))
    assert "owner-first-line" not in ids(check(main("<h1>Answer every enquiry first</h1><p>AI later.</p>"), "owner"))

def test_only_main_is_checked():
    html = "<html><body><header>We leverage</header><main><p>Plain words.</p></main></body></html>"
    assert check(html, None) == []

# ---- beyond the brief: the rules in prose, edges and the output shape ----

def test_every_finding_reads_rule_id_colon_detail():
    findings = check(main(f"<p>We leverage data {EM} it's not a tool, it's a teammate.</p>"), None)
    assert findings and all(re.fullmatch(r"[a-z-]+: .+", f) for f in findings)

def test_clean_copy_has_no_findings():
    assert check(main("<h1>Answer every enquiry first</h1><p>Plain words. Short ones.</p>"), "owner") == []

def test_the_em_dash_is_found_inside_inline_markup_and_the_finding_does_not_repeat_it():
    findings = check(main(f"<p>a <b>b {EM} c</b></p>"), None)
    assert ids(findings) == {"em-dash"}
    assert not any(EM in f for f in findings)

@pytest.mark.parametrize("text", [
    "It's not a tool, it's a teammate.",
    "Not a tool, but a teammate.",
    "This is not just a tool, it is a teammate.",
    "We are not only fast, but careful.",
    "It's not a tool. It's a teammate.",
    "IT'S NOT A TOOL. IT'S A TEAMMATE.",
    "Its not a tool. Its a teammate.",
])
def test_contrast_framing_forms(text):
    assert "contrast-framing" in ids(check(main(f"<p>{text}</p>"), None))

@pytest.mark.parametrize("text", [
    "We do not buy leads, we sell them.",
    "It's a teammate, not a tool.",
    "Note the date, but not the price.",
    "It's not ready yet. We ship on Friday.",
])
def test_contrast_framing_leaves_ordinary_negatives_alone(text):
    assert "contrast-framing" not in ids(check(main(f"<p>{text}</p>"), None))

def test_contrast_framing_across_a_heading_and_the_line_under_it():
    html = "<h1>It's not a tool.</h1><p>It's a teammate.</p>"
    assert "contrast-framing" in ids(check(main(html), None))

@pytest.mark.parametrize("phrase", [
    "In today's market", "It's worth noting that", "Let's dive in", "In a world where", "At the end of the day",
    "Needless to say", "Simply put",
])
def test_throat_clearing(phrase):
    assert "throat-clearing" in ids(check(main(f"<p>{phrase} we answer.</p>"), None))

def test_throat_clearing_with_a_curly_apostrophe_and_odd_spacing():
    assert "throat-clearing" in ids(check(main("<p>In today’s market we answer.</p>"), None))
    assert "throat-clearing" in ids(check(main("<p>At the end\nof   the day we answer.</p>"), None))

def test_curly_apostrophe_contrast_framing():
    assert "contrast-framing" in ids(check(main("<p>It’s not a tool, it’s a teammate.</p>"), None))

@pytest.mark.parametrize("word", [
    "leverage", "synergy", "cutting-edge", "game-changer", "game-changing", "revolutionize", "revolutionise",
    "seamless", "seamlessly", "unlock", "empower", "robust", "holistic", "next-level", "supercharge", "elevate",
    "world-class", "best-in-class",
])
def test_buzzwords(word):
    assert "buzzword" in ids(check(main(f"<p>A {word} approach.</p>"), None))
    assert "buzzword" in ids(check(main(f"<p>{word.title()} approach.</p>"), None))

@pytest.mark.parametrize("text", ["A leveraged buyout.", "Unlocking doors.", "Roboustness.", "Synergistic.", "Seamlessness."])
def test_buzzwords_match_whole_words_only(text):
    assert "buzzword" not in ids(check(main(f"<p>{text}</p>"), None))

@pytest.mark.parametrize("phrase", [
    "peace of mind", "take your business to the next level", "transform your business", "the power of AI",
])
def test_intangible(phrase):
    assert "intangible" in ids(check(main(f"<p>You get {phrase} here.</p>"), None))

def test_her_triad_with_the_oxford_comma_is_exempt_too():
    ok = "<p>Operate efficiently, analyze deeply, and grow immensely.</p>"
    assert "stacked-threes" not in ids(check(main(ok), None))

def test_her_triad_beside_one_other_triad_is_one_triad_not_two():
    one = "<p>Fast, cheap and simple. We operate efficiently, analyze deeply and grow immensely.</p>"
    assert "stacked-threes" not in ids(check(main(one), None))

def test_two_other_triads_fail_even_beside_her_triad():
    html = "<p>Fast, cheap and simple. Quotes, replies and follow-ups. Operate efficiently, analyze deeply and grow immensely.</p>"
    assert "stacked-threes" in ids(check(main(html), None))

def test_oxford_comma_triads_stack_too():
    assert "stacked-threes" in ids(check(main("<p>Fast, cheap, and simple. Quotes, replies, and follow-ups.</p>"), None))

def test_one_triad_per_paragraph_is_fine_even_across_paragraphs():
    html = "<p>Fast, cheap and simple.</p><p>Quotes, replies and follow-ups.</p>"
    assert "stacked-threes" not in ids(check(main(html), None))

def test_a_triad_split_by_inline_markup_still_counts():
    html = "<p>Fast, <b>cheap</b> and simple. Quotes, replies and <a href=\"/x\">follow-ups</a>.</p>"
    assert "stacked-threes" in ids(check(main(html), None))

def test_plain_two_item_lists_are_not_triads():
    assert "stacked-threes" not in ids(check(main("<p>Fast and cheap. Quotes and replies.</p>"), None))

def test_owner_first_line_checks_only_the_first_sentence():
    assert "owner-first-line" in ids(check(main("<p>Our agents answer. Then you sleep.</p>"), "owner"))
    assert "owner-first-line" not in ids(check(main("<p>You sleep. Our agents answer.</p>"), "owner"))

@pytest.mark.parametrize("first", ["Agent first", "Agents first", "Built with AI", "AI-powered replies", "Meet the agent."])
def test_owner_first_line_words(first):
    assert "owner-first-line" in ids(check(main(f"<h1>{first}</h1><p>Plain.</p>"), "owner"))

@pytest.mark.parametrize("first", ["Paid in full", "Said and done", "Agenda first", "Raid the fridge", "Ai Weiwei opens"])
def test_owner_first_line_does_not_match_inside_other_words(first):
    assert "owner-first-line" not in ids(check(main(f"<h1>{first}</h1><p>Plain.</p>"), "owner"))

@pytest.mark.parametrize("audience", [None, "founders", "Owner", ""])
def test_owner_first_line_only_applies_to_the_owner_audience(audience):
    assert "owner-first-line" not in ids(check(main("<h1>AI that answers enquiries</h1>"), audience))

def test_a_block_boundary_ends_the_first_sentence_without_a_full_stop():
    assert "owner-first-line" not in ids(check(main("<h1>Answer every enquiry first</h1><p>Our agents help.</p>"), "owner"))

def test_the_first_sentence_runs_across_inline_markup():
    assert "owner-first-line" in ids(check(main("<p>Answer <b>every</b> enquiry with <a href=\"/a\">AI</a>. Then sleep.</p>"), "owner"))

def test_empty_blocks_before_the_first_text_are_skipped():
    assert "owner-first-line" in ids(check(main("<div> <p> </p><h1>AI answers</h1></div>"), "owner"))

def test_script_and_style_text_inside_main_is_not_copy():
    html = main(f"<p>Plain.</p><script>var leverage = '{EM}';</script><style>.robust {{}}</style>")
    assert check(html, None) == []

def test_a_page_without_main_has_no_copy_to_check():
    assert check("<html><body><p>We leverage</p></body></html>", None) == []

def test_the_same_finding_is_reported_once():
    findings = check(main("<p>We leverage data. We leverage data.</p>"), None)
    assert len(findings) == len(set(findings)) == 1
