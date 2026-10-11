"""Tests for sitecheck.py. Offline only: fixtures live in tmp_path and urlopen is always faked."""
import datetime
import email.message
import io
import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
TOOL = HERE.parent / "checks" / "sitecheck.py"  # the tool lives in checks/, its tests here
from checks import sitecheck  # noqa: E402

EM = chr(0x2014)
DOT = chr(0xB7)
HOST = "site.example"
BODY_LINE = 7  # first line of the page body produced by page()
NAV = ('<nav><a href="/">Home</a> <a href="/about">About</a> <a href="contact.html">Contact</a> '
       '<a href="mailto:team@example.com">Mail</a></nav>')


def head(stem, skip=()):
    url = f"https://{HOST}/" + ("" if stem == "index" else stem)
    parts = {
        "title": f"<title>{stem.title()} page</title>",
        "description": f'<meta name="description" content="A page about {stem}.">',
        "og": f'<meta property="og:image" content="https://{HOST}/og.png">',
        "canonical": f'<link rel="canonical" href="{url}">',
    }
    return "".join(v for k, v in parts.items() if k not in skip)


def page(stem="index", body=None, extra_head="", skip=(), nav=NAV):
    if body is None:
        body = f"<h1>{stem.title()}</h1>\n<p>Plain words.</p>"
    return (f"<!doctype html>\n<html><head>\n{head(stem, skip)}{extra_head}\n</head>\n"
            f"<body>\n{nav}\n{body}\n</body></html>\n")


def sitemap_xml(entries, ns=sitecheck.SITEMAP_NS):
    rows = ""
    for loc, lastmod in entries:
        loc = loc if loc.startswith("http") else f"https://{HOST}{loc}"
        rows += f"<url><loc>{loc}</loc>" + (f"<lastmod>{lastmod}</lastmod>" if lastmod else "") + "</url>\n"
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="{ns}">\n{rows}</urlset>\n'


GOOD_ROBOTS = f"User-agent: *\nAllow: /\n\nSitemap: https://{HOST}/sitemap.xml\n"
GOOD_ENTRIES = [("/", "2026-01-01"), ("/about", "2026-01-02"), ("/contact", "2026-01-03T10:00:00Z")]


def site(tmp_path, extra=None, name="s", cname=HOST):
    """A clean three-page site. `extra` adds or replaces files; a None value deletes one."""
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    files = {"index.html": page("index"), "about.html": page("about"), "contact.html": page("contact"),
             "robots.txt": GOOD_ROBOTS, "sitemap.xml": sitemap_xml(GOOD_ENTRIES)}
    if cname:
        files["CNAME"] = cname + "\n"
    files.update(extra or {})
    for rel, content in files.items():
        f = root / rel
        if content is None:
            f.exists() and f.unlink()
            continue
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
    return root


def run(*roots, offline=True, banned=None):
    return sitecheck.run([str(r) for r in roots], banned=banned, offline=offline)


def only(findings, check, level=None):
    return [f for f in findings if f.check == check and (level is None or f.level == level)]


class Resp:
    status = 200

    def __init__(self):
        self.asked = None

    def read(self, n=-1):
        self.asked = n
        return b""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Net:
    """Scripted urlopen. script maps url to outcomes consumed per call (the last one repeats):
    an int status, "timeout" or "dns". Unlisted URLs answer 200."""

    def __init__(self, script=None):
        self.script, self.calls, self.requests, self.resps = script or {}, [], [], []
        self.lock = threading.Lock()

    def __call__(self, req, timeout=None):
        url = req.full_url
        with self.lock:
            self.calls.append(url)
            self.requests.append((req, timeout))
            outcomes = self.script.get(url, [200])
            out = outcomes[min(self.calls.count(url) - 1, len(outcomes) - 1)]
        if out == "timeout":
            raise TimeoutError("timed out")
        if out == "dns":
            raise urllib.error.URLError(OSError("Name or service not known"))
        if out >= 400:
            raise urllib.error.HTTPError(url, out, "error", email.message.Message(), io.BytesIO(b""))
        resp = Resp()
        self.resps.append(resp)
        return resp


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("unexpected network call")
    monkeypatch.setattr(urllib.request, "urlopen", boom)


@pytest.fixture
def net(monkeypatch):
    def install(script=None):
        n = Net(script)
        monkeypatch.setattr(urllib.request, "urlopen", n)
        return n
    return install


def links_site(tmp_path, urls, name="s"):
    body = "<h1>Home</h1>\n" + "\n".join(f'<a href="{u}">x</a>' for u in urls)
    return site(tmp_path, {"index.html": page("index", body=body)}, name=name)


# ------------------------------------------------------------------ baseline

def test_good_site_has_no_findings(tmp_path):
    assert run(site(tmp_path)) == []


def test_files_outside_the_scanned_set_are_ignored(tmp_path):
    bad = page("x", body=f"<h1>X</h1><p>a {EM} b</p>")
    root = site(tmp_path, {".git/x.html": bad, ".claude/x.txt": EM, "node_modules/p/x.html": bad,
                           "notes.md": EM, "style.css": f"/* {EM} */", "CNAME": HOST + f" {EM}\n"})
    assert run(root) == []


# ------------------------------------------------------------------- em-dash

def test_em_dash_in_visible_text_fires_on_the_right_line(tmp_path):
    body = f"<h1>Home</h1>\n<p>first line\nsecond line {EM} here\nthird</p>"
    fs = only(run(site(tmp_path, {"index.html": page(body=body)})), "em-dash")
    assert [(f.level, f.path, f.line) for f in fs] == [("FAIL", "index.html", BODY_LINE + 2)]


def test_em_dash_in_comment_script_and_style_does_not_fire(tmp_path):
    body = (f"<h1>Home</h1>\n<!-- note {EM} to self -->\n<!--\n multi {EM} line\n-->\n"
            f'<script>var s = "{EM}";</script>\n<style>/* {EM} */</style>')
    assert only(run(site(tmp_path, {"index.html": page(body=body)})), "em-dash") == []


def test_em_dash_in_aria_label_fires(tmp_path):
    body = f'<h1>Home</h1>\n<button aria-label="Open {EM} menu">Menu</button>'
    fs = only(run(site(tmp_path, {"index.html": page(body=body)})), "em-dash")
    assert [(f.level, f.line) for f in fs] == [("FAIL", BODY_LINE + 1)]


@pytest.mark.parametrize("snippet", [
    '<img src="/about.html" alt="a {} b">',
    '<a href="/about" title="a {} b">x</a>',
    '<input placeholder="a {} b">',
])
def test_em_dash_in_checked_attributes_fires(tmp_path, snippet):
    body = "<h1>Home</h1>\n" + snippet.format(EM)
    assert len(only(run(site(tmp_path, {"index.html": page(body=body)})), "em-dash")) == 1


def test_em_dash_in_meta_content_and_title_fires(tmp_path):
    extra = f'<meta name="twitter:title" content="a {EM} b">'
    fs = only(run(site(tmp_path, {"index.html": page(extra_head=extra)})), "em-dash")
    assert len(fs) == 1
    fs = only(run(site(tmp_path, {"index.html": page(skip=("title",), extra_head=f"<title>a {EM} b</title>")}, name="t")), "em-dash")
    assert len(fs) == 1


def test_em_dash_in_unchecked_attribute_or_as_entity(tmp_path):
    quiet = f'<h1>Home</h1>\n<div data-note="a {EM} b" class="c">ok</div>'
    assert only(run(site(tmp_path, {"index.html": page(body=quiet)})), "em-dash") == []
    loud = "<h1>Home</h1>\n<p>a &mdash; b</p>"
    assert len(only(run(site(tmp_path, {"index.html": page(body=loud)}, name="t")), "em-dash")) == 1


@pytest.mark.parametrize("name", ["llms.txt", "feed.xml"])
def test_em_dash_in_txt_and_xml_fires_with_line(tmp_path, name):
    fs = only(run(site(tmp_path, {name: f"one\ntwo {EM} three\n"})), "em-dash")
    assert [(f.path, f.line) for f in fs] == [(name, 2)]
    assert only(run(site(tmp_path, {name: "one\ntwo - three\n"}, name="t")), "em-dash") == []


def test_tool_and_tests_pass_their_own_em_dash_check(tmp_path):
    for p in (TOOL, HERE / "test_sitecheck.py"):
        assert EM.encode() not in p.read_bytes()
    root = site(tmp_path, {"sitecheck.txt": TOOL.read_text(encoding="utf-8"),
                           "test_sitecheck.txt": (HERE / "test_sitecheck.py").read_text(encoding="utf-8")})
    assert only(run(root), "em-dash") == []


# --------------------------------------------------------------- placeholder

@pytest.mark.parametrize("text", ["Name ____", "Lorem ipsum dolor", "LOREM IPSUM", "TODO write this",
                                  "TBD", "Fix: FIXME later", "a_____b"])
def test_placeholder_fires(tmp_path, text):
    fs = only(run(site(tmp_path, {"index.html": page(body=f"<h1>Home</h1>\n<p>{text}</p>")})), "placeholder")
    assert [(f.level, f.line) for f in fs] == [("FAIL", BODY_LINE + 1)]


def test_placeholder_in_attribute_fires(tmp_path):
    body = '<h1>Home</h1>\n<input placeholder="Your name ____">'
    assert len(only(run(site(tmp_path, {"index.html": page(body=body)})), "placeholder")) == 1


@pytest.mark.parametrize("text", ["snake__case", "my todo list", "TODOS and FIXMEs", "tbd", "Autodoc", "lorem"])
def test_placeholder_stays_quiet_on_lookalikes(tmp_path, text):
    body = f"<h1>Home</h1>\n<p>{text}</p>"
    assert only(run(site(tmp_path, {"index.html": page(body=body)})), "placeholder") == []


def test_placeholder_ignores_comments_scripts_and_text_files(tmp_path):
    body = "<h1>Home</h1>\n<!-- TODO ____ -->\n<script>// FIXME</script>"
    root = site(tmp_path, {"index.html": page(body=body), "notes.txt": "TODO lorem ipsum ____\n"})
    assert only(run(root), "placeholder") == []


# -------------------------------------------------------------- banned-phrase

@pytest.mark.parametrize("phrase", sitecheck.BANNED_PHRASES)
def test_banned_phrase_is_case_insensitive(tmp_path, phrase):
    for i, text in enumerate((phrase.upper(), phrase.lower(), phrase.title())):
        root = site(tmp_path, {"index.html": page(body=f"<h1>Home</h1>\n<p>We build {text} daily.</p>")}, name=f"s{i}")
        fs = only(run(root), "banned-phrase")
        assert [(f.level, f.path, f.line) for f in fs] == [("FAIL", "index.html", BODY_LINE + 1)]
        assert phrase in fs[0].message


def test_banned_phrase_spans_a_line_break_and_covers_attributes_and_text_files(tmp_path):
    phrase = next(p for p in sitecheck.BANNED_PHRASES if " " in p)
    body = f'<h1>Home</h1>\n<p>{phrase.replace(" ", chr(10) + "   ")}</p>\n<img src="/about.html" alt="{phrase}">'
    root = site(tmp_path, {"index.html": page(body=body), "llms.txt": f"intro\n{phrase}\n"})
    img_line = BODY_LINE + 2 + phrase.count(" ")  # the phrase is split over one line per space
    assert sorted((f.path, f.line) for f in only(run(root), "banned-phrase")) == [
        ("index.html", BODY_LINE + 1), ("index.html", img_line), ("llms.txt", 2)]


def test_banned_phrase_quiet_on_clean_site(tmp_path):
    assert only(run(site(tmp_path)), "banned-phrase") == []


def test_banned_file_replaces_the_default_list(tmp_path):
    bf = tmp_path / "banned.txt"
    bf.write_text("# comment\n\nwidget synergy\n  Acme Rocket  \n", encoding="utf-8")
    assert sitecheck.load_banned(str(bf)) == ["widget synergy", "Acme Rocket"]
    default = sitecheck.BANNED_PHRASES[0]
    body = f"<h1>Home</h1>\n<p>WIDGET SYNERGY and {default}</p>"
    root = site(tmp_path, {"index.html": page(body=body)})
    fs = only(run(root, banned=sitecheck.load_banned(str(bf))), "banned-phrase")
    assert [f.message for f in fs] == ["banned phrase: widget synergy"]


def test_banned_file_option_on_the_command_line(tmp_path, capsys):
    bf = tmp_path / "banned.txt"
    bf.write_text("widget synergy\n", encoding="utf-8")
    root = site(tmp_path, {"index.html": page(body="<h1>Home</h1>\n<p>Widget Synergy</p>")})
    assert sitecheck.main(["--offline", "--json", "--banned-file", str(bf), str(root)]) == 1
    assert [f["check"] for f in json.loads(capsys.readouterr().out)] == ["banned-phrase"]
    with pytest.raises(SystemExit) as e:
        sitecheck.main(["--offline", "--banned-file", str(tmp_path / "nope.txt"), str(root)])
    assert e.value.code == 2


# -------------------------------------------------------------- internal-link

def test_resolution_rule(tmp_path):
    root = site(tmp_path, {"docs/index.html": page("docs"), "files/a.txt": "x", "img/logo.png": "x"})
    r = sitecheck.resolve
    assert r(root, "/about") == "about.html"          # P + .html
    assert r(root, "/about.html") == "about.html"     # P as a file
    assert r(root, "/docs") == "docs/index.html"      # P/index.html
    assert r(root, "/docs/") == "docs/index.html"
    assert r(root, "/") == "index.html"
    assert r(root, "/files/a.txt") == "files/a.txt"
    assert r(root, "/img/logo.png") == "img/logo.png"
    assert r(root, "/nope") is None
    assert r(root, "/../../etc/passwd") is None
    assert r(root, "/files") is None                  # a directory without an index


def test_internal_links_that_resolve_stay_quiet(tmp_path):
    hrefs = ["/contact", "contact.html", "/about?x=1#team", "/about#top", f"https://{HOST}/about",
             f"https://{HOST}/", "#top", "", "mailto:a@example.com", "tel:+0000", "javascript:void(0)",
             "data:text/plain;base64,AA==", "/docs/", "docs/"]
    root = site(tmp_path, {"index.html": page(body="<h1>Home</h1>\n" + "\n".join(f'<a href="{h}">x</a>' for h in hrefs)),
                           "docs/index.html": page("docs", nav="")})
    assert only(run(root), "internal-link") == []


def test_broken_internal_links_fail_with_their_line(tmp_path):
    body = ('<h1>Home</h1>\n<a href="/missing">a</a>\n<img src="img/ghost.png">\n'
            f'<a href="https://{HOST}/gone">b</a>\n<script src="/app.js"></script>\n<a href="../../../etc/passwd">c</a>')
    fs = only(run(site(tmp_path, {"index.html": page(body=body)})), "internal-link")
    assert [(f.level, f.line) for f in fs] == [("FAIL", BODY_LINE + i) for i in (1, 2, 3, 4, 5)]


def test_relative_links_resolve_against_the_page_directory(tmp_path):
    body = '<h1>Docs</h1>\n<a href="../about">ok</a>\n<a href="intro">ok</a>\n<a href="../nope">bad</a>\n<a href="about">bad</a>'
    root = site(tmp_path, {"docs/index.html": page("docs", body=body, nav=""), "docs/intro.html": page("intro", nav="", skip=("canonical",))})
    assert [f.line for f in only(run(root), "internal-link")] == [BODY_LINE - 1 + 4, BODY_LINE - 1 + 5]


def test_head_asset_links_are_checked(tmp_path):
    ok = site(tmp_path, {"index.html": page(extra_head='<link rel="stylesheet" href="/style.css">'), "style.css": "a{}"})
    assert only(run(ok), "internal-link") == []
    bad = site(tmp_path, {"index.html": page(extra_head='<link rel="stylesheet" href="/style.css">')}, name="t")
    assert len(only(run(bad), "internal-link")) == 1


# -------------------------------------------------------------- external-link

def test_external_link_ok_is_quiet_and_request_is_browser_like(tmp_path, net):
    n = net()
    assert only(run(links_site(tmp_path, ["https://example.com/ok"]), offline=False), "external-link") == []
    req, timeout = n.requests[0]
    assert n.calls == ["https://example.com/ok"]
    assert req.get_method() == "GET" and req.data is None
    assert req.get_header("User-agent").startswith("Mozilla/5.0")
    assert timeout == 10
    assert n.resps[0].asked == 64 * 1024


@pytest.mark.parametrize("code", [404, 410, 500])
def test_external_4xx_5xx_fails(tmp_path, net, code):
    net({"https://example.com/x": [code]})
    fs = only(run(links_site(tmp_path, ["https://example.com/x"]), offline=False), "external-link")
    assert [(f.level, f.path, f.line) for f in fs] == [("FAIL", "index.html", BODY_LINE + 1)]
    assert f"HTTP {code}" in fs[0].message


def test_external_gets_exactly_one_retry(tmp_path, net):
    n = net({"https://example.com/flaky": [500, 200], "https://example.com/down": [503]})
    root = links_site(tmp_path, ["https://example.com/flaky", "https://example.com/down"])
    fs = only(run(root, offline=False), "external-link")
    assert [f.level for f in fs] == ["FAIL"] and "/down" in fs[0].message
    assert sorted(n.calls) == ["https://example.com/down"] * 2 + ["https://example.com/flaky"] * 2


def test_external_timeout_warns_and_network_error_fails(tmp_path, net):
    n = net({"https://example.com/slow": ["timeout"], "https://example.com/dead": ["dns"]})
    fs = only(run(links_site(tmp_path, ["https://example.com/slow", "https://example.com/dead"]), offline=False), "external-link")
    by_url = {f.message.split()[0]: f.level for f in fs}
    assert by_url == {"https://example.com/slow": "WARN", "https://example.com/dead": "FAIL"}
    assert n.calls.count("https://example.com/slow") == 2


@pytest.mark.parametrize("url", ["https://cal.com/team/intro", "https://x.com/someone",
                                 "https://www.instagram.com/someone/", "https://www.linkedin.com/company/example"])
@pytest.mark.parametrize("code", [403, 429])
def test_bot_blocking_hosts_warn_on_403_and_429(tmp_path, net, url, code):
    net({url: [code]})
    fs = only(run(links_site(tmp_path, [url]), offline=False), "external-link")
    assert [f.level for f in fs] == ["WARN"]


def test_bot_hosts_still_fail_on_404_and_other_hosts_fail_on_403(tmp_path, net):
    net({"https://cal.com/gone": [404], "https://example.com/private": [403], "https://notcal.com/x": [403]})
    urls = ["https://cal.com/gone", "https://example.com/private", "https://notcal.com/x"]
    fs = only(run(links_site(tmp_path, urls), offline=False), "external-link")
    assert [f.level for f in fs] == ["FAIL"] * 3


def test_external_urls_are_fetched_once_across_repos_and_reported_everywhere(tmp_path, net):
    n = net({"https://example.com/shared": [404]})
    a = links_site(tmp_path, ["https://example.com/shared#one", "https://example.com/shared#two"], name="a")
    b = links_site(tmp_path, ["https://example.com/shared"], name="b")
    fs = only(run(a, b, offline=False), "external-link")
    assert n.calls == ["https://example.com/shared"] * 2  # one fetch plus its one retry, not one per link
    assert sorted((f.repo, f.line) for f in fs) == sorted([(str(a), BODY_LINE + 1), (str(a), BODY_LINE + 2), (str(b), BODY_LINE + 1)])


def test_external_check_skips_own_host_mailto_and_origin_hints_and_handles_protocol_relative(tmp_path, net):
    n = net()
    extra = '<link rel="preconnect" href="https://fonts.example.com"><link rel="dns-prefetch" href="//cdn2.example.com">'
    body = f'<h1>Home</h1>\n<a href="https://{HOST}/about">own</a>\n<script src="//cdn.example.com/x.js"></script>'
    run(site(tmp_path, {"index.html": page(body=body, extra_head=extra)}), offline=False)
    assert n.calls == ["https://cdn.example.com/x.js"]


def test_offline_makes_zero_network_calls(tmp_path, monkeypatch, capsys):
    calls = []

    def forbidden(*a, **k):
        calls.append(a)
        raise AssertionError("network used with --offline")
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    root = links_site(tmp_path, ["https://example.com/a", "https://www.linkedin.com/in/x"])
    assert only(run(root, offline=True), "external-link") == []
    assert sitecheck.main(["--offline", str(root)]) == 0
    assert calls == []


def test_external_check_does_use_the_network_when_online(tmp_path, net):
    n = net()
    run(links_site(tmp_path, ["https://example.com/a"]), offline=False)
    assert n.calls == ["https://example.com/a"]


# --------------------------------------------------------------------- robots

def robots_findings(tmp_path, text, **kw):
    return only(run(site(tmp_path, {"robots.txt": text}, **kw)), "robots")


def test_robots_missing_fails(tmp_path):
    fs = only(run(site(tmp_path, {"robots.txt": None})), "robots")
    assert [(f.level, f.path) for f in fs] == [("FAIL", "robots.txt")]


def test_robots_good_is_quiet(tmp_path):
    assert robots_findings(tmp_path, GOOD_ROBOTS) == []


def test_robots_needs_a_sitemap_line_with_the_sitemap_xml_path(tmp_path):
    for i, text in enumerate(["User-agent: *\nAllow: /\n", f"User-agent: *\nSitemap: https://{HOST}/other.xml\n"]):
        fs = robots_findings(tmp_path, text, name=f"s{i}")
        assert [f.level for f in fs] == ["FAIL"] and "Sitemap" in fs[0].message
    assert robots_findings(tmp_path, f"sitemap: https://{HOST}/sitemap.xml\n", name="lower") == []


def test_robots_sitemap_host_mismatch_warns(tmp_path):
    fs = robots_findings(tmp_path, "User-agent: *\nSitemap: https://other.example/sitemap.xml\n")
    assert [(f.level, f.line) for f in fs] == [("WARN", 2)]


@pytest.mark.parametrize("text", [
    f"User-agent: *\nDisallow: /\nSitemap: https://{HOST}/sitemap.xml\n",
    f"user-agent: *\nDISALLOW: /  # everything\nSitemap: https://{HOST}/sitemap.xml\n",
    f"User-agent: BadBot\nUser-agent: *\nDisallow: /\nSitemap: https://{HOST}/sitemap.xml\n",
])
def test_robots_whole_site_block_under_star_fails(tmp_path, text):
    fs = [f for f in robots_findings(tmp_path, text) if f.level == "FAIL"]
    assert len(fs) == 1 and "whole site" in fs[0].message


@pytest.mark.parametrize("text", [
    f"User-agent: BadBot\nDisallow: /\n\nUser-agent: *\nAllow: /\nSitemap: https://{HOST}/sitemap.xml\n",
    f"User-agent: *\nAllow: /\nUser-agent: BadBot\nDisallow: /\nSitemap: https://{HOST}/sitemap.xml\n",
    f"User-agent: *\nDisallow: /private\nDisallow:\nSitemap: https://{HOST}/sitemap.xml\n",
])
def test_robots_partial_blocks_and_other_agents_are_fine(tmp_path, text):
    assert robots_findings(tmp_path, text) == []


# -------------------------------------------------------------------- sitemap

def sm_findings(tmp_path, xml, extra=None, **kw):
    return only(run(site(tmp_path, {"sitemap.xml": xml, **(extra or {})}, **kw)), "sitemap")


def test_sitemap_missing_or_malformed_fails(tmp_path):
    fs = only(run(site(tmp_path, {"sitemap.xml": None})), "sitemap")
    assert [(f.level, f.path) for f in fs] == [("FAIL", "sitemap.xml")]
    broken = f'<?xml version="1.0"?>\n<urlset xmlns="{sitecheck.SITEMAP_NS}">\n<url><loc>x</loc>\n'
    fs = sm_findings(tmp_path, broken, name="t")
    assert [f.level for f in fs] == ["FAIL"] and "well-formed" in fs[0].message


@pytest.mark.parametrize("ns", ["http://example.com/not-sitemaps", ""])
def test_sitemap_wrong_namespace_fails(tmp_path, ns):
    fs = sm_findings(tmp_path, sitemap_xml(GOOD_ENTRIES, ns=ns))
    assert any(f.level == "FAIL" and "namespace" in f.message for f in fs)


def test_sitemap_loc_contact_resolves_to_contact_html(tmp_path):
    xml = sitemap_xml([("/", None), ("/about", None), ("/contact", None)])
    assert sm_findings(tmp_path, xml) == []


def test_sitemap_loc_problems_fail_on_their_own_line(tmp_path):
    xml = sitemap_xml([("/", None), ("/ghost", None), ("https://other.example/about", None), ("/about", None),
                       ("/contact", None)])
    fs = [f for f in sm_findings(tmp_path, xml) if f.level == "FAIL"]
    assert sorted((f.line, f.message.split()[0]) for f in fs) == [(4, "loc"), (5, "loc")]
    assert "does not resolve" in fs[0].message and "not on host" in fs[1].message


def test_sitemap_loc_must_be_absolute(tmp_path):
    fs = sm_findings(tmp_path, sitemap_xml([("https://", None)]).replace("https://</loc>", "/about</loc>"))
    assert any(f.level == "FAIL" and "absolute" in f.message for f in fs)


@pytest.mark.parametrize("value", ["2026-01-05", "2026-01-05T10:00:00Z", "2026-01-05T10:00:00+05:30",
                                   "2026-01-05T10:00", "2026-01-05T10:00:00.250Z",
                                   datetime.datetime.now(datetime.timezone.utc).date().isoformat()])
def test_sitemap_good_lastmod_is_quiet(tmp_path, value):
    xml = sitemap_xml([("/", value), ("/about", value), ("/contact", value)])
    assert sm_findings(tmp_path, xml) == []


@pytest.mark.parametrize("value", ["06/10/2026", "2026-13-45", "yesterday", "2026-01-05 10:00:00", "20260105",
                                   "2999-01-01", "2999-01-01T00:00:00Z"])
def test_sitemap_bad_or_future_lastmod_fails(tmp_path, value):
    xml = sitemap_xml([("/", value), ("/about", None), ("/contact", None)])
    fs = sm_findings(tmp_path, xml)
    assert [(f.level, f.line) for f in fs] == [("FAIL", 3)] and "lastmod" in fs[0].message


def test_indexable_page_missing_from_sitemap_warns(tmp_path):
    fs = sm_findings(tmp_path, sitemap_xml(GOOD_ENTRIES), extra={"orphan.html": page("orphan")})
    assert [(f.level, f.path) for f in fs] == [("WARN", "orphan.html")]


def test_sitemap_skips_noindex_and_404_pages(tmp_path):
    noindex = page("orphan", extra_head='<meta name="robots" content="NOINDEX, nofollow">')
    extra = {"orphan.html": noindex, "404.html": page("404")}
    assert sm_findings(tmp_path, sitemap_xml(GOOD_ENTRIES), extra=extra) == []


def test_sitemap_hosts_are_per_repo(tmp_path):
    a = site(tmp_path, name="a", cname="a.example")
    b = site(tmp_path, name="b", cname="b.example")
    fs = run(a, b)
    assert {(f.repo, f.check) for f in fs if f.level == "FAIL"} >= {(str(a), "sitemap"), (str(b), "sitemap")}


# ------------------------------------------------------------------- headings

def heading_findings(tmp_path, body, **kw):
    return only(run(site(tmp_path, {"index.html": page(body=body, **kw)})), "headings")


def test_headings_good_page_is_quiet(tmp_path):
    body = "<h1>A</h1><h2>B</h2><h3>C</h3><h2>D</h2><h3>E</h3><h2>F</h2>"
    assert heading_findings(tmp_path, body) == []


@pytest.mark.parametrize("body, text", [("<p>none</p>", "0 h1"), ("<h1>A</h1>\n<h1>B</h1>", "2 h1")])
def test_headings_h1_count_is_info(tmp_path, body, text):
    fs = heading_findings(tmp_path, body)
    assert [f.level for f in fs] == ["INFO"] and text in fs[0].message


def test_headings_level_skip_is_info_with_line(tmp_path):
    fs = heading_findings(tmp_path, "<h1>A</h1>\n<h2>B</h2>\n<h4>C</h4>")
    assert [(f.level, f.line) for f in fs] == [("INFO", BODY_LINE + 2)] and "h2 to h4" in fs[0].message


def test_headings_skip_redirect_stubs(tmp_path):
    stub = '<!doctype html><meta http-equiv="refresh" content="0; url=/about"><p>Moved.</p>'
    root = site(tmp_path, {"old.html": stub})
    assert only(run(root), "headings") == []


# ----------------------------------------------------------------------- meta

@pytest.mark.parametrize("skip, what", [("title", "<title>"), ("description", "meta description"),
                                        ("og", "og:image"), ("canonical", "canonical link")])
def test_meta_missing_piece_warns(tmp_path, skip, what):
    fs = only(run(site(tmp_path, {"about.html": page("about", skip=(skip,))})), "meta")
    assert [(f.level, f.path, f.message) for f in fs] == [("WARN", "about.html", f"missing {what}")]


def test_meta_empty_title_counts_as_missing_and_variants_are_accepted(tmp_path):
    fs = only(run(site(tmp_path, {"about.html": page("about", skip=("title",), extra_head="<title>  </title>")})), "meta")
    assert [f.message for f in fs] == ["missing <title>"]
    variant = page("about", skip=("og", "canonical"),
                   extra_head=f'<meta name="og:image" content="https://{HOST}/og.png">'
                              f'<link rel="Canonical" href="https://{HOST}/about">')
    assert only(run(site(tmp_path, {"about.html": variant}, name="t")), "meta") == []


def test_meta_skips_noindex_pages_redirect_stubs_and_404(tmp_path):
    bare = "<!doctype html><title>x</title><h1>x</h1>"
    noindex = '<!doctype html><meta name="robots" content="noindex"><h1>x</h1>'
    stub = '<!doctype html><meta http-equiv="refresh" content="0; url=/about">'
    root = site(tmp_path, {"hidden.html": noindex, "old.html": stub, "404.html": bare})
    assert only(run(root), "meta") == []


# ----------------------------------------------------------------------- cname

def test_cname_is_read_from_the_first_line(tmp_path):
    for text, want in [("Site.Example\nignored.example\n", "site.example"), ("  site.example  \n", "site.example"),
                       ("https://Site.Example/\n", "site.example"), ("", None)]:
        root = tmp_path / "c"
        root.mkdir(exist_ok=True)
        (root / "CNAME").write_text(text)
        assert sitecheck.read_cname(root) == want
    assert sitecheck.read_cname(tmp_path / "missing") is None


def test_without_cname_host_checks_are_skipped_with_one_info(tmp_path):
    xml = sitemap_xml([("https://anywhere.example/", None), ("https://anywhere.example/about", None),
                       ("https://anywhere.example/contact", None)])
    root = site(tmp_path, {"sitemap.xml": xml, "robots.txt": "User-agent: *\nSitemap: https://anywhere.example/sitemap.xml\n"},
                cname=None)
    fs = run(root)
    assert [(f.level, f.check) for f in fs] == [("INFO", "cname")]


# ------------------------------------------------------------------------ CLI

def test_exit_code_is_1_with_a_fail_and_0_without(tmp_path, capsys):
    good = site(tmp_path, name="good")
    bad = site(tmp_path, {"index.html": page(body=f"<h1>Home</h1>\n<p>a {EM} b</p>")}, name="bad")
    assert sitecheck.main(["--offline", str(good)]) == 0
    assert sitecheck.main(["--offline", str(bad)]) == 1
    assert sitecheck.main(["--offline", str(good), str(bad)]) == 1


def test_warn_and_info_alone_do_not_fail_the_run(tmp_path):
    root = site(tmp_path, {"about.html": page("about", skip=("og",), body="<p>no h1</p>")})
    fs = run(root)
    assert {f.level for f in fs} == {"WARN", "INFO"}
    assert sitecheck.main(["--offline", str(root)]) == 0


def test_json_output_is_a_list_of_findings(tmp_path, capsys):
    root = site(tmp_path, {"index.html": page(body=f"<h1>Home</h1>\n<p>a {EM} b</p>")})
    assert sitecheck.main(["--offline", "--json", str(root)]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data == [{"repo": str(root), "level": "FAIL", "check": "em-dash", "path": "index.html",
                     "line": BODY_LINE + 1, "message": "em dash (U+2014)"}]
    assert sitecheck.main(["--offline", "--json", str(site(tmp_path, name="clean"))]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_human_report_groups_by_repo_then_level_and_ends_with_a_summary(tmp_path, capsys):
    a = site(tmp_path, name="a", cname="a.example")
    b = site(tmp_path, {"index.html": page("index", skip=("og",), body=f"<h1>Home</h1>\n<h3>x</h3>\n<p>a {EM} b</p>")},
             name="b")
    sitecheck.main(["--offline", str(a), str(b)])
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"== {a} ==" and lines.count(f"== {b} ==") == 1
    # repo a has only the sitemap host mismatch to report; find b's block and check level order
    block = lines[lines.index(f"== {b} =="):]
    order = [ln.split()[0] for ln in block if ln.split() and ln.split()[0] in ("FAIL", "WARN", "INFO")]
    assert order[:3] == ["FAIL", "WARN", "INFO"]
    assert any("[em-dash] index.html:9" in ln for ln in block)
    assert lines[-1].startswith("FAIL ") and f" {DOT} WARN " in lines[-1] and f" {DOT} INFO " in lines[-1]


def test_summary_line_counts(tmp_path, capsys):
    root = site(tmp_path, {"index.html": page(skip=("og",), body=f"<h1>Home</h1>\n<h3>x</h3>\n<p>a {EM} b</p>")})
    sitecheck.main(["--offline", str(root)])
    assert capsys.readouterr().out.splitlines()[-1] == f"FAIL 1 {DOT} WARN 1 {DOT} INFO 1"


def test_clean_repo_is_labelled_clean(tmp_path, capsys):
    root = site(tmp_path)
    sitecheck.main(["--offline", str(root)])
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"== {root} == clean" and out[-1] == f"FAIL 0 {DOT} WARN 0 {DOT} INFO 0"


def test_missing_repo_dir_is_a_usage_error(tmp_path):
    with pytest.raises(SystemExit) as e:
        sitecheck.main(["--offline", str(tmp_path / "nope")])
    assert e.value.code == 2


def test_runs_as_a_script(tmp_path):
    root = site(tmp_path)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    done = subprocess.run([sys.executable, str(TOOL), "--offline", str(root)],
                          capture_output=True, text=True, env=env)
    assert done.returncode == 0 and "clean" in done.stdout


# ----------------------------------------------------- host override (added in syahi-labs/site)
# A build's output directories hold no CNAME file, so the build says which host a directory is for.

ABOUT_LINK = f'<h1>Home</h1><p><a href="https://{HOST}/missing">Missing</a></p>'


def test_a_host_override_stands_in_for_the_cname_file(tmp_path):
    root = site(tmp_path, {"index.html": page("index", ABOUT_LINK)}, cname=None)
    assert only(sitecheck.run([str(root)], offline=True, host=HOST), "internal-link", "FAIL")
    assert only(sitecheck.run([str(root)], offline=True, host=HOST), "cname") == []
    # without it the same repo has no host: the link is not known to be internal, and one INFO says so
    assert only(run(root), "internal-link") == [] and [f.check for f in only(run(root), "cname")] == ["cname"]


def test_a_host_override_beats_the_cname_file(tmp_path):
    root = site(tmp_path, {"index.html": page("index", ABOUT_LINK)}, cname="other.example")
    assert only(run(root), "internal-link") == []
    assert only(sitecheck.run([str(root)], offline=True, host=HOST), "internal-link", "FAIL")


def test_a_host_override_is_case_insensitive(tmp_path):
    root = site(tmp_path, {"index.html": page("index", ABOUT_LINK)}, cname=None)
    assert only(sitecheck.run([str(root)], offline=True, host=HOST.upper()), "internal-link", "FAIL")


def test_a_host_override_also_checks_the_sitemap_and_robots_hosts(tmp_path):
    root = site(tmp_path, cname=None)
    fs = sitecheck.run([str(root)], offline=True, host="elsewhere.example")
    assert only(fs, "sitemap", "FAIL") and only(fs, "robots", "WARN")
    assert sitecheck.run([str(root)], offline=True, host=HOST) == []


def test_no_host_override_changes_nothing(tmp_path):
    root = site(tmp_path)
    assert sitecheck.run([str(root)], offline=True) == sitecheck.run([str(root)], offline=True, host=None)
