# tests/test_pipeline_checks.py: the checks that run inside every build (Task 8)
import pytest

from checks import sitecheck
from sitebuild.pipeline import BuildResult, build

EM = chr(0x2014)
FRONT = "---\ntitle: T\ndescription: d\nupdated: 2026-10-06\napproved: 2026-10-06\nlayout: page\n{extra}---\n"


def add_page(root, rel, body, extra="", base="content"):
    path = root / base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(FRONT.format(extra=extra) + body + "\n", encoding="utf-8")
    return path


def built(root, tmp_path, release=False):
    return build(root, tmp_path / "dist", release=release)


def naming(items, *needles):
    """The items that carry every needle."""
    return [i for i in items if all(n in i for n in needles)]


# ---- the fixture is clean, and what is not an error is a warning ----

def test_a_build_result_has_no_warnings_until_something_adds_one():
    assert BuildResult().warnings == []


def test_the_fixture_builds_with_no_problems_and_one_pending_tab_warning_per_page(mini_root, tmp_path):
    r = built(mini_root, tmp_path)
    assert r.problems == []
    assert len(r.warnings) == 3
    for page in ("404.html", "index.html", "signet.html"):
        (warning,) = naming(r.warnings, f"syahi.sh/{page}")
        assert "/services" in warning and "pending" in warning and "internal-link" in warning


def test_warnings_are_the_same_on_every_run(mini_root, tmp_path):
    assert build(mini_root, tmp_path / "a").warnings == build(mini_root, tmp_path / "b").warnings


def test_a_pending_page_that_exists_is_unlisted_and_says_so_as_a_warning(mini_root, tmp_path):
    add_page(mini_root, "services.html", "<h1>Services draft</h1>")
    r = built(mini_root, tmp_path)
    assert r.problems == []
    assert naming(r.warnings, "services.html", "sitemap")


# ---- the copy check runs on every rendered page ----

def test_a_copy_problem_is_a_problem_naming_the_page(mini_root, tmp_path):
    page = add_page(mini_root, "dash.html", f"<h1>Dash</h1><p>a {EM} b</p>")
    (problem,) = naming(built(mini_root, tmp_path).problems, str(page), "em-dash", "copycheck")
    assert EM not in problem


@pytest.mark.parametrize("body, rule", [
    ("<p>We leverage data.</p>", "buzzword"),
    ("<p>It's not a tool, it's a teammate.</p>", "contrast-framing"),
    ("<p>Fast, cheap and simple. Quotes, replies and follow-ups.</p>", "stacked-threes"),
])
def test_each_copy_rule_fails_the_build_through_the_pipeline(mini_root, tmp_path, body, rule):
    page = add_page(mini_root, "copy.html", "<h1>Copy</h1>" + body)
    assert naming(built(mini_root, tmp_path).problems, str(page), rule)


def test_the_copy_check_reads_main_only(mini_root, tmp_path):
    # the footer and header are the template's, so a buzzword there is not the page's copy
    edit = mini_root / "templates" / "base.html"
    edit.write_text(edit.read_text(encoding="utf-8").replace("Skip to content", "Leverage menu"), encoding="utf-8")
    assert [p for p in built(mini_root, tmp_path).problems if "buzzword" in p] == []


def test_the_page_audience_reaches_the_copy_check(mini_root, tmp_path):
    owner = add_page(mini_root, "owner.html", "<h1>AI answers your enquiries</h1>", extra="audience: owner\n")
    other = add_page(mini_root, "other.html", "<h1>AI answers your enquiries</h1>")
    problems = built(mini_root, tmp_path).problems
    assert naming(problems, str(owner), "owner-first-line")
    assert not naming(problems, str(other), "owner-first-line")


def test_the_katha_host_is_checked_too(mini_root, tmp_path):
    page = add_page(mini_root, "index.html", f"<h1>Katha</h1><p>a {EM} b</p>", base="katha/content")
    assert naming(built(mini_root, tmp_path).problems, str(page), "em-dash")


def test_the_404_is_checked_too(mini_root, tmp_path):
    page = mini_root / "content" / "404.html"
    page.write_text(page.read_text(encoding="utf-8").replace("<h1>Not found</h1>", "<h1>Not found</h1><h1>Again</h1>"), encoding="utf-8")
    assert naming(built(mini_root, tmp_path).problems, str(page), "one-h1")


# ---- the HTML checks run on every rendered page ----

@pytest.mark.parametrize("body, rule", [
    ("<h1>a</h1><h1>b</h1>", "one-h1"),
    ("<h1>a</h1><h3>b</h3>", "heading-order"),
    ("<h1>a</h1><p>स्याही</p>", "lang-hi"),
    ("<h1>a</h1><p>Only 5 owners.</p>", "numbers-from-claims"),
    ("<h1>a</h1><p><b>x</p></b>", "balanced"),
    ("<p>No heading at all.</p>", "one-h1"),
])
def test_each_html_rule_fails_the_build_through_the_pipeline(mini_root, tmp_path, body, rule):
    page = add_page(mini_root, "markup.html", body)
    assert naming(built(mini_root, tmp_path).problems, str(page), rule, "htmlcheck")


def test_what_the_html_rules_allow_builds_clean(mini_root, tmp_path):
    add_page(mini_root, "allowed.html", (
        '<h1>a</h1><p><span lang="hi">स्याही</span> <time datetime="2026-10-06">6 Oct</time></p>'
        '<div data-sample><p>09:14 draft</p></div><p>Run <code>build 2</code>.</p>'
        "<h2>b</h2><p>{{ claim('signet-price-line') }}</p>"), extra="claims: [signet-price-line]\n")
    assert built(mini_root, tmp_path).problems == []


# ---- sitecheck runs over each host directory ----

def test_a_dead_internal_link_is_a_problem_naming_the_output_file_and_line(mini_root, tmp_path):
    add_page(mini_root, "links.html", '<h1>Links</h1><p><a href="/nowhere">x</a></p>')
    (problem,) = naming(built(mini_root, tmp_path).problems, "syahi.sh/links.html:", "internal-link", "/nowhere")
    assert "sitecheck" in problem


def test_each_host_directory_is_checked_with_its_own_host(mini_root, tmp_path):
    # Output directories hold no CNAME, so a link to the site's own absolute URL is only seen as
    # internal when the build passes the host. A dead one must fail, a live one must not.
    add_page(mini_root, "own.html", '<h1>Own</h1><p><a href="https://syahi.example/nowhere">x</a> <a href="https://syahi.example/signet">y</a></p>')
    add_page(mini_root, "index.html", '<h1>Katha</h1><p><a href="https://katha.example/gone">x</a></p>', base="katha/content")
    problems = built(mini_root, tmp_path).problems
    assert len(naming(problems, "syahi.sh/own.html", "https://syahi.example/nowhere")) == 1
    assert not naming(problems, "https://syahi.example/signet")
    assert naming(problems, "katha.syahi.sh/index.html", "https://katha.example/gone")


def test_the_base_url_host_is_what_is_passed_not_the_directory_name(mini_root, tmp_path, monkeypatch):
    seen = []
    real = sitecheck.run
    monkeypatch.setattr(sitecheck, "run", lambda repos, **kw: seen.append((repos, kw)) or real(repos, **kw))
    built(mini_root, tmp_path)
    assert sorted((r[0].name, kw["host"], kw["offline"]) for r, kw in seen) == [
        ("katha.syahi.sh", "katha.example", True), ("syahi.sh", "syahi.example", True)]


def test_the_build_never_touches_the_network(mini_root, tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the build touched the network")
    monkeypatch.setattr(sitecheck, "fetch", refuse)
    monkeypatch.setattr(sitecheck.urllib.request, "urlopen", refuse)
    add_page(mini_root, "ext.html", '<h1>Ext</h1><p><a href="https://elsewhere.example/page">x</a></p>')
    assert built(mini_root, tmp_path).problems == []


def test_a_banned_phrase_in_the_output_is_a_problem(mini_root, tmp_path):
    add_page(mini_root, "banned.html", f"<h1>Banned</h1><p>The {sitecheck.BANNED_PHRASES[1]} app.</p>")
    assert naming(built(mini_root, tmp_path).problems, "syahi.sh/banned.html", "banned-phrase")


def test_an_em_dash_anywhere_in_the_output_is_a_problem(mini_root, tmp_path):
    # the page's own copy check reads main only; sitecheck reads the whole file, head included
    page = mini_root / "content" / "signet.html"
    page.write_text(page.read_text(encoding="utf-8").replace("title: Signet Example", f"title: Signet {EM} Example"), encoding="utf-8")
    assert naming(built(mini_root, tmp_path).problems, "syahi.sh/signet.html", "em-dash")


# ---- links to pending pages: a warning in dev, a problem in release ----

PENDING_FORMS = ["/services", "/services/", "/services.html", "/services#top", "https://syahi.example/services"]


@pytest.mark.parametrize("href", PENDING_FORMS)
def test_a_link_to_a_pending_page_is_a_warning_in_a_dev_build(mini_root, tmp_path, href):
    add_page(mini_root, "pend.html", f'<h1>Pend</h1><p><a href="{href}">s</a></p>')
    r = built(mini_root, tmp_path)
    assert r.problems == []
    assert naming(r.warnings, "syahi.sh/pend.html", "internal-link", "pending page")


@pytest.mark.parametrize("href", PENDING_FORMS)
def test_a_link_to_a_pending_page_is_a_problem_in_a_release_build(mini_root, tmp_path, href):
    add_page(mini_root, "pend.html", f'<h1>Pend</h1><p><a href="{href}">s</a></p>')
    r = built(mini_root, tmp_path, release=True)
    assert naming(r.problems, "syahi.sh/pend.html", "sitecheck", "internal-link")
    assert not naming(r.warnings, "internal-link")


def test_only_the_pending_target_is_downgraded(mini_root, tmp_path):
    add_page(mini_root, "mixed.html", '<h1>Mixed</h1><p><a href="/services">s</a> <a href="/nowhere">n</a></p>')
    r = built(mini_root, tmp_path)
    assert len(naming(r.problems, "syahi.sh/mixed.html", "internal-link")) == 1 and naming(r.problems, "/nowhere")
    assert naming(r.warnings, "syahi.sh/mixed.html", "/services")


def test_a_dead_link_with_a_quote_in_it_is_a_problem_not_a_crash(mini_root, tmp_path):
    add_page(mini_root, "quote.html", '<h1>Quote</h1><p><a href="/it\'s-gone">x</a></p>')
    assert naming(built(mini_root, tmp_path).problems, "syahi.sh/quote.html", "internal-link")


def test_a_page_that_is_not_pending_is_never_downgraded(mini_root, tmp_path):
    (mini_root / "site.yaml").write_text(
        (mini_root / "site.yaml").read_text(encoding="utf-8").replace("pending_pages: [/services]", "pending_pages: [/media]"), encoding="utf-8")
    r = built(mini_root, tmp_path)
    assert naming(r.problems, "internal-link", "/services") and r.warnings == []
