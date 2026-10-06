# tests/test_schema.py
import dataclasses, datetime, json
from pathlib import Path

import pytest

from sitebuild.claims import ClaimError, ClaimRegister
from sitebuild.content import Page
from sitebuild.render import make_env, render_page
from sitebuild.schema import SchemaError, build_jsonld, format_rupees, jsonld_mismatches, visible_text
from sitebuild.site import Link, load_site

REPO = Path(__file__).resolve().parents[1]
CLAIMS = """
- {id: org-name, text: "Syahi", source: s, updated: 2026-10-06, status: live}
- {id: org-alternate-name, text: "स्याही", source: s, updated: 2026-10-06, status: live}
- {id: org-legal-name, text: "SYAHI TECHNOLOGIES LLP", source: s, updated: 2026-10-06, status: live}
- {id: org-llpin, text: "LLPIN ADB-1993", source: s, updated: 2026-10-06, status: live}
- {id: org-founding-date, text: "2026-08-13", source: s, updated: 2026-10-06, status: live}
- {id: org-locality, text: "Bengaluru", source: s, updated: 2026-10-06, status: live}
- {id: signet-name, text: "Signet by Syahi", source: s, updated: 2026-10-06, status: live}
- {id: signet-price-line, text: "₹1,499 a month or ₹14,999 a year, GST included.", source: s, updated: 2026-10-06, status: live}
"""
# Made-up people, shows and store links for the nodes the brief's own tests do not reach.
EXTRA_CLAIMS = """
- {id: founder-name, text: "Founder Example", source: s, updated: 2026-10-06, status: live}
- {id: founder-line, text: "Founder Example has twenty years in testing.", source: s, updated: 2026-10-06, status: live}
- {id: katha-show-name, text: "Show Example", source: s, updated: 2026-10-06, status: live}
- {id: katha-show-url, text: "https://store.example/shows/show-example", source: s, updated: 2026-10-06, status: live}
- {id: katha-title-name, text: "शीर्षक उदाहरण", source: s, updated: 2026-10-06, status: live}
- {id: katha-title-url, text: "https://store.example/t/title-example", source: s, updated: 2026-10-06, status: live}
- {id: signet-price-amount, text: "1499", source: s, updated: 2026-10-06, status: live}
- {id: katha-title-price, text: "₹99 + GST = ₹116.82", source: s, updated: 2026-10-06, status: live}
- {id: katha-title-price-amount, text: "116.82", source: s, updated: 2026-10-06, status: live}
"""

def setup(tmp_path):
    p = tmp_path / "c.yaml"; p.write_text(CLAIMS + EXTRA_CLAIMS, encoding="utf-8")
    return load_site(REPO / "site.yaml"), ClaimRegister.load(p)

def pg(slug, schema=()):
    d = datetime.date(2026, 10, 6)
    return Page(slug=slug, title="Signet by Syahi", description="d", updated=d, approved=d, layout="page",
                claims=(), schema=tuple(schema), audience=None, body="", source=Path("x.html"))

def types(nodes):
    return [n["@type"] for n in nodes]

def test_home_has_org_without_street(tmp_path):
    site, claims = setup(tmp_path)
    nodes = build_jsonld(pg("/"), site, claims)
    org = next(n for n in nodes if n["@type"] == "Organization")
    assert org["@id"] == "https://syahi.sh/#org"
    assert org["legalName"] == "SYAHI TECHNOLOGIES LLP"
    assert org["alternateName"] == "स्याही"
    assert set(org["address"]) == {"@type", "addressLocality", "addressRegion", "addressCountry"}
    assert org["sameAs"] == [l.href for l in site.profiles]
    assert "WebSite" in types(nodes)

def test_software_application_offer(tmp_path):
    site, claims = setup(tmp_path)
    nodes = build_jsonld(pg("/signet", ["SoftwareApplication"]), site, claims)
    app = next(n for n in nodes if n["@type"] == "SoftwareApplication")
    assert app["offers"]["price"] == "1499" and app["offers"]["priceCurrency"] == "INR"

def test_every_page_has_webpage_and_breadcrumbs(tmp_path):
    site, claims = setup(tmp_path)
    t = types(build_jsonld(pg("/services/quote", ["Service"]), site, claims))
    assert "WebPage" in t and "BreadcrumbList" in t and "Service" in t

def test_never_reviews(tmp_path):
    site, claims = setup(tmp_path)
    blob = json.dumps([build_jsonld(pg(s, ["SoftwareApplication", "Service"]), site, claims) for s in ["/", "/signet"]])
    assert "Review" not in blob and "AggregateRating" not in blob

def test_mismatch_found_and_exemptions(tmp_path):
    ld = {"@context": "https://schema.org", "@type": "Thing", "name": "Shown name",
          "description": "Hidden words", "url": "https://syahi.sh/x", "foundingDate": "2026-08-13"}
    html = ('<html><body><p>Shown   name</p><script type="application/ld+json">'
            + json.dumps(ld, ensure_ascii=False) + "</script></body></html>")
    assert jsonld_mismatches(html) == ["description: Hidden words"]

def test_visible_text_skips_scripts_and_styles():
    assert visible_text("<style>a{}</style><p>a  b</p><script>x</script>") == "a b"


# ---- beyond the brief ----------------------------------------------------------------------
FOUNDER_LINKS = (Link("Personal X", "https://social.example/founder"), Link("Personal code", "https://code.example/founder"))

def node(nodes, kind):
    return next(n for n in nodes if n["@type"] == kind)

def katha_site(site):
    return dataclasses.replace(site, base_url="https://katha.example", name="Katha", header="katha")

def ld_html(*blocks, body="<p>x</p>", head=""):
    scripts = "".join('<script type="application/ld+json">' + (b if isinstance(b, str) else json.dumps(b, ensure_ascii=False))
                      + "</script>" for b in blocks)
    return f"<html><head>{head}{scripts}</head><body>{body}</body></html>"


# build_jsonld: the nodes

def test_home_nodes_and_their_order(tmp_path):
    site, claims = setup(tmp_path)
    assert types(build_jsonld(pg("/"), site, claims)) == ["Organization", "WebSite", "WebPage", "BreadcrumbList"]

def test_only_the_home_page_carries_the_organization_and_website(tmp_path):
    site, claims = setup(tmp_path)
    assert types(build_jsonld(pg("/signet"), site, claims)) == ["WebPage", "BreadcrumbList"]

def test_organization_fields_come_from_claims_and_fixed_values(tmp_path):
    site, claims = setup(tmp_path)
    org = node(build_jsonld(pg("/"), site, claims), "Organization")
    assert org["name"] == "Syahi" and org["foundingDate"] == "2026-08-13"
    assert org["founder"] == {"@id": "https://syahi.sh/about#surabhi"}
    assert org["address"] == {"@type": "PostalAddress", "addressLocality": "Bengaluru",
                              "addressRegion": "Karnataka", "addressCountry": "IN"}
    assert org["logo"] == "https://syahi.sh/assets/brand/mark-512.png"
    assert org["contactPoint"] == {"@type": "ContactPoint", "contactType": "sales", "url": "https://syahi.sh/contact"}

def test_organization_has_no_same_as_when_there_are_no_profiles(tmp_path):
    site, claims = setup(tmp_path)
    org = node(build_jsonld(pg("/"), dataclasses.replace(site, profiles=()), claims), "Organization")
    assert "sameAs" not in org

def test_website_node(tmp_path):
    site, claims = setup(tmp_path)
    web = node(build_jsonld(pg("/"), site, claims), "WebSite")
    assert web["@id"] == "https://syahi.sh/#site" and web["url"] == "https://syahi.sh/"
    assert web["name"] == "Syahi" and web["publisher"] == {"@id": "https://syahi.sh/#org"}

def test_webpage_node_is_the_clean_url_and_points_at_site_and_org(tmp_path):
    site, claims = setup(tmp_path)
    page = node(build_jsonld(pg("/services/quote"), site, claims), "WebPage")
    assert page == {"@type": "WebPage", "url": "https://syahi.sh/services/quote", "name": "Signet by Syahi",
                    "isPartOf": {"@id": "https://syahi.sh/#site"}, "publisher": {"@id": "https://syahi.sh/#org"}}
    assert node(build_jsonld(pg("/"), site, claims), "WebPage")["url"] == "https://syahi.sh/"

def test_service_node(tmp_path):
    site, claims = setup(tmp_path)
    svc = node(build_jsonld(pg("/services/quote", ["Service"]), site, claims), "Service")
    assert svc == {"@type": "Service", "name": "Signet by Syahi", "provider": {"@id": "https://syahi.sh/#org"},
                   "areaServed": "IN"}

def test_software_application_fields(tmp_path):
    site, claims = setup(tmp_path)
    app = node(build_jsonld(pg("/signet", ["SoftwareApplication"]), site, claims), "SoftwareApplication")
    assert app["name"] == "Signet by Syahi" and app["applicationCategory"] == "BusinessApplication"
    assert app["offers"] == {"@type": "Offer", "price": "1499", "priceCurrency": "INR",
                             "description": "₹1,499 a month or ₹14,999 a year, GST included."}

def test_profile_page_has_the_founder_as_main_entity(tmp_path):
    site, claims = setup(tmp_path)
    site = dataclasses.replace(site, founder_profiles=FOUNDER_LINKS)
    nodes = build_jsonld(pg("/about", ["ProfilePage"]), site, claims)
    assert types(nodes) == ["WebPage", "BreadcrumbList", "ProfilePage"]
    profile = node(nodes, "ProfilePage")
    assert profile["url"] == "https://syahi.sh/about"
    person = profile["mainEntity"]
    assert person == {"@type": "Person", "@id": "https://syahi.sh/about#surabhi", "name": "Founder Example",
                      "description": "Founder Example has twenty years in testing.",
                      "worksFor": {"@id": "https://syahi.sh/#org"},
                      "sameAs": ["https://social.example/founder", "https://code.example/founder"]}

def test_person_has_no_same_as_when_no_founder_profiles(tmp_path):
    site, claims = setup(tmp_path)
    assert site.founder_profiles == ()
    person = node(build_jsonld(pg("/about", ["ProfilePage"]), site, claims), "ProfilePage")["mainEntity"]
    assert "sameAs" not in person

def test_podcast_series_node(tmp_path):
    site, claims = setup(tmp_path)
    series = node(build_jsonld(pg("/", ["PodcastSeries"]), katha_site(site), claims), "PodcastSeries")
    assert series == {"@type": "PodcastSeries", "name": "Show Example",
                      "url": "https://store.example/shows/show-example", "inLanguage": "hi"}

def test_audiobook_node(tmp_path):
    site, claims = setup(tmp_path)
    book = node(build_jsonld(pg("/", ["Audiobook"]), katha_site(site), claims), "Audiobook")
    assert book == {"@type": "Audiobook", "name": "शीर्षक उदाहरण", "url": "https://store.example/t/title-example",
                    "inLanguage": "hi",
                    "offers": {"@type": "Offer", "price": "116.82", "priceCurrency": "INR"}}

def test_a_store_link_claim_must_be_an_https_url(tmp_path):
    site, claims = setup(tmp_path)
    bad = tmp_path / "bad.yaml"
    bad.write_text((CLAIMS + EXTRA_CLAIMS).replace("https://store.example/shows/show-example", "/shows/show-example"),
                   encoding="utf-8")
    with pytest.raises(SchemaError) as err:
        build_jsonld(pg("/", ["PodcastSeries"]), katha_site(site), ClaimRegister.load(bad))
    assert "katha-show-url" in str(err.value) and "x.html" in str(err.value)

def test_the_second_host_points_at_the_main_hosts_entities(tmp_path):
    site, claims = setup(tmp_path)
    nodes = build_jsonld(pg("/", ["PodcastSeries", "Audiobook"]), katha_site(site), claims)
    assert types(nodes) == ["WebPage", "BreadcrumbList", "PodcastSeries", "Audiobook"]
    page = node(nodes, "WebPage")
    assert page["url"] == "https://katha.example/"
    assert page["isPartOf"] == {"@id": "https://syahi.sh/#site"} and page["publisher"] == {"@id": "https://syahi.sh/#org"}
    assert node(nodes, "BreadcrumbList")["itemListElement"] == [
        {"@type": "ListItem", "position": 1, "name": "Katha", "item": "https://katha.example/"}]

def test_a_listed_type_is_added_once_in_listed_order(tmp_path):
    site, claims = setup(tmp_path)
    nodes = build_jsonld(pg("/signet", ["Service", "SoftwareApplication", "Service"]), site, claims)
    assert types(nodes) == ["WebPage", "BreadcrumbList", "Service", "SoftwareApplication"]

def test_unknown_and_review_types_fail_naming_the_page(tmp_path):
    site, claims = setup(tmp_path)
    for kind, expect in (("SoftwareApplicaton", "not supported"), ("Review", "never emitted"),
                         ("AggregateRating", "never emitted"), ("Organization", "not supported")):
        with pytest.raises(SchemaError) as err:
            build_jsonld(pg("/signet", [kind]), site, claims)
        assert "x.html" in str(err.value) and kind in str(err.value) and expect in str(err.value), kind

def test_a_missing_claim_is_a_claim_error_naming_the_page(tmp_path):
    site, claims = setup(tmp_path)
    p = tmp_path / "thin.yaml"
    p.write_text('- {id: org-name, text: "Syahi", source: s, updated: 2026-10-06, status: live}\n', encoding="utf-8")
    with pytest.raises(ClaimError) as err:
        build_jsonld(pg("/"), site, ClaimRegister.load(p))
    assert "x.html" in str(err.value) and "org-alternate-name" in str(err.value)

def test_the_output_is_deterministic_and_serialisable(tmp_path):
    site, claims = setup(tmp_path)
    a = build_jsonld(pg("/", ["Service"]), site, claims)
    b = build_jsonld(pg("/", ["Service"]), site, claims)
    assert a == b
    assert json.dumps(a, ensure_ascii=False, sort_keys=True) == json.dumps(b, ensure_ascii=False, sort_keys=True)


# build_jsonld: breadcrumbs

def crumbs(nodes):
    return [(c["position"], c["name"], c["item"]) for c in node(nodes, "BreadcrumbList")["itemListElement"]]

def test_breadcrumbs_use_tab_labels_and_the_page_title(tmp_path):
    site, claims = setup(tmp_path)
    nodes = build_jsonld(dataclasses.replace(pg("/services/quote"), title="Quote in Ten Minutes"), site, claims)
    assert crumbs(nodes) == [(1, "Syahi", "https://syahi.sh/"), (2, "Services", "https://syahi.sh/services"),
                             (3, "Quote in Ten Minutes", "https://syahi.sh/services/quote")]

def test_a_tab_page_is_named_by_its_tab_not_its_long_title(tmp_path):
    site, claims = setup(tmp_path)
    assert crumbs(build_jsonld(pg("/signet"), site, claims)) == [
        (1, "Syahi", "https://syahi.sh/"), (2, "Signet", "https://syahi.sh/signet")]

def test_the_home_page_has_one_crumb(tmp_path):
    site, claims = setup(tmp_path)
    assert crumbs(build_jsonld(pg("/"), site, claims)) == [(1, "Syahi", "https://syahi.sh/")]

def test_an_unnamed_level_is_skipped_never_invented(tmp_path):
    site, claims = setup(tmp_path)
    got = crumbs(build_jsonld(dataclasses.replace(pg("/a/b/c"), title="Deep page"), site, claims))
    assert got == [(1, "Syahi", "https://syahi.sh/"), (2, "Deep page", "https://syahi.sh/a/b/c")]

def test_every_url_is_absolute_on_the_host(tmp_path):
    site, claims = setup(tmp_path)
    site = dataclasses.replace(site, founder_profiles=FOUNDER_LINKS)
    def urls(value, key=""):
        if isinstance(value, dict):
            for k, v in value.items():
                yield from urls(v, k)
        elif isinstance(value, list):
            for v in value:
                yield from urls(v, key)
        elif key in ("url", "logo", "item", "@id"):
            yield value
    found = list(urls(build_jsonld(pg("/", ["Service", "SoftwareApplication", "ProfilePage"]), site, claims)))
    assert len(found) >= 10 and all(u.startswith("https://syahi.sh/") for u in found), found


# visible_text

def test_visible_text_skips_template_and_noscript_and_comments():
    html = "<p>a</p><template><p>no</p><template>no</template></template><noscript>no</noscript><!-- no --><p>b</p>"
    assert visible_text(html) == "ab"

def test_visible_text_decodes_entities_and_collapses_every_kind_of_space():
    assert visible_text("<p>Tom &amp; Jerry \n\t say &lt;hi&gt;</p>") == "Tom & Jerry say <hi>"

def test_visible_text_keeps_title_and_body_but_not_attributes():
    html = '<html><head><title>The title</title><meta name="description" content="meta only"></head><body><a href="/x" title="tip">link</a></body></html>'
    assert visible_text(html) == "The titlelink"

def test_visible_text_survives_a_script_that_is_never_closed_and_empty_input():
    assert visible_text("") == ""
    assert visible_text("<p>kept</p><script>var a = 1;") == "kept"


# jsonld_mismatches

def test_a_hidden_value_is_named_by_its_key_at_any_depth():
    ld = {"@type": "Organization", "name": "Shown", "address": {"@type": "PostalAddress", "streetAddress": "12 Hidden Road"},
          "knowsAbout": ["Shown", "Secret topic"], "@graph": [{"@type": "Thing", "alternateName": "Ghost"}]}
    assert jsonld_mismatches(ld_html(ld, body="<p>Shown</p>")) == [
        "streetAddress: 12 Hidden Road", "knowsAbout: Secret topic", "alternateName: Ghost"]

def test_every_exempt_key_passes_even_when_its_text_is_not_on_the_page():
    exempt = ["@context", "@type", "@id", "url", "logo", "image", "sameAs", "item", "priceCurrency", "areaServed",
              "addressCountry", "addressRegion", "inLanguage", "foundingDate", "datePublished", "dateModified",
              "contentUrl", "embedUrl"]
    ld = {key: "never shown" for key in exempt}
    ld["sameAs"] = ["https://a.example/x", "https://b.example/y"]
    ld["image"] = {"@type": "ImageObject", "url": "https://img.example/a.png"}
    assert jsonld_mismatches(ld_html(ld, body="<p>nothing relevant</p>")) == []

def test_enumeration_values_that_the_nodes_emit_are_exempt():
    ld = {"@type": "SoftwareApplication", "applicationCategory": "BusinessApplication",
          "contactPoint": {"@type": "ContactPoint", "contactType": "sales"}}
    assert jsonld_mismatches(ld_html(ld)) == []

def test_dates_and_the_numeric_price_are_exempt_other_numbers_are_not():
    ld = {"a": "2026-10-06", "b": "2026-10-06T09:30:00+05:30", "c": "2026-10-06T09:30:00Z",
          "offers": {"price": "1499", "priceCurrency": "INR"}}
    assert jsonld_mismatches(ld_html(ld)) == []
    assert jsonld_mismatches(ld_html({"name": "1499"})) == ["name: 1499"]
    assert jsonld_mismatches(ld_html({"price": "from 1499"})) == ["price: from 1499"]
    assert jsonld_mismatches(ld_html({"date": "2026-13-45 and more"})) == ["date: 2026-13-45 and more"]

def test_non_string_values_are_not_checked():
    ld = {"@type": "ListItem", "position": 2, "count": 1.5, "flag": True, "none": None}
    assert jsonld_mismatches(ld_html(ld)) == []

def test_matching_ignores_whitespace_and_entity_encoding_but_not_case():
    ld = {"name": "Tom & Jerry   say\nhi", "alternateName": "tom"}
    body = "<p>Tom &amp; Jerry say hi</p>"
    assert jsonld_mismatches(ld_html(ld, body=body)) == ["alternateName: tom"]

def test_the_title_in_the_head_counts_as_text_but_a_meta_description_does_not():
    head = '<title>Only in the title</title><meta name="description" content="Only in meta">'
    ld = {"name": "Only in the title", "description": "Only in meta"}
    assert jsonld_mismatches(ld_html(ld, head=head)) == ["description: Only in meta"]

def test_text_inside_another_script_or_a_template_does_not_make_a_value_visible():
    body = "<script>var s = 'Only here';</script><template>Only there</template><noscript>Or here</noscript>"
    ld = {"name": "Only here", "alternateName": "Only there", "description": "Or here"}
    assert jsonld_mismatches(ld_html(ld, body=body)) == [
        "name: Only here", "alternateName: Only there", "description: Or here"]

def test_every_jsonld_block_is_checked_and_other_scripts_are_not():
    other = '<script type="text/javascript">{"name": "not json-ld"}</script>'
    html = ld_html({"name": "One"}, {"name": "Two"}, body="<p>One</p>" + other)
    assert jsonld_mismatches(html) == ["name: Two"]

def test_a_page_without_jsonld_has_no_mismatches():
    assert jsonld_mismatches("<html><body><p>plain</p></body></html>") == []

def test_a_block_that_is_not_json_is_reported_not_skipped():
    out = jsonld_mismatches(ld_html({"name": "Fine"}, "{not json", body="<p>Fine</p>"))
    assert len(out) == 1 and out[0].startswith("json-ld: block 2 is not valid JSON")

def test_a_top_level_array_and_escaped_closers_are_read():
    block = json.dumps([{"name": "a</b> shown"}, {"name": "unseen"}], ensure_ascii=False).replace("</", "<\\/")
    assert jsonld_mismatches(ld_html(block, body="<p>a&lt;/b&gt; shown</p>")) == ["name: unseen"]

def test_the_script_type_is_matched_loosely():
    block = json.dumps({"name": "Loose"})
    html = f'<body><p>x</p><script TYPE=" Application/LD+JSON ">{block}</script></body>'
    assert jsonld_mismatches(html) == ["name: Loose"]


# the two halves together: the nodes build_jsonld makes, rendered into a real page

def rendered(tmp_path, page, site, claims):
    env = make_env(REPO, site, claims)
    return render_page(env, page, build_jsonld(page, site, claims))

def test_a_home_page_that_shows_its_claims_has_no_mismatch(tmp_path):
    site, claims = setup(tmp_path)
    page = dataclasses.replace(pg("/"), body="<p>{{ claim('org-alternate-name') }}</p>")
    assert jsonld_mismatches(rendered(tmp_path, page, site, claims)) == []

def test_a_home_page_that_hides_a_claim_is_caught(tmp_path):
    site, claims = setup(tmp_path)
    page = dataclasses.replace(pg("/"), body="<p>No second name here.</p>")
    assert jsonld_mismatches(rendered(tmp_path, page, site, claims)) == ["alternateName: स्याही"]

def test_the_webpage_url_is_the_canonical_link(tmp_path):
    site, claims = setup(tmp_path)
    for slug in ("/", "/signet", "/services/quote"):
        html = rendered(tmp_path, pg(slug), site, claims)
        canonical = html.split('<link rel="canonical" href="')[1].split('"')[0]
        webpage = next(n for n in build_jsonld(pg(slug), site, claims) if n["@type"] == "WebPage")
        assert webpage["url"] == canonical

def test_a_signet_page_that_shows_its_name_and_price_has_no_mismatch(tmp_path):
    site, claims = setup(tmp_path)
    body = "<h1>{{ claim('signet-name') }}</h1><p>{{ claim('signet-price-line') }}</p>"
    page = dataclasses.replace(pg("/signet", ["SoftwareApplication"]), body=body)
    assert jsonld_mismatches(rendered(tmp_path, page, site, claims)) == []


# ---- fix round 1: prices come from claims and must match the page; reads do not mark claims used ----
def register(tmp_path, *swaps):
    """The fixture register with some claim text swapped, as a new ClaimRegister."""
    text = CLAIMS + EXTRA_CLAIMS
    for old, new in swaps:
        assert old in text, old
        text = text.replace(old, new)
    path = tmp_path / "swapped.yaml"
    path.write_text(text, encoding="utf-8")
    return ClaimRegister.load(path)

@pytest.mark.parametrize("amount, shown", [
    ("1499", "\u20b91,499"), ("14999", "\u20b914,999"), ("116.82", "\u20b9116.82"), ("150000", "\u20b91,50,000"),
    ("0", "\u20b90"), ("999", "\u20b9999"), ("1000", "\u20b91,000"), ("99999", "\u20b999,999"),
    ("100000", "\u20b91,00,000"), ("12345678", "\u20b91,23,45,678"), ("1234567.5", "\u20b912,34,567.5"),
    ("1499.00", "\u20b91,499.00"),
])
def test_rupees_use_indian_grouping(amount, shown):
    assert format_rupees(amount) == shown

@pytest.mark.parametrize("bad", ["", "abc", "1,499", "\u20b91499", "1499.", ".5", "01499", " 1499", "1499 ", "-5", "1e3", "1499.5.5", "\u0661\u0664"])
def test_format_rupees_refuses_anything_but_plain_digits(bad):
    with pytest.raises(ValueError):
        format_rupees(bad)

def test_the_offer_price_is_the_claims_amount(tmp_path):
    site, _ = setup(tmp_path)
    claims = register(tmp_path, ('text: "1499"', 'text: "1799"'),
                      ("\u20b91,499 a month or \u20b914,999 a year", "\u20b91,799 a month or \u20b914,999 a year"))
    app = node(build_jsonld(pg("/signet", ["SoftwareApplication"]), site, claims), "SoftwareApplication")
    assert app["offers"]["price"] == "1799"

def test_the_audiobook_price_is_the_claims_amount(tmp_path):
    site, _ = setup(tmp_path)
    claims = register(tmp_path, ('text: "116.82"', 'text: "58.41"'), ("\u20b999 + GST = \u20b9116.82", "\u20b950 + GST = \u20b958.41"))
    book = node(build_jsonld(pg("/", ["Audiobook"]), katha_site(site), claims), "Audiobook")
    assert book["offers"]["price"] == "58.41"

def test_a_signet_amount_that_the_price_line_does_not_show_fails_the_build(tmp_path):
    site, _ = setup(tmp_path)
    claims = register(tmp_path, ('text: "1499"', 'text: "1799"'))   # the line still says 1,499
    with pytest.raises(SchemaError) as err:
        build_jsonld(pg("/signet", ["SoftwareApplication"]), site, claims)
    msg = str(err.value)
    assert "x.html" in msg and "signet-price-amount" in msg and "signet-price-line" in msg and "\u20b91,799" in msg

def test_an_audiobook_amount_that_the_price_claim_does_not_show_fails_the_build(tmp_path):
    site, _ = setup(tmp_path)
    claims = register(tmp_path, ('text: "116.82"', 'text: "120.00"'))   # katha-title-price still says 116.82
    with pytest.raises(SchemaError) as err:
        build_jsonld(pg("/", ["Audiobook"]), katha_site(site), claims)
    msg = str(err.value)
    assert "x.html" in msg and "katha-title-price-amount" in msg and "katha-title-price" in msg and "\u20b9120.00" in msg

@pytest.mark.parametrize("bad", ["1,499", "\u20b91499", "1499.", "01499", "abc", " 1499"])
def test_a_malformed_amount_fails_naming_the_claim(tmp_path, bad):
    site, _ = setup(tmp_path)
    signet = register(tmp_path, ('text: "1499"', f'text: "{bad}"'))
    with pytest.raises(SchemaError) as err:
        build_jsonld(pg("/signet", ["SoftwareApplication"]), site, signet)
    assert "signet-price-amount" in str(err.value) and "x.html" in str(err.value)
    katha = register(tmp_path, ('text: "116.82"', f'text: "{bad}"'))
    with pytest.raises(SchemaError) as err:
        build_jsonld(pg("/", ["Audiobook"]), katha_site(site), katha)
    assert "katha-title-price-amount" in str(err.value) and "x.html" in str(err.value)

@pytest.mark.parametrize("line", [
    "\u20b91,4990 a month",        # the amount followed by more digits
    "\u20b911,499 a month",        # the amount preceded by more digits
    "\u20b91,499.50 a month",      # a different amount with decimals
    "\u20b91,499,000 a month",     # grouped further on
    "1,499 a month",           # no rupee sign: not as it appears on the page
    "\u20b91499 a month",          # no grouping: not as it appears on the page
])
def test_the_amount_must_appear_whole_and_as_the_page_writes_it(tmp_path, line):
    site, _ = setup(tmp_path)
    claims = register(tmp_path, ("\u20b91,499 a month or \u20b914,999 a year, GST included.", line))
    with pytest.raises(SchemaError):
        build_jsonld(pg("/signet", ["SoftwareApplication"]), site, claims)

@pytest.mark.parametrize("line", ["Pay \u20b91,499.", "\u20b91,499", "From \u20b91,499, billed monthly", "(\u20b91,499/month)"])
def test_the_amount_is_found_at_the_end_of_a_sentence_and_in_brackets(tmp_path, line):
    site, _ = setup(tmp_path)
    claims = register(tmp_path, ("\u20b91,499 a month or \u20b914,999 a year, GST included.", line))
    app = node(build_jsonld(pg("/signet", ["SoftwareApplication"]), site, claims), "SoftwareApplication")
    assert app["offers"]["price"] == "1499" and app["offers"]["description"] == line

def without(tmp_path, claim_id):
    lines = [l for l in (CLAIMS + EXTRA_CLAIMS).splitlines() if f"id: {claim_id}," not in l]
    path = tmp_path / f"without-{claim_id}.yaml"
    path.write_text("\n".join(lines), encoding="utf-8")
    return ClaimRegister.load(path)

@pytest.mark.parametrize("claim_id, slug, kind, second_host", [
    ("signet-price-amount", "/signet", "SoftwareApplication", False),
    ("signet-price-line", "/signet", "SoftwareApplication", False),
    ("katha-title-price-amount", "/", "Audiobook", True),
    ("katha-title-price", "/", "Audiobook", True),
])
def test_a_missing_price_claim_is_a_claim_error_naming_the_page(tmp_path, claim_id, slug, kind, second_host):
    site, _ = setup(tmp_path)
    site = katha_site(site) if second_host else site
    with pytest.raises(ClaimError) as err:
        build_jsonld(pg(slug, [kind]), site, without(tmp_path, claim_id))
    assert claim_id in str(err.value) and "x.html" in str(err.value)

def test_a_retired_claim_fails_the_same_way_it_does_in_a_page(tmp_path):
    site, _ = setup(tmp_path)
    claims = register(tmp_path, ('{id: org-name, text: "Syahi", source: s, updated: 2026-10-06, status: live}',
                                 '{id: org-name, text: "Syahi", source: s, updated: 2026-10-06, status: retired}'))
    with pytest.raises(ClaimError) as err:
        build_jsonld(pg("/"), site, claims)
    assert "org-name" in str(err.value) and "retired" in str(err.value) and "x.html" in str(err.value)

def test_build_jsonld_does_not_mark_claims_used(tmp_path):
    site, claims = setup(tmp_path)
    site = dataclasses.replace(site, founder_profiles=FOUNDER_LINKS)
    assert claims.used == set()
    build_jsonld(pg("/", ["Service", "SoftwareApplication", "ProfilePage"]), site, claims)
    build_jsonld(pg("/", ["PodcastSeries", "Audiobook"]), katha_site(site), claims)
    assert claims.used == set()

def test_rendering_marks_only_what_the_page_shows(tmp_path):
    site, claims = setup(tmp_path)
    page = dataclasses.replace(pg("/"), body="<p>{{ claim('org-alternate-name') }}</p>")
    rendered(tmp_path, page, site, claims)
    assert claims.used == {"org-legal-name", "org-llpin", "org-alternate-name"}
