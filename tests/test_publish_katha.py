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
    res = run("--repo", str(r), "--dist", str(d), "--no-fetch", "--site-sha", SITE_SHA)
    assert res.returncode == 0, res.stderr
    assert (r / "index.html").read_text() == "new" and (r / "feed.xml").read_text() == "<rss/>"
    changed = git(r, "show", "--name-only", "--format=", "HEAD").stdout.split()
    assert "feed.xml" not in changed and "CNAME" not in changed


def test_refuses_dist_with_feed(tmp_path):
    r = feed_repo(tmp_path); d = dist(tmp_path, extra="feed.xml")
    res = run("--repo", str(r), "--dist", str(d), "--no-fetch", "--site-sha", SITE_SHA)
    assert res.returncode == 2 and "feed.xml" in (res.stdout + res.stderr)


def test_refuses_dirty_repo(tmp_path):
    r = feed_repo(tmp_path); (r / "index.html").write_text("dirty"); d = dist(tmp_path)
    assert run("--repo", str(r), "--dist", str(d), "--no-fetch", "--site-sha", SITE_SHA).returncode == 2


def test_dry_run_changes_nothing(tmp_path):
    r = feed_repo(tmp_path); d = dist(tmp_path)
    head_before = git(r, "rev-parse", "HEAD").stdout
    assert run("--repo", str(r), "--dist", str(d), "--no-fetch", "--dry-run", "--site-sha", SITE_SHA).returncode == 0
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


def test_the_commit_subject_uses_the_site_sha_verbatim(tmp_path):
    for number, given in enumerate(("0123abc", "9" * 40, "abcd")):
        (tmp_path / f"r{number}").mkdir()
        r = feed_repo(tmp_path / f"r{number}"); d = dist(tmp_path / f"r{number}")
        (d / "index.html").write_text(f"new {given}")
        assert run("--repo", str(r), "--dist", str(d), "--no-fetch", "--site-sha", given).returncode == 0
        assert git(r, "log", "-1", "--format=%s").stdout.strip() == f"katha.syahi.sh: index from syahi-labs/site {given} [agent]"


def test_the_site_sha_is_required_and_nothing_is_guessed_from_the_tools_own_checkout(tmp_path):
    r = feed_repo(tmp_path); d = dist(tmp_path); before = head(r)
    res = run("--repo", str(r), "--dist", str(d), "--no-fetch")
    assert res.returncode == 2 and "--site-sha" in said(res), said(res)
    assert head(r) == before and (r / "index.html").read_text() == "old" and git(r, "status", "--porcelain").stdout == ""


@pytest.mark.parametrize("given", ["abc1234-dirty", "main", "xyz", "abc", "ABC1234", "abc1234 [agent]", "", "abc1234\n", "0" * 41])
def test_a_site_sha_that_is_not_a_git_sha_is_refused(tmp_path, given):
    r = feed_repo(tmp_path); d = dist(tmp_path); before = head(r)
    res = run("--repo", str(r), "--dist", str(d), "--no-fetch", "--site-sha", given)
    assert res.returncode == 2 and "--site-sha" in said(res), said(res)
    assert head(r) == before and (r / "index.html").read_text() == "old"


def test_the_help_says_the_sha_is_required_and_that_a_dry_run_still_fetches():
    res = run("--help")
    assert res.returncode == 0
    text = " ".join(res.stdout.split())
    assert "[--site-sha" not in text and "--site-sha SITE_SHA" in text          # required: no brackets in the usage
    assert "verbatim" in text and "required" in text.lower()
    dry = text[text.index("--dry-run", text.index("options:")):]
    assert "still fetches" in dry and "refs/remotes/origin/main" in dry


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
        tool.publish(r, d, dry_run=False, fetch=False, site_sha=SITE_SHA, say=lambda line: None)
    assert "feed.xml" in str(err.value) and "nothing is committed" in str(err.value)
    assert (r / "feed.xml").read_text() == "<rss/>"
    assert head(r) == before


def test_staging_is_by_explicit_path_and_there_is_no_push():
    import re
    text = TOOL.read_text(encoding="utf-8")
    assert re.search(r'"add",\s*"(?:-A|--all|-u|\.)"', text) is None
    assert re.search(r'git\(repo,\s*"push"', text) is None and '"push"' not in text.replace("git push", "")


# ---- git metadata in the dist: a copy of it would plant a repository, hooks or config inside katha-feed ----

@pytest.mark.parametrize("relative", [
    ".git/config", ".git/hooks/pre-commit", "assets/.git/config", "assets/sub/.git/HEAD",
    ".gitignore", ".gitattributes", "assets/.gitignore", "assets/sub/deep/.gitmodules", ".github/workflows/x.yml",
    ".GIT/config", ".Gitignore",
])
def test_refuses_any_git_named_entry_in_the_dist_at_any_depth(tmp_path, relative):
    r = feed_repo(tmp_path); d = dist(tmp_path)
    (d / relative).parent.mkdir(parents=True, exist_ok=True); (d / relative).write_text("x")
    res = publish(r, d, "--no-fetch")
    refused(res, ".git")
    assert (r / "index.html").read_text() == "old" and git(r, "status", "--porcelain").stdout == ""
    assert not (r / "assets").exists() and not (r / ".gitignore").exists()


def test_a_gitlink_file_named_dot_git_is_refused_too(tmp_path):
    r = feed_repo(tmp_path); d = dist(tmp_path); (d / ".git").write_text("gitdir: ../elsewhere\n")
    refused(publish(r, d, "--no-fetch"), ".git")


def test_other_dotfiles_in_the_dist_are_skipped_not_refused(tmp_path):
    r = feed_repo(tmp_path); d = dist(tmp_path); (d / ".DS_Store").write_text("x")
    res = publish(r, d, "--no-fetch")
    assert res.returncode == 0, said(res)
    assert ".DS_Store" in res.stdout and not (r / ".DS_Store").exists()


# ---- a failure in the middle of the copy ----

PARTLY = "partly written"


def test_an_os_error_while_copying_is_a_refusal_that_says_to_check_git_status(tmp_path, capsys):
    tool = load_tool()
    r = feed_repo(tmp_path); d = dist(tmp_path)
    real = tool.copy_file

    def fails_on_the_third_file(src, dest):
        if dest.name == "robots.txt":
            raise PermissionError(13, "Permission denied", str(dest))
        real(src, dest)

    tool.copy_file = fails_on_the_third_file
    code = tool.main(["--repo", str(r), "--dist", str(d), "--no-fetch", "--site-sha", SITE_SHA])
    err = capsys.readouterr().err
    assert code == 2
    assert PARTLY in err and "git status" in err and str(r) in err and "robots.txt" in err
    assert (r / "index.html").read_text() == "new"                      # the warning is true: some files are written
    assert git(r, "status", "--porcelain").stdout != "" and head(r) == git(r, "rev-parse", "main").stdout.strip()
    assert (r / "feed.xml").read_text() == "<rss/>"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_a_read_only_assets_directory_is_a_refusal_not_a_traceback(tmp_path):
    r = feed_repo(tmp_path)
    (r / "assets").mkdir(); (r / "assets" / "old.css").write_text("old")
    git(r, "add", "assets/old.css"); git(r, "commit", "-q", "-m", "assets")
    d = dist(tmp_path)
    (r / "assets").chmod(0o555)
    try:
        res = publish(r, d, "--no-fetch")
    finally:
        (r / "assets").chmod(0o755)
    assert res.returncode == 2, said(res)
    assert "Traceback" not in said(res) and PARTLY in said(res) and "git status" in said(res)
    assert (r / "feed.xml").read_text() == "<rss/>" and (r / "CNAME").exists()


def test_an_os_error_while_removing_a_stale_file_is_the_same_refusal(tmp_path, capsys):
    tool = load_tool()
    r = feed_repo(tmp_path)
    (r / "assets").mkdir(); (r / "assets" / "old.css").write_text("old")
    git(r, "add", "assets/old.css"); git(r, "commit", "-q", "-m", "assets")
    d = dist(tmp_path)

    def cannot_remove(repo, rel):
        raise OSError(30, "Read-only file system", rel)

    tool.remove_file = cannot_remove
    code = tool.main(["--repo", str(r), "--dist", str(d), "--no-fetch", "--site-sha", SITE_SHA])
    err = capsys.readouterr().err
    assert code == 2 and PARTLY in err and "git status" in err and "assets/old.css" in err


def test_a_git_failure_after_the_copy_also_says_the_tree_may_be_partly_written(tmp_path, capsys):
    tool = load_tool()
    r = feed_repo(tmp_path); d = dist(tmp_path)
    real = tool.git

    def add_fails(repo, *args, **kwargs):
        if args[0] == "add":
            raise tool.Refusal("git add failed: index.lock exists")
        return real(repo, *args, **kwargs)

    tool.git = add_fails
    code = tool.main(["--repo", str(r), "--dist", str(d), "--no-fetch", "--site-sha", SITE_SHA])
    err = capsys.readouterr().err
    assert code == 2 and "index.lock" in err and PARTLY in err and "git status" in err


def test_a_failure_before_the_copy_does_not_claim_the_tree_was_touched(tmp_path):
    r = feed_repo(tmp_path); d = dist(tmp_path, extra="feed.xml")
    res = publish(r, d, "--no-fetch")
    assert res.returncode == 2 and PARTLY not in said(res)


# ---- names are never globs ----

def test_git_add_runs_with_literal_pathspecs(tmp_path, monkeypatch):
    tool = load_tool()
    r = feed_repo(tmp_path); d = dist(tmp_path)
    seen = []
    real = subprocess.run

    def spy(cmd, *args, **kwargs):
        seen.append((cmd, (kwargs.get("env") or {}).get("GIT_LITERAL_PATHSPECS")))
        return real(cmd, *args, **kwargs)

    monkeypatch.setattr(tool.subprocess, "run", spy)
    monkeypatch.setenv("GIT_LITERAL_PATHSPECS", "0")               # whatever the caller had, the tool decides
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    tool.publish(r, d, dry_run=False, fetch=False, site_sha=SITE_SHA, say=lambda line: None)
    adds = [flag for cmd, flag in seen if cmd[3:4] == ["add"]]
    assert adds and set(adds) == {"1"}, seen


def test_file_names_with_glob_characters_are_copied_and_committed_as_themselves(tmp_path):
    r = feed_repo(tmp_path)
    (r / "assets").mkdir()
    for name, text in (("a.css", "old a"), ("[ab].css", "old star"), ("gone.css", "gone")):
        (r / "assets" / name).write_text(text)
    git(r, "add", "assets"); git(r, "commit", "-q", "-m", "assets")
    d = dist(tmp_path)
    (d / "assets" / "*.css").write_text("star")
    (d / "assets" / "[ab].css").write_text("bracket")
    (d / "assets" / "a?.css").write_text("question")
    res = publish(r, d, "--no-fetch")
    assert res.returncode == 0, said(res)
    changed = sorted(git(r, "show", "--name-only", "--format=", "HEAD", "-z").stdout.split("\0"))
    assert [c for c in changed if c] == ["assets/*.css", "assets/[ab].css", "assets/a.css", "assets/a?.css",
                                        "assets/gone.css", "index.html", "robots.txt", "sitemap.xml"]
    shown = lambda name: git(r, "show", f"HEAD:assets/{name}").stdout
    assert (shown("*.css"), shown("[ab].css"), shown("a?.css"), shown("a.css")) == ("star", "bracket", "question", "a{}")
    assert not (r / "assets" / "gone.css").exists() and git(r, "status", "--porcelain").stdout == ""


def test_the_staged_set_guard_is_still_there():
    text = TOOL.read_text(encoding="utf-8")
    assert 'git(repo, "diff", "--cached", "--name-only"' in text and "staged != sorted(changed + stale)" in text
