"""A build of the real site inputs, for tests that check the pages that ship.

The real inputs are copied to a throwaway root and built into a throwaway out directory. Pages of
the main host that Task 9 ports in later parts (the home page and /signet, which every page links to)
get a stand-in until the real page exists, so the whole build can be held to zero problems now and
keeps being held to it as each real page lands. A stand-in is only ever written where no real page is.
It shows the organisation's name and its Devanagari name because the main host's home page carries the
Organization structured data, and every string in structured data must be on the page.
"""
import shutil
from pathlib import Path
from typing import NamedTuple

from sitebuild.pipeline import BuildResult, build

REPO = Path(__file__).resolve().parents[1]
REAL_INPUTS = ("katha", "data", "templates", "tokens", "assets", "content")
STAND_IN = """---
title: Stand-in
description: A stand-in for a page that is ported in a later part of Task 9.
updated: 2026-10-06
approved: 2026-10-06
layout: page
claims: [org-name, org-alternate-name]
---
<h1>{{ claim("org-name") }}</h1>
<p><span lang="hi">{{ claim("org-alternate-name") }}</span></p>
"""
STAND_INS = ("index.html", "signet.html")


class RealSite(NamedTuple):
    root: Path
    out: Path
    result: BuildResult


def build_real_site(tmp_path_factory) -> RealSite:
    root = tmp_path_factory.mktemp("site")
    for name in REAL_INPUTS:
        if (REPO / name).is_dir():
            shutil.copytree(REPO / name, root / name)
    shutil.copy(REPO / "site.yaml", root / "site.yaml")
    (root / "content").mkdir(exist_ok=True)
    for name in STAND_INS:
        if not (root / "content" / name).exists():
            (root / "content" / name).write_text(STAND_IN, encoding="utf-8")
    out = tmp_path_factory.mktemp("out") / "dist"
    return RealSite(root, out, build(root, out))
