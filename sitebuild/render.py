"""Render a Page to a full HTML document.

One Jinja environment serves two jobs: the page body is itself a template
(it calls `claim()` and `date`), and it is then placed inside the layout the
page names. StrictUndefined and autoescape are on, so a typo fails the build
and a claim's text can never inject markup. The environment is a sandbox,
because a page body is written by an agent from a draft, and it is the one
place where text becomes code.
"""
from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePath

import jinja2
import jinja2.sandbox
from markupsafe import Markup

from sitebuild import assets
from sitebuild.claims import ClaimError, ClaimRegister
from sitebuild.content import Page
from sitebuild.schema import page_url
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


class SiteEnvironment(jinja2.sandbox.SandboxedEnvironment):
    """The environment make_env returns: a sandbox that also carries the SiteConfig.

    render_page reads `env.site`, so it can only run on an environment built for one host.
    """

    def __init__(self, site: SiteConfig, **options):
        super().__init__(**options)
        self.site = site
        # The site root the templates and assets live under: where a page's own share image is read from.
        self.root: Path | None = None
        # The default share image's pixel size, read from the file when the environment is made.
        # None when the file is absent; `default_og_error` says why when it is there but unreadable.
        self.default_og_size: tuple[int, int] | None = None
        self.default_og_error: str | None = None
        # Where picture() writes the image variants it makes (the host's assets/ folder). None outside a build.
        self.assets_out: Path | None = None

    def is_safe_attribute(self, obj, attr, value):
        # The sandbox blocks dunders and unsafe callables, but a Path is ordinary: `page.source`
        # would let a body call read_text() or iterdir() and print any file the build can see.
        # A body may still print the path itself, which needs no attribute access.
        if isinstance(obj, PurePath):
            return False
        return super().is_safe_attribute(obj, attr, value)


def make_env(root: Path, site: SiteConfig, claims: ClaimRegister) -> SiteEnvironment:
    """The environment for one host: templates from root/templates, `site`, `claim()` and `date`."""
    env = SiteEnvironment(
        site,
        loader=jinja2.FileSystemLoader(Path(root) / "templates"),
        autoescape=True,
        undefined=jinja2.StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    def claim(id: str, form: str = "full") -> Markup:
        """The claim's text, escaped, in a span that names it so the checks can find it."""
        return Markup('<span data-claim="{}">{}</span>').format(id, claims.text(id, form))

    def claim_text(id: str, form: str = "full") -> str:
        """The claim's text as a plain string, for an attribute (aria-label, alt, title, placeholder).

        A span cannot sit inside an attribute, so `claim()` is no help there. The text comes out as a plain
        string, which autoescape escapes like any value, and the claim is recorded as used. The element then
        names the claims its attributes took their digits from, `data-claims="id,id"`, and the HTML check
        proves the digits are those claims' current text.
        """
        return claims.text(id, form)

    def picture(src: str, alt: str, sizes: str = "100vw", loading: str = "lazy", fetchpriority: str | None = None) -> Markup:
        """<picture> of an image under assets/: AVIF and WebP variants, an <img> sized from the file.

        The page's first image passes loading="eager" and fetchpriority="high"; every other one stays lazy.
        """
        if env.assets_out is None:
            raise assets.AssetError("picture() needs a build: there is no output folder to write the variants to")
        relative = PurePath(src)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise assets.AssetError(f"picture(): {src!r} must be a path under assets/")
        source = Path(root) / "assets" / relative
        if source.is_symlink() or not source.is_file():
            raise assets.AssetError(f"picture(): assets/{relative.as_posix()} is not a file")
        base = "/".join(["/assets", *relative.parent.parts])
        variants = assets.image_variants(source, env.assets_out / relative.parent, url_base=base)
        return Markup(assets.picture_html(variants, alt, sizes, loading, fetchpriority))

    env.root = Path(root)
    env.default_og_size, env.default_og_error = _image_size(Path(root) / DEFAULT_OG_IMAGE.lstrip("/"))
    env.globals["site"] = site
    env.globals["claim"] = claim
    env.globals["claim_text"] = claim_text
    env.globals["picture"] = picture
    env.filters["date"] = format_date
    return env


def _image_size(path: Path) -> tuple[tuple[int, int] | None, str | None]:
    """(width, height) of an image file, or (None, None) when there is no such file, or (None, reason)."""
    from PIL import Image   # the one place the page renderer needs it; Task 7's pipeline uses it everywhere
    try:
        with Image.open(path) as image:
            return image.size, None
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError, Image.DecompressionBombError) as err:   # UnidentifiedImageError is an OSError
        return None, f"{type(err).__name__}: {err}"


def render_page(env: SiteEnvironment, page: Page, jsonld: list[dict]) -> str:
    """The full HTML document for one page. Every failure of the page names page.source.

    `env` must come from make_env. A plain Jinja environment has no site to render with, and
    that is a bug in the caller, not in the page, so it raises TypeError and names no page.
    """
    if not isinstance(env, SiteEnvironment):
        raise TypeError(f"render_page needs the environment make_env() returns, got {type(env).__name__}")
    try:
        return _render(env, page, jsonld)
    except RenderError:
        raise  # already names the page
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
    except Exception as err:
        # A body is code: `{{ 5|date }}` raises TypeError, `{{ 1 / 0 }}` ZeroDivisionError, and
        # none of them is a TemplateError. This is the boundary that attaches the file, so any
        # failure leaves as a RenderError naming it, with the original kept as __cause__.
        raise RenderError(f"{page.source}: {type(err).__name__}: {err}") from err


def _layout_template(page: Page) -> str:
    return f"layouts/{page.layout}.html"


def _render(env: SiteEnvironment, page: Page, jsonld: list[dict]) -> str:
    if not LAYOUT_NAME.fullmatch(page.layout):
        raise RenderError(f"{page.source}: layout {page.layout!r} is not a valid layout name")
    site = env.site
    layout = env.get_template(_layout_template(page))
    body = Markup(env.from_string(page.body).render(page=page))
    og_image = _og_image(site, page)
    return layout.render(
        page=page,
        body=body,
        canonical=_canonical(site, page),
        og_image=og_image,
        og_image_size=_og_image_size(env, page),
        tabs=[NavTab(tab.label, tab.href, _current(page.slug, tab.href)) for tab in site.tabs],
        jsonld=[_jsonld_block(node, number, page) for number, node in enumerate(jsonld, start=1)],
    )


def _canonical(site: SiteConfig, page: Page) -> str:
    """Clean URL: no .html, no trailing slash, except the root."""
    return page_url(site.base_url, page.slug)


def _og_image(site: SiteConfig, page: Page) -> str:
    image = page.og_image or DEFAULT_OG_IMAGE
    if image.startswith("https://"):
        return image
    if image.startswith("/") and not image.startswith("//"):
        return site.base_url + image
    raise RenderError(f"{page.source}: og_image must be a path starting with / or an https:// URL, got {image!r}")


def _og_image_size(env: SiteEnvironment, page: Page) -> tuple[int, int] | None:
    """The pixel size the page's share image declares, read from the file, or None when there is no file to read.

    The default image's size was read when the environment was made. A page's own image is a path under the site
    root, read the same way; a missing, unreadable or out-of-root file is a RenderError naming the page, because
    a share image that is not there is a broken link preview. An image on another host (`https://...`) has no file
    here, so it declares no size.
    """
    if page.og_image is None:
        if env.default_og_error:
            raise RenderError(f"{page.source}: the default og:image {DEFAULT_OG_IMAGE} has no readable size ({env.default_og_error})")
        return env.default_og_size
    if not page.og_image.startswith("/") or env.root is None:
        return None
    relative = PurePath(page.og_image.lstrip("/"))
    if ".." in relative.parts:
        raise RenderError(f"{page.source}: og_image {page.og_image!r} must not climb out of the site root with '..'")
    size, error = _image_size(env.root / relative)
    if size is None:
        raise RenderError(f"{page.source}: og_image {page.og_image} " + (f"has no readable size ({error})" if error else "is not a file under the site root"))
    return size


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
