import dataclasses
import datetime
from pathlib import Path
import pytest
from sitebuild.content import load_pages, ContentError

FM = """---
title: Signet by Syahi
description: An approval layer.
updated: 2026-10-06
approved: 2026-10-06
layout: page
claims: [signet-d10]
---
<p>Hello</p>
"""

def write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

def test_slugs_from_paths(tmp_path):
    write(tmp_path / "index.html", FM)
    write(tmp_path / "signet.html", FM)
    write(tmp_path / "services" / "quote.html", FM)
    assert [p.slug for p in load_pages(tmp_path)] == ["/", "/services/quote", "/signet"]

def test_front_matter_fields(tmp_path):
    write(tmp_path / "signet.html", FM)
    (page,) = load_pages(tmp_path)
    assert page.title == "Signet by Syahi"
    assert page.updated == datetime.date(2026, 10, 6)
    assert page.approved == datetime.date(2026, 10, 6)
    assert page.claims == ("signet-d10",)
    assert page.schema == ()
    assert page.audience is None
    assert page.body.strip() == "<p>Hello</p>"

@pytest.mark.parametrize("missing", ["title", "description", "updated", "approved", "layout"])
def test_missing_required_key_names_file_and_key(tmp_path, missing):
    text = "\n".join(l for l in FM.splitlines() if not l.startswith(missing + ":")) + "\n"
    write(tmp_path / "signet.html", text)
    with pytest.raises(ContentError) as e:
        load_pages(tmp_path)
    assert "signet.html" in str(e.value) and missing in str(e.value)

def test_unknown_key_is_an_error(tmp_path):
    write(tmp_path / "x.html", FM.replace("layout: page", "layout: page\ntitel: typo"))
    with pytest.raises(ContentError) as e:
        load_pages(tmp_path)
    assert "titel" in str(e.value)

@pytest.mark.parametrize("key, bad", [
    ("updated", "2026-02-30"),
    ("approved", "2026-13-01"),
    ("updated", "2026-10-32"),
    ("approved", "2026-10-06 25:00:00"),
])
def test_impossible_date_fails_as_content_error_naming_the_file(tmp_path, key, bad):
    # PyYAML builds the date inside safe_load, so this must not escape as a raw ValueError.
    write(tmp_path / "signet.html", FM.replace(f"{key}: 2026-10-06", f"{key}: {bad}"))
    with pytest.raises(ContentError) as e:
        load_pages(tmp_path)
    message = str(e.value)
    assert message.startswith(str(tmp_path / "signet.html"))
    assert "front matter" in message and "date" in message
    assert "out of range" in message or "must be in" in message


def test_no_front_matter_fails(tmp_path):
    write(tmp_path / "x.html", "<p>no front matter</p>")
    with pytest.raises(ContentError):
        load_pages(tmp_path)

def test_optional_keys_load(tmp_path):
    extra = "claims: [a-1, b-2]\nschema: [Organization, WebPage]\naudience: founders\nog_image: img/card.png"
    text = FM.replace("claims: [signet-d10]", extra)
    write(tmp_path / "signet.html", text)
    (page,) = load_pages(tmp_path)
    assert page.claims == ("a-1", "b-2")
    assert page.schema == ("Organization", "WebPage")
    assert page.audience == "founders"
    assert page.og_image == "img/card.png"

def test_og_image_defaults_to_none(tmp_path):
    write(tmp_path / "signet.html", FM)
    (page,) = load_pages(tmp_path)
    assert page.og_image is None

def test_page_is_frozen_and_keeps_source(tmp_path):
    write(tmp_path / "signet.html", FM)
    (page,) = load_pages(tmp_path)
    assert page.source == tmp_path / "signet.html"
    with pytest.raises(dataclasses.FrozenInstanceError):
        page.title = "changed"

def test_unknown_key_error_names_file(tmp_path):
    write(tmp_path / "x.html", FM.replace("layout: page", "layout: page\ntitel: typo"))
    with pytest.raises(ContentError) as e:
        load_pages(tmp_path)
    assert "x.html" in str(e.value)

@pytest.mark.parametrize("bad", [
    "updated: soon",
    "updated: 2026-10-06 09:30:00",
    "title: [a, b]",
    "claims: signet-d10",
    "claims: [1, 2]",
])
def test_wrong_value_type_is_an_error(tmp_path, bad):
    key = bad.split(":")[0]
    lines = [bad if l.startswith(key + ":") else l for l in FM.splitlines()]
    write(tmp_path / "x.html", "\n".join(lines) + "\n")
    with pytest.raises(ContentError) as e:
        load_pages(tmp_path)
    assert "x.html" in str(e.value) and key in str(e.value)

def test_unclosed_front_matter_fails(tmp_path):
    write(tmp_path / "x.html", "---\ntitle: T\n<p>never closed</p>\n")
    with pytest.raises(ContentError) as e:
        load_pages(tmp_path)
    assert "x.html" in str(e.value)

def test_front_matter_that_is_not_a_mapping_fails(tmp_path):
    write(tmp_path / "x.html", "---\n- a\n- b\n---\n<p>x</p>\n")
    with pytest.raises(ContentError):
        load_pages(tmp_path)

def test_missing_content_dir_fails(tmp_path):
    with pytest.raises(ContentError) as e:
        load_pages(tmp_path / "content")
    assert "content" in str(e.value)

def test_non_html_files_are_ignored(tmp_path):
    write(tmp_path / "signet.html", FM)
    write(tmp_path / "notes.txt", "not a page")
    assert [p.slug for p in load_pages(tmp_path)] == ["/signet"]


# ---- draft pages: new or changed copy she has not approved yet ----

def test_draft_defaults_to_false(tmp_path):
    write(tmp_path / "signet.html", FM)
    (page,) = load_pages(tmp_path)
    assert page.draft is False


def test_draft_true_loads_and_approved_may_be_left_out(tmp_path):
    text = "\n".join(l for l in FM.splitlines() if not l.startswith("approved:")).replace("layout: page", "layout: page\ndraft: true")
    write(tmp_path / "signet.html", text + "\n")
    (page,) = load_pages(tmp_path)
    assert page.draft is True and page.approved is None


def test_a_draft_may_still_carry_a_date(tmp_path):
    write(tmp_path / "signet.html", FM.replace("layout: page", "layout: page\ndraft: true"))
    (page,) = load_pages(tmp_path)
    assert page.draft is True and page.approved == datetime.date(2026, 10, 6)


@pytest.mark.parametrize("draft", ["false", "False", "no"])
def test_a_page_that_is_not_a_draft_still_needs_approved(tmp_path, draft):
    text = "\n".join(l for l in FM.splitlines() if not l.startswith("approved:")).replace("layout: page", f"layout: page\ndraft: {draft}")
    write(tmp_path / "signet.html", text + "\n")
    with pytest.raises(ContentError) as e:
        load_pages(tmp_path)
    assert "signet.html" in str(e.value) and "approved" in str(e.value)


def test_a_page_with_no_draft_key_and_no_approved_fails_naming_both(tmp_path):
    text = "\n".join(l for l in FM.splitlines() if not l.startswith("approved:")) + "\n"
    write(tmp_path / "signet.html", text)
    with pytest.raises(ContentError) as e:
        load_pages(tmp_path)
    assert "approved" in str(e.value) and "draft" in str(e.value)


@pytest.mark.parametrize("bad", ['"true"', "1", "0", "[true]", "maybe", "~", "''"])
def test_draft_must_be_a_real_boolean(tmp_path, bad):
    write(tmp_path / "x.html", FM.replace("layout: page", f"layout: page\ndraft: {bad}"))
    with pytest.raises(ContentError) as e:
        load_pages(tmp_path)
    assert "x.html" in str(e.value) and "draft" in str(e.value)


def test_an_impossible_approved_date_on_a_draft_is_still_an_error(tmp_path):
    write(tmp_path / "x.html", FM.replace("approved: 2026-10-06", "approved: 2026-13-01").replace("layout: page", "layout: page\ndraft: true"))
    with pytest.raises(ContentError) as e:
        load_pages(tmp_path)
    assert "x.html" in str(e.value) and "date" in str(e.value)


# ---- link-preview copy: og_title, og_description, og_image_alt ----
# Optional. A page whose shared-link preview says something other than its title and description (today's
# Signet page, the home page and the Katha pitch do) carries the preview's own words here.

PREVIEW = "og_title: A shorter title\nog_description: A shorter line for a shared link.\nog_image_alt: A seal above three words."


def test_the_preview_copy_defaults_to_none(tmp_path):
    write(tmp_path / "signet.html", FM)
    (page,) = load_pages(tmp_path)
    assert (page.og_title, page.og_description, page.og_image_alt) == (None, None, None)


def test_the_preview_copy_loads(tmp_path):
    write(tmp_path / "signet.html", FM.replace("layout: page", "layout: page\n" + PREVIEW))
    (page,) = load_pages(tmp_path)
    assert page.og_title == "A shorter title"
    assert page.og_description == "A shorter line for a shared link."
    assert page.og_image_alt == "A seal above three words."


@pytest.mark.parametrize("key", ["og_title", "og_description", "og_image_alt"])
@pytest.mark.parametrize("bad", ["[a, b]", "''", "'   '", "12"])
def test_the_preview_copy_must_be_a_non_empty_string(tmp_path, key, bad):
    write(tmp_path / "x.html", FM.replace("layout: page", f"layout: page\n{key}: {bad}"))
    with pytest.raises(ContentError) as e:
        load_pages(tmp_path)
    assert "x.html" in str(e.value) and key in str(e.value)


@pytest.mark.parametrize("key", ["og_title", "og_description", "og_image_alt"])
def test_the_preview_copy_may_not_hold_an_em_dash(tmp_path, key):
    write(tmp_path / "x.html", FM.replace("layout: page", f"layout: page\n{key}: \"a {chr(0x2014)} b\""))
    with pytest.raises(ContentError) as e:
        load_pages(tmp_path)
    message = str(e.value)
    assert "x.html" in message and key in message and "em dash" in message and chr(0x2014) not in message


def test_preload_fonts_names_published_faces(tmp_path):
    write(tmp_path / "a.html", FM.replace("layout: page", "layout: page\npreload_fonts: [fraunces-italic]"))
    write(tmp_path / "b.html", FM)
    a, b = load_pages(tmp_path)
    assert a.preload_fonts == ("fraunces-italic",) and b.preload_fonts == ()


def test_preload_fonts_naming_no_face_is_an_error_naming_file_and_key(tmp_path):
    write(tmp_path / "a.html", FM.replace("layout: page", "layout: page\npreload_fonts: [comic-sans]"))
    with pytest.raises(ContentError, match=r"a\.html.*preload_fonts.*comic-sans"):
        load_pages(tmp_path)
