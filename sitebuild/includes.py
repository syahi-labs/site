"""The template files a page body is made of.

A page body can `{% include %}` a partial, and a partial can include another, so a page is the file
it is written in plus every file it pulls in. `included_templates` finds them by reading the templates,
not by rendering them: the build needs the files even when a branch of the page does not run.

What it returns is (files, problems). `files` are the resolved template paths in the order first met,
each once, so a cycle ends. `problems` say what could not be traced, without the page's name (the caller
adds it): an include whose name is not a fixed string, and a name no template answers to. A template the
engine cannot parse is left alone: rendering the page reports that error, and it names the file.
"""
from __future__ import annotations

from pathlib import Path

import jinja2
from jinja2 import meta


def included_templates(env: jinja2.Environment, body: str) -> tuple[list[Path], list[str]]:
    """Every template `body` includes, extends or imports, directly or through the templates it reaches."""
    files: list[Path] = []
    problems: list[str] = []
    seen: set[str] = set()
    pending = [body]
    while pending:
        try:
            names = list(meta.find_referenced_templates(env.parse(pending.pop(0))))
        except jinja2.TemplateSyntaxError:
            continue
        for name in names:
            if name is None:
                problems.append("an include whose name is not a fixed string cannot be traced to its file: write it as a quoted name")
            elif name not in seen:
                seen.add(name)
                try:
                    source, filename, _ = env.loader.get_source(env, name)
                except jinja2.TemplateNotFound:
                    problems.append(f"include '{name}' not found under templates/")
                    continue
                files.append(Path(filename))
                pending.append(source)
    return files, problems
