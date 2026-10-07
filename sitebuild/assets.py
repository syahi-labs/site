"""Content-hashed assets, self-hosted font subsets, image variants and the `picture()` helper.

Every asset URL the pages and stylesheets link carries the first ten hex characters of the SHA-256 of its
bytes (`mark.3f9a1c2b7d.svg`), so a file can be cached forever and a changed file gets a new URL.

Fonts are SIL OFL TrueType sources under assets/fonts/src. The build subsets each family against the text of
one host's pages, so a host only ships the glyphs it shows, and emits a family only when that host has text for
it. A missing source or a failed subset is a named problem, never a silent fallback to a system font.

Files an outside consumer asks for by a fixed URL keep a stable, unhashed copy next to the hashed one (see
`STABLE_ONLY` and `ALSO_STABLE`). Nothing here reads the clock, the machine or dict order, so a build is
byte-identical run to run.
"""
from __future__ import annotations

import hashlib
import html
import io
import os
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath

URL_BASE = "/assets"
HASH_LENGTH = 10
FONT_SOURCES = Path("fonts") / "src"      # under assets/
FONT_OUTPUT_DIR = "fonts"                 # under the published assets/
# Under assets/, the vendored font sources: input to the font pipeline, never published as assets themselves.
BUILD_OWNED = ("fonts",)

# Stable names, kept exactly as they are because something outside the page asks for them by URL:
# the share images (a link preview caches the URL), the Organization logo in the JSON-LD, the 192 px mark.
STABLE_ONLY = ("brand/og-default.png", "brand/og-signet.png", "brand/mark-512.png", "brand/icon-192.png")
# The files the page head links get a hashed copy for the pages and keep their stable name for browsers,
# crawlers and iOS, which ask for /favicon.ico and /apple-touch-icon.png without reading a page.
ALSO_STABLE = ("brand/favicon.ico", "brand/favicon.svg", "brand/apple-touch-icon.png")
# Copied to the host root too, where a browser looks first.
ROOT_COPIES = {"favicon.ico": "brand/favicon.ico", "apple-touch-icon.png": "brand/apple-touch-icon.png"}

# Layout features stay (Devanagari conjuncts need them). These are kept besides the page's own characters:
# digits, space, ASCII punctuation, a no-break space and the typographic punctuation a later edit may use.
# Letters are not here: the page text names exactly the letters it shows.
_BASELINE = (
    set(range(0x20, 0x41)) | set(range(0x5B, 0x61)) | set(range(0x7B, 0x7F))
    | {0xA0, 0xB7, 0xD7}
    | set(range(0x2010, 0x2016)) | {0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2026, 0x2192, 0x20B9}
)


class AssetError(Exception):
    """An asset cannot be built. The message names the file and the reason."""


# ---- hashing and publishing ---------------------------------------------------------------


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:HASH_LENGTH]


def hashed_name_for(name: str, data: bytes) -> str:
    """`name` with the content hash before its extension: `mark.svg` is `mark.3f9a1c2b7d.svg`."""
    path = PurePosixPath(name)
    return f"{path.stem}.{_digest(data)}{path.suffix}"


def hashed_name(path: Path) -> str:
    """The file's name with the first 10 hex characters of the SHA-256 of its bytes before the extension."""
    return hashed_name_for(Path(path).name, Path(path).read_bytes())


def publish_bytes(name: str, data: bytes, out_dir: Path, url_base: str = URL_BASE) -> str:
    """Write `data` as the hashed form of `name` in `out_dir` and return its URL under `url_base`."""
    hashed = hashed_name_for(name, data)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / hashed).write_bytes(data)
    return f"{url_base}/{hashed}"


def publish(src: Path, out_dir: Path, url_base: str = URL_BASE) -> str:
    """Copy `src` to its hashed name in `out_dir` and return `/assets/<hashed>` (or under `url_base`)."""
    return publish_bytes(Path(src).name, Path(src).read_bytes(), Path(out_dir), url_base)


# ---- the page text a font has to cover ------------------------------------------------------


_VOID = frozenset("area base br col embed hr img input link meta source track wbr".split())
_SKIPPED = frozenset({"script", "style", "template", "head", "title"})   # noscript text is shown, so it counts


class _Text(HTMLParser):
    """The text of <body>, split into Hindi runs (inside an element with lang="hi") and the rest."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.latin: list[str] = []
        self.hindi: list[str] = []
        self._stack: list[tuple[str, bool]] = []
        self._skipped = 0

    def _is_hi(self) -> bool:
        return bool(self._stack) and self._stack[-1][1]

    def handle_starttag(self, tag, attrs):
        if tag in _VOID:
            return
        lang = (dict(attrs).get("lang") or "").strip().lower()
        hindi = self._is_hi() if not lang else lang.split("-")[0] == "hi"
        self._stack.append((tag, hindi))
        if tag in _SKIPPED:
            self._skipped += 1

    def handle_startendtag(self, tag, attrs):
        return

    def handle_endtag(self, tag):
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                for closed, _ in self._stack[index:]:
                    if closed in _SKIPPED and self._skipped:
                        self._skipped -= 1
                del self._stack[index:]
                return

    def handle_data(self, data):
        if self._skipped:
            return
        (self.hindi if self._is_hi() else self.latin).append(data)


def page_text(page_html: str) -> tuple[str, str]:
    """(text outside Hindi runs, text inside lang="hi" runs) of one rendered page's <body>."""
    scan = _Text()
    scan.feed(page_html)
    scan.close()
    return "".join(scan.latin), "".join(scan.hindi)


# ---- fonts ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Face:
    """One @font-face: a source file, the family name CSS asks for, and the token role that asks for it."""
    key: str          # the published name, fonts/<key>.woff2
    family: str
    role: str         # serif, sans, mono or deva: the --font-<role> token
    source: str       # file under assets/fonts/src
    style: str = "normal"
    weight: int | None = None   # a static font's weight; a variable font declares its axis range instead


FACES = (
    Face("fraunces", "Fraunces", "serif", "Fraunces[SOFT,WONK,opsz,wght].ttf"),
    Face("fraunces-italic", "Fraunces", "serif", "Fraunces-Italic[SOFT,WONK,opsz,wght].ttf", style="italic"),
    Face("inter", "Inter", "sans", "Inter[opsz,wght].ttf"),
    Face("ibm-plex-mono-regular", "IBM Plex Mono", "mono", "IBMPlexMono-Regular.ttf", weight=400),
    Face("ibm-plex-mono-medium", "IBM Plex Mono", "mono", "IBMPlexMono-Medium.ttf", weight=500),
    Face("tiro-devanagari-hindi", "Tiro Devanagari Hindi", "deva", "TiroDevanagariHindi-Regular.ttf", weight=400),
)
KEPT_AXES = ("wght", "opsz")
BODY_FACE = "inter"       # the body font (--font-sans on body)
HEADLINE_FACE = "fraunces"   # every page's h1; with the body font, the two faces every page preloads (base.html)
BODY_PRELOAD_KEY = f"{FONT_OUTPUT_DIR}/{BODY_FACE}.woff2"

_ROLE_USE = re.compile(r"font-family\s*:\s*var\(\s*--font-(serif|sans|mono|deva)\s*\)")
_ITALIC_USE = re.compile(r"font-style\s*:\s*italic")


def faces_needed(css_texts: list[str], text: str, hindi: str) -> list[Face]:
    """The faces a host needs: those whose role its stylesheets ask for and for which it has text.

    Latin roles need the page to have any text outside Hindi runs, Devanagari needs a Hindi run, and the
    italic Fraunces needs a stylesheet that asks for italic. A family nothing asks for is not emitted.
    """
    roles = {match.group(1) for css in css_texts for match in _ROLE_USE.finditer(css)}
    italic = any(_ITALIC_USE.search(css) for css in css_texts)
    needed = []
    for face in FACES:
        if face.role not in roles:
            continue
        has_text = bool(hindi.strip()) if face.role == "deva" else bool(text.strip())
        if not has_text or (face.style == "italic" and not italic):
            continue
        needed.append(face)
    return needed


_JOINERS = "‌‍"      # ZWNJ and ZWJ shape Devanagari conjuncts but are not "printable"


def _unicodes(text: str) -> set[int]:
    """The code points to keep: those of `text` in both cases, then the baseline.

    A stylesheet may set `text-transform` (uppercase, capitalize), so the page's "Subject" can be drawn as
    "SUBJECT". Both cases of every cased character are kept, for any script that has them, instead of
    guessing which rules apply where.
    """
    kept = {char for char in text if char.isprintable() or char in " " + _JOINERS}
    for char in list(kept):
        kept.update(char.upper() + char.lower())
    return {ord(char) for char in kept if char.isprintable() or char in " " + _JOINERS} | _BASELINE


_CONTENT = re.compile(r"""\bcontent\s*:\s*(?P<value>(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|[^;}"'])*)""", re.S)
_CSS_STRING = re.compile(r""""((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)'""", re.S)
_CSS_ESCAPE = re.compile(r"\\(?:([0-9a-fA-F]{1,6})[ \t\r\n\f]?|(\r\n|[\n\r\f])|(.))", re.S)


def css_content_text(css: str) -> str:
    """The characters of every `content:` string in a stylesheet, CSS escapes decoded.

    `content:"\2713 ok"` is a check mark and "ok": one optional space ends an escape, and a backslash before a
    line break continues the string. Generated text is drawn in a Latin family, so a glyph a stylesheet names
    must be in the subset or it falls back to a system font.
    """
    def decode(match: re.Match) -> str:
        if match.group(1):
            code = int(match.group(1), 16)
            return chr(code) if 0 < code <= 0x10FFFF and not 0xD800 <= code <= 0xDFFF else "�"
        return "" if match.group(2) else match.group(3)

    found = []
    for rule in _CONTENT.finditer(css):
        for string in _CSS_STRING.finditer(rule["value"]):
            body = string.group(1) if string.group(1) is not None else string.group(2)
            found.append(_CSS_ESCAPE.sub(decode, body))
    return "".join(found)


def _subset_bytes(source_digest: str, source_path: str, codepoints: tuple[int, ...],
                  weights: tuple[int, int] | None = None, all_features: bool = True) -> bytes:
    from fontTools import subset
    from fontTools.ttLib import TTFont

    options = subset.Options()
    options.flavor = "woff2"
    if all_features:
        options.layout_features = ["*"]       # else fontTools' own list: the features a browser applies unasked
    options.name_IDs = ["*"]
    options.hinting = False
    options.notdef_outline = True
    options.drop_tables = [*options.drop_tables, "meta"]
    options.recalc_timestamp = False
    font = TTFont(source_path, recalcTimestamp=False)      # a rebuilt head.modified would make the bytes depend on the clock
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=codepoints)
    subsetter.subset(font)
    if "fvar" in font:
        # Axes no stylesheet asks for (Fraunces SOFT and WONK) are pinned at their defaults; wght and opsz stay.
        from fontTools.varLib import instancer
        limits: dict = {axis.axisTag: axis.defaultValue for axis in font["fvar"].axes if axis.axisTag not in KEPT_AXES}
        if weights is not None:
            # The weights the stylesheets use, not the whole axis: the masters beyond them are dead weight.
            axis = next((a for a in font["fvar"].axes if a.axisTag == "wght"), None)
            if axis is not None:
                low, high = max(weights[0], axis.minValue), min(weights[1], axis.maxValue)
                if (low, high) != (axis.minValue, axis.maxValue) and low <= high:
                    if not hasattr(instancer, "AxisTriple"):
                        from fontTools import version as fonttools_version
                        raise RuntimeError(f"fontTools {fonttools_version} cannot move an axis default; "
                                           "the build needs fonttools>=4.50 (requirements.txt), run it from the .venv")
                    limits["wght"] = instancer.AxisTriple(low, min(max(400, low), high), high)
        if limits:
            font = instancer.instantiateVariableFont(font, limits, inplace=False)
    buffer = io.BytesIO()
    font.recalcTimestamp = False
    font.flavor = "woff2"
    font.save(buffer)
    return buffer.getvalue()


# Everything `_subset_bytes` does besides the source and the characters. Change it with that function, so an
# entry made by an older recipe is never read back as the new one's.
_RECIPE = "woff2 names=* hinting=off notdef=outline drop+=meta pin-axes-except=" + ",".join(KEPT_AXES) + " limit-wght v2"


def _cache_dir() -> Path:
    """Where subsets are remembered between builds: SITEBUILD_CACHE, else a folder in the user's own cache."""
    if os.environ.get("SITEBUILD_CACHE"):
        return Path(os.environ["SITEBUILD_CACHE"])
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "syahi-sitebuild"


def _covers(data: bytes, source_path: str, codepoints: tuple[int, ...]) -> bool:
    """Whether `data` parses as a font whose cmap holds every requested code point the source font has."""
    from fontTools.ttLib import TTFont

    try:
        wanted = set(codepoints) & set(TTFont(source_path, lazy=True).getBestCmap())
        return wanted <= set(TTFont(io.BytesIO(data), lazy=True).getBestCmap())
    except Exception:
        return False


def _cached_subset(source_digest: str, source_path: str, codepoints: tuple[int, ...],
                   weights: tuple[int, int] | None = None, all_features: bool = True) -> bytes:
    """`_subset_bytes`, remembered on disk. A subset is a pure function of the source bytes, the characters and
    the fontTools version, so a hit is the same bytes a fresh subset would give; a cache that cannot be read or
    written is skipped, never a problem. Subsetting a big variable font costs a second or more.
    """
    from fontTools import version as fonttools_version

    key = hashlib.sha256(f"{fonttools_version}|{_RECIPE}|{source_digest}|{codepoints}|{weights}|{all_features}".encode()).hexdigest()
    entry = _cache_dir() / f"{key}.woff2"
    try:
        cached = entry.read_bytes()
        if _covers(cached, source_path, codepoints):     # a damaged or foreign file is rebuilt, never trusted
            return cached
    except OSError:
        pass
    data = _subset_bytes(source_digest, source_path, codepoints, weights, all_features)
    try:
        entry.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        scratch = entry.with_name(f"{entry.name}.{os.getpid()}.tmp")
        scratch.write_bytes(data)
        os.replace(scratch, entry)
    except OSError:
        pass
    return data


def _subset(src: Path, text: str, weights: tuple[int, int] | None = None, all_features: bool = True) -> bytes:
    """The woff2 bytes of `src` subset to `text`. Raises AssetError naming the file."""
    try:
        data = src.read_bytes()
    except OSError as err:
        raise AssetError(f"{src}: font source cannot be read ({err.strerror or err})") from err
    try:
        return _cached_subset(hashlib.sha256(data).hexdigest(), str(src), tuple(sorted(_unicodes(text))),
                              weights, all_features)
    except Exception as err:   # fontTools raises many types; every one is a build problem naming the file
        raise AssetError(f"{src}: font cannot be subset ({type(err).__name__}: {err})") from err


def subset_font(src: Path, text: str, out: Path) -> Path:
    """A woff2 of `src` holding only the glyphs `text` needs, plus digits and punctuation. Layout features stay.

    Raises AssetError naming the file when the source is missing or cannot be subset.
    """
    out = Path(out)
    data = _subset(Path(src), text)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return out


_FONT_WEIGHT = re.compile(r"font-weight\s*:\s*([^;}]+)", re.I)
_FONT_SHORTHAND = re.compile(r"(?<![-\w])font\s*:\s*(?!inherit\b)", re.I)     # `font: inherit` hands down what is already set
_FONT_FEATURES = re.compile(r"font-feature-settings|font-variant|font-kerning|font-language-override|(?<![-\w])font\s*:\s*(?!inherit\b)", re.I)
_WEIGHT_WORDS = {"normal": 400, "bold": 700}


def used_weights(css_texts: list[str]) -> tuple[int, int] | None:
    """The (lowest, highest) weight the stylesheets can ask for, or None when it cannot be known.

    400 and 700 are always inside: `normal`, and what the browser gives <b>, <strong>, <th> and headings that
    set no weight. A relative keyword (`lighter`, `bolder`), a `font:` shorthand or an inherited value could
    land anywhere, so any of them gives None and the face keeps its whole axis.
    """
    found = {400, 700}
    for css in css_texts:
        if _FONT_SHORTHAND.search(css):
            return None
        for match in _FONT_WEIGHT.finditer(css):
            value = match.group(1).strip().lower().removesuffix("!important").strip()
            if value in _WEIGHT_WORDS:
                found.add(_WEIGHT_WORDS[value])
            elif value.isdigit():
                found.add(int(value))
            else:
                return None
    return min(found), max(found)


def needs_all_features(css_texts: list[str]) -> bool:
    """Whether a stylesheet asks for font features by hand (small caps, tabular figures, ligatures off...).

    Without such a rule a browser applies only the features it turns on unasked, so the rest are not shipped.
    """
    return any(_FONT_FEATURES.search(css) for css in css_texts)


def _weight_range(face: Face, source: Path, limit: tuple[int, int] | None = None) -> str:
    from fontTools.ttLib import TTFont

    if face.weight is not None:
        return str(face.weight)
    try:
        with TTFont(str(source), lazy=True) as font:
            for axis in font["fvar"].axes:
                if axis.axisTag == "wght":
                    low, high = round(axis.minValue), round(axis.maxValue)
                    if limit is not None and limit[0] <= limit[1]:
                        low, high = max(low, limit[0]), min(high, limit[1])
                    return f"{low} {high}"
    except Exception as err:
        raise AssetError(f"{source}: font axes cannot be read ({type(err).__name__}: {err})") from err
    raise AssetError(f"{source}: no wght axis, and the face declares no static weight")


def publish_fonts(assets_src: Path, assets_out: Path, css_texts: list[str], text: str, hindi: str
                  ) -> tuple[dict[str, str], str, dict[str, int], list[str]]:
    """Subset and publish the faces a host needs.

    Returns (manifest entries `fonts/<key>.woff2` to URL, the @font-face CSS, bytes per face, problems).
    Each face is subset against the host's own text; a face whose source is missing or fails is a problem
    and is left out of the CSS.
    """
    manifest: dict[str, str] = {}
    sizes: dict[str, int] = {}
    problems: list[str] = []
    rules: list[str] = []
    text += "".join(css_content_text(css) for css in css_texts)       # generated text is drawn in a Latin face
    for face in faces_needed(css_texts, text, hindi):
        source = assets_src / FONT_SOURCES / face.source
        if source.is_symlink():
            problems.append(f"{source}: a symbolic link is never used as a font source")
            continue
        try:
            limit = None if face.weight is not None else used_weights(css_texts)
            weight = _weight_range(face, source, limit)
            data = _subset(source, hindi if face.role == "deva" else text, limit,
                           all_features=face.role == "deva" or needs_all_features(css_texts))
        except AssetError as err:
            problems.append(str(err))
            continue
        url = publish_bytes(f"{face.key}.woff2", data, assets_out / FONT_OUTPUT_DIR, f"{URL_BASE}/{FONT_OUTPUT_DIR}")
        manifest[f"{FONT_OUTPUT_DIR}/{face.key}.woff2"] = url
        sizes[face.key] = len(data)
        rules.append(
            f"@font-face{{font-family:'{face.family}';font-style:{face.style};font-weight:{weight};"
            f"font-display:swap;src:url({url}) format('woff2')}}"
        )
    css = ("/* @font-face rules written by the build from this host's subset fonts */\n" + "\n".join(rules) + "\n") if rules else ""
    return manifest, css, sizes, problems


# ---- URL rewriting ----------------------------------------------------------------------------


_HTML_URL = re.compile(r'(?P<attr>\b(?:href|src)=")(?P<url>/assets/[^"#?]+)(?P<end>[#?][^"]*)?(?=")')
_CSS_URL = re.compile(r"""url\(\s*(?P<q>['"]?)(?P<url>/assets/[^'")\s#?]+)(?P<end>[#?][^'")\s]*)?(?P=q)\s*\)""")


def _key(url: str) -> str:
    return url[len(URL_BASE) + 1:]


_FONT_PRELOAD = re.compile(r'<link rel="preload"[^>]*\bhref="(?P<url>/assets/fonts/[^"]+)"[^>]*>\n?')


def rewrite_html(page_html: str, manifest: dict[str, str]) -> str:
    """Point every `href` and `src` that names a source asset at its hashed URL. Other values stay as written.

    A font preload for a face the host does not ship (nothing asks for it, or it failed and is a problem of its
    own) is dropped, so a page never preloads a file that is not there.
    """
    def drop_dangling(match: re.Match) -> str:
        return match[0] if _key(match["url"]) in manifest else ""

    def swap(match: re.Match) -> str:
        url = html.unescape(match["url"])
        return f"{match['attr']}{manifest.get(_key(url), match['url'])}{match['end'] or ''}"
    return _HTML_URL.sub(swap, _FONT_PRELOAD.sub(drop_dangling, page_html))


def rewrite_css(css: str, manifest: dict[str, str], where: str) -> tuple[str, list[str]]:
    """Point every `url(/assets/...)` at the hashed URL. One that names no published asset is a problem."""
    problems: list[str] = []

    def swap(match: re.Match) -> str:
        key = _key(match["url"])
        if key not in manifest:
            problems.append(f"{where}: url({match['url']}) names no asset the build publishes")
            return match[0]
        return f"url({match['q']}{manifest[key]}{match['end'] or ''}{match['q']})"
    return _CSS_URL.sub(swap, css), problems


# ---- images ---------------------------------------------------------------------------------


def image_variants(src: Path, out_dir: Path, widths=(240, 480, 960, 1600), url_base: str = URL_BASE) -> list[dict]:
    """AVIF and WebP at each of `widths` narrower than the source, and at the source's own width.

    Never upscales. Each dict has `url`, `width`, `height` and `format`, widest first within a format.
    """
    from PIL import Image, ImageOps

    src, out_dir = Path(src), Path(out_dir)
    try:
        with Image.open(src) as opened:
            image = ImageOps.exif_transpose(opened)
            image.load()
    except (OSError, ValueError, Image.DecompressionBombError) as err:
        raise AssetError(f"{src}: image cannot be read ({type(err).__name__}: {err})") from err
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB")
    full_width, full_height = image.size
    sizes = sorted({w for w in widths if w < full_width} | {full_width})
    variants = []
    for fmt, options in (("avif", {"quality": 55, "speed": 6}), ("webp", {"quality": 80, "method": 6})):
        for width in reversed(sizes):
            height = max(1, round(full_height * width / full_width))
            scaled = image if width == full_width else image.resize((width, height), Image.LANCZOS)
            buffer = io.BytesIO()
            try:
                scaled.save(buffer, format=fmt.upper(), **options)
            except (OSError, ValueError, KeyError) as err:
                raise AssetError(f"{src}: cannot encode {fmt} at {width}px ({type(err).__name__}: {err})") from err
            url = publish_bytes(f"{src.stem}-{width}w.{fmt}", buffer.getvalue(), out_dir, url_base)
            variants.append({"url": url, "width": width, "height": height, "format": fmt})
    return variants


def picture_html(variants: list[dict], alt: str, sizes: str, loading: str, fetchpriority: str | None,
                 css_class: str | None = None) -> str:
    """<picture> with an AVIF source, a WebP source and an <img> on the widest WebP, sized from the file.

    `css_class` goes on the <img>, which is the element a stylesheet sizes."""
    esc = lambda value: html.escape(str(value), quote=True)
    sources = []
    for fmt in ("avif", "webp"):
        group = [v for v in variants if v["format"] == fmt]
        srcset = ", ".join(f"{v['url']} {v['width']}w" for v in sorted(group, key=lambda v: v["width"]))
        sources.append(f'<source type="image/{fmt}" srcset="{esc(srcset)}" sizes="{esc(sizes)}">')
    widest = max((v for v in variants if v["format"] == "webp"), key=lambda v: v["width"])
    extra = f' fetchpriority="{esc(fetchpriority)}"' if fetchpriority else ""
    klass = f' class="{esc(css_class)}"' if css_class else ""
    img = (f'<img{klass} src="{esc(widest["url"])}" width="{widest["width"]}" height="{widest["height"]}" alt="{esc(alt)}" '
           f'loading="{esc(loading)}" decoding="async"{extra}>')
    return "<picture>" + "".join(sources) + img + "</picture>"
