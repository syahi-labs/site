# tests/test_partials.py
#
# A page that includes a partial is made of two files, so a change to either is a change to the page.
#   - lastmod is the latest commit date over the page source and every partial it includes, directly or
#     through another partial, so editing a partial moves the lastmod of every page that includes it;
#   - an include the build cannot trace to a file is a build problem;
#   - the approval integrity rule: a non-draft page whose source or partial was committed after its
#     `approved` date was changed after she approved it. A release build refuses that (a problem naming the
#     page and the file); a dev build says so (a warning).
# Made-up pages and made-up dates throughout.
import os
import re
import subprocess
from pathlib import Path

import jinja2

from sitebuild.includes import included_templates
from sitebuild.pipeline import build

SITEMAP_ROW = r"<loc>https://syahi.example(/[a-z]*)</loc>\s*<lastmod>([0-9-]+)</lastmod>"
NOTE = "{% include \"partials/note.html\" %}\n"


# ---- tracing includes ----

def env_for(tmp_path, **templates):
    root = tmp_path / "templates"
    for name, text in templates.items():
        path = root / name.replace("__", "/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    root.mkdir(exist_ok=True)
    return jinja2.Environment(loader=jinja2.FileSystemLoader(root), autoescape=True)


def relative(paths, tmp_path):
    return [p.relative_to(tmp_path / "templates").as_posix() for p in paths]


def test_a_body_with_no_include_has_no_dependency(tmp_path):
    env = env_for(tmp_path)
    assert included_templates(env, "<p>Hello {{ 1 + 1 }}</p>") == ([], [])


def test_a_direct_include_is_found_with_its_file(tmp_path):
    env = env_for(tmp_path, partials__a="<p>a</p>")
    files, problems = included_templates(env, '<h1>x</h1>{% include "partials/a" %}')
    assert problems == [] and relative(files, tmp_path) == ["partials/a"]
    assert files[0].is_file() and files[0].read_text(encoding="utf-8") == "<p>a</p>"


def test_an_include_inside_a_condition_or_a_loop_is_still_a_dependency(tmp_path):
    env = env_for(tmp_path, partials__a="a", partials__b="b")
    body = '{% if x %}{% include "partials/a" %}{% endif %}{% for i in y %}{% include "partials/b" %}{% endfor %}'
    files, problems = included_templates(env, body)
    assert problems == [] and relative(files, tmp_path) == ["partials/a", "partials/b"]


def test_a_partial_that_includes_another_is_followed(tmp_path):
    env = env_for(tmp_path, partials__a='<i>{% include "partials/b" %}</i>', partials__b='{% include "partials/c" %}', partials__c="c")
    files, problems = included_templates(env, '{% include "partials/a" %}')
    assert problems == [] and relative(files, tmp_path) == ["partials/a", "partials/b", "partials/c"]


def test_a_template_reached_twice_is_listed_once_and_a_cycle_ends(tmp_path):
    env = env_for(tmp_path, partials__a='{% include "partials/b" %}', partials__b='{% include "partials/a" %}')
    files, problems = included_templates(env, '{% include "partials/a" %}{% include "partials/b" %}{% include "partials/a" %}')
    assert problems == [] and relative(files, tmp_path) == ["partials/a", "partials/b"]


def test_extends_import_and_from_import_are_dependencies_too(tmp_path):
    env = env_for(tmp_path, layouts__x="{% block b %}{% endblock %}", macros="{% macro m() %}m{% endmacro %}")
    files, problems = included_templates(env, '{% extends "layouts/x" %}{% import "macros" as m %}{% from "macros" import m %}')
    assert problems == [] and relative(files, tmp_path) == ["layouts/x", "macros"]


def test_an_include_that_is_not_a_fixed_name_is_a_problem(tmp_path):
    env = env_for(tmp_path, partials__a="a")
    files, problems = included_templates(env, '{% set n = "partials/a" %}{% include n %}')
    assert files == [] and len(problems) == 1 and "include" in problems[0] and "fixed" in problems[0]


def test_an_include_of_a_file_that_is_not_there_is_a_problem_naming_it(tmp_path):
    env = env_for(tmp_path)
    files, problems = included_templates(env, '{% include "partials/missing" %}')
    assert files == [] and len(problems) == 1 and "partials/missing" in problems[0] and "not found" in problems[0]


def test_a_missing_file_deep_in_a_chain_is_found_with_the_chain_so_far(tmp_path):
    env = env_for(tmp_path, partials__a='{% include "partials/gone" %}')
    files, problems = included_templates(env, '{% include "partials/a" %}')
    assert relative(files, tmp_path) == ["partials/a"] and "partials/gone" in problems[0]


def test_a_template_the_engine_cannot_parse_is_left_for_the_render_to_report(tmp_path):
    env = env_for(tmp_path, partials__a="{% if %}")
    assert included_templates(env, '{% include "partials/a" %}{% if %}') == ([], [])
    files, problems = included_templates(env, '{% include "partials/a" %}')
    assert relative(files, tmp_path) == ["partials/a"] and problems == []


# ---- the build: lastmod ----

def git(root, *args, day=None):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    if day:
        stamp = f"{day}T12:00:00+00:00"
        env.update(GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=root, check=True, env=env, capture_output=True)


def commit(root, day, *paths):
    if not (root / ".git").exists():
        git(root, "init", "-q")
    git(root, "add", *paths)
    git(root, "commit", "-q", "-m", f"c {day}", day=day)


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def include_note(root: Path, *pages: str, partial_text="<p>A made-up note.</p>\n"):
    write(root / "templates" / "partials" / "note.html", partial_text)
    for page in pages:
        path = root / "content" / page
        path.write_text(path.read_text(encoding="utf-8") + NOTE, encoding="utf-8")


def lastmods(out: Path) -> dict:
    return dict(re.findall(SITEMAP_ROW, (out / "syahi.sh" / "sitemap.xml").read_text(encoding="utf-8")))


def test_a_partial_committed_after_its_pages_moves_every_pages_lastmod(mini_root, tmp_path):
    include_note(mini_root, "index.html", "signet.html")
    commit(mini_root, "2026-09-01", "content/index.html", "content/signet.html")
    commit(mini_root, "2026-09-20", "templates/partials/note.html")
    assert build(mini_root, tmp_path / "dist").problems == []
    assert lastmods(tmp_path / "dist") == {"/": "2026-09-20", "/signet": "2026-09-20"}


def test_a_partial_older_than_the_page_changes_nothing(mini_root, tmp_path):
    include_note(mini_root, "index.html", "signet.html")
    commit(mini_root, "2026-08-01", "templates/partials/note.html")
    commit(mini_root, "2026-09-01", "content/index.html", "content/signet.html")
    assert build(mini_root, tmp_path / "dist").problems == []
    assert lastmods(tmp_path / "dist") == {"/": "2026-09-01", "/signet": "2026-09-01"}


def test_only_the_pages_that_include_the_partial_move(mini_root, tmp_path):
    include_note(mini_root, "index.html")
    commit(mini_root, "2026-09-01", "content/index.html", "content/signet.html")
    commit(mini_root, "2026-09-20", "templates/partials/note.html")
    assert build(mini_root, tmp_path / "dist").problems == []
    assert lastmods(tmp_path / "dist") == {"/": "2026-09-20", "/signet": "2026-09-01"}


def test_a_partial_two_levels_down_moves_the_page(mini_root, tmp_path):
    include_note(mini_root, "index.html", partial_text='<p>x</p>{% include "partials/inner.html" %}\n')
    write(mini_root / "templates" / "partials" / "inner.html", "<p>inner</p>\n")
    commit(mini_root, "2026-09-01", "content/index.html", "content/signet.html", "templates/partials/note.html")
    commit(mini_root, "2026-09-25", "templates/partials/inner.html")
    assert build(mini_root, tmp_path / "dist").problems == []
    assert lastmods(tmp_path / "dist") == {"/": "2026-09-25", "/signet": "2026-09-01"}


def test_the_katha_host_page_moves_with_a_partial_too(mini_root, tmp_path):
    katha = mini_root / "katha" / "content" / "index.html"
    katha.write_text(katha.read_text(encoding="utf-8") + NOTE, encoding="utf-8")
    write(mini_root / "templates" / "partials" / "note.html", "<p>A made-up note.</p>\n")
    commit(mini_root, "2026-09-01", "katha/content/index.html")
    commit(mini_root, "2026-09-22", "templates/partials/note.html")
    assert build(mini_root, tmp_path / "dist").problems == []
    sitemap = (tmp_path / "dist" / "katha.syahi.sh" / "sitemap.xml").read_text(encoding="utf-8")
    assert "<lastmod>2026-09-22</lastmod>" in sitemap


def test_an_untracked_partial_adds_no_date_and_an_untracked_page_still_falls_back_to_updated(mini_root, tmp_path):
    include_note(mini_root, "index.html", "signet.html")
    commit(mini_root, "2026-09-01", "content/signet.html")        # the partial and the home are not tracked
    assert build(mini_root, tmp_path / "dist").problems == []
    assert lastmods(tmp_path / "dist") == {"/": "2026-10-06", "/signet": "2026-09-01"}


def test_a_dynamic_include_is_a_build_problem_naming_the_page(mini_root, tmp_path):
    page = mini_root / "content" / "index.html"
    include_note(mini_root)
    page.write_text(page.read_text(encoding="utf-8") + '{% set name = "partials/note.html" %}{% include name %}\n', encoding="utf-8")
    result = build(mini_root, tmp_path / "dist")
    assert any(str(page) in p and "include" in p and "fixed" in p for p in result.problems)


def test_a_missing_partial_is_reported_once_by_the_render(mini_root, tmp_path):
    page = mini_root / "content" / "index.html"
    page.write_text(page.read_text(encoding="utf-8") + '{% include "partials/nowhere.html" %}\n', encoding="utf-8")
    result = build(mini_root, tmp_path / "dist")
    assert [p for p in result.problems if "nowhere" in p] == [f"{page}: template 'partials/nowhere.html' not found"]


# ---- the build: an edit after approval needs a new approval ----

def stale(items, page_name):
    return [i for i in items if page_name in i and "after the page was approved" in i]


def test_a_partial_changed_after_approval_is_a_release_problem_and_a_dev_warning(mini_root, tmp_path):
    include_note(mini_root, "index.html", "signet.html")
    commit(mini_root, "2026-10-06", "content/index.html", "content/signet.html")
    commit(mini_root, "2026-10-07", "templates/partials/note.html")
    dev = build(mini_root, tmp_path / "dev")
    assert stale(dev.problems, "index.html") == [] and dev.problems == []
    for name in ("index.html", "signet.html"):
        (warning,) = stale(dev.warnings, name)
        assert "partials/note.html" in warning and "2026-10-07" in warning and "2026-10-06" in warning and "re-approve" in warning
    release = build(mini_root, tmp_path / "release", release=True)
    for name in ("index.html", "signet.html"):
        (problem,) = stale(release.problems, name)
        assert str(mini_root / "content" / name) in problem and "partials/note.html" in problem
        assert stale(release.warnings, name) == []


def test_a_page_source_changed_after_approval_is_the_same_finding_naming_the_page_file(mini_root, tmp_path):
    commit(mini_root, "2026-10-06", "content/index.html", "content/signet.html")
    path = mini_root / "content" / "signet.html"
    path.write_text(path.read_text(encoding="utf-8") + "<p>Added later.</p>\n", encoding="utf-8")
    commit(mini_root, "2026-10-09", "content/signet.html")
    release = build(mini_root, tmp_path / "release", release=True)
    (problem,) = stale(release.problems, "signet.html")
    assert problem.count(str(path)) >= 2 and "2026-10-09" in problem
    assert stale(release.problems, "index.html") == []
    (warning,) = stale(build(mini_root, tmp_path / "dev").warnings, "signet.html")
    assert "2026-10-09" in warning


def test_a_change_on_the_day_of_approval_passes(mini_root, tmp_path):
    include_note(mini_root, "index.html", "signet.html")
    commit(mini_root, "2026-10-06", "content/index.html", "content/signet.html", "templates/partials/note.html")
    for release in (False, True):
        result = build(mini_root, tmp_path / f"out-{release}", release=release)
        assert stale(result.problems, "html") == [] and stale(result.warnings, "html") == []


def test_a_change_before_approval_passes(mini_root, tmp_path):
    include_note(mini_root, "index.html", "signet.html")
    commit(mini_root, "2026-09-30", "content/index.html", "content/signet.html", "templates/partials/note.html")
    result = build(mini_root, tmp_path / "release", release=True)
    assert stale(result.problems, "html") == [] and stale(result.warnings, "html") == []


def test_a_draft_page_is_exempt_because_it_claims_no_approval(mini_root, tmp_path):
    page = mini_root / "content" / "signet.html"
    page.write_text(page.read_text(encoding="utf-8").replace("approved: 2026-10-06\n", "draft: true\n", 1), encoding="utf-8")
    include_note(mini_root, "signet.html")
    commit(mini_root, "2026-10-20", "content/signet.html", "templates/partials/note.html")
    result = build(mini_root, tmp_path / "dist", release=True)
    assert stale(result.problems, "signet.html") == [] and stale(result.warnings, "signet.html") == []
    assert any("signet.html" in p and "draft" in p for p in result.problems)       # still refused, for being a draft


def test_a_tree_with_no_git_history_has_nothing_to_compare(mini_root, tmp_path):
    include_note(mini_root, "index.html")
    result = build(mini_root, tmp_path / "release", release=True)
    assert stale(result.problems, "html") == [] and stale(result.warnings, "html") == []


def test_the_finding_names_every_file_that_changed_after_approval(mini_root, tmp_path):
    include_note(mini_root, "index.html", partial_text='{% include "partials/inner.html" %}\n')
    write(mini_root / "templates" / "partials" / "inner.html", "<p>inner</p>\n")
    commit(mini_root, "2026-10-08", "content/index.html", "templates/partials/note.html", "templates/partials/inner.html")
    result = build(mini_root, tmp_path / "release", release=True)
    found = stale(result.problems, "index.html")
    assert len(found) == 3
    assert {name for name in ("content/index.html", "partials/note.html", "partials/inner.html") if any(name in f for f in found)} == {
        "content/index.html", "partials/note.html", "partials/inner.html"}
