"""Shared fixtures."""
import shutil
from pathlib import Path

import pytest

from real_site import RealSite, build_real_site

REPO = Path(__file__).resolve().parents[1]
MINI = Path(__file__).parent / "fixtures" / "mini"
# What a site root holds besides the fixture's own site.yaml, claims and content: the real shared chrome.
SHARED_DIRS = ("templates", "tokens", "assets")


@pytest.fixture
def mini_root(tmp_path):
    """A complete, writable site root: the mini fixture plus the repo's real templates, tokens and assets.

    The fixture holds only the made-up content. The shared chrome is copied from the repo, never kept in
    two places, so a change to a real template is exercised by the pipeline tests at once. Each test gets
    its own copy and may edit it.
    """
    root = tmp_path / "root"
    shutil.copytree(MINI, root)
    for name in SHARED_DIRS:
        source = REPO / name
        if source.is_dir():
            shutil.copytree(source, root / name)
    return root


@pytest.fixture(scope="session")
def real_site(tmp_path_factory) -> RealSite:
    """One build of the real inputs for the whole run, with stand-ins for pages not ported yet. Read only."""
    return build_real_site(tmp_path_factory)
