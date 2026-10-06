"""Render a Page to a full HTML document.

One Jinja environment serves two jobs: the page body is itself a template
(it calls `claim()` and `date`), and it is then placed inside the layout the
page names. StrictUndefined and autoescape are on, so a typo fails the build
and a claim's text can never inject markup.
"""
from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass
from pathlib import Path

import jinja2
from markupsafe import Markup

from sitebuild.claims import ClaimError, ClaimRegister
from sitebuild.content import Page
from sitebuild.site import SiteConfig

DEFAULT_OG_IMAGE = "/assets/brand/og-default.png"
LAYOUT_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
# Fixed English abbreviations: no locale, no platform strftime flags.
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class RenderError(Exception):
    """A page cannot be rendered: bad layout, template error, bad og_image. The message names the file."""


@dataclass(frozen=True)
class NavTab:
    label: str
    href: str
    current: str | None  # "page" on the page itself, "true" on a section's parent tab, else None


def format_date(d: datetime.date) -> str:
    """6 Oct 2026: day without a leading zero, three-letter month, four-digit year."""
    if not isinstance(d, datetime.date):
        raise TypeError(f"format_date needs a date, got {type(d).__name__}")
    return f"{d.day} {MONTHS[d.month - 1]} {d.year:04d}"


def make_env(root: Path, site: SiteConfig, claims: ClaimRegister) -> jinja2.Environment:
    """The environment for one host: templates from root/templates, `site`, `claim()` and `date`."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(Path(root) / "templates"),
        autoescape=True,
        undefined=jinja2.StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    def claim(id: str, form: str = "full") -> Markup:
        """The claim's text, escaped, in a span that names it so the checks can find it."""
        return Markup('<span data-claim="{}">{}</span>').format(id, claims.text(id, form))

    env.globals["site"] = site
    env.globals["claim"] = claim
    env.filters["date"] = format_date
    return env


def render_page(env: jinja2.Environment, page: Page, jsonld: list[dict]) -> str:
    """The full HTML document for one page. Every failure names page.source."""
    try:
        return _render(env, page, jsonld)
    except ClaimError as err:
        raise ClaimError(f"{page.source}: {err}") from err
    except jinja2.TemplateNotFound as err:
        if err.name == _layout_template(page):
            raise RenderError(f"{page.source}: layout '{page.layout}' has no template at templates/{err.name}") from err
        raise RenderError(f"{page.source}: template '{err.name}' not found") from err
    except jinja2.TemplateSyntaxError as err:
        where = err.name or "the page body"
        raise RenderError(f"{page.source}: template syntax error in {where}, line {err.lineno}: {err.message}") from err
    except jinja2.TemplateError as err:
        raise RenderError(f"{page.source}: {err}") from err


def _layout_template(page: Page) -> str:
    return f"layouts/{page.layout}.html"


def _render(env: jinja2.Environment, page: Page, jsonld: list[dict]) -> str:
    if not LAYOUT_NAME.fullmatch(page.layout):
        raise RenderError(f"{page.source}: layout {page.layout!r} is not a valid layout name")
    site = env.globals["site"]
    layout = env.get_template(_layout_template(page))
    body = Markup(env.from_string(page.body).render(page=page))
    return layout.render(
        page=page,
        body=body,
        canonical=_canonical(site, page),
        og_image=_og_image(site, page),
        tabs=[NavTab(tab.label, tab.href, _current(page.slug, tab.href)) for tab in site.tabs],
        jsonld=[_jsonld_block(node, number, page) for number, node in enumerate(jsonld, start=1)],
    )


def _canonical(site: SiteConfig, page: Page) -> str:
    """Clean URL: no .html, no trailing slash, except the root."""
    return site.base_url + page.slug


def _og_image(site: SiteConfig, page: Page) -> str:
    image = page.og_image or DEFAULT_OG_IMAGE
    if image.startswith("https://"):
        return image
    if image.startswith("/") and not image.startswith("//"):
        return site.base_url + image
    raise RenderError(f"{page.source}: og_image must be a path starting with / or an https:// URL, got {image!r}")


def _current(slug: str, href: str) -> str | None:
    if not href.startswith("/"):
        return None
    if slug == href:
        return "page"
    if href != "/" and slug.startswith(href + "/"):
        return "true"
    return None


def _jsonld_block(node: dict, number: int, page: Page) -> Markup:
    """One node as JSON that cannot close or confuse the script element it sits in."""
    try:
        text = json.dumps(node, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as err:
        raise RenderError(f"{page.source}: JSON-LD node {number} cannot be serialised ({err})") from err
    return Markup(text.replace("</", "<\\/").replace("<!--", "\\u003c!--"))
