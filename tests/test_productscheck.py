# tests/test_productscheck.py: the claims check for /products (her ruling, 2026-11-21).
import pytest

from checks.productscheck import check

BANNED = {
    "beta": "<p>Join the beta.</p>",
    "waitlist": "<p>Join the waitlist.</p>",
    "wait list": "<p>Join the wait list.</p>",
    "coming soon": "<p>Coming soon.</p>",
    "voice agent": "<p>A voice agent for you.</p>",
    "best": "<p>The best speech to text.</p>",
    "most accurate": "<p>The most accurate there is.</p>",
    "accuracy": "<p>High accuracy.</p>",
    "an accuracy number": "<p>Reads 97% right.</p>",
    "a price": "<p>Pricing starts soon.</p>",
    "a rupee sign": "<p>₹499 a month.</p>",
    "a dollar sign": "<p>$5.</p>",
    "free": "<p>Free to try.</p>",
    "on sale": "<p>Now on sale.</p>",
    "cloning": "<p>Voice cloning.</p>",
    "a choice of voices": "<p>A choice of voices.</p>",
    "open source": "<p>It is open source.</p>",
    "open-source": "<p>It is open-source.</p>",
    "GitHub": '<a href="https://github.com/x">code</a>',
    "on-device": "<p>Runs on-device.</p>",
    "never leaves": "<p>Audio never leaves your machine.</p>",
    "tamper-proof": "<p>Tamper-proof watermark.</p>",
    "customers": "<p>Our customers love it.</p>",
    "partners": "<p>With our partners.</p>",
    "a rival": "<p>Better than Whisper.</p>",
    "HQ": "<p>Your HQ.</p>",
    "Signet": "<p>Signet by Syahi.</p>",
    "a label": '<a aria-label="Join the beta">Go</a>',
    "a meta tag": '<meta name="description" content="Best voice AI">',
    "an entity": "<p>The &#98;est one.</p>",
}


@pytest.mark.parametrize("text", BANNED.values(), ids=BANNED.keys())
def test_each_banned_thing_is_a_finding_on_products(text):
    assert check(f"<main>{text}</main>", "/products") != []


@pytest.mark.parametrize("block", [
    '{"@type": "SoftwareApplication", "offers": {"@type": "Offer"}}',
    '{"@type": "SoftwareApplication", "aggregateRating": {"ratingValue": "5"}}',
    '{"@type": "SoftwareApplication", "review": []}',
    '{"@type": "SoftwareApplication", "availability": "PreOrder"}',
    '{"@type": "Offer", "availability": "PreSale"}',
    '{"@type": "Offer", "price": "0"}',
])
def test_each_banned_structured_data_is_a_finding(block):
    findings = check(f'<main><p>Plain.</p></main><script type="application/ld+json">{block}</script>', "/products")
    assert any(f.startswith("structured-data") or "claim-words" in f for f in findings), block


def test_clean_words_and_clean_structured_data_pass():
    html = ('<title>Voice AI for English, Hindi and Hinglish | Syahi</title><main><h1>Voice AI for English, Hindi and Hinglish</h1>'
            '<p>In private preview, built in-house.</p></main>'
            '<script type="application/ld+json">{"@type": "SoftwareApplication", "name": "Syahi Talk"}</script>')
    assert check(html, "/products") == []


def test_a_word_inside_another_word_is_not_a_finding():
    assert check("<main><p>A bestowed gift, a betamax, a hqx file.</p></main>", "/products") == []


def test_style_blocks_are_not_read():
    assert check("<style>.best{color:red}</style><main><p>Plain.</p></main>", "/products") == []


def test_every_other_slug_is_left_alone():
    assert check("<main><p>The best beta waitlist. Signet.</p></main>", "/about") == []
    assert check("<main><p>The best beta waitlist. Signet.</p></main>", "/products/x") == []


def test_each_finding_is_named_once():
    findings = check("<main><p>best best best</p></main>", "/products")
    assert len(findings) == 1 and findings[0].startswith("claim-words: best")
