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
    "It's a teammate, not a tool.",
    "We don't store your rate card.",
    "Note the date, but not the price.",
    "It's not ready yet. We ship on Friday.",
    "Don't worry, you will get a reply.",
    "You don't need a login. You get a link.",
    "We don't spam; replies are quick.",
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

@pytest.mark.parametrize("text", ["A leveraged buyout.", "Leveraged.", "Roboustness.", "Synergistic.", "Seamlessness.", "Leverager."])
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

# ---- fix round 1, ruling 1: buzzwords match their inflections and their spaced and hyphenated forms ----

def test_signet_empowers_and_leverages():
    findings = check(main("<p>Signet empowers owners and leverages data.</p>"), None)
    assert 'buzzword: "empowers"' in findings and 'buzzword: "leverages"' in findings

INFLECTED = [
    "leverage", "leverages", "leveraging",
    "unlock", "unlocks", "unlocking", "unlocked",
    "empower", "empowers", "empowering", "empowered",
    "elevate", "elevates", "elevating", "elevated",
    "revolutionize", "revolutionizes", "revolutionizing", "revolutionized",
    "revolutionise", "revolutionises", "revolutionising", "revolutionised",
    "supercharge", "supercharges", "supercharging", "supercharged",
    "synergy", "synergies",
    "seamless", "seamlessly", "robust", "holistic",
]

@pytest.mark.parametrize("word", INFLECTED)
def test_every_inflection_of_a_buzzword_fires(word):
    assert f'buzzword: "{word}"' in check(main(f"<p>We {word} your shop.</p>"), None)
    assert f'buzzword: "{word}"' in check(main(f"<p>{word.capitalize()} your shop.</p>"), None)

def test_the_finance_sense_of_leveraged_stays_legal():
    for text in ("A leveraged buyout.", "The fund was leveraged.", "Highly leveraged firms fail first."):
        assert "buzzword" not in ids(check(main(f"<p>{text}</p>"), None))

@pytest.mark.parametrize("phrase", [
    "cutting-edge", "cutting edge", "Cutting Edge",
    "game-changer", "game changer", "game-changers", "game changers",
    "game-changing", "game changing",
    "world-class", "world class", "best-in-class", "best in class", "next-level", "next level",
])
def test_spaced_and_hyphenated_buzzword_variants_fire(phrase):
    assert "buzzword" in ids(check(main(f"<p>A {phrase} tool.</p>"), None))

def test_a_spaced_variant_reports_what_the_page_says():
    assert 'buzzword: "world class"' in check(main("<p>World  Class replies.</p>"), None)

@pytest.mark.parametrize("text", ["The cutting of the edge.", "A world of class.", "In class, at the next stop level.", "Gamechanger"])
def test_the_compound_buzzwords_need_their_words_together(text):
    assert "buzzword" not in ids(check(main(f"<p>{text}</p>"), None))

# ---- ruling 2: contrast framing is contraction-aware and punctuation-aware ----

@pytest.mark.parametrize("text", [
    "It isn't a tool; it's a teammate.",
    "It isn't just a tool, it's a teammate.",
    "This is not a tool; it's a teammate.",
    "It's not a tool - it's a teammate.",
    "It's not a tool. It is a teammate.",
    "We don't sell tools, we sell time.",
    "We do not buy leads, we sell them.",
    "It doesn't just reply, it decides.",
    "You don't need a tool; you need a teammate.",
    "Signet isn't a tool, it's a teammate.",
    "This isn't just a tool, this is a teammate.",
    "It's not a tool -- it's a teammate.",
    "It's not a tool – it's a teammate.",
    f"It's not a tool {EM} it's a teammate.",
    f"It's not a tool{EM}it's a teammate.",
    "It's not a tool: it's a teammate.",
])
def test_contrast_framing_contracted_and_punctuated_forms(text):
    assert "contrast-framing" in ids(check(main(f"<p>{text}</p>"), None))

@pytest.mark.parametrize("html", [
    "<h1>It's not a tool</h1><p>It's a teammate.</p>",
    "<h1>It isn't a tool</h1><p>It is a teammate.</p>",
    "<h1>This is not a tool</h1><h2>It's a teammate</h2>",
])
def test_contrast_framing_across_blocks_without_a_full_stop(html):
    assert "contrast-framing" in ids(check(main(html), None))

def test_two_blocks_that_do_not_frame_a_contrast_stay_clean():
    assert "contrast-framing" not in ids(check(main("<h1>Quotes in a day</h1><p>It's not ready yet, and we say so.</p>"), None))

# ---- ruling 4: the owner rule also reads the h1, and knows A.I. and agentic ----

def test_an_eyebrow_before_the_h1_cannot_hide_it():
    assert "owner-first-line" in ids(check(main("<p>New this week</p><h1>AI that answers enquiries</h1>"), "owner"))
    assert "owner-first-line" not in ids(check(main("<p>New this week</p><h1>Answer every enquiry first</h1><p>AI later.</p>"), "owner"))

def test_the_h1_is_read_whole_not_only_its_first_sentence():
    assert "owner-first-line" in ids(check(main("<p>New</p><h1>Quotes sent. AI does the rest.</h1>"), "owner"))

def test_one_finding_when_the_h1_is_also_the_first_block():
    findings = [f for f in check(main("<h1>AI that answers enquiries</h1>"), "owner") if f.startswith("owner-first-line")]
    assert len(findings) == 1

@pytest.mark.parametrize("first", ["A.I. answers enquiries", "Built with A.I. for owners", "A.I replies", "Agentic replies", "Meet our agentic team"])
def test_owner_first_line_catches_dotted_ai_and_agentic(first):
    assert "owner-first-line" in ids(check(main(f"<h1>{first}</h1><p>Plain.</p>"), "owner"))

@pytest.mark.parametrize("first", ["Agentless installs", "A. Ideal fit", "Said it"])
def test_owner_first_line_dotted_ai_and_agentic_stay_whole_words(first):
    assert "owner-first-line" not in ids(check(main(f"<h1>{first}</h1><p>Plain.</p>"), "owner"))

# ---- ruling 5: the copy rules also read the page title and meta description ----

HEAD = '<html><head><title>{title}</title><meta name="description" content="{desc}"></head><body><main><p>Plain words.</p></main></body></html>'

def test_title_and_description_are_checked_and_labelled():
    findings = check(HEAD.format(title="We leverage data", desc=f"It's not a tool, it's a teammate. In today's market {EM} done."), None)
    assert 'buzzword: title: "leverage"' in findings
    for rule in ("contrast-framing", "throat-clearing", "em-dash"):
        assert any(f.startswith(f"{rule}: description: ") for f in findings), rule
    assert not any(EM in f for f in findings)

@pytest.mark.parametrize("title, rule", [
    (f"A {EM} B", "em-dash"),
    ("It's not a tool, it's a teammate", "contrast-framing"),
    ("In today's market", "throat-clearing"),
    ("Robust replies", "buzzword"),
    ("Peace of mind for owners", "intangible"),
])
def test_every_copy_rule_reads_the_title_and_the_description(title, rule):
    assert any(f.startswith(f"{rule}: title: ") for f in check(HEAD.format(title=title, desc="Plain."), None))
    assert any(f.startswith(f"{rule}: description: ") for f in check(HEAD.format(title="Plain", desc=title), None))

def test_the_title_and_description_skip_the_two_rules_that_belong_to_the_page_body():
    html = HEAD.format(title="AI first, agents next", desc="Fast, cheap and simple. Quotes, replies and follow-ups.")
    assert check(html, "owner") == []

def test_the_description_meta_is_found_by_name_and_other_metas_are_not_copy():
    html = ('<html><head><title>Plain</title><meta name="Description" content="We leverage">'
            '<meta property="og:description" content="We empower"><meta name="keywords" content="robust"></head>'
            '<body><main><p>Plain.</p></main></body></html>')
    assert check(html, None) == ['buzzword: description: "leverage"']

def test_a_title_inside_an_svg_is_not_the_page_title():
    html = '<html><head><title>Plain</title></head><body><header><svg><title>We leverage</title></svg></header><main><p>Plain.</p></main></body></html>'
    assert check(html, None) == []

def test_a_clean_title_and_description_add_nothing():
    assert check(HEAD.format(title="Plain title", desc="Plain description."), "owner") == []

# ---- fix round 2: the same-subject frame starts a sentence and is never a conditional ----

@pytest.mark.parametrize("text", [
    "If we don't hear back, we call you.",
    "If you don't like it, you pay nothing.",
    "If you can't pay today, you can pay later.",
    "When it doesn't fit, it goes back.",
    "I don't know, I guess so.",
])
def test_conditional_clauses_and_hedges_are_not_contrast_frames(text):
    assert "contrast-framing" not in ids(check(main(f"<p>{text}</p>"), None))

@pytest.mark.parametrize("word", ["If", "When", "Unless", "Once", "Until", "Because", "Since", "Although", "While", "Whether"])
def test_a_clause_introduced_by_a_subordinator_is_never_a_frame(word):
    assert "contrast-framing" not in ids(check(main(f"<p>{word} we don't hear back, we call you.</p>"), None))
    assert "contrast-framing" not in ids(check(main(f"<p>Plain words. {word.lower()} you don't like it, you pay nothing.</p>"), None))

@pytest.mark.parametrize("html", [
    "<p>We don't sell tools, we sell time.</p>",
    "<p>Plain words. We don't sell tools, we sell time.</p>",
    "<p>Done! We don't sell tools, we sell time.</p>",
    "<p>Really? We don't sell tools, we sell time.</p>",
    "<p>\"We don't sell tools, we sell time.\"</p>",
    "<p>Plain words. (We don't sell tools, we sell time.)</p>",
    "<p>\"Plain words.\" We don't sell tools, we sell time.</p>",
    "<h1>Quotes</h1><p>We don't sell tools, we sell time.</p>",
    "<p>Our promise:</p><p>We don't sell tools, we sell time.</p>",
    "<p>Fast,</p><p>we don't sell tools, we sell time.</p>",
])
def test_the_same_subject_frame_fires_where_a_sentence_starts(html):
    assert "contrast-framing" in ids(check(main(html), None))

def test_a_block_boundary_before_a_conditional_does_not_make_it_a_frame():
    assert "contrast-framing" not in ids(check(main("<p>Our promise:</p><p>If we don't hear back, we call you.</p>"), None))

def test_the_same_subject_frame_in_the_title_and_description_starts_at_the_text():
    html = '<html><head><title>We don\'t sell tools, we sell time</title><meta name="description" content="If we don\'t hear back, we call you."></head><body><main><p>Plain.</p></main></body></html>'
    findings = check(html, None)
    assert any(f.startswith("contrast-framing: title: ") for f in findings)
    assert not any(f.startswith("contrast-framing: description: ") for f in findings)

def test_the_finding_shows_the_frame_from_its_subject():
    (finding,) = [f for f in check(main("<p>Plain words. We don't sell tools, we sell time.</p>"), None) if f.startswith("contrast-framing")]
    assert finding == 'contrast-framing: "We don\'t sell tools, we"'

def test_the_dotted_initialism_is_reported_with_its_dot():
    assert 'owner-first-line: the opening says "A.I.": "A.I. answers enquiries"' in check(main("<h1>A.I. answers enquiries</h1>"), "owner")
    assert 'owner-first-line: the opening says "A.I": "A.I replies"' in check(main("<h1>A.I replies</h1>"), "owner")
    assert 'owner-first-line: the opening says "A.I.": "Built with A.I."' in check(main("<p>Built with A.I. for owners.</p>"), "owner")
