"""One deterministic build of both hosts.

`build` loads and validates every input, renders each page of syahi.sh and
katha.syahi.sh into `out/<host>/`, writes each host's sitemap and robots.txt
(and syahi.sh's llms.txt), publishes every stylesheet, image, brand file and subset font under a
content-hashed name (sitebuild.assets), links them from the pages, and runs the checks.

The checks (the `checks` package) run inside the build, so a page that fails one fails the build:
  - per rendered page: copycheck (the copy in <main>, told the page's audience) and htmlcheck;
  - per host directory: sitecheck, offline, told the host the site's base URL names, because an
    output directory holds no CNAME.

It raises nothing for a content problem. Each one lands in
`BuildResult.problems`, and the caller (build.py) decides the exit code. What is worth saying but
does not fail the build lands in `BuildResult.warnings`: a link to a pending page in a dev build, and
sitecheck's own WARN findings. A problem on one page never stops the others from being built, so a
single run reports everything it can.

A page is its source plus every partial it includes. Its sitemap `lastmod` is the latest author date of a
commit over all of them (the author date survives a rebase, an amend and a squash; the committer date does not).
A non-draft page whose source or partial was written after its `approved` date was changed after she approved
it, and one with uncommitted changes has a date that does not describe it: a release build refuses both, a dev
build warns.

Deterministic: the same tree gives byte-identical files. Nothing written
depends on the clock, the machine, or dict and set order. Files are UTF-8
with LF endings. Dates come from git history or the page's own front matter.
"""
from __future__ import annotations

import ast
import datetime
import os
import re
import shutil
from contextlib import contextmanager
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from checks import copycheck, htmlcheck, sitecheck
from sitebuild import assets
from sitebuild.claims import ClaimError, ClaimRegister
from sitebuild.content import ContentError, Page, load_pages
from sitebuild.generated import NOT_FOUND_SLUG, llms_txt, robots_txt, sitemap_xml
from sitebuild.gitdates import GitDateError, has_uncommitted_changes, last_commit_date
from sitebuild.includes import included_templates
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
    warnings: list[str] = field(default_factory=list)         # worth reading, never fails the build
    font_bytes: dict[str, dict[str, int]] = field(default_factory=dict)   # host name to woff2 bytes per face


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
    env.assets_out = host_out / "assets"
    rendered_pages = []
    rendered_html = []
    for page in item.pages:
        html = _render(env, site, claims, page, release, problems)
        if html is not None:
            rendered_pages.append(page)
            rendered_html.append(html)
    # What a crawler or a reader is told about: no pending page and no /404.
    listed = [p for p in rendered_pages if p.slug != NOT_FOUND_SLUG and p.slug not in site.pending_pages]
    # A page is its source plus every partial it includes; one git question per file, asked once.
    files = {p.slug: _page_files(env, p, problems) for p in rendered_pages}
    git = _GitFacts()
    _write(host_out / "robots.txt", robots_txt(site.base_url))
    try:
        _write(host_out / "sitemap.xml", sitemap_xml([(p.slug, _lastmod(p, files[p.slug], git)) for p in listed], site.base_url))
    except (GitDateError, ValueError) as err:
        problems.append(f"{host.name}: sitemap.xml: {err}")
    _approval_findings(rendered_pages, files, git, release, result)
    if host.llms:
        try:
            _write(host_out / "llms.txt", llms_txt(site, listed, claims))
        except ClaimError as err:
            problems.append(f"{host.name}: llms.txt: {err}")
    # Fonts are subset against the text just rendered, stylesheets carry the font URLs, and a page links the
    # stylesheets: so the pages are written last, with their asset links pointing at the hashed files.
    problems.extend(_missing_page_css(root, rendered_pages))
    font_bytes = result.font_bytes.setdefault(host.name, {})
    manifest, asset_problems = _publish_assets(root, host_out, rendered_html, [p.css for p in rendered_pages if p.css], font_bytes)
    problems.extend(asset_problems)
    for page, html in zip(rendered_pages, rendered_html):
        _write(host_out / _file_for(page.slug), assets.rewrite_html(html, manifest))
    if release:
        problems.extend(_release_site_problems(item))
        problems.extend(_release_draft_problems(item))
    _site_checks(host_out, item, release, result)
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
    """The checks that need a rendered page: structured data, claims, copy, HTML and, in release, pending links."""
    problems = [f"{page.source}: structured data not shown on the page: {mismatch}" for mismatch in jsonld_mismatches(html)]
    problems += [f"{page.source}: copycheck: {finding}" for finding in copycheck.check(html, page.audience)]
    problems += [f"{page.source}: htmlcheck: {finding}" for finding in htmlcheck.check(html, claims.renderings())]
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


def _site_checks(host_out: Path, item: _Loaded, release: bool, result: BuildResult) -> None:
    """Run sitecheck over one host's output. FAIL findings are problems and WARN findings are warnings.

    A dead link to a pending page is expected while the page is pending, so a dev build only warns
    about it. A release build refuses pending pages, so there it is a problem like any other dead link.
    The directory has no CNAME, so the host comes from the site's base URL. Offline: no network in a build.
    """
    host = urlsplit(item.site.base_url).hostname
    for finding in sitecheck.run([host_out], offline=True, host=host):
        where = f"{item.host.name}/{finding.path}" + (f":{finding.line}" if finding.line else "")
        text = f"{where}: sitecheck [{finding.check}]: {finding.message}"
        if finding.level == "FAIL" and not release and _is_pending_link(finding, item.site, host):
            result.warnings.append(f"{text} (pending page)")
        elif finding.level == "FAIL":
            result.problems.append(text)
        elif finding.level == "WARN":
            result.warnings.append(text)


# sitecheck words a dead link "<attr> <repr of the value> does not resolve to a file".
_DEAD_LINK = re.compile(r"(?:href|src) (?P<value>.+) does not resolve to a file")


def _is_pending_link(finding, site: SiteConfig, host: str | None) -> bool:
    """Whether a sitecheck finding is a dead link whose target is one of the site's pending pages."""
    match = _DEAD_LINK.fullmatch(finding.message) if finding.check == "internal-link" else None
    if match is None:
        return False
    try:
        value = ast.literal_eval(match["value"])
        kind, target = sitecheck.classify(finding.path, value, host)
    except (ValueError, SyntaxError):
        return False
    return kind == "internal" and _internal_path(target, site.base_url) in site.pending_pages


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


def _release_draft_problems(item: _Loaded) -> list[str]:
    """A release build refuses a draft page, one problem per page. A draft is copy no one has approved,
    and the made-by line already says so; shipping it would publish what she has not read."""
    return [f"{page.source}: release build: page is a draft (not yet approved); approve it and remove `draft: true`"
            for page in item.pages if page.draft]


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


class _GitFacts:
    """What git says about a file, each asked once per host, so a partial shared by many pages costs one question."""

    def __init__(self) -> None:
        self._dates: dict[Path, datetime.date | None] = {}
        self._uncommitted: dict[Path, bool] = {}

    def date(self, path: Path) -> datetime.date | None:
        if path not in self._dates:
            self._dates[path] = last_commit_date(path)
        return self._dates[path]

    def uncommitted(self, path: Path) -> bool:
        if path not in self._uncommitted:
            self._uncommitted[path] = has_uncommitted_changes(path)
        return self._uncommitted[path]


def _page_files(env, page: Page, problems: list[str]) -> list[Path]:
    """The page's source, then every template its body includes. What cannot be traced is a problem."""
    included, untraceable = included_templates(env, page.body)
    problems.extend(f"{page.source}: {problem}" for problem in untraceable)
    return [page.source, *included]


def _lastmod(page: Page, files: list[Path], git: _GitFacts) -> datetime.date:
    """The latest day any of the page's files was written, by author date; if git tracks none, the page's `updated`."""
    changed = [date for date in map(git.date, files) if date is not None]
    return max(changed) if changed else page.updated


def _approval_findings(pages: list[Page], files: dict[str, list[Path]], git: _GitFacts, release: bool, result: BuildResult) -> None:
    """What makes a page's approval untrue, per file, for every non-draft page.

    A file written after the page's `approved` date was changed after she approved it. A file with
    uncommitted changes (modified, staged or never added) has a date that describes the commit, not the file,
    so it would pass the first rule by never being committed. A release build refuses both, a dev build warns.
    A draft claims no approval, and a release build refuses it anyway. Naming the file says what to look at.
    """
    for page in pages:
        if page.draft or page.approved is None:
            continue
        messages = []
        try:
            for path in files[page.slug]:
                if git.uncommitted(path):
                    messages.append(f"{page.source}: {path}: uncommitted changes; commit before release")
                date = git.date(path)
                if date is not None and date > page.approved:
                    messages.append(f"{page.source}: {path} last changed {date.isoformat()}, after the page was approved on "
                                    f"{page.approved.isoformat()}: re-approve the page")
        except GitDateError as err:
            messages = [f"{page.source}: {err}"]
        (result.problems if release else result.warnings).extend(messages)


def _file_for(slug: str) -> Path:
    """Where a page lives under its host: `/` is index.html, `/a/b` is a/b.html (served at /a/b)."""
    return Path("index.html") if slug == "/" else Path(slug.lstrip("/") + ".html")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))  # bytes, so no platform newline translation


STYLESHEETS = ("tokens.css", "base.css")
PAGE_CSS_DIR = Path("tokens") / "pages"
ASSETS_DIR = "assets"
# Names under assets/ that the build writes itself: the shared stylesheets, the page stylesheets and the
# subset fonts. A source file there would shadow a real output, so it is refused rather than published.
RESERVED_ASSETS = (*STYLESHEETS, "pages", *assets.BUILD_OWNED)


def _publish_assets(root: Path, host_out: Path, pages_html: list[str], css_names: list[str],
                    sizes: dict[str, int] | None = None) -> tuple[dict[str, str], list[str]]:
    """Publish every asset of one host under host_out/assets/ with a content-hashed name.

    Returns (the manifest from a source path under assets/ to its hashed URL, problems). The order matters:
    the images and the brand files come first, then the fonts (subset against this host's own text), then
    the stylesheets, because a stylesheet's `url()` and the font rules it carries name hashed files and its
    own hash covers them. A page links the manifest's URLs once `assets.rewrite_html` has run.

    Files an outside consumer asks for by a fixed URL keep a stable copy (assets.STABLE_ONLY and
    assets.ALSO_STABLE), and /favicon.ico and /apple-touch-icon.png are copied to the host root.
    A dotfile is never an asset (.DS_Store, .gitkeep). A symbolic link is refused and not followed, so
    nothing outside the repo can reach the public output. A file in a name the build writes itself (see
    RESERVED_ASSETS) is refused too. Returns problems, never raises.
    """
    problems: list[str] = []
    assets_src, assets_out = root / ASSETS_DIR, host_out / "assets"
    manifest = _publish_asset_tree(assets_src, assets_out, problems)
    for url_name, key in assets.ROOT_COPIES.items():
        if (assets_src / key).is_file() and not (assets_src / key).is_symlink():
            shutil.copyfile(assets_src / key, host_out / url_name)

    sheets = _stylesheet_sources(root, css_names, problems)
    text = "".join(assets.page_text(html)[0] for html in pages_html)
    hindi = "".join(assets.page_text(html)[1] for html in pages_html)
    font_manifest, font_css, font_sizes, font_problems = assets.publish_fonts(
        assets_src, assets_out, [css for _, css in sheets], text, hindi)
    problems.extend(font_problems)
    manifest.update(font_manifest)
    if sizes is not None:
        sizes.update(font_sizes)

    for key, css in sheets:
        css, css_problems = assets.rewrite_css(css, manifest, f"{ASSETS_DIR}/{key}")
        problems.extend(css_problems)
        if key == "tokens.css":
            css = font_css + css     # the rules already name hashed files
        folder = assets_out / PurePosixPath(key).parent
        base = "/".join([assets.URL_BASE, *PurePosixPath(key).parent.parts])
        manifest[key] = assets.publish_bytes(PurePosixPath(key).name, css.encode("utf-8"), folder, base)
    return manifest, problems


def _stylesheet_sources(root: Path, css_names: list[str], problems: list[str]) -> list[tuple[str, str]]:
    """(key under assets/, text) of the shared stylesheets, then each page stylesheet a page names, sorted."""
    sheets = []
    for name in STYLESHEETS:
        source = root / "tokens" / name
        if not source.is_file():
            problems.append(f"{source}: stylesheet not found")
        else:
            sheets.append((name, source.read_bytes().decode("utf-8")))
    for name in sorted(set(css_names)):
        source = root / PAGE_CSS_DIR / f"{name}.css"
        if source.is_file():
            sheets.append((f"pages/{name}.css", source.read_bytes().decode("utf-8")))
    return sheets


def _publish_asset_tree(source: Path, target: Path, problems: list[str]) -> dict[str, str]:
    """Publish every file under `source` under `target`, in the same folder, as its hashed name.

    Returns the manifest (path under `source` to URL). No folder is not a problem.
    """
    manifest: dict[str, str] = {}
    if source.is_symlink():
        problems.append(f"{source}: the assets folder is a symbolic link; refusing to publish through it")
        return manifest
    if not source.is_dir():
        return manifest
    # os.walk does not follow links, so a linked folder shows up in `dirs` and is never entered.
    for folder, dirs, files in os.walk(source):
        here = Path(folder)
        dirs[:] = sorted(name for name in dirs if not name.startswith("."))
        for name in sorted(files + [name for name in dirs if (here / name).is_symlink()]):
            path = here / name
            relative = path.relative_to(source)
            key = relative.as_posix()
            if name.startswith("."):
                continue
            if name in FORBIDDEN_OUTPUTS:
                problems.append(f"{path}: {name} must never be part of the build output")
            elif path.is_symlink():
                problems.append(f"{path}: a symbolic link in assets/ is never published (it could reach files outside the repo)")
            elif relative.parts[0] in assets.BUILD_OWNED and (relative.parts[:2] == ("fonts", "src") or relative.as_posix() == "fonts/LICENSES.md"):
                continue    # the vendored font sources and their licence record: input, not an asset
            elif relative.parts[0] in RESERVED_ASSETS:
                problems.append(f"{path}: assets/{relative.parts[0]} is reserved for what the build writes itself (stylesheets and subset fonts) and is not published")
            else:
                folder_out = target / relative.parent
                data = path.read_bytes()
                if key in assets.STABLE_ONLY or key in assets.ALSO_STABLE:
                    folder_out.mkdir(parents=True, exist_ok=True)
                    (folder_out / name).write_bytes(data)
                if key not in assets.STABLE_ONLY:
                    base = "/".join([assets.URL_BASE, *relative.parent.parts])
                    manifest[key] = assets.publish_bytes(name, data, folder_out, base)
    return manifest


def _missing_page_css(root: Path, pages: list[Page]) -> list[str]:
    """A page naming a stylesheet that has no file is a problem naming the pages that use it."""
    problems = []
    for name in sorted({page.css for page in pages if page.css}):
        if not (root / PAGE_CSS_DIR / f"{name}.css").is_file():
            users = ", ".join(str(page.source) for page in pages if page.css == name)
            problems.append(f"{users}: css '{name}' has no stylesheet at {PAGE_CSS_DIR.as_posix()}/{name}.css")
    return problems
