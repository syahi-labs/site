# tests/test_page_css.py
#
# The one mechanism for page-scoped CSS: a page names a stylesheet in its front matter (`css: name`),
# the build publishes tokens/pages/<name>.css to <host>/assets/pages/<name>.css, and the base template
# links it after tokens.css and base.css. Task 9 reuses it for every ported page.
import re
from pathlib import Path

import pytest

from sitebuild.content import ContentError, load_pages
from asset_urls import hashed_file, hashed_url
from sitebuild.pipeline import build

def link(host: Path) -> str:
    return f'<link rel="stylesheet" href="{hashed_url(host, "pages/demo.css")}">'


PAGE_CSS = ".demo{margin-top:var(--space-4)}\n"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def add_css(root: Path, name: str = "demo", text: str = PAGE_CSS) -> None:
    write(root / "tokens" / "pages" / f"{name}.css", text)


def use_css(page: Path, name: str = "demo") -> None:
    text = page.read_text(encoding="utf-8")
    assert "\nlayout: page\n" in text
    page.write_text(text.replace("\nlayout: page\n", f"\nlayout: page\ncss: {name}\n", 1), encoding="utf-8")


# ---- front matter ----

FM = """---
title: A page
description: A made-up page.
updated: 2026-10-06
approved: 2026-10-06
layout: page
{extra}---
<p>Hello</p>
"""


def test_css_is_optional_and_defaults_to_none(tmp_path):
    write(tmp_path / "a.html", FM.format(extra=""))
    (page,) = load_pages(tmp_path)
    assert page.css is None


def test_css_names_a_stylesheet(tmp_path):
    write(tmp_path / "a.html", FM.format(extra="css: katha-index\n"))
    (page,) = load_pages(tmp_path)
    assert page.css == "katha-index"


@pytest.mark.parametrize("bad", ["../secret", "a/b", "Demo", "demo.css", "-demo", "de mo", "''"])
def test_a_css_name_that_is_not_a_plain_name_is_refused(tmp_path, bad):
    write(tmp_path / "a.html", FM.format(extra=f"css: {bad}\n"))
    with pytest.raises(ContentError) as err:
        load_pages(tmp_path)
    assert "a.html" in str(err.value) and "css" in str(err.value)


def test_css_must_be_a_string(tmp_path):
    write(tmp_path / "a.html", FM.format(extra="css: [demo]\n"))
    with pytest.raises(ContentError) as err:
        load_pages(tmp_path)
    assert "css" in str(err.value)


# ---- the build ----

def test_a_page_with_css_gets_the_file_published_and_linked(mini_root, tmp_path):
    add_css(mini_root); use_css(mini_root / "content" / "signet.html")
    result = build(mini_root, tmp_path / "dist")
    assert result.problems == []
    host = tmp_path / "dist" / "syahi.sh"
    assert hashed_file(host, "pages/demo.css").read_text(encoding="utf-8") == PAGE_CSS
    html = (host / "signet.html").read_text(encoding="utf-8")
    assert link(host) in html
    # after the shared sheets, so a page can refine the base, and inside <head>
    assert html.index("/assets/tokens.") < html.index("/assets/base.") < html.index(link(host)) < html.index("</head>")


def test_a_page_without_css_links_none(mini_root, tmp_path):
    add_css(mini_root); use_css(mini_root / "content" / "signet.html")
    assert build(mini_root, tmp_path / "dist").problems == []
    home = (tmp_path / "dist" / "syahi.sh" / "index.html").read_text(encoding="utf-8")
    assert "/assets/pages/" not in home


def test_the_other_host_does_not_get_a_page_css_it_does_not_use(mini_root, tmp_path):
    add_css(mini_root); use_css(mini_root / "content" / "signet.html")
    assert build(mini_root, tmp_path / "dist").problems == []
    assert not (tmp_path / "dist" / "katha.syahi.sh" / "assets" / "pages").exists()


def test_the_katha_host_uses_it_too(mini_root, tmp_path):
    add_css(mini_root); use_css(mini_root / "katha" / "content" / "index.html")
    result = build(mini_root, tmp_path / "dist")
    assert result.problems == []
    host = tmp_path / "dist" / "katha.syahi.sh"
    assert hashed_file(host, "pages/demo.css").is_file()
    assert link(host) in (host / "index.html").read_text(encoding="utf-8")
    assert not (tmp_path / "dist" / "syahi.sh" / "assets" / "pages").exists()


def test_two_pages_can_share_one_stylesheet(mini_root, tmp_path):
    add_css(mini_root)
    use_css(mini_root / "content" / "signet.html"); use_css(mini_root / "content" / "index.html")
    result = build(mini_root, tmp_path / "dist")
    assert result.problems == []
    for page in ("index.html", "signet.html"):
        assert link(tmp_path / "dist" / "syahi.sh") in (tmp_path / "dist" / "syahi.sh" / page).read_text(encoding="utf-8")


def test_a_css_name_with_no_stylesheet_is_a_problem_naming_page_and_file(mini_root, tmp_path):
    use_css(mini_root / "content" / "signet.html", "ghost")
    result = build(mini_root, tmp_path / "dist")
    mentioned = [p for p in result.problems if "ghost" in p and "signet.html" in p and "tokens/pages/ghost.css" in p]
    assert mentioned, result.problems


def test_the_published_css_is_byte_identical_to_the_source(mini_root, tmp_path):
    add_css(mini_root, text=".a{padding:var(--space-2)}\r\n.b{color:var(--ink)}\n")
    use_css(mini_root / "content" / "signet.html")
    assert build(mini_root, tmp_path / "dist").problems == []
    published = hashed_file(tmp_path / "dist" / "syahi.sh", "pages/demo.css").read_bytes()
    assert published == (mini_root / "tokens" / "pages" / "demo.css").read_bytes()


def test_the_base_template_has_one_page_stylesheet_hook():
    base = (Path(__file__).resolve().parents[1] / "templates" / "base.html").read_text(encoding="utf-8")
    assert len(re.findall(r"/assets/pages/", base)) == 1


# ---- no text fades through partial opacity ----

# Text caught at partial opacity fails colour contrast for as long as the fade runs, and the gate's axe pass
# lands inside the fade on some runs. An animation that changes opacity may only draw something with no text.
FADES_WITH_NO_TEXT = {"dropfall"}      # the ink drop on the home wordmark: an svg path


def keyframe_fades(css: str) -> dict[str, set[str]]:
    """Each @keyframes name that changes opacity between its start and its end, with the values it passes through.

    A missing `from` or `to` frame is the element's own opacity, 1 for everything here, so a keyframe with only
    `from{opacity:0}` is a fade too.
    """
    import re
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    found = {}
    for match in re.finditer(r"@keyframes\s+([\w-]+)\s*\{", css):
        depth, end = 1, match.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(css[end], 0)
            end += 1
        frames = re.findall(r"([^{}]+)\{([^{}]*)\}", css[match.end():end - 1])
        values = {"start": "1", "end": "1"}
        for selectors, body in frames:
            opacity = re.search(r"opacity\s*:\s*([\d.]+)", body)
            for selector in (x.strip() for x in selectors.split(",")):
                point = "start" if selector in ("from", "0%") else "end" if selector in ("to", "100%") else None
                if point and opacity:
                    values[point] = opacity.group(1)
                elif opacity:
                    values[selector] = opacity.group(1)
        if len(set(values.values())) > 1:
            found[match.group(1)] = set(values.values())
    return found


def test_a_from_only_fade_is_a_fade():
    assert keyframe_fades("@keyframes a{from{opacity:0}}") == {"a": {"0", "1"}}
    assert keyframe_fades("@keyframes a{to{opacity:0}}") == {"a": {"0", "1"}}
    assert keyframe_fades("@keyframes a{from{opacity:0}to{opacity:1}}") == {"a": {"0", "1"}}
    assert keyframe_fades("@keyframes a{0%{opacity:1}50%{opacity:.4}100%{opacity:1}}") == {"a": {"1", ".4"}}
    assert keyframe_fades("@keyframes a{from,to{opacity:0;visibility:hidden}}") == {}
    assert keyframe_fades("@keyframes a{from{transform:none}to{transform:scale(2)}}") == {}


def test_only_a_textless_animation_changes_opacity_between_its_frames():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "tokens"
    for sheet in sorted(root.rglob("*.css")):
        for name, values in keyframe_fades(sheet.read_text(encoding="utf-8")).items():
            assert name in FADES_WITH_NO_TEXT, f"{sheet.name}: @keyframes {name} fades {sorted(values)}"
