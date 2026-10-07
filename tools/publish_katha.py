#!/usr/bin/env python3
"""Publish katha.syahi.sh's index from a site build into the katha-feed repo, and commit it. Never push.

    python tools/publish_katha.py --repo PATH --dist PATH --site-sha SHA [--dry-run] [--no-fetch]

PATH for --repo is a clean checkout of katha-feed on main. PATH for --dist is the katha host's
directory from a build, `dist/katha.syahi.sh`. SHA is the syahi-labs/site commit that build came from.

katha.syahi.sh also serves feed.xml, which Spotify reads, and CNAME, which keeps the domain. This tool
may never change either one. It copies only what a build owns:

    index.html, robots.txt, sitemap.xml, favicon.ico, apple-touch-icon.png and _headers (the last three when the
    build has them) and everything under assets/

and removes stale files under assets/ and nowhere else. It stages each path by name (never `-A` or
`.`, and git is told to read every path literally, so a file called `*.css` is a file and not a
pattern), commits `katha.syahi.sh: index from syahi-labs/site <sha> [agent]`, and stops. Pushing is
her decision, so there is no push in this file.

Exit 0: published, nothing to publish, or a dry run. Exit 2: refused, with the reason on stderr. A
refusal changes nothing, except one that comes after the copy has started (a write fails, feed.xml
or CNAME fails its read-back, git fails): that one says the working tree may be partly written and
must be checked with `git status` before trying again. Exit 1: the commit itself failed after the
copy; the message says how to look.

It refuses when:
  - the repo is not a git checkout, or has any uncommitted change (staged, modified or untracked);
  - the repo is not on main;
  - HEAD differs from origin/main after a fetch (skipped by --no-fetch, which tests use);
  - the dist holds feed.xml or CNAME anywhere, in any letter case, or anything named .git or starting
    with .git (.git, .gitignore, .github, ...) at any depth, or a symbolic link, or no index.html,
    robots.txt or sitemap.xml;
  - the dist sits inside the repo or the repo inside the dist;
  - the copy would change feed.xml or CNAME: a destination that is a symbolic link, sits behind
    one, or is the same file as one of them (a hard link).

--site-sha is required and is used verbatim in the commit subject: the commit is the receipt that
says which site commit the published files came from, so the tool never guesses it from its own
checkout. Lower-case hex, 4 to 40 characters.

Standard library only.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PROTECTED = ("feed.xml", "CNAME")            # katha-feed owns both; no build may change either
PAGES = ("index.html", "robots.txt", "sitemap.xml")
# Root files browsers and iOS ask for by a fixed URL, with no page to read them from. Copied when the build has them.
ROOT_ICONS = ("favicon.ico", "apple-touch-icon.png")
# Edge cache rules, written by every build. Copied when the build has it.
ROOT_RULES = ("_headers",)
ASSETS = "assets"
BRANCH = "main"
REMOTE = "origin"
SHA = re.compile(r"[0-9a-f]{4,40}")
FETCH_TIMEOUT = 120
SHOWN = 8                                     # how many paths a refusal lists before it says "and N more"
GIT_NAME = ".git"                             # a dist entry named this or starting with it never gets copied


class Refusal(Exception):
    """The publish must not go ahead. The message is the reason, and it is the whole output."""


class CommitFailed(Exception):
    """git commit failed after the copy was staged."""


def git(repo: Path, *args: str, check: bool = True, timeout: float | None = None) -> subprocess.CompletedProcess:
    # A fetch must fail, never wait for a password. Every path handed to git is a literal name:
    # a build file called `*.css` or `[ab].css` is that file, not a pattern that matches others.
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_LITERAL_PATHSPECS="1")
    try:
        done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=env, timeout=timeout)
    except subprocess.TimeoutExpired as err:
        raise Refusal(f"git {args[0]} timed out after {err.timeout:.0f} seconds") from err
    except OSError as err:
        raise Refusal(f"cannot run git ({err})") from err
    if check and done.returncode != 0:
        raise Refusal(f"git {' '.join(args[:2])} failed in {repo}: {_first_line(done.stderr or done.stdout)}")
    return done


def _first_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[0] if lines else "no output"


def _some(items: list[str]) -> str:
    shown = ", ".join(items[:SHOWN])
    return shown + (f" and {len(items) - SHOWN} more" if len(items) > SHOWN else "")


# ---- the dist ----

def plan_dist(dist: Path) -> tuple[list[str], list[str]]:
    """(paths to copy, paths left out), each relative to the dist with `/` separators, both sorted.

    Raises Refusal for a dist that is not a clean build output of the katha host.
    """
    if not dist.is_dir():
        raise Refusal(f"the dist {dist} is not a directory")
    blocked = {name.lower() for name in PROTECTED}
    everything, protected, gitnames, links = [], [], [], []
    for root, dirs, files in os.walk(dist, followlinks=False):
        for name in dirs + files:
            path = Path(root, name)
            rel = path.relative_to(dist).as_posix()
            if name.lower() in blocked:
                protected.append(rel)
            if name.lower().startswith(GIT_NAME):
                gitnames.append(rel)
            if path.is_symlink():
                links.append(rel)
            elif not path.is_dir():
                if not path.is_file():
                    links.append(rel)           # a socket or a device: not a build output either
                else:
                    everything.append(rel)
        dirs[:] = [name for name in dirs if not name.lower().startswith(GIT_NAME)]   # named already; do not walk inside
    if protected:
        raise Refusal(f"the dist contains {_some(sorted(protected))}: feed.xml and CNAME belong to katha-feed, "
                      "and a build must never carry either")
    if gitnames:
        raise Refusal(f"the dist contains {_some(sorted(gitnames))}: nothing named .git or starting with .git is ever "
                      "copied, because a copy would plant git metadata, hooks or ignore rules inside katha-feed")
    if links:
        raise Refusal(f"the dist contains a symbolic link or a special file ({_some(sorted(links))}); "
                      "a build output is plain files")
    missing = [name for name in PAGES if name not in everything]
    if missing:
        raise Refusal(f"the dist has no {', '.join(missing)}: this is not the katha host's build output")
    if (dist / ASSETS).exists() and not (dist / ASSETS).is_dir():
        raise Refusal(f"the dist's {ASSETS} is not a directory")
    icons = tuple(name for name in (*ROOT_ICONS, *ROOT_RULES) if name in everything)
    copy = sorted(PAGES + icons + tuple(rel for rel in everything if rel.startswith(ASSETS + "/")))
    left = sorted(rel for rel in everything if rel not in copy)
    return copy, left


def check_apart(repo: Path, dist: Path) -> None:
    repo_real, dist_real = repo.resolve(), dist.resolve()
    if dist_real == repo_real or repo_real in dist_real.parents:
        raise Refusal(f"the dist {dist} is inside the repo {repo}: build it somewhere else")
    if dist_real in repo_real.parents:
        raise Refusal(f"the repo {repo} is inside the dist {dist}")


# ---- the repo ----

def check_repo(repo: Path, fetch: bool) -> None:
    if not repo.is_dir():
        raise Refusal(f"the repo {repo} is not a directory")
    top = git(repo, "rev-parse", "--show-toplevel", check=False)
    if top.returncode != 0:
        raise Refusal(f"{repo} is not a git repository")
    if Path(top.stdout.strip()).resolve() != repo.resolve():
        raise Refusal(f"{repo} is not the top of a git repository (that is {top.stdout.strip()}); name the top")
    branch = git(repo, "symbolic-ref", "--short", "-q", "HEAD", check=False).stdout.strip()
    if branch != BRANCH:
        raise Refusal(f"the repo is on {branch or 'a detached HEAD'}, not {BRANCH}")
    dirty = [entry for entry in git(repo, "status", "--porcelain", "--untracked-files=all", "-z").stdout.split("\0") if entry]
    if dirty:
        raise Refusal(f"the repo has uncommitted changes ({_some([e[3:] for e in dirty])}); "
                      "commit or discard them first")
    if fetch:
        check_origin(repo)


def check_origin(repo: Path) -> None:
    """Fetch origin's main, then HEAD must be exactly origin/main: not behind it, not ahead of it."""
    spec = f"+refs/heads/{BRANCH}:refs/remotes/{REMOTE}/{BRANCH}"
    done = git(repo, "fetch", "--quiet", "--no-tags", REMOTE, spec, check=False, timeout=FETCH_TIMEOUT)
    if done.returncode != 0:
        raise Refusal(f"cannot fetch {REMOTE}/{BRANCH}, so HEAD cannot be compared with it: "
                      f"{_first_line(done.stderr or done.stdout)}")
    mine = git(repo, "rev-parse", "HEAD", check=False)
    theirs = git(repo, "rev-parse", f"refs/remotes/{REMOTE}/{BRANCH}", check=False)
    if mine.returncode != 0 or theirs.returncode != 0:
        raise Refusal(f"cannot read HEAD and {REMOTE}/{BRANCH} to compare them")
    if mine.stdout.strip() != theirs.stdout.strip():
        counts = git(repo, "rev-list", "--left-right", "--count", f"HEAD...{REMOTE}/{BRANCH}", check=False).stdout.split()
        ahead, behind = (counts + ["?", "?"])[:2]
        raise Refusal(f"HEAD is not {REMOTE}/{BRANCH} after a fetch (HEAD {mine.stdout.strip()[:7]} is "
                      f"{ahead} ahead and {behind} behind {theirs.stdout.strip()[:7]}): "
                      "bring the repo level with origin first")


def tracked_assets(repo: Path) -> list[str]:
    out = git(repo, "ls-files", "-z", "--", ASSETS).stdout
    return sorted(p for p in out.split("\0") if p and p.startswith(ASSETS + "/"))


def check_destinations(repo: Path, paths: list[str]) -> None:
    """No path the copy writes or removes may be, or sit behind, a symbolic link, or be a protected file.

    A symbolic link at index.html pointing to feed.xml would make the copy rewrite the feed through it.
    A hard link is the same file under two names, so the same applies. Each is refused by name.
    """
    protected = [repo / name for name in PROTECTED if (repo / name).exists()]
    for rel in paths:
        walk = repo
        for part in Path(rel).parts:
            walk = walk / part
            if walk.is_symlink():
                target = os.path.realpath(walk)
                hits = [p.name for p in protected if os.path.realpath(p) == target]
                note = f"; the copy would change {hits[0]}" if hits else ""
                raise Refusal(f"{walk.relative_to(repo).as_posix()} in the repo is a symbolic link "
                              f"(to {os.path.relpath(target, repo)}){note}: the copy would write through it")
        dest = repo / rel
        for keep in protected:
            if dest.exists() and os.path.samefile(dest, keep):
                raise Refusal(f"{rel} is the same file as {keep.name}; the copy would change {keep.name}")


def _partly_written(repo: Path) -> str:
    return (f"The working tree of {repo} may be partly written and nothing is committed: "
            f"run `git status` in {repo} and check it before trying again")


def snapshot_protected(repo: Path) -> dict[str, bytes]:
    return {name: (repo / name).read_bytes() for name in PROTECTED if (repo / name).is_file()}


def verify_protected(repo: Path, before: dict[str, bytes]) -> None:
    """feed.xml and CNAME must read back exactly as they were. If one moved, put it back and refuse."""
    changed = []
    for name in PROTECTED:
        path = repo / name
        was = before.get(name)
        now = path.read_bytes() if path.is_file() else None
        if was != now:
            changed.append(name)
            if was is not None:
                path.write_bytes(was)
            elif path.exists():
                path.unlink()
    if changed:
        raise Refusal(f"{' and '.join(changed)} changed during the copy and was put back. {_partly_written(repo)}. "
                      "This is a bug in the publish step: stop and tell Surabhi")


# ---- the copy ----

def status_of(repo: Path, dist: Path, rel: str) -> str:
    dest = repo / rel
    if not dest.exists():
        return "add"
    return "same" if dest.read_bytes() == (dist / rel).read_bytes() else "update"


def copy_file(src: Path, dest: Path) -> None:
    """Write src to dest through a temporary file and an atomic replace, so no other name for dest's inode changes."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=dest.name + ".", suffix=".tmp", dir=dest.parent)
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(src.read_bytes())
        os.chmod(temp, 0o644)
        os.replace(temp, dest)
    except BaseException:
        if os.path.exists(temp):
            os.unlink(temp)
        raise


def remove_file(repo: Path, rel: str) -> None:
    (repo / rel).unlink()
    parent = (repo / rel).parent
    while parent != repo / ASSETS and parent != repo and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent


def check_site_sha(site_sha: str) -> str:
    """The sha the caller names, unchanged, or a Refusal. It goes into a commit subject, so it must be only a sha."""
    if not isinstance(site_sha, str) or not SHA.fullmatch(site_sha):
        raise Refusal(f"--site-sha {site_sha!r} is not a git sha: lower-case hex, 4 to 40 characters, "
                      "the syahi-labs/site commit the dist was built from")
    return site_sha


# ---- the whole run ----

def publish(repo: Path, dist: Path, dry_run: bool, fetch: bool, site_sha: str, say) -> None:
    sha = check_site_sha(site_sha)
    check_apart(repo, dist)
    copy, left = plan_dist(dist)
    check_repo(repo, fetch)
    wanted = [rel for rel in copy if rel.startswith(ASSETS + "/")]
    stale = [rel for rel in tracked_assets(repo) if rel not in wanted]
    check_destinations(repo, copy + stale)

    labels = {rel: status_of(repo, dist, rel) for rel in copy}
    changed = [rel for rel in copy if labels[rel] != "same"]
    message = f"katha.syahi.sh: index from syahi-labs/site {sha} [agent]"
    say(f"{'dry run: ' if dry_run else ''}katha.syahi.sh index from syahi-labs/site {sha}")
    say(f"repo {repo}, dist {dist}")
    if not fetch:
        say("note: --no-fetch, so HEAD was not compared with origin/main")
    for rel in copy:
        say(f"  {labels[rel]:<7}{rel}")
    for rel in stale:
        say(f"  remove {rel}")
    for rel in left:
        say(f"  skip   {rel} (not on the publish list)")
    if not changed and not stale:
        say("nothing to publish: the repo already holds this build")
        return
    if dry_run:
        say("feed.xml and CNAME: not on the list, not touched")
        say(f"would commit: {message}")
        return

    before = snapshot_protected(repo)
    try:
        for rel in changed:
            copy_file(dist / rel, repo / rel)
        for rel in stale:
            remove_file(repo, rel)
        verify_protected(repo, before)
        say("feed.xml and CNAME: read back byte for byte, untouched")
        if changed:
            git(repo, "add", "--", *changed)
        if stale:
            git(repo, "rm", "-q", "--", *stale)
        staged = sorted(p for p in git(repo, "diff", "--cached", "--name-only", "--no-renames", "-z").stdout.split("\0") if p)
        if staged != sorted(changed + stale):
            raise Refusal(f"the staged paths ({_some(staged)}) are not the copied paths ({_some(sorted(changed + stale))})")
    except OSError as err:
        raise Refusal(f"{err}. {_partly_written(repo)}") from err
    except Refusal as err:
        raise Refusal(str(err) if "git status" in str(err) else f"{err}. {_partly_written(repo)}") from err
    done = git(repo, "commit", "-q", "-m", message, check=False)
    if done.returncode != 0:
        raise CommitFailed(f"git commit failed: {_first_line(done.stderr or done.stdout)}. The copy is staged in {repo} "
                           f"and nothing is committed. Look with: git -C {repo} status")
    short = git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
    say(f"committed {short}: {message}")
    say(f"not pushed. Pushing is Surabhi's call: git -C {repo} push origin {BRANCH}")


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Copy the katha.syahi.sh build into katha-feed and commit it. Never pushes.")
    parser.add_argument("--repo", type=Path, required=True, help="a clean katha-feed checkout on main")
    parser.add_argument("--dist", type=Path, required=True, help="the katha host's build output, dist/katha.syahi.sh")
    parser.add_argument("--site-sha", required=True,
                        help="REQUIRED. The syahi-labs/site commit the dist was built from. It is used verbatim in the "
                             "commit subject, so it is the receipt; the tool never guesses it from its own checkout")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would change and change nothing in the working tree, the index or HEAD. "
                             "It still fetches origin/main, which updates refs/remotes/origin/main; --no-fetch skips that")
    parser.add_argument("--no-fetch", action="store_true",
                        help="skip the fetch and the HEAD against origin/main check (tests)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    try:
        publish(args.repo, args.dist, args.dry_run, not args.no_fetch, args.site_sha, print)
    except Refusal as err:
        print(f"refused: {err}", file=sys.stderr)
        return 2
    except CommitFailed as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
