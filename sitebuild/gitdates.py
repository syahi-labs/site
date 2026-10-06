"""The date a content file last changed, from git.

`last_commit_date` asks the file's own repo (`git -C <its directory>`), so it works
for a content file in this repo and for one in another. It reports the committer
date (`%cs`), the day the change landed. A file git does not track, in a repo or
outside one, has no date: `None`. Any other git failure raises GitDateError naming
the file, so a broken checkout cannot quietly hand a stale `lastmod` to the sitemap.
"""
from __future__ import annotations

import datetime
import os
import subprocess
from pathlib import Path

# git's "this is not a failure, there is just no history for the file" messages (read under LC_ALL=C).
NO_HISTORY = ("not a git repository", "does not have any commits yet")


class GitDateError(Exception):
    """git could not answer for a reason other than 'untracked'. The message names the file."""


def last_commit_date(path: Path) -> datetime.date | None:
    """The committer date of the last commit touching `path`, in its repo; None if untracked."""
    path = Path(path)
    # LC_ALL=C pins git's messages, so the NO_HISTORY check does not depend on the machine's language.
    env = dict(os.environ, LC_ALL="C")
    command = ["git", "-C", str(path.parent), "log", "-1", "--format=%cs", "--", path.name]
    try:
        done = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
    except OSError as err:
        raise GitDateError(f"{path}: cannot run git ({err})") from err
    if done.returncode != 0:
        if any(message in done.stderr for message in NO_HISTORY):
            return None
        raise GitDateError(f"{path}: git log failed ({done.stderr.strip() or 'exit ' + str(done.returncode)})")
    stamp = done.stdout.strip()
    if not stamp:
        return None
    try:
        return datetime.date.fromisoformat(stamp)
    except ValueError as err:
        raise GitDateError(f"{path}: git printed {stamp!r}, which is not a YYYY-MM-DD date") from err
