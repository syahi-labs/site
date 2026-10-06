import dataclasses
from pathlib import Path

import pytest

from sitebuild.site import Link, SiteConfig, SiteError, load_site

REPO = Path(__file__).resolve().parents[1]
EM_DASH = chr(0x2014)

GOOD = """
base_url: https://example.test
name: Example
header: syahi
tabs:
  - {label: One, href: /one}
  - {label: Away, href: "https://away.example/"}
cta: {label: Go, href: "https://go.example/x"}
profiles:
  - {label: Elsewhere, href: "https://elsewhere.example/me"}
policies:
  - {label: Terms, href: /terms}
pending_pages: [/one]
"""


def site_file(tmp_path, text):
    path = tmp_path / "site.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_real_site_yaml_holds_the_fixed_values():
    site = load_site(REPO / "site.yaml")
    assert site.base_url == "https://syahi.sh"
    assert site.name == "Syahi"
    assert site.header == "syahi"
    assert [(t.label, t.href) for t in site.tabs] == [
        ("Services", "/services"), ("Signet", "/signet"), ("Media", "/media"), ("About", "/about")]
    assert site.cta == Link("Book a call", "https://cal.com/surabhipradhan/30-mins-discussion-about-syahi")
    assert [p.label for p in site.profiles] == ["LinkedIn", "Instagram", "Threads", "GitHub"]
    assert [(p.label, p.href) for p in site.policies] == [
        ("Contact", "/contact"), ("Privacy", "/privacy"), ("Terms", "/terms"), ("Refunds", "/refund")]
    assert site.pending_pages == frozenset({"/services", "/media", "/about", "/paper-machine"})


def test_good_file_loads_with_types(tmp_path):
    site = load_site(site_file(tmp_path, GOOD))
    assert isinstance(site, SiteConfig)
    assert isinstance(site.tabs, tuple) and isinstance(site.pending_pages, frozenset)
    assert site.tabs[1] == Link("Away", "https://away.example/")


def test_config_is_frozen(tmp_path):
    site = load_site(site_file(tmp_path, GOOD))
    with pytest.raises(dataclasses.FrozenInstanceError):
        site.name = "Other"
    with pytest.raises(dataclasses.FrozenInstanceError):
        site.cta.label = "Other"


@pytest.mark.parametrize("old, new, expect", [
    ("base_url: https://example.test\n", "", "missing required key(s): base_url"),
    ("header: syahi\n", "header: other\n", "'header' must be one of"),
    ("base_url: https://example.test\n", "base_url: https://example.test/\n", "no trailing slash"),
    ("base_url: https://example.test\n", "base_url: example.test\n", "'base_url'"),
    ("name: Example\n", "name: ''\n", "'name' must be a non-empty string"),
    ("pending_pages: [/one]\n", "pending_pages: [one]\n", "pending_pages"),
    ("pending_pages: [/one]\n", "pending_pages: /one\n", "pending_pages"),
    ("pending_pages: [/one]\n", "pending_pages: [/one, /one]\n", "more than once"),
    ("pending_pages: [/one]\n", "pending_pages: [/one]\nextra: 1\n", "unknown key(s): extra"),
    ("  - {label: One, href: /one}\n", "  - {label: One}\n", "tabs"),
    ("  - {label: One, href: /one}\n", "  - {label: One, href: one}\n", "href"),
    ("  - {label: One, href: /one}\n", "  - {label: One, href: 'http://plain.example/'}\n", "href"),
    ("  - {label: One, href: /one}\n", "  - {label: One, href: /one, rel: me}\n", "unknown key(s): rel"),
    ("  - {label: One, href: /one}\n", "  - {label: " + EM_DASH + ", href: /one}\n", "em dash"),
    ("cta: {label: Go, href: \"https://go.example/x\"}\n", "cta: Go\n", "cta"),
    ("pending_pages: [/one]\n", "pending_pages: []\nprofiles: []\n", "defined more than once"),
    ("pending_pages: [/one]\n", "pending_pages: [/one]\nfounder_profiles: nope\n", "'founder_profiles' must be a list"),
    ("pending_pages: [/one]\n", "pending_pages: [/one]\nfounder_profiles:\n", "'founder_profiles' must be a list"),
    ("pending_pages: [/one]\n", "pending_pages: [/one]\nfounder_profiles: [{label: Me}]\n", "founder_profiles[1]"),
    ("pending_pages: [/one]\n", "pending_pages: [/one]\nfounder_profiles: [{label: Me, href: 'http://plain.example/'}]\n", "href"),
    ("pending_pages: [/one]\n", "pending_pages: [/one]\nfounder_profiles: []\nfounder_profiles: []\n", "defined more than once"),
])
def test_bad_values_fail_and_name_the_file(tmp_path, old, new, expect):
    path = site_file(tmp_path, GOOD.replace(old, new))
    with pytest.raises(SiteError) as err:
        load_site(path)
    assert str(path) in str(err.value)
    assert expect in str(err.value)


def test_empty_tabs_are_rejected(tmp_path):
    text = GOOD.replace("  - {label: One, href: /one}\n  - {label: Away, href: \"https://away.example/\"}\n", "")
    text = text.replace("tabs:\n", "tabs: []\n")
    with pytest.raises(SiteError, match="'tabs' must be a non-empty list"):
        load_site(site_file(tmp_path, text))


def test_invalid_yaml_and_wrong_shape_fail(tmp_path):
    with pytest.raises(SiteError, match="not valid YAML"):
        load_site(site_file(tmp_path, "a: [unclosed"))
    with pytest.raises(SiteError, match="must be a YAML mapping"):
        load_site(site_file(tmp_path, "- just\n- a list\n"))
    with pytest.raises(SiteError, match="cannot read file"):
        load_site(tmp_path / "missing.yaml")


def test_founder_profiles_default_to_none(tmp_path):
    assert load_site(site_file(tmp_path, GOOD)).founder_profiles == ()


def test_founder_profiles_load_as_links_in_order(tmp_path):
    text = GOOD + 'founder_profiles:\n  - {label: Personal X, href: "https://social.example/me"}\n  - {label: Code, href: "https://code.example/me"}\n'
    site = load_site(site_file(tmp_path, text))
    assert site.founder_profiles == (Link("Personal X", "https://social.example/me"), Link("Code", "https://code.example/me"))
    assert isinstance(site.founder_profiles, tuple)
    assert site.profiles == (Link("Elsewhere", "https://elsewhere.example/me"),)  # the footer list is untouched


def test_founder_profiles_is_the_last_field_with_a_default():
    fields = dataclasses.fields(SiteConfig)
    assert fields[-1].name == "founder_profiles" and fields[-1].default == ()
