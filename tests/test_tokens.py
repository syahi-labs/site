"""Guards on the interim token file and the base stylesheet.

The UI phase re-values the tokens. These tests pin what must stay true when it
does: every text and background pair we use meets WCAG AA, and the type scale,
motion durations and reduced-motion rule keep their shape.
"""
import re
from pathlib import Path

import pytest

from css_guard import DECLARED_TOKENS, FONT_TOKENS, NAMED_COLOURS, SIZE_TOKENS, page_css_violations

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


# ---- the cascade: a global a:hover must not beat a component's own colours ----
# TEXT_PAIRS lists the pairs we intend. This resolves the pairs the stylesheet really
# produces, hover and focus included, because that is where a global `a:hover` rule
# once overrode the skip link's colour and left it at 2.11:1.
SIMPLE_SELECTOR = re.compile(r"([a-z][a-z0-9]*)?((?:\.[\w-]+|:[a-z-]+)*)")


def plain_rules(css):
    """(selector list, declarations) for every plain rule outside an at-rule, in source order."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    rules, pos = [], 0
    while True:
        opening = css.find("{", pos)
        if opening < 0:
            return rules
        prelude, depth, i = css[pos:opening].strip(), 1, opening + 1
        while depth:
            depth += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        pos = i
        if prelude.startswith("@"):
            continue  # @media, @supports, @font-face: conditional or not about elements
        body = css[opening + 1:i - 1]
        decls = {}
        for item in body.split(";"):
            if ":" in item:
                prop, value = item.split(":", 1)
                decls[prop.strip()] = value.strip()
        rules.append((prelude, decls))


def resolved_colours(css, tag, classes, states):
    """(color, background) as hex for an element in a state, by specificity then source order.

    Only selectors made of one type, classes and pseudo-classes are considered. A selector
    with a combinator needs ancestors this element does not have, and a pseudo-element
    styles something else, so neither can touch the element's own colours.
    """
    winners = {}
    for order, (prelude, decls) in enumerate(plain_rules(css)):
        for selector in (part.strip() for part in prelude.split(",")):
            match = SIMPLE_SELECTOR.fullmatch(selector)
            if not match or not selector:
                continue
            kind = match.group(1)
            parts = re.findall(r"[.:][\w-]+", match.group(2))
            wanted_classes = {p[1:] for p in parts if p[0] == "."}
            wanted_states = {p[1:] for p in parts if p[0] == ":"}
            if (kind not in (None, tag) or not wanted_classes <= classes
                    or not wanted_states <= states):
                continue
            specificity = (0, len(parts), 1 if kind else 0)
            for prop in ("color", "background", "background-color"):
                if prop in decls:
                    key = "background" if prop.startswith("background") else "color"
                    rank = (specificity, order)
                    if key not in winners or rank >= winners[key][0]:
                        winners[key] = (rank, decls[prop])
    out = []
    for key in ("color", "background"):
        assert key in winners, f"no {key} reaches <{tag}> {sorted(classes)} in {sorted(states)}"
        value = winners[key][1]
        var = re.fullmatch(r"var\(--([a-z-]+)\)", value)
        out.append(declared(var.group(1)) if var else value)
    for value in out:
        assert re.fullmatch(r"#[0-9a-fA-F]{6}", value), f"cannot resolve {value!r} to a hex colour"
    return out


STATES = {
    "rest": set(),
    "hover": {"hover"},
    "focus": {"focus", "focus-visible"},
    "hover and focus": {"hover", "focus", "focus-visible"},
}


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("name, classes", [("skip link", {"skip"}), ("call button", {"cta"})])
def test_components_keep_aa_colours_in_every_state(name, classes, state):
    fg, bg = resolved_colours(BASE, "a", classes, STATES[state])
    ratio = contrast(fg, bg)
    assert ratio >= 4.5, f"{name} on {state} is {fg} on {bg}, {ratio:.2f}:1, below 4.5:1"


def test_the_cascade_check_catches_a_global_hover_beating_a_component():
    """The stylesheet as it was before the fix: a:hover (0,1,1) beats .skip (0,1,0)."""
    old = "a:hover{color:var(--act)} .skip{background:var(--ink);color:var(--ground)}"
    fg, bg = resolved_colours(old, "a", {"skip"}, {"hover"})
    assert fg.upper() == declared("act").upper()
    assert contrast(fg, bg) < 4.5


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


def px(name):
    value = declared(name)
    return float(value[:-3]) * 16 if value.endswith("rem") else float(value[:-2])


def test_type_scale_runs_11_to_52_px():
    # The reading scale. The hero steps (--fs-hero-*) are the display wordmark's and sit above it.
    sizes = [px(name) for name in re.findall(r"--(fs-(?!hero)[a-z0-9-]+)\s*:", TOKENS)]
    assert min(sizes) == 11 and max(sizes) == 52
    assert sizes == sorted(sizes)


def test_the_hero_steps_are_the_home_wordmarks_range_and_sit_above_the_reading_scale():
    assert (px("fs-hero-min"), px("fs-hero")) == (72, 168)
    assert px("fs-display") < px("fs-hero-min") < px("fs-hero")
    assert {"--fs-hero", "--fs-hero-min"} <= SIZE_TOKENS and "--fs-body" in SIZE_TOKENS and "--space-4" not in SIZE_TOKENS


# ---- brand marks: logo colours, not palette ----

def test_the_signet_dot_is_the_one_brand_mark_token_in_its_own_commented_group():
    marks = re.findall(r"(--mark-[a-z0-9-]+)\s*:", TOKENS)
    assert marks == ["--mark-signet-dot"]
    assert declared("mark-signet-dot").upper() == "#B06325"
    assert "brand marks (logo colours, not palette)" in TOKENS
    assert TOKENS.index("brand marks (logo colours, not palette)") < TOKENS.index("--mark-signet-dot")


def test_the_dot_token_colours_the_seals_dot_and_nothing_else():
    users = {}
    for path in [*(REPO / "tokens").rglob("*.css"), *TEMPLATES, *(REPO / "content").rglob("*.html")]:
        if path.name == "tokens.css":
            continue
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"([^{}]*)\{[^{}]*var\(--mark-signet-dot\)[^{}]*\}", text):
            users.setdefault(path.name, []).append(match.group(1).strip())
    assert users == {"base.css": [".seal-dot"]}
    for selector in (".seal-ring", ".seal-core"):
        assert re.search(re.escape(selector) + r"\s*\{[^}]*var\(--ink\)", BASE), selector


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


# ---- page-scoped CSS: colours and type families come from tokens.css; sizes and spacing are not policed ----
# The guard is tests/css_guard.py. This is where it runs over every sheet, and where it is tested itself.

PAGE_CSS = sorted((REPO / "tokens" / "pages").glob("*.css"))


@pytest.mark.parametrize("css", PAGE_CSS, ids=lambda path: path.name)
def test_page_css_uses_tokens_only(css):
    assert page_css_violations(css.read_text(encoding="utf-8")) == [], css.name


@pytest.mark.parametrize("css", PAGE_CSS, ids=lambda path: path.name)
def test_page_css_has_no_em_dash_import_or_remote_url(css):
    text = css.read_text(encoding="utf-8")
    assert EM_DASH not in text and "@import" not in text and "url(http" not in text, css.name


def test_there_is_a_page_stylesheet_to_guard():
    assert (REPO / "tokens" / "pages" / "katha-index.css") in PAGE_CSS


# ---- the guard's own tests ----

def test_the_font_tokens_are_read_from_tokens_css():
    assert {"--font-serif", "--font-sans", "--font-mono", "--font-deva"} <= FONT_TOKENS
    assert all(declared(name[2:]) for name in FONT_TOKENS)                 # each one is really declared
    assert not any(name.startswith(("--fs-", "--space-", "--lh-")) for name in FONT_TOKENS)


def test_the_guard_reads_the_token_set_it_is_given_not_a_fixed_list():
    assert page_css_violations("a{font-family:var(--font-new)}", families={"--font-new"}) == []
    assert page_css_violations("a{font-family:var(--font-serif)}", families={"--font-new"})


def test_the_named_colour_list_is_css_color_4s():
    assert len(NAMED_COLOURS) == 148
    assert {"red", "rebeccapurple", "grey", "gray", "tan", "whitesmoke"} <= NAMED_COLOURS
    assert not NAMED_COLOURS & {"transparent", "currentcolor", "inherit", "initial", "unset", "none"}


@pytest.mark.parametrize("fine", [
    # type roles by token: the property and the shorthand
    "a{font-family:var(--font-serif)}",
    "a{font-family:var(--font-mono),var(--font-sans)}",
    "a{font-family:var( --font-deva )}",
    "a{font-family:var(--font-serif)!important}",
    "a{font-family:inherit}", "a{font:inherit}",
    "a{font:500 var(--fs-small)/var(--lh-body) var(--font-mono)}",
    "a{font:italic 600 var(--fs-lead) var(--font-serif)}",
    "a{font:600 clamp(var(--fs-small),2vw,var(--fs-h3))/1.2 var(--font-serif)}",
    "a{font:600 max(var(--fs-small),var(--fs-ui))/1.2 var(--font-serif)}",
    "a{font:var(--fs-small)/1.5 var(--font-mono),var(--font-sans)}",
    "a{font:var(--fs-small)/20px var(--font-mono)}", "a{font:700 var(--fs-body) var(--font-serif), var(--font-sans)}",
    "a::marker{font-family:var(--font-mono)}",
    # colour: tokens, the allowed keywords, comments and names that are not values
    "a{color:var(--ink)}", "a{background:var(--ground-deep)}", "a{border:1px solid var(--rule)}",
    "a{color:transparent}", "a{color:currentColor}", "a{color:currentcolor}", "a{color:inherit}",
    "a{color:initial}", "a{color:unset}", "a{background:none}",
    "/* #fff, rgb( and Georgia in a comment */a{color:var(--muted)}",
    ".red{color:var(--ink)}", ".gold-rule{border-color:var(--rule)}", "#tan{color:var(--ink)}",
    "a{content:'red'}", 'a{content:"Georgia #fff"}', "a{background:url(#red)}",
    "a:hover{color:var(--act)}", "a{transition:background-color var(--dur-fast) var(--ease)}",
    "a{--x:var(--ink)}",
    # a page may make its own custom properties; only the names tokens.css defines are tokens.css's alone
    "a{--card-gap:var(--space-4)}", "a{--card-pad:1rem}", "a{--cols:3}", "a{--FONT-SERIF:inherit}",
    "a{padding:var(--space-4)}", "a{font-family:var(--font-serif)}", ".ink{--ring:var(--ink)}",
    "@property --card-gap{syntax:'<length>';inherits:false;initial-value:1rem}",
    "a{color:var(--ink) /* red */}", "a{/* #fff */color:var(--ink);/* rgb(1,2,3) Georgia */}",
    "a{counter-reset:red-count}", "a{animation-name:fade-gold-in}", "a{list-style:zero-padded inside}",
    # a font size is a step of the scale: one step; clamp() with a step at each bound and any length between;
    # min() or max() of steps only
    "a{font-size:var(--fs-body)}", "a{font-size:var( --fs-body )}", "a{font-size:var(--fs-hero)}",
    "a{font-size:var(--fs-body)!important}", "a{font-size:inherit}", "a{font-size:initial}",
    "a{font-size:clamp(var(--fs-lead),2.8vw,var(--fs-h3))}",
    "a{font-size:clamp(var(--fs-hero-min),14vw,var(--fs-hero))}",
    "a{font-size:clamp(var(--fs-small),calc(var(--fs-body) + .5vw),var(--fs-h2))}",
    "a{font-size:clamp( var(--fs-small) , 2dvw , var(--fs-h2) )}",
    "a{font-size:clamp(var(--fs-small),1.5rem,var(--fs-h2))}", "a{font-size:clamp(var(--fs-small),var(--x),var(--fs-h2))}",
    "a{font-size:clamp(var(--fs-small),max(2vw,1rem) + 1vh,var(--fs-h2))}",
    "a{font-size:min(var(--fs-h1),var(--fs-h2))}", "a{font-size:max(var(--fs-small),var(--fs-ui))}",
    "a{font-size:max(var(--fs-small))}", "a{font-size:min( var(--fs-h1) , var(--fs-hero) , var(--fs-h2) )}",
    "a{font-size:MAX(var(--fs-small),var(--fs-ui))}",
    # spacing, line heights and the rest of the lengths are not policed
    "a{margin:13px 7px}", "a{line-height:1.37}", "a{line-height:24px}", "a{padding:.3em}",
    "a{letter-spacing:.24em}", "a{border-width:1.5px}", "a{width:12rem;height:2em;gap:.75rem}",
    "a{font-size-adjust:.5}",
])
def test_the_page_css_guard_lets_these_through(fine):
    assert page_css_violations(fine) == [], fine


@pytest.mark.parametrize("bad", [
    # raw colours, every form
    "a{color:#abc}", "a{color:#AABBCC}", "a{color:#aabbccdd}", "a{border:1px solid #fff}",
    "a{color:rgb(1,2,3)}", "a{color:RGB(1,2,3)}", "a{color:rgba(1,2,3,.5)}",
    "a{color:hsl(1,2%,3%)}", "a{color:hsla(1,2%,3%,.5)}", "a{color:hwb(1 2% 3%)}",
    "a{color:oklch(60% .1 30)}", "a{color:oklab(60% .1 .1)}", "a{color:lab(50% 40 59)}",
    "a{color:lch(50% 40 59)}", "a{color:color(display-p3 1 0 0)}",
    "a{color:var(--ink,#fff)}",
    "a{--accent:#abc}", "a{--accent:red}",
    "a{box-shadow:0 0 4px red}",
    # literal families, every form
    "a{font-family:serif}", "a{font-family:Georgia}", "a{font-family:'Fraunces',serif}",
    'a{font-family:"Inter"}', "a{font-family:system-ui}", "a{font-family:monospace}",
    "a{font-family:var(--font-serif),serif}", "a{font-family:var(--font-serif,serif)}",
    "a{font-family:var(--font-missing)}", "a{font-family:var(--ink)}", "a{font-family:var(--fs-body)}",
    "a{font-family:var(--font-serif) Georgia}",
    "a{font:12px Georgia}", "a{font:12px serif}", 'a{font:12px/1.5 "Inter",sans-serif}',
    "a{font:12px var(--font-serif),serif}", "a{font:12px var(--font-missing)}", "a{font:12px/1.4 var(--ink)}",
    "a{font:caption}", "a{font:italic 600 1rem monospace}", "a{font:12px}", "a{font:12px/1.4}",
    "a{font:var(--fs-nope) var(--font-serif)}", "a{font:12px/var(--lh-nope) var(--font-serif)}",
    "@font-face{font-family:'Fraunces';src:url(f.woff2)}",
    # redefining a custom property tokens.css defines: the way around the family and colour rules
    "a{--font-serif:Georgia}", ":root{--font-serif:Georgia,serif}", "a{--font-serif:serif}",
    "a{--font-serif:var(--font-sans)}", "a{ --font-serif : Georgia }", "a{--font-mono:monospace!important}",
    "a{--ground:var(--ink)}", "a{--ink:var(--ground)}", "a{--act:var(--ink)}", ":root{--ground:#fff}",
    ":root{--space-4:2rem}", "a{--fs-body:20px}", "a{--lh-body:1}", "a{--wrap:100%}", "a{--travel:99px}",
    "@media (min-width:40em){:root{--gutter:0}}",
    "@property --font-serif{syntax:'*';inherits:true;initial-value:Georgia}",
    "@property --ink{syntax:'<color>';inherits:true}",
    # a raw font size, alone or in the shorthand: sizes come from the scale
    "a{font-size:12px}", "a{font-size:1rem}", "a{font-size:1.25em}", "a{font-size:120%}", "a{font-size:0}",
    "a{font-size:large}", "a{font-size:smaller}", "a{font-size:medium}", "a{font-size:5vw}",
    "a{font-size:12px!important}", "a{FONT-SIZE:12PX}",
    "a{font-size:clamp(1rem,2vw,2rem)}", "a{font-size:clamp(var(--fs-small),2vw,24px)}",
    "a{font-size:clamp(var(--fs-small),2vw,1.5em)}", "a{font-size:clamp(1rem,2vw,var(--fs-h2))}",
    "a{font-size:calc(var(--fs-body) + 2px)}", "a{font-size:calc(1rem*2)}", "a{font-size:min(5vw,6vw)}",
    "a{font-size:clamp(var(--fs-small),2vw)extra}",
    # the loose forms: a step somewhere is not enough, every bound is a step
    "a{font-size:clamp(var(--fs-small),2vw,40vw)}", "a{font-size:max(var(--fs-small),5vw)}",
    "a{font-size:calc(var(--fs-micro)*9)}", "a{font:600 max(var(--fs-small),5vw)/1.2 var(--font-serif)}",
    "a{font-size:min(var(--fs-h1),8vw)}", "a{font-size:max(var(--fs-small),1.2vw)}", "a{font-size:min(var(--fs-h1),50%)}",
    "a{font-size:calc(var(--fs-body)*1.1)}", "a{font-size:calc(var(--fs-body) + .2vw)}", "a{font-size:calc(var(--fs-body))}",
    "a{font-size:clamp(2vw,3vw,var(--fs-h2))}", "a{font-size:clamp(var(--fs-small),2vw,var(--fs-nope))}",
    "a{font-size:clamp(var(--fs-small),2vw,var(--fs-h2),4vw)}", "a{font-size:clamp(var(--fs-small),,var(--fs-h2))}",
    "a{font-size:clamp(var(--fs-small),var(--fs-body))}", "a{font-size:clamp(var(--fs-small))}",
    "a{font-size:clamp(var(--fs-small),2vw,calc(var(--fs-h2)))}", "a{font-size:clamp(var(--fs-small),2vw,clamp(var(--fs-h1),1vw,var(--fs-h2)))}",
    "a{font-size:clamp(var(--fs-small),url(x),var(--fs-h2))}", "a{font-size:clamp(var(--fs-small),2vw,var(--fs-h2)}",
    "a{font-size:clamp(var(--fs-small),(2vw,var(--fs-h2))}", "a{font-size:clamp(var(--fs-small),2vw,var(--fs-h2)) clamp(var(--fs-small),2vw,var(--fs-h2))}",
    "a{font-size:min()}", "a{font-size:max()}", "a{font-size:min(var(--fs-h1),var(--fs-nope))}",
    "a{font-size:min(var(--fs-h1),var(--fs-h2),2vw)}", "a{font-size:max(var(--fs-small),var(--fs-ui,12px))}",
    "a{font:calc(var(--fs-micro)*9)/1.2 var(--font-serif)}", "a{font:clamp(var(--fs-small),2vw,40vw) var(--font-serif)}",
    "a{font-size:var(--fs-nope)}", "a{font-size:var(--space-4)}", "a{font-size:var(--font-serif)}",
    "a{font-size:var(--fs-body,12px)}", "a{font-size:var(--size)}", "a{font-size:env(safe-area-inset-top)}",
    "a{font:12px var(--font-serif)}", "a{font:italic 600 1.25rem var(--font-serif)}",
    "a{font:600 clamp(1rem,2vw,2rem)/1.2 var(--font-serif)}", "a{font:large var(--font-serif)}",
    "a{font:calc(1rem + 2px)/1.2 var(--font-serif)}", "a{font:12px/1.5 var(--font-mono),var(--font-sans)}",
    "a{font:bold 14px/1 var(--font-mono)}",
])
def test_the_page_css_guard_catches_these(bad):
    assert page_css_violations(bad), bad


def test_a_raw_size_is_named_with_what_to_use():
    (found,) = page_css_violations("a{font-size:12px}")
    assert found.startswith("font-size: 12px") and "var(--fs-" in found and "tokens.css" in found
    assert any("var(--fs-" in item for item in page_css_violations("a{font:12px var(--font-serif)}"))


def test_the_middle_of_a_clamp_is_the_pace_and_the_bounds_are_the_steps():
    assert page_css_violations("a{font-size:clamp(var(--fs-small),2vw,var(--fs-h2))}") == []
    assert page_css_violations("a{font-size:2vw}") and page_css_violations("a{font-size:clamp(2vw,3vw,4vw)}")
    (found,) = page_css_violations("a{font-size:clamp(var(--fs-small),2vw,40vw)}")
    assert "upper bound 40vw is not a type-scale step" in found
    (found,) = page_css_violations("a{font-size:max(var(--fs-small),5vw)}")
    assert "max() argument 5vw is not a type-scale step" in found
    (found,) = page_css_violations("a{font-size:calc(var(--fs-micro)*9)}")
    assert "calc() is not a font size" in found
    (found,) = page_css_violations("a{font-size:clamp(1rem,2vw,var(--fs-h2))}")
    assert "lower bound 1rem is not a type-scale step" in found


def test_the_sheets_that_ship_pass_the_strict_rule():
    for name in ("home.css", "katha-index.css", "policy.css"):
        assert page_css_violations((REPO / "tokens" / "pages" / name).read_text(encoding="utf-8")) == [], name
    # base.css is not a page sheet, but its h1 is the pattern the rule is built on
    assert page_css_violations("h1{font-size:clamp(var(--fs-h2),6vw,var(--fs-display))}") == []
    assert "clamp(var(--fs-h2),6vw,var(--fs-display))" in BASE


# ---- data URIs in a page sheet: only the colours a mask needs ----

def svg_uri(inner, quote='"'):
    from urllib.parse import quote as q
    return "a{mask-image:url(" + quote + "data:image/svg+xml," + q(f"<svg xmlns='http://www.w3.org/2000/svg'>{inner}</svg>") + quote + ")}"


@pytest.mark.parametrize("inner", [
    "<rect width='4' height='4' fill='#fff'/>", "<rect fill='#FFFFFF'/>", "<rect fill='#000'/>", "<rect fill='#000000'/>",
    "<rect fill='white'/>", "<rect fill='black'/>", "<rect fill='none' stroke='#000'/>",
    "<rect style='fill:#fff;stroke:none'/>",
    "<filter id='t'><feTurbulence baseFrequency='0.02'/></filter><rect fill='#fff' filter='url(#t)'/>",
    "<filter id='fad'><feTurbulence/></filter><rect fill='#fff' filter='url(#fad)'/>",   # an id that looks like hex
])
def test_a_data_uri_may_hold_a_mask_s_black_and_white(inner):
    assert page_css_violations(svg_uri(inner)) == [], inner
    assert page_css_violations(svg_uri(inner, "'")) == [], inner


@pytest.mark.parametrize("inner", [
    "<rect fill='#B06325'/>", "<rect fill='#f00'/>", "<rect fill='red'/>", "<rect fill='rgb(1,2,3)'/>",
    "<rect style='fill:#abc'/>", "<rect stroke='hsl(1,2%,3%)'/>", "<stop stop-color='#ff0000'/>",
    "<rect fill='#fff'/><circle fill='#221A0E'/>", "<rect style='fill:#fff;stroke:#123456'/>",
    "<style>rect{fill:#abc}</style><rect/>", "<rect fill='#ffffff00'/>",
])
def test_a_data_uri_may_not_hold_any_other_colour(inner):
    assert page_css_violations(svg_uri(inner)), inner


def test_a_data_uri_that_cannot_be_read_for_colours_is_refused():
    assert page_css_violations("a{background:url(data:image/png;base64,AAAA)}")
    assert page_css_violations("a{background:url('data:text/html,<p>hi</p>')}")


def test_a_base64_svg_is_decoded_and_checked():
    import base64
    clean = base64.b64encode(b"<svg xmlns='http://www.w3.org/2000/svg'><rect fill='#fff'/></svg>").decode()
    dirty = base64.b64encode(b"<svg xmlns='http://www.w3.org/2000/svg'><rect fill='#B06325'/></svg>").decode()
    assert page_css_violations("a{mask-image:url(data:image/svg+xml;base64,%s)}" % clean) == []
    assert page_css_violations("a{mask-image:url(data:image/svg+xml;base64,%s)}" % dirty)


def test_a_url_that_is_not_a_data_uri_is_left_alone():
    assert page_css_violations("a{background:url(/assets/img/a.webp)}") == []
    assert page_css_violations("a{background:url('/assets/img/a.webp')}") == []


@pytest.mark.parametrize("name", sorted(NAMED_COLOURS))
def test_every_named_colour_is_caught_in_any_case(name):
    assert page_css_violations("a{color:%s}" % name)
    assert page_css_violations("a{border:1px solid %s}" % name.upper())
    assert page_css_violations("a{background:%s}" % name.capitalize())


# ---- a page sheet may not redefine what tokens.css defines ----

def test_the_guard_knows_every_custom_property_tokens_css_defines():
    names = set(re.findall(r"(--[\w-]+)\s*:", re.search(r":root\s*\{(.*?)\}", TOKENS, re.S).group(1)))
    assert DECLARED_TOKENS == names
    assert {"--font-serif", "--font-sans", "--font-mono", "--font-deva", "--ground", "--ink", "--act",
            "--space-4", "--fs-body", "--lh-body", "--wrap", "--travel"} <= DECLARED_TOKENS


@pytest.mark.parametrize("name", sorted(DECLARED_TOKENS))
def test_every_token_name_is_refused_as_a_page_property_with_any_value(name):
    for value in ("var(--x)", "1rem", "inherit", "Georgia"):
        found = page_css_violations(f"a{{{name}:{value}}}")
        assert any(name in item and "tokens.css" in item for item in found), (name, value, found)
    assert page_css_violations("@property %s{syntax:'*';inherits:true}" % name)


def test_the_message_says_what_to_do():
    (found,) = page_css_violations("a{--font-serif:Georgia}")
    assert found.startswith("--font-serif:") and "tokens.css" in found and "redefin" in found


def test_a_name_that_differs_only_in_case_is_a_different_property():
    # custom property names are case sensitive, so --Ink is not --ink
    assert page_css_violations("a{--Ink:var(--ground)}") == []


def test_other_names_and_a_token_used_not_defined_stay_clean():
    assert page_css_violations("a{--ink-soft:var(--muted);color:var(--ink);padding:var(--space-4)}") == []
    assert page_css_violations("a{--space-4x:2rem}") == []
