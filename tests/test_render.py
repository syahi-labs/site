# tests/test_render.py
import dataclasses
import datetime
import json
import re
from html.parser import HTMLParser
from pathlib import Path
import jinja2
import jinja2.sandbox
import pytest
from sitebuild.claims import ClaimRegister, ClaimError
from sitebuild.content import Page
from sitebuild.render import RenderError, make_env, render_page, format_date
from sitebuild.site import load_site

REPO = Path(__file__).resolve().parents[1]
CLAIMS = """
- id: org-legal-name
  text: "SYAHI TECHNOLOGIES LLP"
  source: "MCA record"
  updated: 2026-08-13
  status: live
- id: org-llpin
  text: "LLPIN ADB-1993"
  source: "MCA record"
  updated: 2026-08-13
  status: live
- id: demo-line
  text: "Five <b>bold</b> owners"
  source: "test"
  updated: 2026-10-06
  status: live
"""

class Collect(HTMLParser):
    def __init__(self):
        super().__init__(); self.tags = []; self.text = []; self.links = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs); self.tags.append((tag, a))
        if tag == "a": self.links.append(a.get("href"))
    def handle_data(self, d): self.text.append(d)

def page(slug="/signet", body="<p>{{ claim('demo-line') }}</p>", approved=datetime.date(2026, 10, 6)):
    return Page(slug=slug, title="T", description="D", updated=approved, approved=approved,
                layout="page", claims=(), schema=(), audience=None, body=body, source=Path("x.html"))

@pytest.fixture
def env(tmp_path):
    cp = tmp_path / "claims.yaml"; cp.write_text(CLAIMS, encoding="utf-8")
    site = load_site(REPO / "site.yaml")
    return make_env(REPO, site, ClaimRegister.load(cp))

def parse(html):
    c = Collect(); c.feed(html); return c

def test_format_date():
    assert format_date(datetime.date(2026, 10, 6)) == "6 Oct 2026"
    assert format_date(datetime.date(2026, 12, 25)) == "25 Dec 2026"

def test_canonical_is_clean_url(env):
    c = parse(render_page(env, page("/services/quote"), []))
    canon = [a["href"] for t, a in c.tags if t == "link" and a.get("rel") == "canonical"]
    assert canon == ["https://syahi.sh/services/quote"]

def test_root_canonical(env):
    c = parse(render_page(env, page("/"), []))
    assert [a["href"] for t, a in c.tags if t == "link" and a.get("rel") == "canonical"] == ["https://syahi.sh/"]

def test_tabs_and_cta_in_order(env):
    html = render_page(env, page(), [])
    start = html.index('aria-label="Main"'); end = html.index("</nav>", start)
    nav = parse(html[start - 5:end])
    assert nav.links[:5] == ["/services", "/signet", "/media", "/about",
                             "https://cal.com/surabhipradhan/30-mins-discussion-about-syahi"]

def test_made_by_line_exact(env):
    html = render_page(env, page(approved=datetime.date(2026, 10, 12)), [])
    assert "Drafted with AI from our own records. Checked and approved by Surabhi Pradhan on 12 Oct 2026." in html

def test_claim_is_escaped_and_tagged(env):
    html = render_page(env, page(), [])
    assert '<span data-claim="demo-line">Five &lt;b&gt;bold&lt;/b&gt; owners</span>' in html

def test_unknown_claim_fails(env):
    with pytest.raises(ClaimError):
        render_page(env, page(body="{{ claim('missing') }}"), [])

def test_skip_link_first_and_main_id(env):
    c = parse(render_page(env, page(), []))
    body_i = [i for i, (t, a) in enumerate(c.tags) if t == "body"][0]
    assert c.tags[body_i + 1] == ("a", {"class": "skip", "href": "#main"})
    assert ("main", {"id": "main"}) in c.tags

def test_no_scripts_except_jsonld(env):
    c = parse(render_page(env, page(), [{"@type": "WebPage"}]))
    scripts = [a for t, a in c.tags if t == "script"]
    assert scripts and all(a.get("type") == "application/ld+json" for a in scripts)

def test_footer_profiles_are_company_only(env):
    html = render_page(env, page(), [])
    foot = parse(html[html.index("<footer"):])
    for href in ["https://www.linkedin.com/company/syahi-sh", "https://www.instagram.com/syahitech",
                 "https://www.threads.com/@syahitech", "https://github.com/syahi-labs"]:
        assert href in foot.links
    assert not any("x.com" in (h or "") or "github.com/surpradhan" in (h or "") for h in foot.links)


# ---- beyond the brief: head, header, footer, JSON-LD, errors ----
def head_meta(html):
    c = parse(html)
    return {a.get("name") or a.get("property"): a.get("content")
            for t, a in c.tags if t == "meta" and (a.get("name") or a.get("property"))}


def test_document_shell(env):
    html = render_page(env, page(), [])
    assert html.startswith("<!doctype html>")
    c = parse(html)
    assert ("html", {"lang": "en"}) in c.tags
    assert ("meta", {"charset": "utf-8"}) in c.tags or ("meta", {"charset": "UTF-8"}) in c.tags
    assert ("meta", {"name": "viewport", "content": "width=device-width, initial-scale=1"}) in c.tags
    assert "<title>T</title>" in html
    assert html.count("<header") == 1 and html.count("<footer") == 1 and html.count("<main") == 1


def test_stylesheets_are_linked_in_order_not_inlined(env):
    html = render_page(env, page(), [])
    sheets = [a["href"] for t, a in parse(html).tags if t == "link" and a.get("rel") == "stylesheet"]
    assert [Path(s).name for s in sheets] == ["tokens.css", "base.css"]
    assert "<style" not in html


def test_open_graph_and_description(env):
    meta = head_meta(render_page(env, page("/signet"), []))
    assert meta["description"] == "D"
    assert meta["og:title"] == "T" and meta["og:description"] == "D"
    assert meta["og:url"] == "https://syahi.sh/signet"
    assert meta["og:type"] == "website"
    assert meta["og:image"] == "https://syahi.sh/assets/brand/og-default.png"


def test_og_image_override_relative_and_absolute(env):
    rel = dataclasses.replace(page(), og_image="/assets/brand/mark-512.png")
    assert head_meta(render_page(env, rel, []))["og:image"] == "https://syahi.sh/assets/brand/mark-512.png"
    absolute = dataclasses.replace(page(), og_image="https://cdn.example/card.png")
    assert head_meta(render_page(env, absolute, []))["og:image"] == "https://cdn.example/card.png"


def test_head_values_are_escaped(env):
    odd = dataclasses.replace(page(), title='A & "B" <i>', description="x\" onload=\"y")
    html = render_page(env, odd, [])
    assert "<title>A &amp; &#34;B&#34; &lt;i&gt;</title>" in html
    assert 'content="x&#34; onload=&#34;y"' in html


def test_wordmark_links_home_before_the_nav(env):
    html = render_page(env, page(), [])
    header = html[html.index("<header"):html.index("</header>")]
    assert header.index('href="/"') < header.index('aria-label="Main"')
    assert ">Syahi</a>" in header


def test_nav_is_one_set_inside_a_closed_details_menu(env):
    html = render_page(env, page(), [])
    nav = html[html.index('aria-label="Main"'):html.index("</nav>")]
    assert '<details class="nav-menu">' in nav and "<summary>Menu</summary>" in nav
    assert "open" not in re.search(r"<details[^>]*>", nav).group(0)
    assert nav.count('href="/services"') == 1
    assert nav.count('class="cta"') == 1
    assert 'class="cta" href="https://cal.com/surabhipradhan/30-mins-discussion-about-syahi">Book a call</a>' in nav


def test_current_tab_is_marked(env):
    def current(slug):
        html = render_page(env, page(slug), [])
        nav = html[html.index('aria-label="Main"'):html.index("</nav>")]
        return re.findall(r'<a href="([^"]+)"[^>]*aria-current="([^"]+)"', nav)
    assert current("/signet") == [("/signet", "page")]
    assert current("/services/quote") == [("/services", "true")]
    assert current("/servicesx") == []
    assert current("/") == []


def test_footer_order_and_legal_line(env):
    html = render_page(env, page(), [])
    foot = html[html.index("<footer"):]
    order = [foot.index(s) for s in ("linkedin.com", 'data-claim="org-legal-name"', 'data-claim="org-llpin"',
                                     "Bengaluru", 'href="/contact"', 'href="/refund"', "Drafted with AI")]
    assert order == sorted(order)
    assert '<span data-claim="org-legal-name">SYAHI TECHNOLOGIES LLP</span>' in foot
    assert '<span data-claim="org-llpin">LLPIN ADB-1993</span>' in foot
    assert [h for h in parse(foot).links if h.startswith("/")] == ["/contact", "/privacy", "/terms", "/refund"]


def test_footer_claims_are_recorded_as_used(tmp_path):
    cp = tmp_path / "claims.yaml"; cp.write_text(CLAIMS, encoding="utf-8")
    register = ClaimRegister.load(cp)
    render_page(make_env(REPO, load_site(REPO / "site.yaml"), register), page(), [])
    assert register.used == {"org-legal-name", "org-llpin", "demo-line"}


def test_body_is_a_template_and_comes_out_inside_main(env):
    html = render_page(env, page(body="<p>{{ page.title }} on {{ page.approved|date }}</p>"), [])
    assert "<p>T on 6 Oct 2026</p>" in html[html.index("<main"):html.index("</main>")]


def test_body_variables_are_escaped(env):
    odd = dataclasses.replace(page(body="<p>{{ page.title }}</p>"), title="<script>x</script>")
    assert "<p>&lt;script&gt;x&lt;/script&gt;</p>" in render_page(env, odd, [])


def test_jsonld_is_sorted_utf8_and_cannot_close_the_script(env):
    node = {"@type": "WebPage", "name": "a</script><script>alert(1)</script> स्याही <!-- x",
            "b": 1, "a": 2}
    html = render_page(env, page(), [node, {"@type": "Organization"}])
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert len(blocks) == 2
    assert html.count("</script>") == 2 and html.count("<script type=") == 2
    parsed = json.loads(blocks[0])
    assert parsed == node
    assert blocks[0].index('"@type"') < blocks[0].index('"a"') < blocks[0].index('"b"')
    assert "स्याही" in blocks[0]          # ensure_ascii=False
    assert "<\\/script>" in blocks[0] and "<!--" not in blocks[0]


def test_no_jsonld_means_no_script_at_all(env):
    assert "<script" not in render_page(env, page(), [])


def test_no_em_dash_in_output(env):
    assert chr(0x2014) not in render_page(env, page(), [])


def test_errors_name_the_page_file(env):
    with pytest.raises(ClaimError) as err:
        render_page(env, page(body="{{ claim('missing') }}"), [])
    assert "x.html" in str(err.value) and "missing" in str(err.value)


def test_template_problems_are_render_errors_naming_the_file(env):
    for body, expect in (("{{ nope }}", "nope"), ("{% if %}", "x.html"), ("{{ page.nothing }}", "nothing")):
        with pytest.raises(RenderError) as err:
            render_page(env, page(body=body), [])
        assert "x.html" in str(err.value) and expect in str(err.value)


def test_unknown_layout_is_a_render_error(env):
    for layout in ("nope", "../base", ""):
        with pytest.raises(RenderError) as err:
            render_page(env, dataclasses.replace(page(), layout=layout), [])
        assert "x.html" in str(err.value) and "layout" in str(err.value)


def test_format_date_rejects_non_dates():
    with pytest.raises(TypeError):
        format_date("2026-10-06")


def test_date_filter_is_format_date(env):
    assert env.from_string("{{ d|date }}").render(d=datetime.date(2026, 1, 9)) == "9 Jan 2026"


# ---- Task 3 follow-up: errors that name the page, a sandbox, an explicit environment ----
def test_python_errors_from_a_body_are_render_errors_naming_the_page(env):
    for body, kind in (("{{ 5|date }}", "TypeError"), ("{{ claim() }}", "TypeError"),
                       ("{{ range(1, 2, 0) }}", "ValueError"), ("{{ 1 / 0 }}", "ZeroDivisionError")):
        with pytest.raises(RenderError) as err:
            render_page(env, page(body=body), [])
        assert "x.html" in str(err.value), body
        assert kind in str(err.value), body


def test_a_render_error_is_not_wrapped_twice(env):
    with pytest.raises(RenderError) as err:
        render_page(env, dataclasses.replace(page(), layout="nope"), [])
    assert str(err.value).count("x.html") == 1


def test_the_environment_is_a_sandbox_and_still_an_environment(env):
    assert isinstance(env, jinja2.Environment)
    assert isinstance(env, jinja2.sandbox.SandboxedEnvironment)


def test_a_body_cannot_reach_python_internals(env):
    for body in ("{{ ''.__class__.__mro__ }}", "{{ claim.__globals__ }}", "{{ site.__class__ }}"):
        with pytest.raises(RenderError) as err:
            render_page(env, page(body=body), [])
        assert "x.html" in str(err.value), body
        assert "unsafe" in str(err.value), body


def test_a_body_cannot_read_files_through_the_page_source_path(env):
    for body in ("{{ page.source.read_text() }}", "{{ page.source.parent.iterdir() }}"):
        with pytest.raises(RenderError) as err:
            render_page(env, page(body=body), [])
        assert "x.html" in str(err.value) and "unsafe" in str(err.value), body


def test_the_sandbox_still_allows_what_pages_need(env):
    body = "{{ site.name }} {{ page.slug }} {{ page.approved|date }} {{ page.source }}"
    html = render_page(env, page(body=body), [])
    assert "Syahi /signet 6 Oct 2026 x.html" in html


def test_render_page_refuses_an_environment_make_env_did_not_make():
    with pytest.raises(TypeError) as err:
        render_page(jinja2.Environment(), page(), [])
    assert "make_env" in str(err.value)


# ---- draft pages say so in the made-by line ----

DRAFT_LINE = "Drafted with AI from our own records. Not yet approved."


def draft_page(**changes):
    return dataclasses.replace(page(), approved=None, draft=True, **changes)


def test_a_draft_made_by_line_is_exact_and_claims_no_approval(env):
    html = render_page(env, draft_page(), [])
    assert f'<p class="made-by">{DRAFT_LINE}</p>' in html
    assert "Checked and approved" not in html and "Surabhi Pradhan" not in html.split("<footer")[1]


def test_a_draft_that_carries_a_date_still_says_not_yet_approved(env):
    html = render_page(env, dataclasses.replace(page(), draft=True), [])
    assert f'<p class="made-by">{DRAFT_LINE}</p>' in html and "Checked and approved" not in html


def test_a_page_that_is_not_a_draft_keeps_the_approved_line(env):
    html = render_page(env, page(), [])
    assert "Checked and approved by Surabhi Pradhan on 6 Oct 2026." in html and "Not yet approved" not in html


# ---- link-preview copy: the base emits the preview's own words, and falls back to the page's ----

def preview_page(**fields):
    return dataclasses.replace(page("/signet"), **fields)


def test_without_preview_copy_the_preview_says_the_title_and_the_description(env):
    meta = head_meta(render_page(env, page("/signet"), []))
    assert meta["og:title"] == meta["twitter:title"] == "T"
    assert meta["og:description"] == meta["twitter:description"] == "D"
    assert "og:image:alt" not in meta and "twitter:image:alt" not in meta


def test_the_preview_copy_replaces_the_title_and_the_description_in_both_tag_sets(env):
    meta = head_meta(render_page(env, preview_page(og_title="Short", og_description="A line.", og_image_alt="A seal."), []))
    assert meta["og:title"] == meta["twitter:title"] == "Short"
    assert meta["og:description"] == meta["twitter:description"] == "A line."
    assert meta["og:image:alt"] == meta["twitter:image:alt"] == "A seal."
    assert meta["description"] == "D"                               # the search snippet and the tab keep the page's own


def test_each_preview_field_falls_back_on_its_own(env):
    meta = head_meta(render_page(env, preview_page(og_title="Short"), []))
    assert meta["og:title"] == "Short" and meta["og:description"] == "D" and "og:image:alt" not in meta
    meta = head_meta(render_page(env, preview_page(og_description="A line."), []))
    assert meta["og:title"] == "T" and meta["twitter:description"] == "A line."


def test_the_title_element_and_the_json_ld_name_stay_the_pages_title(env):
    html = render_page(env, preview_page(og_title="Short"), [{"@type": "WebPage", "name": "T"}])
    assert "<title>T</title>" in html


def test_preview_copy_is_escaped(env):
    html = render_page(env, preview_page(og_title='A & "B"', og_image_alt='x" onload="y'), [])
    assert 'property="og:title" content="A &amp; &#34;B&#34;"' in html
    assert 'property="og:image:alt" content="x&#34; onload=&#34;y"' in html


def test_the_preview_tags_sit_in_one_group_in_the_head(env):
    html = render_page(env, preview_page(og_image_alt="A seal."), [])
    head = html.split("</head>")[0]
    names = ("og:title", "og:description", "og:url", "og:type", "og:image", "og:image:width", "og:image:height", "og:image:alt",
             "twitter:card", "twitter:title", "twitter:description", "twitter:image", "twitter:image:alt")
    order = [head.index(f'"{name}"') for name in names]
    assert order == sorted(order)


# ---- claim_text(): a claim's text as a plain string, for an attribute ----
# claim() writes a span, which cannot sit inside an attribute. claim_text() gives the text itself, escaped like
# any value, and records the claim as used, so the front matter list and the build's "rendered" check see it.

def attr_page(body, **fields):
    return dataclasses.replace(page(body=body), **fields)


def test_claim_text_puts_the_plain_text_into_an_attribute(env):
    html = render_page(env, attr_page("<a href=\"/x\" aria-label=\"Say {{ claim_text('demo-line') }} now\">x</a>"), [])
    assert 'aria-label="Say Five &lt;b&gt;bold&lt;/b&gt; owners now"' in html     # escaped once, and no span in an attribute
    assert "<span" not in html[html.index("<main"):html.index("</main>")]


def test_claim_text_takes_the_short_form_too(tmp_path):
    cp = tmp_path / "claims.yaml"
    cp.write_text(CLAIMS + '- {id: length, text: "30 minutes", short: "30-minute", source: s, updated: 2026-10-06, status: live}\n', encoding="utf-8")
    env = make_env(REPO, load_site(REPO / "site.yaml"), ClaimRegister.load(cp))
    html = render_page(env, attr_page("<a href=\"/x\" aria-label=\"A {{ claim_text('length', 'short') }} call\">x</a>"), [])
    assert 'aria-label="A 30-minute call"' in html


def test_claim_text_escapes_a_quote_so_it_cannot_close_the_attribute(tmp_path):
    cp = tmp_path / "claims.yaml"
    cp.write_text(CLAIMS + '- {id: odd, text: "say \\"hi\\" now", source: s, updated: 2026-10-06, status: live}\n', encoding="utf-8")
    env = make_env(REPO, load_site(REPO / "site.yaml"), ClaimRegister.load(cp))
    html = render_page(env, attr_page("<a href=\"/x\" aria-label=\"{{ claim_text('odd') }}\">x</a>"), [])
    assert 'aria-label="say &#34;hi&#34; now"' in html


def test_claim_text_records_the_claim_as_used(tmp_path):
    cp = tmp_path / "claims.yaml"; cp.write_text(CLAIMS, encoding="utf-8")
    register = ClaimRegister.load(cp)
    env = make_env(REPO, load_site(REPO / "site.yaml"), register)
    render_page(env, attr_page("<a href=\"/x\" title=\"{{ claim_text('demo-line') }}\">x</a>"), [])
    assert "demo-line" in register.used


def test_claim_text_fails_on_an_unknown_id_and_on_a_missing_short_form(env):
    with pytest.raises(ClaimError):
        render_page(env, attr_page("<a href=\"/x\" title=\"{{ claim_text('missing') }}\">x</a>"), [])
    with pytest.raises(ClaimError):
        render_page(env, attr_page("<a href=\"/x\" title=\"{{ claim_text('demo-line', 'short') }}\">x</a>"), [])
