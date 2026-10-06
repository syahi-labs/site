"""Guards on the interim token file and the base stylesheet.

The UI phase re-values the tokens. These tests pin what must stay true when it
does: every text and background pair we use meets WCAG AA, and the type scale,
motion durations and reduced-motion rule keep their shape.
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TOKENS = (REPO / "tokens" / "tokens.css").read_text(encoding="utf-8")
BASE = (REPO / "tokens" / "base.css").read_text(encoding="utf-8")
TEMPLATES = sorted((REPO / "templates").rglob("*.html"))
EM_DASH = chr(0x2014)


def declared(name):
    """The value of `--name` in the first :root block."""
    root = re.search(r":root\s*\{(.*?)\}", TOKENS, re.S).group(1)
    match = re.search(r"--" + re.escape(name) + r"\s*:\s*([^;]+);", root)
    assert match, f"--{name} is not declared in :root"
    return match.group(1).strip()


def channel(value):
    value = value.lstrip("#")
    return [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def luminance(hex_colour):
    r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channel(hex_colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# (text colour token, background token): every pair base.css and the templates put together.
TEXT_PAIRS = [
    ("ink", "ground"), ("ink", "ground-deep"),
    ("muted", "ground"), ("muted", "ground-deep"),
    ("act", "ground"), ("act", "ground-deep"),
    ("ground", "act"),   # CTA label
    ("ground", "ink"),   # skip link
]


@pytest.mark.parametrize("fg, bg", TEXT_PAIRS)
def test_text_pairs_meet_wcag_aa(fg, bg):
    ratio = contrast(declared(fg), declared(bg))
    assert ratio >= 4.5, f"--{fg} on --{bg} is {ratio:.2f}:1, below 4.5:1"


def test_role_names_not_colour_names():
    for name in ("ground", "ground-deep", "ink", "muted", "rule", "hair", "act"):
        declared(name)
    assert not re.search(r"--(parchment|wax|ink-soft|ink-faint|ink-hair)\b", TOKENS)


def test_interim_values_are_todays_palette():
    assert declared("ink").upper() == "#221A0E"
    assert declared("ground").upper() == "#F0E8D2"
    assert declared("ground-deep").upper() == "#E6DBBE"
    assert declared("act").upper() == "#8E2F1E"


def test_font_families_are_tokens_with_system_fallbacks():
    for name, first, generic in (("font-serif", "Fraunces", "serif"), ("font-sans", "Inter", "sans-serif"),
                                 ("font-mono", "IBM Plex Mono", "monospace"),
                                 ("font-deva", "Tiro Devanagari Hindi", "serif")):
        value = declared(name)
        assert value.startswith(f"'{first}'"), value
        assert value.rstrip().endswith(generic), value


def test_type_scale_runs_11_to_52_px():
    sizes = []
    for name in re.findall(r"--(fs-[a-z0-9-]+)\s*:", TOKENS):
        value = declared(name)
        px = float(value[:-3]) * 16 if value.endswith("rem") else float(value[:-2])
        sizes.append(px)
    assert min(sizes) == 11 and max(sizes) == 52
    assert sizes == sorted(sizes)


def test_motion_durations_and_reduced_motion():
    assert [declared(n) for n in ("dur-fast", "dur-base", "dur-slow")] == ["180ms", "320ms", "1200ms"]
    block = re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{(.*?)\n\}", TOKENS, re.S)
    assert block, "tokens.css has no prefers-reduced-motion rule"
    assert re.search(r"--travel\s*:\s*0", block.group(1)), "reduced motion must zero the travel distance"


def test_spacing_steps_exist():
    for step in range(1, 10):
        declared(f"space-{step}")


def test_base_css_contract():
    assert ":lang(hi){letter-spacing:normal}" in BASE
    assert ":focus-visible" in BASE
    assert ".skip:focus" in BASE
    assert "scroll-behavior" in BASE
    # smooth scrolling only for people who have not asked for less motion
    assert re.search(r"prefers-reduced-motion:\s*no-preference\)\s*\{\s*html\s*\{\s*scroll-behavior:\s*smooth", BASE)


def test_no_gradients_no_shadows_no_pills():
    css = TOKENS + BASE
    assert "gradient(" not in css and "box-shadow" not in css and "999px" not in css


def test_no_em_dash_in_tokens_base_or_templates():
    for path in [REPO / "tokens" / "tokens.css", REPO / "tokens" / "base.css", *TEMPLATES]:
        assert EM_DASH not in path.read_text(encoding="utf-8"), path


def test_no_scripts_in_templates_except_jsonld():
    for path in TEMPLATES:
        for tag in re.findall(r"<script[^>]*>", path.read_text(encoding="utf-8")):
            assert 'type="application/ld+json"' in tag, (path, tag)
