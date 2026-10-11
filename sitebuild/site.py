"""Load site.yaml into a validated SiteConfig.

One site.yaml per host holds the chrome every page shares: base URL, header
tabs, the one action, footer profiles and policies. `founder_profiles` is the
one optional key: the founder's own profiles, which feed structured data and
never the footer (D5). Every error message starts with the file path.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

REQUIRED_KEYS = ("base_url", "name", "header", "tabs", "cta", "profiles", "policies", "pending_pages")
OPTIONAL_KEYS = ("founder_profiles",)
LINK_KEYS = ("label", "href")
HEADERS = ("syahi", "katha")
EM_DASH = chr(0x2014)


class SiteError(Exception):
    """site.yaml is unreadable or invalid. The message names the file."""


@dataclass(frozen=True)
class Link:
    label: str
    href: str


@dataclass(frozen=True)
class SiteConfig:
    base_url: str
    name: str
    tabs: tuple[Link, ...]
    cta: Link
    profiles: tuple[Link, ...]
    policies: tuple[Link, ...]
    pending_pages: frozenset[str]
    header: str
    founder_profiles: tuple[Link, ...] = ()


class _Loader(yaml.SafeLoader):
    """SafeLoader that refuses a key written twice in one mapping, instead of keeping the last."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue
            key = self.construct_object(key_node, deep=True)
            try:
                if key in seen:
                    raise SiteError(f"key {key!r} is defined more than once")
                seen.add(key)
            except TypeError:
                break  # unhashable key: the parent class reports it
        return super().construct_mapping(node, deep)


def load_site(path: Path) -> SiteConfig:
    """Load and validate one site.yaml."""
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as err:
        raise SiteError(f"{path}: cannot read file ({err})") from err
    try:
        data = yaml.load(raw, Loader=_Loader)
    except SiteError as err:
        raise SiteError(f"{path}: {err}") from err
    except (yaml.YAMLError, ValueError) as err:
        raise SiteError(f"{path}: not valid YAML ({err})") from err
    if not isinstance(data, dict):
        raise SiteError(f"{path}: site.yaml must be a YAML mapping")
    missing = [key for key in REQUIRED_KEYS if key not in data]
    if missing:
        raise SiteError(f"{path}: missing required key(s): {', '.join(missing)}")
    unknown = sorted(str(key) for key in data if key not in REQUIRED_KEYS + OPTIONAL_KEYS)
    if unknown:
        raise SiteError(f"{path}: unknown key(s): {', '.join(unknown)}")
    tabs = _links(data["tabs"], "tabs", path)
    if not tabs:
        raise SiteError(f"{path}: 'tabs' must be a non-empty list")
    return SiteConfig(
        base_url=_base_url(data["base_url"], path),
        name=_text(data["name"], "name", path),
        tabs=tabs,
        cta=_link(data["cta"], "cta", path),
        profiles=_links(data["profiles"], "profiles", path),
        policies=_links(data["policies"], "policies", path),
        pending_pages=_pending(data["pending_pages"], path),
        header=_header(data["header"], path),
        founder_profiles=_links(data["founder_profiles"], "founder_profiles", path) if "founder_profiles" in data else (),
    )


def _text(value: object, key: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SiteError(f"{path}: '{key}' must be a non-empty string")
    if EM_DASH in value:
        raise SiteError(f"{path}: '{key}' contains an em dash")
    return value


def _base_url(value: object, path: Path) -> str:
    text = _text(value, "base_url", path)
    if not text.startswith("https://") or len(text) == len("https://"):
        raise SiteError(f"{path}: 'base_url' must be an https:// URL, got {text!r}")
    if text.endswith("/"):
        raise SiteError(f"{path}: 'base_url' must have no trailing slash, got {text!r}")
    return text


def _header(value: object, path: Path) -> str:
    if value not in HEADERS:
        raise SiteError(f"{path}: 'header' must be one of {', '.join(HEADERS)}, got {value!r}")
    return value


def _link(value: object, where: str, path: Path) -> Link:
    if not isinstance(value, dict):
        raise SiteError(f"{path}: '{where}' must be a mapping with keys {', '.join(LINK_KEYS)}")
    missing = [key for key in LINK_KEYS if key not in value]
    if missing:
        raise SiteError(f"{path}: '{where}' is missing required key(s): {', '.join(missing)}")
    unknown = sorted(str(key) for key in value if key not in LINK_KEYS)
    if unknown:
        raise SiteError(f"{path}: '{where}' has unknown key(s): {', '.join(unknown)}")
    label = _text(value["label"], f"{where} label", path)
    href = _text(value["href"], f"{where} href", path)
    if not (href.startswith("/") and not href.startswith("//")) and not href.startswith("https://"):
        raise SiteError(f"{path}: '{where}' href must be a path starting with / or an https:// URL, got {href!r}")
    return Link(label=label, href=href)


def _links(value: object, key: str, path: Path) -> tuple[Link, ...]:
    if not isinstance(value, list):
        raise SiteError(f"{path}: '{key}' must be a list of links")
    return tuple(_link(item, f"{key}[{number}]", path) for number, item in enumerate(value, start=1))


def _pending(value: object, path: Path) -> frozenset[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.startswith("/") for item in value):
        raise SiteError(f"{path}: 'pending_pages' must be a list of paths starting with /")
    if len(set(value)) != len(value):
        raise SiteError(f"{path}: 'pending_pages' lists a path more than once")
    return frozenset(value)
