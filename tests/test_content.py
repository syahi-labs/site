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
