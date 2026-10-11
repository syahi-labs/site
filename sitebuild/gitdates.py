"""The date a content file last changed, and whether it has changes git does not yet hold, from git.

`last_commit_date` asks the file's own repo (`git -C <its directory>`), so it works
for a content file in this repo and for one in another. It reports the AUTHOR date
(`%as`) of the latest commit that touched the file, the day the change was written.
The committer date is the day the commit was last replayed, and a rebase, an amend, a
cherry-pick or a squash merge re-dates it without anything being written, so a lastmod
or an approval compared against it would move for no reason. The author date survives
all four. The latest author date over the file's whole history is used, not the tip
commit's, so a commit replayed on top of newer work with an older author date cannot
hide the newer change. A file git does not track, in a repo or outside one, has no
date: `None`. Any other git failure raises GitDateError naming the file, so a broken
checkout cannot quietly hand a stale `lastmod` to the sitemap.

`has_uncommitted_changes` says whether the file differs from what git holds: modified,
staged, or never added. A date from git describes the committed file, so a file with
uncommitted changes has a date that does not describe it.
"""
from __future__ import annotations

import datetime
import os
import subprocess
from pathlib import Path

# git's "this is not a failure, there is just no history for the file" messages (read under LC_ALL=C).
# The no-repo message is matched through its "(or any" clause, which both genuine wordings carry
# ("...(or any of the parent directories)", and "...(or any parent up to mount point /tmp)" across a
# filesystem boundary). A `.git` file pointing at a gitdir that is gone (a deleted worktree) says only
# "not a git repository: <path>", and that is a broken checkout, not a new file.
NO_HISTORY = ("not a git repository (or any", "does not have any commits yet")


class GitDateError(Exception):
    """git could not answer for a reason other than 'untracked'. The message names the file."""


def _git(path: Path, *args: str) -> subprocess.CompletedProcess:
    """Run git in the file's own directory. LC_ALL=C pins git's messages, so NO_HISTORY does not depend on
    the machine's language."""
    env = dict(os.environ, LC_ALL="C")
    try:
        return subprocess.run(["git", "-C", str(path.parent), *args], capture_output=True, text=True, env=env, check=False)
    except OSError as err:
        raise GitDateError(f"{path}: cannot run git ({err})") from err


def last_commit_date(path: Path) -> datetime.date | None:
    """The latest author date of any commit touching `path`, in its repo; None if untracked."""
    path = Path(path)
    done = _git(path, "log", "--format=%as", "--", path.name)
    if done.returncode != 0:
        if any(message in done.stderr for message in NO_HISTORY):
            return None
        raise GitDateError(f"{path}: git log failed ({done.stderr.strip() or 'exit ' + str(done.returncode)})")
    stamps = done.stdout.split()
    if not stamps:
        return None
    try:
        return max(datetime.date.fromisoformat(stamp) for stamp in stamps)
    except ValueError as err:
        raise GitDateError(f"{path}: git printed {done.stdout.strip()!r}, which is not a list of YYYY-MM-DD dates") from err


def has_uncommitted_changes(path: Path) -> bool:
    """Whether `path` is modified, staged or untracked in its repo. A file outside any repo has nothing to
    differ from, so it is False."""
    path = Path(path)
    done = _git(path, "status", "--porcelain", "--untracked-files=all", "--", path.name)
    if done.returncode != 0:
        if any(message in done.stderr for message in NO_HISTORY):
            return False
        raise GitDateError(f"{path}: git status failed ({done.stderr.strip() or 'exit ' + str(done.returncode)})")
    return bool(done.stdout.strip())
