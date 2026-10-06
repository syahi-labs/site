"""One deterministic build of both hosts.

`build` loads and validates every input, renders each page of syahi.sh and
katha.syahi.sh into `out/<host>/`, writes each host's sitemap and robots.txt
(and syahi.sh's llms.txt), publishes the stylesheets, and runs the checks.

It raises nothing for a content problem. Each one lands in
`BuildResult.problems`, and the caller (build.py) decides the exit code. A
problem on one page never stops the others from being built, so a single run
reports everything it can.

Deterministic: the same tree gives byte-identical files. Nothing written
depends on the clock, the machine, or dict and set order. Files are UTF-8
with LF endings. Dates come from git history or the page's own front matter.
"""
from __future__ import annotations

import datetime
import re
import shutil
from contextlib import contextmanager
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from sitebuild.claims import ClaimError, ClaimRegister
from sitebuild.content import ContentError, Page, load_pages
from sitebuild.generated import NOT_FOUND_SLUG, llms_txt, robots_txt, sitemap_xml
from sitebuild.gitdates import GitDateError, last_commit_date
from sitebuild.render import RenderError, make_env, render_page
from sitebuild.schema import SchemaError, build_jsonld, jsonld_mismatches
from sitebuild.site import SiteConfig, SiteError, load_site

CLAIMS_PATH = Path("data") / "claims.yaml"
# Everything the build reads. An output directory may not be one of these or sit inside one,
# or the next build would read its own output as input.
SOURCES = ("content", "templates", "tokens", "assets", "data", "katha", "site.yaml")
# What a build writes at the top of out/, so the next build can prove a directory is its own output
# before it deletes anything. Only a directory with this marker, holding nothing but the marker and
# the host directories, is ever wiped.
MARKER = ".sitebuild-output"
MARKER_TEXT = "syahi-labs/site build output\n"
# Files the build output must never hold: katha-feed owns both, and a copy here would shadow them.
FORBIDDEN_OUTPUTS = ("feed.xml", "CNAME")


@dataclass(frozen=True)
class Host:
    name: str      # the directory under out/
    header: str    # the SiteConfig.header its site.yaml must declare
    base: Path     # the directory under the root holding its site.yaml and content/
    llms: bool     # whether it writes llms.txt


HOSTS = (
    Host("syahi.sh", "syahi", Path("."), llms=True),
    Host("katha.syahi.sh", "katha", Path("katha"), llms=False),
)


@dataclass
class BuildResult:
    outputs: dict[str, Path] = field(default_factory=dict)    # host name to the directory written
    pages: list[Page] = field(default_factory=list)           # every page of every host, main host first
    problems: list[str] = field(default_factory=list)         # empty means the build is good


@dataclass(frozen=True)
class _Loaded:
    host: Host
    site_path: Path
    site: SiteConfig
    pages: list[Page]


def build(root: Path, out: Path, release: bool = False) -> BuildResult:
    """Build both hosts from `root` into `out`, wiping `out` first. Problems are returned, not raised.

    `out` is wiped only if it is missing, empty, or a previous build's output (see `_wipe_refusal`).
    Anything else is refused as a problem, and nothing is deleted or written.
    """
    root, out = Path(root), Path(out)
    result = BuildResult()
    refusal = _unsafe_out(root, out) or _wipe_refusal(out)
    if refusal:
        result.problems.append(refusal)
        return result
    _reset(out)

    claims, loaded = _load(root, result.problems)
    if result.problems:
        return result
    for item in loaded:
        _build_host(root, out, item, claims, release, result)
    for name in FORBIDDEN_OUTPUTS:
        for path in sorted(out.rglob(name)):
            result.problems.append(f"{path}: {name} must never be part of the build output")
    return result


def _wipe_refusal(out: Path) -> str | None:
    """Why `out` may not be wiped, or None. The proof is positive, never a list of what to avoid.

    Allowed: a path that does not exist, an empty directory, or a previous build's output: a real
    directory holding the marker with its exact text and nothing else but the host directories (real
    directories too). A symbolic link is never followed or deleted, and a file is never replaced.
    """
    if out.is_symlink():
        return f"{out}: the output path is a symbolic link; refusing to build through it or delete it"
    if not out.exists():
        return None
    if not out.is_dir():
        return f"{out}: the output path is a file, not a directory; refusing to replace it"
    found = sorted(out.iterdir())
    if not found:
        return None
    if not _is_marker(out / MARKER):
        return (f"{out}: the output directory is not empty and is not a previous build's output "
                f"(it has no {MARKER} marker); nothing was deleted")
    hosts = {host.name for host in HOSTS}
    strays = [e.name for e in found if e.name != MARKER and not (e.name in hosts and e.is_dir() and not e.is_symlink())]
    if strays:
        return f"{out}: holds {', '.join(strays)}, which a build does not write; nothing was deleted"
    return None


def _is_marker(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        return path.read_text(encoding="utf-8") == MARKER_TEXT
    except (OSError, UnicodeDecodeError):
        return False


def _reset(out: Path) -> None:
    """Empty `out` (already proven safe by `_wipe_refusal`), create it if missing, and write the marker."""
    out.mkdir(parents=True, exist_ok=True)
    for entry in out.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    _write(out / MARKER, MARKER_TEXT)


def _unsafe_out(root: Path, out: Path) -> str | None:
    """Why `out` may not be used, or None. It must not be the root, hold the root, or touch a source."""
    root_real, out_real = root.resolve(), out.resolve()
    if out_real == root_real or out_real in root_real.parents:
        return f"{out}: the output directory must not be the site root or contain it"
    for name in SOURCES:
        source = root_real / name
        if out_real == source or source in out_real.parents:
            return f"{out}: the output directory must not be, or sit inside, {source}"
    return None


def _load(root: Path, problems: list[str]) -> tuple[ClaimRegister | None, list[_Loaded]]:
    """Content first, then each site.yaml, then the claims. Every failure is a problem; none stops the rest."""
    loaded = []
    for host in HOSTS:
        base = root / host.base
        site_path = base / "site.yaml"
        pages = site = None
        try:
            pages = load_pages(base / "content")
        except ContentError as err:
            problems.append(str(err))
        try:
            site = load_site(site_path)
            if site.header != host.header:
                raise SiteError(f"{site_path}: 'header' must be '{host.header}' for {host.name}, got '{site.header}'")
        except SiteError as err:
            problems.append(str(err))
            site = None
        if pages is not None and site is not None:
            loaded.append(_Loaded(host, site_path, site, pages))
    try:
        claims = ClaimRegister.load(root / CLAIMS_PATH)
    except ClaimError as err:
        problems.append(str(err))
        claims = None
    return claims, loaded


def _build_host(root: Path, out: Path, item: _Loaded, claims: ClaimRegister, release: bool, result: BuildResult) -> None:
    host, site, problems = item.host, item.site, result.problems
    host_out = out / host.name
    env = make_env(root, site, claims)
    rendered_pages = []
    for page in item.pages:
        html = _render(env, site, claims, page, release, problems)
        if html is not None:
            _write(host_out / _file_for(page.slug), html)
            rendered_pages.append(page)
    # What a crawler or a reader is told about: no pending page and no /404.
    listed = [p for p in rendered_pages if p.slug != NOT_FOUND_SLUG and p.slug not in site.pending_pages]
    _write(host_out / "robots.txt", robots_txt(site.base_url))
    try:
        _write(host_out / "sitemap.xml", sitemap_xml([(p.slug, _lastmod(p)) for p in listed], site.base_url))
    except (GitDateError, ValueError) as err:
        problems.append(f"{host.name}: sitemap.xml: {err}")
    if host.llms:
        try:
            _write(host_out / "llms.txt", llms_txt(site, listed, claims))
        except ClaimError as err:
            problems.append(f"{host.name}: llms.txt: {err}")
    problems.extend(_publish_assets(root, host_out))
    if release:
        problems.extend(_release_site_problems(item))
    result.outputs[host.name] = host_out
    result.pages.extend(item.pages)


def _render(env, site: SiteConfig, claims: ClaimRegister, page: Page, release: bool, problems: list[str]) -> str | None:
    """The page's HTML, or None with the reason in `problems`. Runs the per-page checks on what it rendered."""
    try:
        # A 404 is served with a failing status and is no entity of the site: it gets no structured data.
        jsonld = [] if page.slug == NOT_FOUND_SLUG else build_jsonld(page, site, claims)
        with _rendered_ids(claims) as rendered:
            html = render_page(env, page, jsonld)
    except (RenderError, ClaimError, SchemaError) as err:
        problems.append(str(err))
        return None
    problems.extend(_page_problems(page, html, rendered, claims, site, release))
    return html


@contextmanager
def _rendered_ids(claims: ClaimRegister):
    """Yield a set that holds, once the block ends, the claim ids rendered inside it.

    `claims.used` is the running total for the build, and a set: an id already in it would not show up
    in a before-and-after difference. So the block starts from an empty `used` and puts the total back.
    """
    before = set(claims.used)
    claims.used.clear()
    rendered: set[str] = set()
    try:
        yield rendered
    finally:
        rendered.update(claims.used)
        claims.used.update(before)


def _page_problems(page: Page, html: str, rendered: set[str], claims: ClaimRegister, site: SiteConfig, release: bool) -> list[str]:
    """The checks that need a rendered page. Task 8 adds the rest here."""
    problems = [f"{page.source}: structured data not shown on the page: {mismatch}" for mismatch in jsonld_mismatches(html)]
    for id in page.claims:
        if id in rendered:
            continue
        try:
            claims.get(id)
        except ClaimError as err:
            problems.append(f"{page.source}: front matter claim '{id}' cannot be used ({err})")
        else:
            problems.append(f"{page.source}: claim '{id}' is listed in front matter but never rendered on the page")
    if release:
        for target in _pending_links(html, site):
            problems.append(f"{page.source}: release build: links to pending page {target}")
    return problems


def _release_site_problems(item: _Loaded) -> list[str]:
    """A release build refuses pending pages, and names each tab, action or policy link that points at one."""
    site, where = item.site, item.site_path
    if not site.pending_pages:
        return []
    problems = [f"{where}: release build with pending pages: {', '.join(sorted(site.pending_pages))}"]
    links = [("tab", link) for link in site.tabs] + [("action", site.cta)] + [("policy", link) for link in site.policies]
    for kind, link in links:
        target = _internal_path(link.href, site.base_url)
        if target in site.pending_pages:
            problems.append(f"{where}: release build: {kind} '{link.label}' links to pending page {target}")
    return problems


class _MainLinks(HTMLParser):
    """The href of every link inside <main>: the page's own links, not the header and footer chrome."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []
        self._in_main = 0

    def handle_starttag(self, tag, attrs):
        if tag == "main":
            self._in_main += 1
        elif tag == "a" and self._in_main:
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)

    def handle_endtag(self, tag):
        if tag == "main" and self._in_main:
            self._in_main -= 1


def _pending_links(html: str, site: SiteConfig) -> list[str]:
    """The pending pages the page body links to, each once, sorted."""
    scan = _MainLinks()
    scan.feed(html)
    scan.close()
    targets = {_internal_path(href, site.base_url) for href in scan.hrefs}
    return sorted(target for target in targets if target in site.pending_pages)


def _internal_path(href: str, base_url: str) -> str | None:
    """The clean path an internal href points at, or None for an external one.

    Clean means no query, fragment, `.html` or trailing slash, as the site's URLs are written.
    """
    if href == base_url or href.startswith(base_url + "/"):
        href = href[len(base_url):] or "/"
    if not href.startswith("/") or href.startswith("//"):
        return None
    path = re.split(r"[?#]", href, maxsplit=1)[0]
    if path.endswith(".html"):
        path = path[: -len(".html")]
    return path.rstrip("/") or "/"


def _lastmod(page: Page) -> datetime.date:
    """The day the file last changed in git; a file git does not track falls back to its own `updated`."""
    return last_commit_date(page.source) or page.updated


def _file_for(slug: str) -> Path:
    """Where a page lives under its host: `/` is index.html, `/a/b` is a/b.html (served at /a/b)."""
    return Path("index.html") if slug == "/" else Path(slug.lstrip("/") + ".html")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))  # bytes, so no platform newline translation


STYLESHEETS = ("tokens.css", "base.css")


def _publish_assets(root: Path, host_out: Path) -> list[str]:
    """Copy the stylesheets to host_out/assets/ under their own names, so the base template's links resolve.

    Task 7 replaces this one function with the hashed asset pipeline. Returns problems, never raises.
    """
    problems = []
    for name in STYLESHEETS:
        source = root / "tokens" / name
        if not source.is_file():
            problems.append(f"{source}: stylesheet not found")
            continue
        target = host_out / "assets" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return problems
