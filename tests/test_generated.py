# tests/test_generated.py
import datetime, os, subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from sitebuild.claims import ClaimError, ClaimRegister
from sitebuild.content import Page
from sitebuild.generated import llms_txt, robots_txt, sitemap_xml
from sitebuild.gitdates import GitDateError, last_commit_date
from sitebuild.site import load_site

EM_DASH = chr(0x2014)
SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

def test_robots_exact():
    assert robots_txt("https://syahi.sh") == "User-agent: *\nAllow: /\n\nSitemap: https://syahi.sh/sitemap.xml\n"

def test_sitemap_clean_urls_sorted():
    xml = sitemap_xml([("/signet", datetime.date(2026, 10, 6)), ("/", datetime.date(2026, 10, 1))], "https://syahi.sh")
    assert xml.splitlines()[0].startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert xml.index("<loc>https://syahi.sh/</loc>") < xml.index("<loc>https://syahi.sh/signet</loc>")
    assert "<lastmod>2026-10-06</lastmod>" in xml and ".html" not in xml

def test_last_commit_date(tmp_path):
    env = dict(os.environ, GIT_AUTHOR_DATE="2026-09-16T10:00:00+05:30", GIT_COMMITTER_DATE="2026-09-16T10:00:00+05:30",
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    f = tmp_path / "a.html"; f.write_text("x")
    subprocess.run(["git", "add", "a.html"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "c"], cwd=tmp_path, check=True, env=env)
    assert last_commit_date(f) == datetime.date(2026, 9, 16)
    g = tmp_path / "new.html"; g.write_text("y")
    assert last_commit_date(g) is None

# ---- beyond the brief's examples: the contract it states in prose ----

D = datetime.date(2026, 10, 6)

def commit_env(day):
    stamp = f"{day}T10:00:00+05:30"
    return dict(os.environ, GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp,
                GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")

def repo_with(tmp_path, name="a.html", day="2026-09-16"):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    f = tmp_path / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("x")
    subprocess.run(["git", "add", name], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "c"], cwd=tmp_path, check=True, env=commit_env(day))
    return f

def test_the_date_is_the_last_commit_not_the_first(tmp_path):
    f = repo_with(tmp_path, day="2026-09-16")
    f.write_text("changed")
    subprocess.run(["git", "add", "a.html"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "c2"], cwd=tmp_path, check=True, env=commit_env("2026-10-02"))
    assert last_commit_date(f) == datetime.date(2026, 10, 2)

def test_the_date_follows_the_file_not_the_repo(tmp_path):
    repo_with(tmp_path, day="2026-09-16")
    other = tmp_path / "b.html"; other.write_text("y")
    subprocess.run(["git", "add", "b.html"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "c2"], cwd=tmp_path, check=True, env=commit_env("2026-10-02"))
    assert last_commit_date(tmp_path / "a.html") == datetime.date(2026, 9, 16)

def test_a_file_in_a_subdirectory_uses_its_own_repo(tmp_path):
    f = repo_with(tmp_path, name="content/deep/a.html", day="2026-09-20")
    assert last_commit_date(f) == datetime.date(2026, 9, 20)

def test_outside_a_repo_is_none_not_an_error(tmp_path, monkeypatch):
    # The ceiling stops git looking in parent directories, so this holds wherever tmp_path lives.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    f = tmp_path / "a.html"; f.write_text("x")
    assert last_commit_date(f) is None

def test_a_repo_with_no_commits_yet_is_none(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    f = tmp_path / "a.html"; f.write_text("x")
    subprocess.run(["git", "add", "a.html"], cwd=tmp_path, check=True)
    assert last_commit_date(f) is None

def test_a_broken_repo_is_an_error_naming_the_file(tmp_path):
    f = repo_with(tmp_path)
    for obj in (tmp_path / ".git" / "objects").glob("??/*"):  # every object emptied: still a repo, history unreadable
        obj.chmod(0o644)
        obj.write_bytes(b"")
    with pytest.raises(GitDateError) as err:
        last_commit_date(f)
    assert str(f) in str(err.value)

def test_a_dangling_worktree_file_is_an_error_naming_the_file(tmp_path, monkeypatch):
    # A `.git` file whose gitdir is gone (a deleted worktree) is a broken checkout, not an untracked
    # file. git words it "not a git repository: <path>", unlike the genuine no-repo message.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    (tmp_path / ".git").write_text(f"gitdir: {tmp_path / 'gone' / 'worktrees' / 'w'}\n", encoding="utf-8")
    f = tmp_path / "a.html"; f.write_text("x")
    with pytest.raises(GitDateError) as err:
        last_commit_date(f)
    assert str(f) in str(err.value)

def test_a_filesystem_boundary_is_still_no_repo_not_an_error(tmp_path, monkeypatch):
    # Across a mount point git words the genuine no-repo case differently; a stand-in git says it so
    # the test does not depend on how this machine is mounted.
    fake = tmp_path / "bin" / "git"
    fake.parent.mkdir()
    fake.write_text("#!/bin/sh\necho 'fatal: not a git repository (or any parent up to mount point /tmp)' >&2\nexit 128\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake.parent) + os.pathsep + os.environ["PATH"])
    f = tmp_path / "a.html"; f.write_text("x")
    assert last_commit_date(f) is None

def test_a_missing_git_is_an_error_naming_the_file(tmp_path, monkeypatch):
    f = repo_with(tmp_path)
    monkeypatch.setenv("PATH", "")
    with pytest.raises(GitDateError) as err:
        last_commit_date(f)
    assert str(f) in str(err.value)

def test_sitemap_is_well_formed_with_the_09_namespace():
    xml = sitemap_xml([("/", D), ("/signet", datetime.date(2026, 9, 3))], "https://syahi.example")
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>\n') and xml.endswith("\n")
    root = ET.fromstring(xml.encode("utf-8"))
    assert root.tag == SITEMAP_NS + "urlset"
    urls = [(u.find(SITEMAP_NS + "loc").text, u.find(SITEMAP_NS + "lastmod").text) for u in root]
    assert urls == [("https://syahi.example/", "2026-10-06"), ("https://syahi.example/signet", "2026-09-03")]

def test_sitemap_sorts_by_slug_whatever_the_input_order():
    entries = [("/signet", D), ("/media/episode-2", D), ("/", D), ("/about", D), ("/media", D)]
    xml = sitemap_xml(entries, "https://syahi.example")
    locs = [u.find(SITEMAP_NS + "loc").text for u in ET.fromstring(xml.encode("utf-8"))]
    assert locs == ["https://syahi.example/", "https://syahi.example/about", "https://syahi.example/media",
                    "https://syahi.example/media/episode-2", "https://syahi.example/signet"]

def test_sitemap_never_has_html_or_a_trailing_slash_beyond_the_root():
    xml = sitemap_xml([("/", D), ("/services/quote", D)], "https://syahi.example")
    locs = [u.find(SITEMAP_NS + "loc").text for u in ET.fromstring(xml.encode("utf-8"))]
    assert not any(loc.endswith(".html") for loc in locs)
    assert [loc for loc in locs if loc.endswith("/")] == ["https://syahi.example/"]

def test_sitemap_escapes_xml_special_characters_in_loc():
    xml = sitemap_xml([("/a&b<c>", D)], "https://syahi.example")
    assert "<loc>https://syahi.example/a&amp;b&lt;c&gt;</loc>" in xml
    root = ET.fromstring(xml.encode("utf-8"))  # still well formed
    assert root[0].find(SITEMAP_NS + "loc").text == "https://syahi.example/a&b<c>"

def test_sitemap_accepts_a_generator_and_lists_every_entry():
    entries = ((slug, D) for slug in ("/signet", "/", "/about"))
    xml = sitemap_xml(entries, "https://syahi.example")
    locs = [u.find(SITEMAP_NS + "loc").text for u in ET.fromstring(xml.encode("utf-8"))]
    assert locs == ["https://syahi.example/", "https://syahi.example/about", "https://syahi.example/signet"]

def test_sitemap_refuses_the_404_page():
    with pytest.raises(ValueError, match="/404"):
        sitemap_xml([("/", D), ("/404", D)], "https://syahi.example")

def test_sitemap_refuses_a_duplicate_slug():
    with pytest.raises(ValueError, match="/signet"):
        sitemap_xml([("/signet", D), ("/", D), ("/signet", datetime.date(2026, 9, 1))], "https://syahi.example")

def test_sitemap_does_not_filter_pending_pages_itself():
    # The pipeline decides what goes in; the generator writes what it is given.
    xml = sitemap_xml([("/", D), ("/later", D)], "https://syahi.example")
    assert "<loc>https://syahi.example/later</loc>" in xml

def test_robots_follows_the_base_url():
    assert robots_txt("https://katha.example") == "User-agent: *\nAllow: /\n\nSitemap: https://katha.example/sitemap.xml\n"

# ---- llms.txt ----

SITE = """
base_url: https://syahi.example
name: Syahi
header: syahi
tabs:
  - {label: One, href: /one}
cta: {label: Go, href: "https://go.example/x"}
profiles: []
policies: []
pending_pages: [/later]
"""
SUMMARY = "Syahi is a made-up studio for tests. Agents draft, a person approves."
CLAIMS = f'- {{id: org-summary, text: "{SUMMARY}", source: s, updated: 2026-10-06, status: live}}\n'

def fixture(tmp_path, claims=CLAIMS):
    s = tmp_path / "site.yaml"; s.write_text(SITE, encoding="utf-8")
    c = tmp_path / "claims.yaml"; c.write_text(claims, encoding="utf-8")
    return load_site(s), ClaimRegister.load(c)

def pg(slug, title="Title", description="Description."):
    return Page(slug=slug, title=title, description=description, updated=D, approved=D, layout="page",
                claims=(), schema=(), audience=None, body="", source=Path("x.html"))

def test_llms_txt_exact_shape_and_order(tmp_path):
    site, claims = fixture(tmp_path)
    pages = [pg("/signet", "Signet", "The approval layer."), pg("/", "Home", "What we do."),
             pg("/about", "About", "Who we are.")]
    assert llms_txt(site, pages, claims) == (
        "# Syahi\n"
        "\n"
        f"> {SUMMARY}\n"
        "\n"
        "## Pages\n"
        "\n"
        "- [Home](https://syahi.example/): What we do.\n"
        "- [About](https://syahi.example/about): Who we are.\n"
        "- [Signet](https://syahi.example/signet): The approval layer.\n"
    )

def test_llms_txt_leaves_out_pending_pages_and_the_404(tmp_path):
    site, claims = fixture(tmp_path)
    text = llms_txt(site, [pg("/"), pg("/later", "Later"), pg("/404", "Not found"), pg("/about", "About")], claims)
    assert "https://syahi.example/later" not in text and "404" not in text
    assert "(https://syahi.example/about)" in text

def test_llms_txt_urls_follow_the_clean_url_rule(tmp_path):
    site, claims = fixture(tmp_path)
    text = llms_txt(site, [pg("/"), pg("/services/quote")], claims)
    assert "(https://syahi.example/)" in text and "(https://syahi.example/services/quote)" in text
    assert ".html" not in text

def test_llms_txt_reads_the_summary_without_marking_it_used(tmp_path):
    site, claims = fixture(tmp_path)
    llms_txt(site, [pg("/")], claims)
    assert claims.used == set()

def test_llms_txt_without_the_summary_claim_fails_by_name(tmp_path):
    site, claims = fixture(tmp_path, claims="[]\n")
    with pytest.raises(ClaimError, match="org-summary"):
        llms_txt(site, [pg("/")], claims)

def test_llms_txt_keeps_each_page_on_one_line(tmp_path):
    site, claims = fixture(tmp_path)
    folded = pg("/about", "About", "Who we are,\n  and what we do.\n")
    lines = llms_txt(site, [folded], claims).splitlines()
    assert "- [About](https://syahi.example/about): Who we are, and what we do." in lines

def test_llms_txt_has_no_em_dash_and_ends_with_one_newline(tmp_path):
    site, claims = fixture(tmp_path)
    text = llms_txt(site, [pg("/"), pg("/about")], claims)
    assert EM_DASH not in text and text.endswith(".\n") and not text.endswith("\n\n")

def test_llms_txt_with_no_pages_still_has_the_header(tmp_path):
    site, claims = fixture(tmp_path)
    assert llms_txt(site, [], claims) == f"# Syahi\n\n> {SUMMARY}\n\n## Pages\n"
