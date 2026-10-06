import dataclasses
import datetime
from pathlib import Path

import pytest

from sitebuild.claims import Claim, ClaimError, ClaimRegister

GOOD = """
- id: price-example
  text: "Founding users start at ₹1,499 a month, after a demo."
  short: "₹1,499 a month"
  source: "Ruling D10, 2026-10-06"
  updated: 2026-10-06
  status: live
- id: old-line
  text: "An old line."
  source: "Retired 2026-10-06"
  updated: 2026-10-06
  status: retired
"""

LIVE_NO_SHORT = """
- id: plain-line
  text: "A plain line."
  source: "Example note"
  updated: 2026-10-06
  status: live
"""

ROOT = Path(__file__).resolve().parent.parent
EM_DASH = chr(0x2014)


def reg(tmp_path, text):
    p = tmp_path / "claims.yaml"
    p.write_text(text, encoding="utf-8")
    return ClaimRegister.load(p)


def load_error(tmp_path, text):
    with pytest.raises(ClaimError) as e:
        reg(tmp_path, text)
    return str(e.value)


def test_full_and_short_forms(tmp_path):
    r = reg(tmp_path, GOOD)
    assert r.text("price-example") == "Founding users start at ₹1,499 a month, after a demo."
    assert r.text("price-example", form="short") == "₹1,499 a month"


def test_unknown_id_fails(tmp_path):
    with pytest.raises(ClaimError) as e:
        reg(tmp_path, GOOD).text("nope")
    assert "nope" in str(e.value)


def test_retired_claim_cannot_be_used(tmp_path):
    with pytest.raises(ClaimError) as e:
        reg(tmp_path, GOOD).text("old-line")
    assert "retired" in str(e.value)


def test_missing_source_fails_at_load(tmp_path):
    with pytest.raises(ClaimError) as e:
        reg(tmp_path, GOOD.replace('  source: "Ruling D10, 2026-10-06"\n', "", 1))
    assert "price-example" in str(e.value)


def test_duplicate_id_fails(tmp_path):
    with pytest.raises(ClaimError):
        reg(tmp_path, GOOD + GOOD)


def test_em_dash_in_text_fails(tmp_path):
    with pytest.raises(ClaimError):
        reg(tmp_path, GOOD.replace("after a demo", "after a demo " + EM_DASH + " soon", 1))


def test_short_form_missing_fails(tmp_path):
    with pytest.raises(ClaimError):
        reg(tmp_path, GOOD).text("old-line", form="short")


def test_used_is_recorded(tmp_path):
    r = reg(tmp_path, GOOD)
    r.text("price-example")
    assert r.used == {"price-example"}


# --- beyond the brief's tests ---

def test_short_form_missing_on_a_live_claim_fails_and_names_the_id(tmp_path):
    r = reg(tmp_path, LIVE_NO_SHORT)
    with pytest.raises(ClaimError) as e:
        r.text("plain-line", form="short")
    assert "plain-line" in str(e.value) and "short" in str(e.value)
    assert r.text("plain-line") == "A plain line."


def test_unknown_form_fails_and_names_the_id(tmp_path):
    with pytest.raises(ClaimError) as e:
        reg(tmp_path, GOOD).text("price-example", form="medium")
    assert "price-example" in str(e.value) and "medium" in str(e.value)


def test_used_records_only_successful_renders(tmp_path):
    r = reg(tmp_path, GOOD + LIVE_NO_SHORT)
    for call in (
        lambda: r.text("nope"),
        lambda: r.text("old-line"),
        lambda: r.text("plain-line", form="short"),
        lambda: r.text("price-example", form="medium"),
    ):
        with pytest.raises(ClaimError):
            call()
    assert r.used == set()
    r.text("plain-line")
    r.text("price-example", form="short")
    assert r.used == {"plain-line", "price-example"}


def test_used_is_not_filled_by_get(tmp_path):
    r = reg(tmp_path, GOOD)
    r.get("price-example")
    assert r.used == set()


def test_registers_do_not_share_used(tmp_path):
    a = reg(tmp_path, GOOD)
    b = reg(tmp_path, GOOD)
    a.text("price-example")
    assert b.used == set()


def test_get_returns_a_frozen_claim(tmp_path):
    claim = reg(tmp_path, GOOD).get("price-example")
    assert isinstance(claim, Claim)
    assert claim.id == "price-example"
    assert claim.short == "₹1,499 a month"
    assert claim.source == "Ruling D10, 2026-10-06"
    assert claim.updated == datetime.date(2026, 10, 6)
    assert claim.status == "live"
    with pytest.raises(dataclasses.FrozenInstanceError):
        claim.text = "changed"


def test_get_without_short_gives_none(tmp_path):
    assert reg(tmp_path, LIVE_NO_SHORT).get("plain-line").short is None


def test_get_unknown_and_retired_fail(tmp_path):
    r = reg(tmp_path, GOOD)
    with pytest.raises(ClaimError) as e:
        r.get("nope")
    assert "nope" in str(e.value)
    with pytest.raises(ClaimError) as e:
        r.get("old-line")
    assert "old-line" in str(e.value) and "retired" in str(e.value)


def test_ids_lists_live_and_retired(tmp_path):
    ids = reg(tmp_path, GOOD).ids()
    assert ids == frozenset({"price-example", "old-line"})
    assert isinstance(ids, frozenset)


@pytest.mark.parametrize("text", ["", "[]\n", "# nothing yet\n"])
def test_empty_register_loads(tmp_path, text):
    r = reg(tmp_path, text)
    assert r.ids() == frozenset()
    assert r.used == set()
    with pytest.raises(ClaimError):
        r.text("anything")


def test_the_shipped_register_loads():
    r = ClaimRegister.load(ROOT / "data" / "claims.yaml")
    assert isinstance(r.ids(), frozenset)


@pytest.mark.parametrize("text", ["id: a-claim\n", "just a string\n", "42\n", "true\n"])
def test_top_level_must_be_a_list(tmp_path, text):
    message = load_error(tmp_path, text)
    assert "claims.yaml" in message and "list" in message


def test_entry_must_be_a_mapping(tmp_path):
    message = load_error(tmp_path, GOOD + "- just a string\n")
    assert "claims.yaml" in message and "#3" in message


def test_invalid_yaml_is_a_claim_error(tmp_path):
    message = load_error(tmp_path, "- id: [unclosed\n")
    assert "claims.yaml" in message


def test_missing_file_is_a_claim_error(tmp_path):
    with pytest.raises(ClaimError) as e:
        ClaimRegister.load(tmp_path / "absent.yaml")
    assert "absent.yaml" in str(e.value)


def test_load_errors_start_with_the_file_path(tmp_path):
    message = load_error(tmp_path, GOOD.replace("status: live", "status: draft", 1))
    assert message.startswith(str(tmp_path / "claims.yaml"))


@pytest.mark.parametrize("missing", ["id", "text", "source", "updated", "status"])
def test_each_required_key_is_required(tmp_path, missing):
    text = "\n".join(
        line for line in LIVE_NO_SHORT.splitlines() if not line.lstrip("- ").startswith(missing + ":")
    ) + "\n"
    if missing == "id":
        text = text.replace("  text:", "- text:", 1)
    message = load_error(tmp_path, text)
    assert missing in message
    if missing != "id":
        assert "plain-line" in message


def test_unknown_key_names_the_claim_and_the_key(tmp_path):
    message = load_error(tmp_path, GOOD.replace("status: live", "status: live\n  tags: [a]", 1))
    assert "price-example" in message and "tags" in message


@pytest.mark.parametrize("bad", ["A", "a", "-ab", "ab_c", "ab c", "Ab", "a" * 62, "é-ab", "ab\n"])
def test_bad_ids_fail(tmp_path, bad):
    quoted = '"' + bad.replace("\n", "\\n") + '"'
    text = LIVE_NO_SHORT.replace("plain-line", quoted)
    message = load_error(tmp_path, text)
    assert "id" in message


@pytest.mark.parametrize("good", ["ab", "a1", "1a", "a-b", "a--b", "b-", "a" * 61])
def test_good_ids_load(tmp_path, good):
    r = reg(tmp_path, LIVE_NO_SHORT.replace("plain-line", good))
    assert r.ids() == frozenset({good})


def test_id_must_be_a_string(tmp_path):
    message = load_error(tmp_path, LIVE_NO_SHORT.replace("id: plain-line", "id: 12345"))
    assert "id" in message


def test_duplicate_id_names_the_id(tmp_path):
    assert "price-example" in load_error(tmp_path, GOOD + GOOD)


def test_duplicate_id_fails_even_when_one_is_retired(tmp_path):
    dup = GOOD.replace("old-line", "price-example")
    assert "price-example" in load_error(tmp_path, dup)


@pytest.mark.parametrize("bad", ["draft", "LIVE", "Retired", "", "yes", "[live]", "true", "1"])
def test_status_must_be_live_or_retired(tmp_path, bad):
    message = load_error(tmp_path, GOOD.replace("status: live", f"status: {bad}", 1))
    assert "price-example" in message and "status" in message


def test_updated_must_be_a_real_date(tmp_path):
    for bad in ['"2026-10-06"', "2026-10-06 10:30:00", "20261006", "soon", "null"]:
        message = load_error(tmp_path, GOOD.replace("updated: 2026-10-06", f"updated: {bad}", 1))
        assert "price-example" in message and "updated" in message, bad


@pytest.mark.parametrize("key", ["text", "short", "source"])
@pytest.mark.parametrize("bad", ["2026-08-13", "1499", "true", "[a, b]", "{a: b}"])
def test_string_fields_reject_other_types(tmp_path, key, bad):
    base = GOOD
    marker = {
        "text": 'text: "Founding users start at ₹1,499 a month, after a demo."',
        "short": 'short: "₹1,499 a month"',
        "source": 'source: "Ruling D10, 2026-10-06"',
    }[key]
    message = load_error(tmp_path, base.replace(marker, f"{key}: {bad}", 1))
    assert "price-example" in message and key in message


@pytest.mark.parametrize("key", ["text", "source"])
@pytest.mark.parametrize("blank", ['""', '"   "'])
def test_required_strings_cannot_be_blank(tmp_path, key, blank):
    marker = {
        "text": 'text: "Founding users start at ₹1,499 a month, after a demo."',
        "source": 'source: "Ruling D10, 2026-10-06"',
    }[key]
    message = load_error(tmp_path, GOOD.replace(marker, f"{key}: {blank}", 1))
    assert "price-example" in message and key in message


def test_blank_short_is_an_error(tmp_path):
    message = load_error(tmp_path, GOOD.replace('short: "₹1,499 a month"', 'short: ""', 1))
    assert "price-example" in message and "short" in message


def test_em_dash_in_short_fails_and_names_the_id(tmp_path):
    message = load_error(tmp_path, GOOD.replace("a month\"\n  source", "a month " + EM_DASH + "\"\n  source", 1))
    assert "price-example" in message and "short" in message


def test_em_dash_in_text_names_the_id_and_field(tmp_path):
    message = load_error(tmp_path, GOOD.replace("after a demo", "after a demo " + EM_DASH + " soon", 1))
    assert "price-example" in message and "em dash" in message and "text" in message


def test_sources_of_this_task_have_no_em_dash():
    for path in (ROOT / "sitebuild" / "claims.py", ROOT / "tests" / "test_claims.py", ROOT / "data" / "claims.yaml"):
        assert EM_DASH not in path.read_text(encoding="utf-8"), path
