# tests/test_pipeline.py
import hashlib
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from asset_urls import hashed_file
from sitebuild import pipeline
from sitebuild.pipeline import MARKER, MARKER_TEXT, BuildResult, build

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def tree_hash(d: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(d.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(d)).encode()); h.update(p.read_bytes())
    return h.hexdigest()

def test_outputs_and_layout(mini_root, tmp_path):
    r = build(mini_root, tmp_path / "dist")
    assert r.problems == []
    s = tmp_path / "dist" / "syahi.sh"
    for f in ["index.html", "signet.html", "404.html", "sitemap.xml", "robots.txt", "llms.txt"]:
        assert (s / f).is_file(), f
    k = tmp_path / "dist" / "katha.syahi.sh"
    assert (k / "index.html").is_file()
    assert not list((tmp_path / "dist").rglob("feed.xml")) and not list((tmp_path / "dist").rglob("CNAME"))

def test_deterministic(mini_root, tmp_path):
    build(mini_root, tmp_path / "a"); build(mini_root, tmp_path / "b")
    assert tree_hash(tmp_path / "a") == tree_hash(tmp_path / "b")

def test_release_fails_with_pending_pages(mini_root, tmp_path):
    r = build(mini_root, tmp_path / "dist", release=True)
    assert any("pending" in p for p in r.problems)

def test_listed_but_unused_claim_is_a_problem(mini_root, tmp_path):
    sig = mini_root / "content" / "signet.html"
    sig.write_text(sig.read_text(encoding="utf-8").replace("claims: [", "claims: [org-name, ", 1), encoding="utf-8")
    r = build(mini_root, tmp_path / "dist")
    assert any("org-name" in p for p in r.problems)

# ---- beyond the brief: the contract it states in prose ----

def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not in {path}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

def sitemap_locs(path: Path) -> list[str]:
    return [u.find(SITEMAP_NS + "loc").text for u in ET.fromstring(path.read_bytes())]

def test_the_result_names_both_hosts_and_their_pages(mini_root, tmp_path):
    r = build(mini_root, tmp_path / "dist")
    assert isinstance(r, BuildResult)
    assert r.outputs == {"syahi.sh": tmp_path / "dist" / "syahi.sh", "katha.syahi.sh": tmp_path / "dist" / "katha.syahi.sh"}
    assert sorted(p.slug for p in r.pages) == ["/", "/", "/404", "/signet"]

def test_a_previous_builds_output_is_wiped_first(mini_root, tmp_path):
    out = tmp_path / "dist"
    assert build(mini_root, out).problems == []
    (out / "syahi.sh" / "stale.html").write_text("old", encoding="utf-8")
    (out / "syahi.sh" / "assets" / "stale.css").write_text("old", encoding="utf-8")
    (out / "katha.syahi.sh" / "deep").mkdir()
    (out / "katha.syahi.sh" / "deep" / "stale.html").write_text("old", encoding="utf-8")
    assert build(mini_root, out).problems == []
    assert not list(out.rglob("stale.*")) and not (out / "katha.syahi.sh" / "deep").exists()
    assert (out / "syahi.sh" / "index.html").is_file()

def test_the_output_does_not_depend_on_where_the_tree_lives(mini_root, tmp_path):
    elsewhere = tmp_path / "a" / "much" / "deeper" / "copy"
    shutil.copytree(mini_root, elsewhere)
    build(mini_root, tmp_path / "one"); build(elsewhere, tmp_path / "two")
    assert tree_hash(tmp_path / "one") == tree_hash(tmp_path / "two")

def test_a_rebuild_over_an_existing_out_is_identical(mini_root, tmp_path):
    out = tmp_path / "dist"
    build(mini_root, out); first = tree_hash(out)
    build(mini_root, out)
    assert tree_hash(out) == first

def test_the_katha_host_layout(mini_root, tmp_path):
    out = tmp_path / "dist" / "katha.syahi.sh"
    assert build(mini_root, tmp_path / "dist").problems == []
    for f in ["index.html", "robots.txt", "sitemap.xml"]:
        assert (out / f).is_file(), f
    assert hashed_file(out, "tokens.css").is_file() and hashed_file(out, "base.css").is_file()
    assert not (out / "llms.txt").exists() and not (out / "404.html").exists()
    assert sitemap_locs(out / "sitemap.xml") == ["https://katha.example/"]

def test_the_katha_header_branch_and_its_own_chrome(mini_root, tmp_path):
    build(mini_root, tmp_path / "dist")
    katha = (tmp_path / "dist" / "katha.syahi.sh" / "index.html").read_text(encoding="utf-8")
    main = (tmp_path / "dist" / "syahi.sh" / "index.html").read_text(encoding="utf-8")
    assert 'class="wordmark wordmark-katha" href="/">Katha Audio</a>' in katha
    assert 'href="https://listen.example/katha"' in katha and "https://cal.example/book" not in katha
    assert "wordmark-katha" not in main and ">Syahi</a>" in main
    assert "LLPIN AAA-0000" in katha  # the same footer

def test_each_host_has_its_own_robots(mini_root, tmp_path):
    build(mini_root, tmp_path / "dist")
    assert (tmp_path / "dist" / "syahi.sh" / "robots.txt").read_text(encoding="utf-8").endswith("Sitemap: https://syahi.example/sitemap.xml\n")
    assert (tmp_path / "dist" / "katha.syahi.sh" / "robots.txt").read_text(encoding="utf-8").endswith("Sitemap: https://katha.example/sitemap.xml\n")

def test_pages_are_written_at_their_clean_url_paths(mini_root, tmp_path):
    (mini_root / "content" / "deep").mkdir()
    (mini_root / "content" / "deep" / "page.html").write_text(
        "---\ntitle: Deep\ndescription: d\nupdated: 2026-10-06\napproved: 2026-10-06\nlayout: page\n---\n<h1>x</h1>\n", encoding="utf-8")
    assert build(mini_root, tmp_path / "dist").problems == []
    s = tmp_path / "dist" / "syahi.sh"
    assert (s / "deep" / "page.html").is_file() and (s / "signet.html").is_file() and (s / "index.html").is_file()
    assert "https://syahi.example/deep/page" in sitemap_locs(s / "sitemap.xml")

def test_the_sitemap_lists_live_pages_only(mini_root, tmp_path):
    # /services is pending and also has a file: it must still stay out of the sitemap and llms.txt.
    (mini_root / "content" / "services.html").write_text(
        "---\ntitle: Services Draft\ndescription: not live\nupdated: 2026-10-06\napproved: 2026-10-06\nlayout: page\n---\n<h1>x</h1>\n", encoding="utf-8")
    assert build(mini_root, tmp_path / "dist").problems == []
    s = tmp_path / "dist" / "syahi.sh"
    assert sitemap_locs(s / "sitemap.xml") == ["https://syahi.example/", "https://syahi.example/signet"]
    llms = (s / "llms.txt").read_text(encoding="utf-8")
    assert "services" not in llms.lower() and "404" not in llms and "/signet" in llms

def test_llms_txt_opens_with_the_summary_claim(mini_root, tmp_path):
    build(mini_root, tmp_path / "dist")
    llms = (tmp_path / "dist" / "syahi.sh" / "llms.txt").read_text(encoding="utf-8")
    assert llms.startswith("# Syahi\n\n> Example Studio is a made-up studio used to test the build.\n")
    assert "- [Signet Example](https://syahi.example/signet): A made-up product page for build tests.\n" in llms

def test_lastmod_is_the_git_date_when_tracked_and_the_updated_date_when_not(mini_root, tmp_path):
    stamp = "2026-09-01T10:00:00+05:30"
    env = dict(os.environ, GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    subprocess.run(["git", "init", "-q"], cwd=mini_root, check=True)
    subprocess.run(["git", "add", "content/signet.html"], cwd=mini_root, check=True)
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "c"], cwd=mini_root, check=True, env=env)
    assert build(mini_root, tmp_path / "dist").problems == []
    xml = (tmp_path / "dist" / "syahi.sh" / "sitemap.xml").read_text(encoding="utf-8")
    dates = dict(re.findall(r"<loc>https://syahi.example(/[a-z]*)</loc>\s*<lastmod>([0-9-]+)</lastmod>", xml))
    assert dates == {"/": "2026-10-06", "/signet": "2026-09-01"}

def test_the_404_is_written_as_404_html_with_no_structured_data(mini_root, tmp_path):
    build(mini_root, tmp_path / "dist")
    html = (tmp_path / "dist" / "syahi.sh" / "404.html").read_text(encoding="utf-8")
    assert "<h1>Not found</h1>" in html and "application/ld+json" not in html
    assert "application/ld+json" in (tmp_path / "dist" / "syahi.sh" / "signet.html").read_text(encoding="utf-8")

def test_every_stylesheet_the_pages_link_is_in_the_output(mini_root, tmp_path):
    build(mini_root, tmp_path / "dist")
    for host in ("syahi.sh", "katha.syahi.sh"):
        html = (tmp_path / "dist" / host / "index.html").read_text(encoding="utf-8")
        hrefs = re.findall(r'<link rel="stylesheet" href="(/[^"]+)"', html)
        assert hrefs, host
        for href in hrefs:
            assert (tmp_path / "dist" / host / href.lstrip("/")).is_file(), (host, href)

# ---- the checks feed problems, and nothing raises ----

def test_a_claim_shared_by_two_pages_is_not_flagged(mini_root, tmp_path):
    # `signet-name` is listed and rendered on the home page and on /signet. The check compares each page's
    # list with what that page rendered, not with what the build had not yet seen.
    for page in ("index.html", "signet.html"):
        assert "signet-name" in (mini_root / "content" / page).read_text(encoding="utf-8")
    assert build(mini_root, tmp_path / "dist").problems == []

def test_a_listed_claim_missing_from_the_register_names_the_id_and_the_page(mini_root, tmp_path):
    sig = mini_root / "content" / "signet.html"
    edit(sig, "claims: [", "claims: [no-such-claim, ")
    r = build(mini_root, tmp_path / "dist")
    assert any("no-such-claim" in p and str(sig) in p for p in r.problems)

def test_json_ld_the_page_does_not_show_is_a_problem_naming_the_page(mini_root, tmp_path):
    sig = mini_root / "content" / "signet.html"
    edit(sig, "<p>{{ claim('signet-price-line') }}</p>\n", "")
    edit(sig, "claims: [signet-name, signet-price-line]", "claims: [signet-name]")
    r = build(mini_root, tmp_path / "dist")
    assert any(str(sig) in p and "description" in p and "a month" in p for p in r.problems)

def test_a_page_that_cannot_render_is_a_problem_and_the_others_are_still_built(mini_root, tmp_path):
    sig = mini_root / "content" / "signet.html"
    edit(sig, "<h1>", "<h1>{{ claim('no-such-claim') }}")
    r = build(mini_root, tmp_path / "dist")
    assert any(str(sig) in p and "no-such-claim" in p for p in r.problems)
    assert (tmp_path / "dist" / "syahi.sh" / "index.html").is_file() and not (tmp_path / "dist" / "syahi.sh" / "signet.html").exists()
    assert sitemap_locs(tmp_path / "dist" / "syahi.sh" / "sitemap.xml") == ["https://syahi.example/"]

@pytest.mark.parametrize("victim, named", [
    ("content/index.html", "index.html"),
    ("site.yaml", "site.yaml"),
    ("data/claims.yaml", "claims.yaml"),
    ("katha/site.yaml", "site.yaml"),
    ("katha/content/index.html", "index.html"),
])
def test_a_file_that_cannot_load_is_a_problem_naming_it(mini_root, tmp_path, victim, named):
    target = mini_root / victim
    target.write_text("{{ not front matter or yaml: [", encoding="utf-8")
    r = build(mini_root, tmp_path / "dist")
    assert any(str(target) in p for p in r.problems), (victim, r.problems)
    assert r.outputs == {}

def test_a_missing_katha_directory_is_a_problem(mini_root, tmp_path):
    shutil.rmtree(mini_root / "katha")
    r = build(mini_root, tmp_path / "dist")
    assert any("katha" in p for p in r.problems)

def test_each_host_must_declare_its_own_header(mini_root, tmp_path):
    edit(mini_root / "katha" / "site.yaml", "header: katha", "header: syahi")
    r = build(mini_root, tmp_path / "dist")
    assert any(str(mini_root / "katha" / "site.yaml") in p and "katha" in p for p in r.problems)

def test_content_is_validated_before_anything_else(tmp_path):
    (tmp_path / "content").mkdir()
    (tmp_path / "content" / "broken.html").write_text("<p>no front matter</p>", encoding="utf-8")
    r = build(tmp_path, tmp_path / "dist")
    assert str(tmp_path / "content" / "broken.html") in r.problems[0]

@pytest.mark.parametrize("unsafe", [".", "content", "templates", "katha", "katha/content", "site.yaml", "tokens/inner"])
def test_an_unsafe_out_is_refused_and_nothing_is_deleted(mini_root, unsafe):
    before = tree_hash(mini_root)
    r = build(mini_root, mini_root / unsafe)
    assert r.problems and r.outputs == {}
    assert tree_hash(mini_root) == before

def test_an_out_that_contains_the_root_is_refused(mini_root):
    r = build(mini_root, mini_root.parent)
    assert r.problems and (mini_root / "site.yaml").is_file()

# ---- the wipe: only a previous build's output, never anything else ----

def entries(d: Path) -> list[str]:
    return sorted(str(p.relative_to(d)) for p in d.rglob("*"))

def refuses(root: Path, out: Path):
    """Build into `out` and assert it was refused with a problem naming it, and that nothing was written."""
    r = build(root, out)
    assert r.outputs == {} and r.pages == []
    assert any(str(out) in p for p in r.problems), r.problems
    return r

def test_a_build_writes_the_marker_at_the_top_of_out_only(mini_root, tmp_path):
    build(mini_root, tmp_path / "dist")
    assert (tmp_path / "dist" / MARKER).read_text(encoding="utf-8") == MARKER_TEXT
    assert [p for p in (tmp_path / "dist").rglob(MARKER)] == [tmp_path / "dist" / MARKER]

@pytest.mark.parametrize("name", [".git", "sitebuild", "tests", "checks", "worker", "tools", ".venv", "dist-old"])
def test_a_directory_of_the_repo_is_never_wiped(mini_root, name):
    victim = mini_root / name
    victim.mkdir()
    (victim / "keep.txt").write_text("precious", encoding="utf-8")
    before = tree_hash(mini_root)
    refuses(mini_root, victim)
    assert tree_hash(mini_root) == before

def test_an_unrelated_non_empty_directory_outside_the_root_is_never_wiped(mini_root, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "sub").mkdir(parents=True)
    (elsewhere / "sub" / "keep.txt").write_text("precious", encoding="utf-8")
    refuses(mini_root, elsewhere)
    assert entries(elsewhere) == ["sub", "sub/keep.txt"]

def test_a_directory_with_the_marker_and_a_stray_file_is_refused(mini_root, tmp_path):
    out = tmp_path / "dist"
    assert build(mini_root, out).problems == []
    (out / "notes.txt").write_text("mine", encoding="utf-8")
    before = entries(out)
    r = refuses(mini_root, out)
    assert any("notes.txt" in p for p in r.problems)
    assert entries(out) == before and (out / "notes.txt").read_text(encoding="utf-8") == "mine"

def test_a_marker_with_other_content_proves_nothing(mini_root, tmp_path):
    out = tmp_path / "dist"
    out.mkdir()
    (out / MARKER).write_text("somebody else's tool\n", encoding="utf-8")
    (out / "syahi.sh").mkdir()
    refuses(mini_root, out)
    assert (out / MARKER).read_text(encoding="utf-8") == "somebody else's tool\n"

def test_a_symlinked_marker_proves_nothing(mini_root, tmp_path):
    out = tmp_path / "dist"
    out.mkdir()
    real = tmp_path / "real-marker"
    real.write_text(MARKER_TEXT, encoding="utf-8")
    (out / MARKER).symlink_to(real)
    (out / "syahi.sh").mkdir()
    refuses(mini_root, out)
    assert real.read_text(encoding="utf-8") == MARKER_TEXT and (out / "syahi.sh").is_dir()

def test_a_host_directory_that_is_a_symlink_is_refused_and_its_target_survives(mini_root, tmp_path):
    out = tmp_path / "dist"
    assert build(mini_root, out).problems == []
    precious = tmp_path / "precious"
    precious.mkdir()
    (precious / "keep.txt").write_text("precious", encoding="utf-8")
    shutil.rmtree(out / "syahi.sh")
    (out / "syahi.sh").symlink_to(precious, target_is_directory=True)
    refuses(mini_root, out)
    assert (precious / "keep.txt").read_text(encoding="utf-8") == "precious" and (out / "syahi.sh").is_symlink()

def test_a_missing_out_is_built_with_its_parents(mini_root, tmp_path):
    out = tmp_path / "not" / "yet" / "dist"
    assert build(mini_root, out).problems == []
    assert (out / "syahi.sh" / "index.html").is_file()

def test_an_empty_out_is_built_into(mini_root, tmp_path):
    out = tmp_path / "dist"
    out.mkdir()
    assert build(mini_root, out).problems == []
    assert (out / "syahi.sh" / "index.html").is_file() and out.is_dir()

def test_building_twice_into_the_same_out_is_accepted_and_identical(mini_root, tmp_path):
    out = tmp_path / "dist"
    assert build(mini_root, out).problems == []
    first = tree_hash(out)
    assert build(mini_root, out).problems == []
    assert build(mini_root, out).problems == []
    assert tree_hash(out) == first

def test_a_failed_build_leaves_an_out_the_next_build_may_replace(mini_root, tmp_path):
    out = tmp_path / "dist"
    index = mini_root / "content" / "index.html"
    good = index.read_text(encoding="utf-8")
    index.write_text("<p>no front matter</p>", encoding="utf-8")
    assert build(mini_root, out).problems
    assert entries(out) == [MARKER]
    index.write_text(good, encoding="utf-8")
    assert build(mini_root, out).problems == []

def test_an_out_that_is_a_file_is_refused_and_left_alone(mini_root, tmp_path):
    out = tmp_path / "dist"
    out.write_text("a file, not a directory", encoding="utf-8")
    refuses(mini_root, out)
    assert out.read_text(encoding="utf-8") == "a file, not a directory"

def test_an_out_that_is_a_symlink_to_a_directory_is_refused_and_its_target_survives(mini_root, tmp_path):
    target = tmp_path / "target"
    assert build(mini_root, target).problems == []  # even a genuine previous build, reached through a link
    before = tree_hash(target)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    refuses(mini_root, link)
    assert link.is_symlink() and tree_hash(target) == before

def test_an_out_that_is_a_dangling_symlink_is_refused(mini_root, tmp_path):
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "nowhere")
    refuses(mini_root, link)
    assert link.is_symlink() and not (tmp_path / "nowhere").exists()

# ---- release mode ----

SERVICES_PAGE = "---\ntitle: Services\ndescription: d\nupdated: 2026-10-06\napproved: 2026-10-06\nlayout: page\n---\n<h1>Services</h1>\n"

def test_release_with_no_pending_pages_is_clean(mini_root, tmp_path):
    # nothing pending means every tab is a real page: the Services tab needs its file, or sitecheck rightly fails the dead link
    edit(mini_root / "site.yaml", "pending_pages: [/services]", "pending_pages: []")
    (mini_root / "content" / "services.html").write_text(SERVICES_PAGE, encoding="utf-8")
    assert build(mini_root, tmp_path / "dist", release=True).problems == []

def test_release_names_the_tab_that_points_at_a_pending_page(mini_root, tmp_path):
    r = build(mini_root, tmp_path / "dist", release=True)
    site_yaml = str(mini_root / "site.yaml")
    assert any(site_yaml in p and "tab 'Services'" in p and "/services" in p for p in r.problems)

def test_release_names_a_page_that_links_to_a_pending_page(mini_root, tmp_path):
    home = mini_root / "content" / "index.html"
    edit(home, "<h1>", '<p><a href="/services/#intro">Services</a> and <a href="https://syahi.example/services.html">again</a></p>\n<h1>')
    r = build(mini_root, tmp_path / "dist", release=True)
    named = [p for p in r.problems if str(home) in p and "/services" in p]
    assert len(named) == 1  # one problem per page and target, however many links

def test_a_dev_build_allows_links_to_pending_pages(mini_root, tmp_path):
    edit(mini_root / "content" / "index.html", "<h1>", '<p><a href="/services">Services</a></p>\n<h1>')
    assert build(mini_root, tmp_path / "dist").problems == []

def test_release_ignores_links_to_pages_that_are_not_pending(mini_root, tmp_path):
    edit(mini_root / "site.yaml", "pending_pages: [/services]", "pending_pages: [/media]")
    (mini_root / "content" / "services.html").write_text(SERVICES_PAGE, encoding="utf-8")
    problems = build(mini_root, tmp_path / "dist", release=True).problems
    assert problems and all("/services" not in p for p in problems)

# ---- the output never holds feed.xml or CNAME ----

def test_the_output_never_holds_feed_xml_or_cname(mini_root, tmp_path, monkeypatch):
    def leaky(root, host_out, *args):
        (host_out / "assets").mkdir(parents=True, exist_ok=True)
        (host_out / "assets" / "feed.xml").write_text("x", encoding="utf-8")
        (host_out / "CNAME").write_text("x", encoding="utf-8")
        return {}, []
    monkeypatch.setattr(pipeline, "_publish_assets", leaky)
    r = build(mini_root, tmp_path / "dist")
    assert any("feed.xml" in p for p in r.problems) and any("CNAME" in p for p in r.problems)


# ---- draft pages can be built and read, never released ----

def make_draft(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = "\n".join(l for l in text.splitlines() if not l.startswith("approved:")) + "\n"
    path.write_text(text.replace("\nlayout: page\n", "\nlayout: page\ndraft: true\n", 1), encoding="utf-8")


def draft_problems(result: BuildResult) -> list[str]:
    return [p for p in result.problems if "page is a draft" in p]


def test_a_dev_build_accepts_a_draft_and_the_page_says_so(mini_root, tmp_path):
    make_draft(mini_root / "content" / "signet.html")
    result = build(mini_root, tmp_path / "dist")
    assert result.problems == []
    html = (tmp_path / "dist" / "syahi.sh" / "signet.html").read_text(encoding="utf-8")
    assert '<p class="made-by">Drafted with AI from our own records. Not yet approved.</p>' in html


def test_a_release_build_names_each_draft_page(mini_root, tmp_path):
    make_draft(mini_root / "content" / "signet.html")
    make_draft(mini_root / "content" / "404.html")
    problems = draft_problems(build(mini_root, tmp_path / "dist", release=True))
    assert len(problems) == 2
    assert any("signet.html" in p and "release" in p for p in problems)
    assert any("404.html" in p and "release" in p for p in problems)


def test_a_release_build_names_a_draft_on_the_katha_host_too(mini_root, tmp_path):
    make_draft(mini_root / "katha" / "content" / "index.html")
    problems = draft_problems(build(mini_root, tmp_path / "dist", release=True))
    assert len(problems) == 1 and "katha" in problems[0]


def test_a_release_build_with_no_draft_has_no_draft_problem(mini_root, tmp_path):
    assert draft_problems(build(mini_root, tmp_path / "dist", release=True)) == []


def test_a_draft_that_fails_to_render_is_still_named_in_release(mini_root, tmp_path):
    page = mini_root / "content" / "signet.html"
    make_draft(page)
    page.write_text(page.read_text(encoding="utf-8") + "{{ claim('no-such-claim') }}\n", encoding="utf-8")
    problems = build(mini_root, tmp_path / "dist", release=True).problems
    assert any("no-such-claim" in p for p in problems)
    assert len([p for p in problems if "page is a draft" in p]) == 1


def test_each_host_gets_a_headers_file_with_the_year_long_rule_and_short_stable_names(mini_root, tmp_path):
    from sitebuild import assets
    result = build(mini_root, tmp_path / "dist")
    assert result.problems == []
    for host in ("syahi.sh", "katha.syahi.sh"):
        text = (tmp_path / "dist" / host / "_headers").read_text(encoding="utf-8")
        assert text.startswith("/assets/*\n  Cache-Control: public, max-age=31536000, immutable\n")
        for key in (*assets.STABLE_ONLY, *assets.ALSO_STABLE):
            held = (tmp_path / "dist" / host / "assets" / key).is_file()
            assert (f"/assets/{key}\n  ! Cache-Control\n  Cache-Control: public, max-age=3600\n" in text) == held, (host, key)
        # Every rule other than the first is a short-cache rule for a stable name, never a second immutable one.
        assert text.count("immutable") == 1
    assert (tmp_path / "dist" / "syahi.sh" / "_headers").read_text(encoding="utf-8").count("max-age=3600") >= 1
    assert result.warnings == [] or all("_headers" not in w for w in result.warnings)


def test_the_headers_file_is_deterministic(mini_root, tmp_path):
    build(mini_root, tmp_path / "a")
    build(mini_root, tmp_path / "b")
    assert (tmp_path / "a" / "syahi.sh" / "_headers").read_bytes() == (tmp_path / "b" / "syahi.sh" / "_headers").read_bytes()
