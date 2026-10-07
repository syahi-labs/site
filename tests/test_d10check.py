# tests/test_d10check.py: where the D10 sentence goes and what else may be said about Signet's customers.
import pytest

from checks.d10check import check
from sitebuild.pipeline import build

D10 = '<span data-claim="signet-d10">Live today: a made-up line. No outside customers yet. Founding users start soon.</span>'
PRICE = '<span data-claim="signet-price-line">From 10 a month.</span>'
BOOK = '<a href="https://cal.com/someone/30-min">Book a demo</a>'


def doc(body, title="x"):
    return f"<html><head><title>{title}</title></head><body><header>Customers and users sign up here.</header><main>{body}</main></body></html>"


def rules(findings):
    return {f.split(":")[0] for f in findings}


# ---- (a) one d10 span wherever Signet is offered ----

def test_the_price_line_without_the_d10_span_is_a_finding():
    found = check(doc(f"<h1>Signet</h1><p>{PRICE}</p>"), "/signet")
    assert rules(found) == {"d10-count"} and "price line" in found[0] and "0" in found[0]


def test_the_price_line_with_exactly_one_d10_span_is_clean():
    assert check(doc(f"<h1>Signet</h1><p>{D10}</p><p>{PRICE}</p>"), "/signet") == []


def test_two_d10_spans_are_a_finding():
    found = check(doc(f"<h1>Signet</h1><p>{D10}</p><p>{D10}</p><p>{PRICE}</p>"), "/signet")
    assert rules(found) == {"d10-count"} and "2" in found[0]


def test_a_signet_booking_link_needs_the_d10_span():
    assert rules(check(doc(f"<h1>Signet</h1><p>{BOOK}</p>"), "/signet")) == {"d10-count"}
    assert rules(check(doc(f"<h1>Other</h1><p>{BOOK}</p>"), "/other")) == {"d10-count"}      # the link says demo
    assert check(doc(f"<h1>Signet</h1><p>{D10}</p><p>{BOOK}</p>"), "/signet") == []


def test_a_plain_booking_link_on_another_page_is_not_a_signet_offer():
    assert check(doc('<h1>Contact</h1><p><a href="https://cal.com/someone/30-min">Book 30 minutes</a></p>'), "/contact") == []


def test_a_page_with_no_signet_offer_needs_no_d10_span():
    assert check(doc("<h1>Katha</h1><p>Audio.</p>"), "/katha") == []


def test_a_booking_link_outside_main_is_not_counted():
    html = f'<html><body><header>{BOOK}</header><main><h1>Other</h1><p>Hi.</p></main></body></html>'
    assert check(html, "/other") == []


# ---- (b) customer talk about Signet stays inside the span ----

def test_a_customers_sentence_with_signet_outside_the_span_is_a_finding():
    found = check(doc("<h1>Home</h1><p>Signet has customers already. We build.</p>"), "/")
    assert len(found) == 1 and found[0].startswith("d10-sentence") and "Signet has customers already." in found[0]


@pytest.mark.parametrize("sentence", ["Our users love it.", "A public app you can sign up for today.", "Plenty of customers.", "Do signup now."])
def test_on_a_signet_page_any_customer_word_outside_the_span_is_a_finding(sentence):
    found = check(doc(f"<h1>Signet</h1><p>{sentence}</p>"), "/signet")
    assert rules(found) == {"d10-sentence"} and sentence in found[0]


def test_a_page_whose_h1_names_signet_is_a_signet_page_whatever_its_path():
    assert rules(check(doc("<h1>About Signet</h1><p>Our users love it.</p>"), "/elsewhere")) == {"d10-sentence"}


def test_customer_words_on_a_page_that_is_not_about_signet_are_fine():
    assert check(doc("<h1>Services</h1><p>Our customers like quotes.</p><p>Signet is the approval layer.</p>"), "/services") == []


def test_the_d10_span_may_say_all_of_it():
    assert check(doc(f"<h1>Signet</h1><p>{D10} Book a call.</p>"), "/signet") == []


def test_the_sentence_beside_the_span_is_still_read():
    found = check(doc(f"<h1>Signet</h1><p>{D10} Our users agree.</p>"), "/signet")
    assert [f.split(":")[0] for f in found] == ["d10-sentence"] and "Our users agree." in found[0]


def test_chrome_outside_main_is_not_read():
    assert check(doc("<h1>Signet</h1><p>Fine.</p>"), "/signet") == []


def test_a_finding_is_reported_once():
    found = check(doc("<h1>Signet</h1><p>Our users.</p><p>Our users.</p>"), "/signet")
    assert len(found) == 1


# ---- in the build: a warning in dev, a problem in release ----

def test_the_build_warns_in_dev_and_refuses_in_release(mini_root, tmp_path):
    page = mini_root / "content" / "signet.html"
    page.write_text(page.read_text(encoding="utf-8") + "<p>Our users sign up daily.</p>\n", encoding="utf-8")
    dev = build(mini_root, tmp_path / "dev")
    assert dev.problems == []
    assert [w for w in dev.warnings if "signet.html" in w and "d10check" in w and "Our users sign up daily." in w]
    release = build(mini_root, tmp_path / "release", release=True)
    assert [p for p in release.problems if "signet.html" in p and "d10check" in p and "Our users sign up daily." in p]


def test_the_build_flags_a_missing_d10_span(mini_root, tmp_path):
    page = mini_root / "content" / "signet.html"
    page.write_text(page.read_text(encoding="utf-8").replace("<p>{{ claim('signet-d10') }}</p>\n", "").replace("signet-d10, ", ""), encoding="utf-8")
    dev = build(mini_root, tmp_path / "dev")
    assert dev.problems == [] and [w for w in dev.warnings if "d10-count" in w and "signet.html" in w]


def test_the_source_holds_no_em_dash():
    from pathlib import Path
    for path in (Path(__file__), Path(__file__).parents[1] / "checks" / "d10check.py"):
        assert chr(0x2014) not in path.read_text(encoding="utf-8"), path
