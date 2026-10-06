# tests/test_publish_katha.py
#
# The guarded publish step. Every test builds throwaway git repos under tmp_path. Nothing here ever
# touches the real katha-feed checkout: it holds feed.xml, which Spotify reads.
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "publish_katha.py"
# Hermetic git: no global or system config, so a developer's signing or hook settings cannot leak in.
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com",
           GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
SITE_SHA = "abc1234"


def git(cwd, *a, check=True):
    return subprocess.run(["git", *a], cwd=cwd, check=check, capture_output=True, text=True, env=ENV)


def feed_repo(tmp_path):
    r = tmp_path / "katha-feed"; r.mkdir()
    git(r, "init", "-q", "-b", "main")
    (r / "feed.xml").write_text("<rss/>"); (r / "CNAME").write_text("katha.syahi.sh\n"); (r / "index.html").write_text("old")
    git(r, "add", "feed.xml", "CNAME", "index.html"); git(r, "commit", "-q", "-m", "init")
    return r


def dist(tmp_path, extra=None):
    d = tmp_path / "dist"; (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("new"); (d / "robots.txt").write_text("r"); (d / "sitemap.xml").write_text("s")
    (d / "assets" / "a.css").write_text("a{}")
    if extra: (d / extra).write_text("x")
    return d


def run(*a):
    return subprocess.run([sys.executable, str(TOOL), *a], capture_output=True, text=True, env=ENV)


def publish(r, d, *flags):
    return run("--repo", str(r), "--dist", str(d), "--site-sha", SITE_SHA, *flags)


def said(res):
    return res.stdout + res.stderr


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def head(r):
    return git(r, "rev-parse", "HEAD").stdout.strip()


def with_origin(tmp_path):
    """A katha-feed clone whose origin is a bare repo, both in sync on main."""
    bare = tmp_path / "origin.git"; bare.mkdir()
    git(bare, "init", "-q", "--bare", "-b", "main")
    r = feed_repo(tmp_path)
    git(r, "remote", "add", "origin", str(bare))
    git(r, "push", "-q", "origin", "main")
    return r, bare


# ---- the brief's four ----

def test_copies_and_commits_without_touching_feed(tmp_path):
    r = feed_repo(tmp_path); d = dist(tmp_path)
    res = run("--repo", str(r), "--dist", str(d), "--no-fetch")
    assert res.returncode == 0, res.stderr
    assert (r / "index.html").read_text() == "new" and (r / "feed.xml").read_text() == "<rss/>"
    changed = git(r, "show", "--name-only", "--format=", "HEAD").stdout.split()
    assert "feed.xml" not in changed and "CNAME" not in changed


def test_refuses_dist_with_feed(tmp_path):
    r = feed_repo(tmp_path); d = dist(tmp_path, extra="feed.xml")
    res = run("--repo", str(r), "--dist", str(d), "--no-fetch")
    assert res.returncode == 2 and "feed.xml" in (res.stdout + res.stderr)


def test_refuses_dirty_repo(tmp_path):
    r = feed_repo(tmp_path); (r / "index.html").write_text("dirty"); d = dist(tmp_path)
    assert run("--repo", str(r), "--dist", str(d), "--no-fetch").returncode == 2


def test_dry_run_changes_nothing(tmp_path):
    r = feed_repo(tmp_path); d = dist(tmp_path)
    head_before = git(r, "rev-parse", "HEAD").stdout
    assert run("--repo", str(r), "--dist", str(d), "--no-fetch", "--dry-run").returncode == 0
    assert git(r, "rev-parse", "HEAD").stdout == head_before and (r / "index.html").read_text() == "old"


# ---- what it copies, stages and commits ----

def test_the_commit_holds_exactly_the_copied_paths_and_a_labelled_message(tmp_path):
    r = feed_repo(tmp_path); d = dist(tmp_path)
    res = publish(r, d, "--no-fetch")
    assert res.returncode == 0, said(res)
    assert sorted(git(r, "show", "--name-only", "--format=", "HEAD").stdout.split()) == [
        "assets/a.css", "index.html", "robots.txt", "sitemap.xml"]
    assert git(r, "log", "-1", "--format=%s").stdout.strip() == f"katha.syahi.sh: index from syahi-labs/site {SITE_SHA} [agent]"
    assert git(r, "status", "--porcelain").stdout == ""
    assert (r / "robots.txt").read_text() == "r" and (r / "sitemap.xml").read_text() == "s"
    assert (r / "assets" / "a.css").read_text() == "a{}"


def test_feed_and_cname_are_byte_identical_afterwards(tmp_path):
    r = feed_repo(tmp_path); d = dist(tmp_path)
    before = (sha(r / "feed.xml"), sha(r / "CNAME"))
    assert publish(r, d, "--no-fetch").returncode == 0
    assert (sha(r / "feed.xml"), sha(r / "CNAME")) == before


def test_removes_stale_files_under_assets_only(tmp_path):
    r = feed_repo(tmp_path)
    (r / "assets").mkdir(); (r / "assets" / "old.css").write_text("old")
    (r / "extra.txt").write_text("keep me")
    git(r, "add", "assets/old.css", "extra.txt"); git(r, "commit", "-q", "-m", "more")
    d = dist(tmp_path)
    res = publish(r, d, "--no-fetch")
    assert res.returncode == 0, said(res)
    assert not (r / "assets" / "old.css").exists()
    assert (r / "extra.txt").read_text() == "keep me"
    assert "assets/old.css" in git(r, "show", "--name-only", "--format=", "HEAD").stdout.split()
    assert git(r, "status", "--porcelain").stdout == ""


def test_files_in_the_dist_that_are_not_on_the_list_are_not_copied(tmp_path):
    r = feed_repo(tmp_path); d = dist(tmp_path, extra="notes.txt")
    res = publish(r, d, "--no-fetch")
    assert res.returncode == 0, said(res)
    assert not (r / "notes.txt").exists()


def test_publishing_the_same_dist_twice_makes_no_second_commit(tmp_path):
    r = feed_repo(tmp_path); d = dist(tmp_path)
    assert publish(r, d, "--no-fetch").returncode == 0
    first = head(r)
    res = publish(r, d, "--no-fetch")
    assert res.returncode == 0 and head(r) == first
    assert "nothing" in said(res).lower()


def test_dry_run_lists_the_files_and_changes_nothing(tmp_path):
    r = feed_repo(tmp_path); d = dist(tmp_path)
    (r / "assets").mkdir(); (r / "assets" / "old.css").write_text("old")
    git(r, "add", "assets/old.css"); git(r, "commit", "-q", "-m", "more")
    before_head, before_tree = head(r), sorted(p.name for p in r.rglob("*") if ".git" not in p.parts)
    res = publish(r, d, "--no-fetch", "--dry-run")
    assert res.returncode == 0, said(res)
    out = res.stdout
    for name in ("index.html", "robots.txt", "sitemap.xml", "assets/a.css", "assets/old.css"):
        assert name in out, name
    assert head(r) == before_head and git(r, "status", "--porcelain").stdout == ""
    assert sorted(p.name for p in r.rglob("*") if ".git" not in p.parts) == before_tree
    assert (r / "index.html").read_text() == "old" and (r / "assets" / "old.css").exists()


def test_a_dirty_site_checkout_is_named_in_the_commit_sha(tmp_path):
    # Without --site-sha the tool asks the site repo. This test repo is not a git repo, so run the
    # tool from a copy of itself placed in a fresh dirty repo.
    site = tmp_path / "site"; (site / "tools").mkdir(parents=True)
    git(site, "init", "-q", "-b", "main")
    (site / "tools" / "publish_katha.py").write_text(TOOL.read_text(encoding="utf-8"), encoding="utf-8")
    git(site, "add", "tools/publish_katha.py"); git(site, "commit", "-q", "-m", "tool")
    (site / "stray.txt").write_text("uncommitted")
    r = feed_repo(tmp_path); d = dist(tmp_path)
    res = subprocess.run([sys.executable, str(site / "tools" / "publish_katha.py"), "--repo", str(r),
                          "--dist", str(d), "--no-fetch"], capture_output=True, text=True, env=ENV)
    assert res.returncode == 0, said(res)
    subject = git(r, "log", "-1", "--format=%s").stdout.strip()
    site_head = git(site, "rev-parse", "--short", "HEAD").stdout.strip()
    assert subject == f"katha.syahi.sh: index from syahi-labs/site {site_head}-dirty [agent]"


# ---- every refusal exits 2 and names its reason ----

def refused(res, *words):
    assert res.returncode == 2, said(res)
    text = said(res).lower()
    for word in words:
        assert word.lower() in text, f"{word!r} not in {said(res)!r}"


def test_refuses_an_untracked_file_in_the_repo(tmp_path):
    r = feed_repo(tmp_path); (r / "scratch.txt").write_text("x"); d = dist(tmp_path)
    refused(publish(r, d, "--no-fetch"), "uncommitted", "scratch.txt")
    assert head(r) == git(r, "rev-parse", "main").stdout.strip() and (r / "index.html").read_text() == "old"


def test_refuses_a_staged_change(tmp_path):
    r = feed_repo(tmp_path); (r / "index.html").write_text("staged"); git(r, "add", "index.html"); d = dist(tmp_path)
    refused(publish(r, d, "--no-fetch"), "uncommitted")


def test_refuses_off_main(tmp_path):
    r = feed_repo(tmp_path); git(r, "checkout", "-q", "-b", "topic"); d = dist(tmp_path)
    refused(publish(r, d, "--no-fetch"), "main", "topic")
    assert (r / "index.html").read_text() == "old"


def test_refuses_a_detached_head(tmp_path):
    r = feed_repo(tmp_path); git(r, "checkout", "-q", "--detach"); d = dist(tmp_path)
    refused(publish(r, d, "--no-fetch"), "main")


def test_refuses_a_path_that_is_not_a_git_repo(tmp_path):
    plain = tmp_path / "plain"; plain.mkdir(); d = dist(tmp_path)
    refused(publish(plain, d, "--no-fetch"), "git")


def test_refuses_a_repo_path_that_does_not_exist(tmp_path):
    refused(publish(tmp_path / "nope", dist(tmp_path), "--no-fetch"), "repo")


@pytest.mark.parametrize("name", ["feed.xml", "CNAME"])
def test_refuses_a_dist_with_feed_or_cname_at_the_top(tmp_path, name):
    r = feed_repo(tmp_path); d = dist(tmp_path, extra=name)
    refused(publish(r, d, "--no-fetch"), name)
    assert (r / "index.html").read_text() == "old"


@pytest.mark.parametrize("relative", ["assets/feed.xml", "assets/deep/CNAME", "FEED.XML", "cname"])
def test_refuses_feed_or_cname_anywhere_in_the_dist_in_any_case(tmp_path, relative):
    r = feed_repo(tmp_path); d = dist(tmp_path)
    (d / relative).parent.mkdir(parents=True, exist_ok=True); (d / relative).write_text("x")
    refused(publish(r, d, "--no-fetch"), Path(relative).name)
    assert (r / "index.html").read_text() == "old" and git(r, "status", "--porcelain").stdout == ""


def test_refuses_when_the_repos_index_is_a_symlink_to_the_feed(tmp_path):
    # Copying onto it would write through the link and rewrite feed.xml: the copy "would change" it.
    r = tmp_path / "katha-feed"; r.mkdir(); git(r, "init", "-q", "-b", "main")
    (r / "feed.xml").write_text("<rss/>"); (r / "CNAME").write_text("katha.syahi.sh\n")
    (r / "index.html").symlink_to("feed.xml")
    git(r, "add", "feed.xml", "CNAME", "index.html"); git(r, "commit", "-q", "-m", "init")
    d = dist(tmp_path)
    refused(publish(r, d, "--no-fetch"), "feed.xml")
    assert (r / "feed.xml").read_text() == "<rss/>"
    assert git(r, "status", "--porcelain").stdout == ""      # refused before anything was copied


def test_refuses_when_assets_in_the_repo_is_a_symlink_to_the_root(tmp_path):
    # Removing "stale" files under assets/ would then delete feed.xml.
    r = tmp_path / "katha-feed"; r.mkdir(); git(r, "init", "-q", "-b", "main")
    (r / "feed.xml").write_text("<rss/>"); (r / "CNAME").write_text("katha.syahi.sh\n")
    (r / "assets").symlink_to(".")
    git(r, "add", "feed.xml", "CNAME", "assets"); git(r, "commit", "-q", "-m", "init")
    d = dist(tmp_path)
    res = publish(r, d, "--no-fetch")
    refused(res, "assets", "symbolic link")
    assert (r / "feed.xml").read_text() == "<rss/>" and (r / "CNAME").exists()
    assert git(r, "status", "--porcelain").stdout == ""      # refused before anything was copied through the link
    assert not (r / "a.css").exists()


def test_refuses_a_symlink_in_the_dist(tmp_path):
    r = feed_repo(tmp_path); d = dist(tmp_path)
    (d / "assets" / "link.css").symlink_to(d / "assets" / "a.css")
    refused(publish(r, d, "--no-fetch"), "symbolic link", "link.css")


def test_refuses_a_dist_with_no_index(tmp_path):
    r = feed_repo(tmp_path); d = dist(tmp_path); (d / "index.html").unlink()
    refused(publish(r, d, "--no-fetch"), "index.html")


def test_refuses_a_dist_missing_robots_or_sitemap(tmp_path):
    r = feed_repo(tmp_path); d = dist(tmp_path); (d / "sitemap.xml").unlink()
    refused(publish(r, d, "--no-fetch"), "sitemap.xml")


def test_refuses_a_dist_that_is_missing(tmp_path):
    refused(publish(feed_repo(tmp_path), tmp_path / "no-such-dist", "--no-fetch"), "dist")


def test_refuses_a_dist_inside_the_repo(tmp_path):
    r = feed_repo(tmp_path)
    d = r / "build"; (d / "assets").mkdir(parents=True)
    for name in ("index.html", "robots.txt", "sitemap.xml"):
        (d / name).write_text("x")
    git(r, "add", "build"); git(r, "commit", "-q", "-m", "build")
    refused(publish(r, d, "--no-fetch"), "inside")


# ---- the origin/main check ----

def test_in_sync_with_origin_publishes_and_never_pushes(tmp_path):
    r, bare = with_origin(tmp_path); d = dist(tmp_path)
    origin_before = git(bare, "rev-parse", "main").stdout.strip()
    res = publish(r, d)
    assert res.returncode == 0, said(res)
    assert head(r) != origin_before
    assert git(bare, "rev-parse", "main").stdout.strip() == origin_before   # never pushed
    assert git(r, "rev-parse", "origin/main").stdout.strip() == origin_before


def test_refuses_when_origin_main_moved_on(tmp_path):
    r, bare = with_origin(tmp_path); d = dist(tmp_path)
    other = tmp_path / "other"; git(tmp_path, "clone", "-q", str(bare), str(other))
    (other / "feed.xml").write_text("<rss>new episode</rss>")
    git(other, "commit", "-q", "-am", "feed: regenerate"); git(other, "push", "-q", "origin", "main")
    # r has not fetched: only the tool's own fetch can see that origin moved.
    refused(publish(r, d), "origin/main")
    assert (r / "index.html").read_text() == "old"


def test_refuses_when_the_repo_has_commits_origin_lacks(tmp_path):
    r, _ = with_origin(tmp_path); d = dist(tmp_path)
    (r / "index.html").write_text("local only"); git(r, "commit", "-q", "-am", "unpushed")
    refused(publish(r, d), "origin/main")


def test_refuses_when_origin_cannot_be_checked(tmp_path):
    r = feed_repo(tmp_path); d = dist(tmp_path)   # no origin remote at all
    refused(publish(r, d), "origin")
    assert (r / "index.html").read_text() == "old"


def test_dry_run_still_applies_the_origin_check(tmp_path):
    r, bare = with_origin(tmp_path); d = dist(tmp_path)
    other = tmp_path / "other"; git(tmp_path, "clone", "-q", str(bare), str(other))
    (other / "feed.xml").write_text("<rss>x</rss>")
    git(other, "commit", "-q", "-am", "feed"); git(other, "push", "-q", "origin", "main")
    refused(publish(r, d, "--dry-run"), "origin/main")


def test_the_tool_is_standard_library_only():
    text = TOOL.read_text(encoding="utf-8")
    assert "import sitebuild" not in text and "from sitebuild" not in text
    assert "yaml" not in text and "jinja" not in text.lower()


def test_no_em_dash_in_the_tool():
    assert chr(0x2014) not in TOOL.read_text(encoding="utf-8")


# ---- the last lines of defence ----

def load_tool():
    import importlib.util
    spec = importlib.util.spec_from_file_location("publish_katha_under_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_refuses_when_index_is_a_hard_link_to_the_feed(tmp_path):
    # Same inode under two names: writing one in place would rewrite the other.
    r = tmp_path / "katha-feed"; r.mkdir(); git(r, "init", "-q", "-b", "main")
    (r / "feed.xml").write_text("<rss/>"); (r / "CNAME").write_text("katha.syahi.sh\n")
    os.link(r / "feed.xml", r / "index.html")
    git(r, "add", "feed.xml", "CNAME", "index.html"); git(r, "commit", "-q", "-m", "init")
    d = dist(tmp_path)
    refused(publish(r, d, "--no-fetch"), "feed.xml")
    assert (r / "feed.xml").read_text() == "<rss/>" and git(r, "status", "--porcelain").stdout == ""


def test_a_failing_commit_exits_1_not_2_and_leaves_feed_and_cname_alone(tmp_path):
    r = feed_repo(tmp_path); d = dist(tmp_path)
    hook = r / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho no >&2\nexit 1\n"); hook.chmod(0o755)
    res = publish(r, d, "--no-fetch")
    assert res.returncode == 1, said(res)
    assert "commit failed" in said(res).lower() and "nothing is committed" in said(res).lower()
    assert (r / "feed.xml").read_text() == "<rss/>" and (r / "CNAME").read_text() == "katha.syahi.sh\n"


def test_the_self_check_puts_back_a_protected_file_that_moved(tmp_path):
    tool = load_tool()
    r = feed_repo(tmp_path)
    before = tool.snapshot_protected(r)
    tool.verify_protected(r, before)                       # untouched: silent
    (r / "feed.xml").write_text("<rss>tampered</rss>"); (r / "CNAME").unlink()
    with pytest.raises(tool.Refusal) as err:
        tool.verify_protected(r, before)
    assert "feed.xml" in str(err.value) and "CNAME" in str(err.value)
    assert (r / "feed.xml").read_text() == "<rss/>" and (r / "CNAME").read_text() == "katha.syahi.sh\n"


def test_publish_puts_the_feed_back_and_commits_nothing_if_a_copy_ever_changes_it(tmp_path, monkeypatch):
    tool = load_tool()
    r = feed_repo(tmp_path); d = dist(tmp_path)
    before = head(r)
    copy_file = tool.copy_file

    def hostile(src, dest):
        copy_file(src, dest)
        (r / "feed.xml").write_text("<rss>tampered</rss>")

    monkeypatch.setattr(tool, "copy_file", hostile)
    with pytest.raises(tool.Refusal) as err:
        tool.publish(r, d, dry_run=False, fetch=False, explicit_sha=SITE_SHA, say=lambda line: None)
    assert "feed.xml" in str(err.value) and "nothing is committed" in str(err.value)
    assert (r / "feed.xml").read_text() == "<rss/>"
    assert head(r) == before


def test_staging_is_by_explicit_path_and_there_is_no_push():
    import re
    text = TOOL.read_text(encoding="utf-8")
    assert re.search(r'"add",\s*"(?:-A|--all|-u|\.)"', text) is None
    assert re.search(r'git\(repo,\s*"push"', text) is None and '"push"' not in text.replace("git push", "")
