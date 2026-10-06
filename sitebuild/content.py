"""Load content files into validated Page records.

A content file is a front matter block (YAML between two `---` lines)
followed by a Jinja body. The slug comes from the path.
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

REQUIRED_KEYS = ("title", "description", "updated", "approved", "layout")
OPTIONAL_KEYS = ("claims", "schema", "audience", "og_image", "css")
FENCE = "---"
# A page stylesheet is named, never pathed: tokens/pages/<name>.css, published as assets/pages/<name>.css.
CSS_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")


class ContentError(Exception):
    """A content file or the content directory is invalid. The message names the file."""


@dataclass(frozen=True)
class Page:
    slug: str
    title: str
    description: str
    updated: datetime.date
    approved: datetime.date
    layout: str
    claims: tuple[str, ...]
    schema: tuple[str, ...]
    audience: str | None
    body: str
    source: Path
    og_image: str | None = None
    css: str | None = None     # the name of this page's own stylesheet in tokens/pages/, or None


def load_pages(content_dir: Path) -> list[Page]:
    """Load every `*.html` under content_dir, sorted by slug."""
    if not content_dir.is_dir():
        raise ContentError(f"{content_dir}: content directory not found")
    pages = [_load_page(path, content_dir) for path in content_dir.rglob("*.html")]
    return sorted(pages, key=lambda page: page.slug)


def _slug(path: Path, content_dir: Path) -> str:
    parts = path.relative_to(content_dir).with_suffix("").parts
    if parts == ("index",):
        return "/"
    return "/" + "/".join(parts)


def _load_page(path: Path, content_dir: Path) -> Page:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as err:
        raise ContentError(f"{path}: cannot read file ({err})") from err
    meta, body = _split_front_matter(text, path)
    _check_keys(meta, path)
    return Page(
        slug=_slug(path, content_dir),
        title=_text(meta, "title", path),
        description=_text(meta, "description", path),
        updated=_date(meta, "updated", path),
        approved=_date(meta, "approved", path),
        layout=_text(meta, "layout", path),
        claims=_text_list(meta, "claims", path),
        schema=_text_list(meta, "schema", path),
        audience=_optional_text(meta, "audience", path),
        body=body,
        source=path,
        og_image=_optional_text(meta, "og_image", path),
        css=_css_name(meta, path),
    )


def _split_front_matter(text: str, path: Path) -> tuple[dict, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip() != FENCE:
        raise ContentError(f"{path}: file must start with a '---' front matter line")
    for end, line in enumerate(lines[1:], start=1):
        if line.rstrip() == FENCE:
            break
    else:
        raise ContentError(f"{path}: front matter is not closed by a '---' line")
    try:
        meta = yaml.safe_load("".join(lines[1:end]))
    except (yaml.YAMLError, ValueError) as err:
        # PyYAML builds dates inside safe_load, so an impossible one such as
        # 2026-02-30 raises ValueError here.
        raise ContentError(
            f"{path}: front matter is not valid YAML, or a date in it is impossible ({err})"
        ) from err
    if not isinstance(meta, dict):
        raise ContentError(f"{path}: front matter must be a YAML mapping")
    return meta, "".join(lines[end + 1:])


def _check_keys(meta: dict, path: Path) -> None:
    missing = [key for key in REQUIRED_KEYS if key not in meta]
    if missing:
        raise ContentError(f"{path}: missing required key(s): {', '.join(missing)}")
    unknown = sorted(str(key) for key in meta if key not in REQUIRED_KEYS + OPTIONAL_KEYS)
    if unknown:
        raise ContentError(f"{path}: unknown front matter key(s): {', '.join(unknown)}")


def _text(meta: dict, key: str, path: Path) -> str:
    value = meta[key]
    if not isinstance(value, str) or not value.strip():
        raise ContentError(f"{path}: '{key}' must be a non-empty string")
    return value


def _optional_text(meta: dict, key: str, path: Path) -> str | None:
    if meta.get(key) is None:
        return None
    return _text(meta, key, path)


def _css_name(meta: dict, path: Path) -> str | None:
    name = _optional_text(meta, "css", path)
    if name is not None and not CSS_NAME.fullmatch(name):
        raise ContentError(
            f"{path}: 'css' must be the plain name of a stylesheet in tokens/pages/ "
            f"(lowercase letters, digits and hyphens, no path or extension), got {name!r}"
        )
    return name


def _date(meta: dict, key: str, path: Path) -> datetime.date:
    value = meta[key]
    # datetime is a date subclass, so check the exact type.
    if type(value) is not datetime.date:
        raise ContentError(f"{path}: '{key}' must be a date written YYYY-MM-DD")
    return value


def _text_list(meta: dict, key: str, path: Path) -> tuple[str, ...]:
    value = meta.get(key)
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ContentError(f"{path}: '{key}' must be a list of strings")
    return tuple(value)
