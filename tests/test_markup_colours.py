# tests/test_markup_colours.py
#
# No raw colour in page markup. Colours come from tokens.css, and a page asks for one by class, so the
# stylesheet decides. The one structural exception is a <mask>: inside a mask the colour is luminance
# (white keeps, black cuts), not a design colour, so #fff and #000 may stay there. The exception is the
# element, not a file: a mask in any content file or template is allowed its black and white and nothing else.
# The same scan covers <style> blocks and style attributes, which follow the page-sheet rules.
import re
from pathlib import Path

import pytest

from css_guard import markup_colour_violations

REPO = Path(__file__).resolve().parents[1]
MARKUP = sorted([*(REPO / "content").rglob("*.html"), *(REPO / "katha" / "content").rglob("*.html"),
                 *(REPO / "templates").rglob("*.html")])


def test_there_is_markup_to_guard_and_the_seal_partial_is_part_of_it():
    names = {path.relative_to(REPO).as_posix() for path in MARKUP}
    assert {"content/index.html", "katha/content/index.html", "templates/base.html",
            "templates/partials/signet-seal.html"} <= names


@pytest.mark.parametrize("path", MARKUP, ids=lambda path: path.relative_to(REPO).as_posix())
def test_no_raw_colour_in_the_markup(path):
    assert markup_colour_violations(path.read_text(encoding="utf-8")) == [], path


def test_the_seal_is_drawn_by_classes_and_keeps_only_its_masks_black_and_white():
    seal = re.sub(r"\{#.*?#\}", "", (REPO / "templates" / "partials" / "signet-seal.html").read_text(encoding="utf-8"), flags=re.S)
    assert seal.count("<mask") == 1 and '<svg class="signet-mark"' in seal
    for cls in ("seal-ring", "seal-core", "seal-dot"):
        assert f'class="{cls}"' in seal
    outside = seal.split("<mask", 1)[0] + seal.split("</mask>", 1)[1]
    assert "#" not in outside.replace("url(#", "")        # no hex anywhere outside the mask but the mask reference
    assert "style=" not in outside and "fill=" not in outside


# ---- the scan's own tests ----

@pytest.mark.parametrize("fine", [
    "<p>Plain text, #fff in the copy and rgb( too.</p>", '<a href="/a#abc">x</a>', '<svg><rect fill="none"/></svg>',
    '<svg><rect class="seal-ring" stroke-width="24"></rect></svg>', '<svg><circle fill="currentColor"/></svg>',
    '<svg><rect fill="url(#fade)"/></svg>',                                     # an id that looks like hex
    '<p style="margin:1rem;color:var(--ink)">x</p>', '<p style="color:inherit;background:transparent">x</p>',
    '<meta name="theme-color" content="#F0E8D2">',                                # not a drawing attribute
    # a mask: black and white, in style or in attributes, at any depth
    '<svg><mask id="m"><rect style="fill:#fff"></rect><g><path style="fill:none;stroke:#000;stroke-width:26"></path></g></mask></svg>',
    '<svg><mask id="m"><rect fill="#FFFFFF"></rect><circle fill="#000000"></circle></mask></svg>',
    '<svg><mask id="m"><rect fill="white"/><rect fill="black"/><rect fill="none"/></mask></svg>',
    "<style>.a{color:var(--ink);font-size:var(--fs-body)}</style>",
    "{# a template comment with #fff in it #}<p>{{ claim('x') }}</p>",
])
def test_the_scan_lets_these_through(fine):
    assert markup_colour_violations(fine) == [], fine


@pytest.mark.parametrize("bad", [
    '<svg><rect style="fill:#221A0E"/></svg>', '<svg><rect fill="#B06325"/></svg>', '<svg><rect stroke="#abc"/></svg>',
    '<svg><stop stop-color="#ff0000"/></svg>', '<svg><feFlood flood-color="#fff"/></svg>', '<svg><rect color="#fff"/></svg>',
    '<svg><rect fill="rgb(1,2,3)"/></svg>', '<svg><rect fill="rgba(1,2,3,.5)"/></svg>', '<svg><rect fill="hsl(1,2%,3%)"/></svg>',
    '<svg><rect fill="hsla(1,2%,3%,.5)"/></svg>', '<svg><rect fill="red"/></svg>', '<svg><rect fill="#FFF"/></svg>',
    '<svg><rect style="fill:none;stroke:#000"/></svg>', '<p style="color:#fff">x</p>', '<p style="background:rgb(1,2,3)">x</p>',
    '<p style="font-family:Georgia">x</p>', '<p style="font-size:12px">x</p>', '<p STYLE="COLOR:#FFF">x</p>',
    "<style>.a{color:#abc}</style>", "<style>.a{font-family:Georgia}</style>", "<style>.a{font-size:12px}</style>",
    "<style>.a{background:url(\"data:image/svg+xml,%3Csvg%3E%3Crect%20fill='%23B06325'/%3E%3C/svg%3E\")}</style>",
    # a mask holds black and white only, not any colour
    '<svg><mask id="m"><rect fill="#B06325"/></mask></svg>', '<svg><mask id="m"><rect style="fill:#f00"/></mask></svg>',
    '<svg><mask id="m"><rect fill="rgb(255,0,0)"/></mask></svg>',
    # the exception ends with the element
    '<svg><mask id="m"><rect fill="#fff"/></mask><rect fill="#fff"/></svg>',
    '<svg><mask id="m"><rect fill="#fff"/></mask><circle style="fill:#000"/></svg>',
    '<svg><mask id="a"><mask id="b"><rect fill="#fff"/></mask><rect fill="#fff"/></mask><rect fill="#000"/></svg>',
])
def test_the_scan_catches_these(bad):
    assert markup_colour_violations(bad), bad


def test_a_finding_names_the_element_and_the_value():
    (found,) = markup_colour_violations('<svg><circle cx="1" fill="#B06325"></circle></svg>')
    assert "<circle>" in found and "fill" in found and "#B06325" in found


def test_the_exception_is_the_mask_element_not_the_file_it_is_in():
    # the same black and white outside a mask is refused wherever it sits
    assert markup_colour_violations('<svg><mask><rect fill="#fff"/></mask></svg>') == []
    assert markup_colour_violations('<svg><defs><rect fill="#fff"/></defs></svg>')
