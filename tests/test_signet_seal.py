# tests/test_signet_seal.py
#
# The Signet seal is one partial (templates/partials/signet-seal.html). Its <mask> has an id, and an id is
# unique in a page, so a page that shows the seal twice needs a different id for each. A seal takes an
# optional per-instance name: {% with seal_id = "cta" %}{% include "partials/signet-seal.html" %}{% endwith %}.
# With none it keeps the id the home page's one seal has always had. Two seals with the same id would be
# invalid HTML, and each mask reference would pick the first mask on the page, so the second seal is
# carved by the wrong shape the day the two ever differ.
#
# A seal beside a heading is decoration: `seal_decorative` hides it from assistive technology, as the Signet
# page's own seal always was, so the port adds no sentence a screen reader reads that the old page did not.
import re
from pathlib import Path

import pytest

from checks import htmlcheck
from sitebuild.claims import ClaimRegister
from sitebuild.pipeline import build
from sitebuild.render import make_env
from sitebuild.site import load_site

REPO = Path(__file__).resolve().parents[1]
INCLUDE = '{% include "partials/signet-seal.html" %}'
LABEL = "The Signet brand seal: an S-curve carved through an ink core, sealed with a copper wax dot"


def with_seal(**names):
    """An include inside a `with` block that binds the given names, the way a page names its seal."""
    bound = ", ".join(f"{name} = {value}" for name, value in names.items())
    return "{% with " + bound + " %}" + INCLUDE + "{% endwith %}"


@pytest.fixture(scope="module")
def env():
    return make_env(REPO, load_site(REPO / "site.yaml"), ClaimRegister.load(REPO / "data" / "claims.yaml"))


def render(env, body):
    return env.from_string(body).render()


def mask_ids(html):
    return re.findall(r'<mask id="([^"]+)"', html)


def mask_references(html):
    return re.findall(r'mask="url\(#([^)]+)\)"', html)


# ---- one seal, as before ----

def test_a_seal_with_no_name_keeps_the_id_the_home_page_has_always_had(env):
    html = render(env, INCLUDE)
    assert mask_ids(html) == ["signet-seal-carve"]
    assert mask_references(html) == ["signet-seal-carve"]


def test_a_seal_with_no_name_is_a_labelled_image(env):
    html = render(env, INCLUDE)
    assert 'role="img"' in html and f'aria-label="{LABEL}"' in html and "aria-hidden" not in html


# ---- a named seal ----

def test_a_named_seal_carries_its_name_in_its_mask_id_and_its_reference(env):
    html = render(env, with_seal(seal_id='"cta"'))
    assert mask_ids(html) == ["signet-seal-carve-cta"]
    assert mask_references(html) == ["signet-seal-carve-cta"]


def test_the_name_reaches_the_partial_through_a_with_block_in_a_page_body(env):
    # `include` sees the block's names, and a name outside the block does not leak out of it
    html = render(env, with_seal(seal_id='"one"') + INCLUDE)
    assert mask_ids(html) == ["signet-seal-carve-one", "signet-seal-carve"]


# ---- two seals on one page ----

def test_a_page_with_two_seals_has_two_distinct_mask_ids_each_referenced_by_its_own_seal(env):
    html = render(env, with_seal(seal_id='"first"') + "<p>between</p>" + with_seal(seal_id='"second"'))
    ids = mask_ids(html)
    assert len(ids) == 2 and len(set(ids)) == 2
    assert mask_references(html) == ids                       # each seal's core is cut by its own mask, in order


def test_a_default_seal_and_a_named_seal_on_one_page_do_not_collide(env):
    html = render(env, INCLUDE + with_seal(seal_id='"cta"'))
    ids = mask_ids(html)
    assert len(ids) == 2 and len(set(ids)) == 2


def test_three_named_seals_have_three_ids(env):
    html = render(env, "".join(with_seal(seal_id=f'"s{n}"') for n in range(3)))
    assert len(set(mask_ids(html))) == 3 and mask_references(html) == mask_ids(html)


def test_the_built_page_with_two_seals_has_unique_ids_and_passes_the_html_check(mini_root, tmp_path):
    page = mini_root / "content" / "two-seals.html"
    page.write_text(
        "---\ntitle: Two seals\ndescription: A made-up page with two seals.\nupdated: 2026-10-06\napproved: 2026-10-06\nlayout: page\n---\n"
        "<h1>Two seals</h1>\n" + INCLUDE + "\n" + with_seal(seal_id='"cta"') + "\n", encoding="utf-8")
    result = build(mini_root, tmp_path / "dist")
    assert [problem for problem in result.problems if "two-seals" in problem] == [], result.problems
    html = (tmp_path / "dist" / "syahi.sh" / "two-seals.html").read_text(encoding="utf-8")
    ids = re.findall(r'\bid="([^"]+)"', html)
    assert len(ids) == len(set(ids)), ids
    assert len(mask_ids(html)) == 2
    assert htmlcheck.check(html) == []


# ---- a decorative seal ----

def test_a_decorative_seal_is_hidden_from_assistive_technology_and_has_no_label(env):
    html = render(env, with_seal(seal_id='"cta"', seal_decorative="true"))
    svg = html[html.index("<svg"): html.index(">", html.index("<svg")) + 1]
    assert 'aria-hidden="true"' in svg and "role=" not in svg and "aria-label" not in html
    assert mask_ids(html) == ["signet-seal-carve-cta"]


def test_a_seal_that_is_not_marked_decorative_stays_labelled_even_when_named(env):
    html = render(env, with_seal(seal_id='"cta"'))
    assert 'role="img"' in html and LABEL in html and "aria-hidden" not in html


# ---- the partial itself ----

def test_the_partial_says_how_to_name_a_seal():
    text = (REPO / "templates" / "partials" / "signet-seal.html").read_text(encoding="utf-8")
    assert "seal_id" in text and "seal_decorative" in text
    assert "One seal per page" not in text                    # the old limit is gone with the id
    assert chr(0x2014) not in text
