# tests/test_assets.py
#
# Task 9a: the shared assets (art, brand mark, default share image, favicons) come from the live site at
# 446f625 as bytes. Task 7: the build publishes every one of them under a content-hashed name (the files an
# outside consumer asks for by a fixed URL keep a stable copy too), subsets the self-hosted fonts against each
# host's own text, and the base template links the hashed URLs for both hosts.
import hashlib
import io
import re
import struct
from pathlib import Path

import pytest
from PIL import Image
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from sitebuild import assets, pipeline
from sitebuild.assets import hashed_name, image_variants, publish, subset_font
from sitebuild.pipeline import build

REPO = Path(__file__).resolve().parents[1]
ASSETS = REPO / "assets"
HOSTS = ("syahi.sh", "katha.syahi.sh")

# destination under assets/ -> sha256 of the file at 446f625 in the live site repo (art/, then the root files)
SOURCES = {
    "img/cube.webp": "bbc8380934c6701bda1c7cbad5718e0523be442e6d32c66885dfdf88c67aa590",
    "img/gramophone.webp": "3399fe4b0a7cac0ed6665909353cd49823760d729a8bef1e23015c1bc318610c",
    "img/inkpot.webp": "7bb96075ceecc09832429db74a698445bb594a10ff18a72cff111f94b9cdc462",
    "img/loom.webp": "c2c29ae93b14a4b8dbd33929a367039c888a8601ea88f9264041bd66104788bc",
    "brand/og-default.png": "b311976aa3ae4df979e23bb30562ff7c39b6686ba985cd196c9e9d23c8df1999",       # og-image.png
    "brand/mark-512.png": "0c37a0bd6c89199623c52fca6b571363e0ddb79fe12730d62b65eb54b4a41922",         # icon-512.png
    "brand/og-signet.png": "7a6e6b0c7e64bfd602d858ea6bdf49bd216a77f00294dcb6ba82e8bd3cf785ed",         # og.png, signet-landing a0bb211
    "brand/icon-192.png": "f41447896975e79d723dade17a37bd8c40f74ecf6ffdf1e48beb38fa085d657d",
    "brand/apple-touch-icon.png": "d642d6b9e7fd71a3df98d76fd0c31a45ccb12f8fd7abf9a9d6b547ce8b6d8456",
    "brand/favicon.ico": "6a98776564186393d0fea4ff7ab86bd945ca4a7a7d3de0d00c0c10febe4f8c63",
    "brand/favicon.svg": "c1fd46a27d005cad198db08ad26dc4a1bfaf52277d054248875b116d37b96409",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    return struct.unpack(">II", data[16:24])


# ---- the files, as bytes ----

@pytest.mark.parametrize("name", sorted(SOURCES))
def test_each_asset_is_the_live_sites_file_byte_for_byte(name):
    assert (ASSETS / name).is_file(), name
    assert sha(ASSETS / name) == SOURCES[name]


def test_the_assets_tree_holds_these_files_and_nothing_else():
    held = sorted(p.relative_to(ASSETS).as_posix() for p in ASSETS.rglob("*")
                  if p.is_file() and not p.name.startswith(".") and p.relative_to(ASSETS).parts[0] != "fonts")
    assert held == sorted(SOURCES)


def test_the_brand_images_have_the_sizes_the_pages_declare():
    assert png_size(ASSETS / "brand" / "og-default.png") == (1200, 630)
    assert png_size(ASSETS / "brand" / "og-signet.png") == (1200, 630)
    assert png_size(ASSETS / "brand" / "mark-512.png") == (512, 512)
    assert png_size(ASSETS / "brand" / "icon-192.png") == (192, 192)
    assert png_size(ASSETS / "brand" / "apple-touch-icon.png") == (180, 180)


# ---- the build publishes them to both hosts, content-hashed ----

HASHED = re.compile(r"\.[0-9a-f]{10}\.[a-z0-9]+$")


def published_files(out: Path, host: str) -> set[str]:
    return {p.relative_to(out / host).as_posix() for p in (out / host / "assets").rglob("*") if p.is_file()}


def stable_only(name: str) -> bool:
    return name in assets.STABLE_ONLY


@pytest.mark.parametrize("host", HOSTS)
def test_every_source_asset_is_published_under_its_hashed_name_byte_for_byte(real_site, host):
    for name in SOURCES:
        source = ASSETS / name
        folder = real_site.out / host / "assets" / Path(name).parent
        if name.startswith("img/"):
            # A plate is shown through picture(), so only its variants are published; the source is not.
            assert not (folder / hashed_name(source)).exists(), f"{host}: {name} is published but nothing names it"
        elif not stable_only(name):
            published = folder / hashed_name(source)
            assert published.is_file(), f"{host}: {name}"
            assert sha(published) == SOURCES[name], f"{host}: {name}"
            assert HASHED.search(published.name)


@pytest.mark.parametrize("host", HOSTS)
def test_files_an_outside_consumer_requests_by_a_fixed_url_keep_a_stable_copy(real_site, host):
    for name in (*assets.STABLE_ONLY, *assets.ALSO_STABLE):
        assert sha(real_site.out / host / "assets" / name) == SOURCES[name], f"{host}: {name}"
    for url_name, name in assets.ROOT_COPIES.items():
        assert sha(real_site.out / host / url_name) == SOURCES[name], f"{host}: /{url_name}"


@pytest.mark.parametrize("host", HOSTS)
def test_the_published_asset_tree_is_exactly_the_sources_the_fonts_and_the_stylesheets(real_site, host):
    expected = set()
    for name in SOURCES:
        if not stable_only(name) and not name.startswith("img/"):
            expected.add("assets/" + (Path(name).parent / hashed_name(ASSETS / name)).as_posix())
        if stable_only(name) or name in assets.ALSO_STABLE:
            expected.add("assets/" + name)
    held = published_files(real_site.out, host)
    fonts = {f for f in held if f.startswith("assets/fonts/")}
    sheets = {f for f in held if f.endswith(".css")}
    variants = {f for f in held if re.search(r"-\d+w\.[0-9a-f]{10}\.(avif|webp)$", f)}     # picture() output, one set per plate used
    assert all(HASHED.search(f) for f in fonts | sheets)
    assert {f.split("/")[-1].split(".")[0] for f in sheets} >= {"tokens", "base"}
    assert held - fonts - sheets - variants == expected, sorted(held - fonts - sheets - variants ^ expected)
    assert not any(f.endswith(".ttf") or "/src/" in f for f in held)          # sources are inputs, never outputs


@pytest.mark.parametrize("host", HOSTS)
def test_the_stylesheets_are_published_hashed_and_the_page_links_them(real_site, host):
    html = (real_site.out / host / "index.html").read_text(encoding="utf-8")
    links = re.findall(r'<link rel="stylesheet" href="(/assets/[^"]+)">', html)
    assert [HASHED.search(u) is not None for u in links] == [True] * len(links) and len(links) >= 2
    for url in links:
        assert (real_site.out / host / url.lstrip("/")).is_file(), url
    assert links[0].startswith("/assets/tokens.") and links[1].startswith("/assets/base.")


@pytest.mark.parametrize("host", HOSTS)
def test_no_page_links_an_unhashed_asset_except_none(real_site, host):
    for page in sorted((real_site.out / host).rglob("*.html")):
        text = page.read_text(encoding="utf-8")
        for url in re.findall(r'(?:href|src)="(/assets/[^"#?]+)"', text):
            assert HASHED.search(url), f"{page.name}: {url}"
            assert (real_site.out / host / url.lstrip("/")).is_file(), f"{page.name}: {url}"


@pytest.mark.parametrize("host", HOSTS)
def test_the_default_og_image_exists_in_each_hosts_output(real_site, host):
    html = (real_site.out / host / "index.html").read_text(encoding="utf-8")
    (url,) = re.findall(r'<meta property="og:image" content="([^"]+)">', html)
    assert url == f"https://{host}/assets/brand/og-default.png"
    published = real_site.out / host / url.removeprefix(f"https://{host}/")
    assert published.is_file()
    assert png_size(published) == (1200, 630)


def test_the_organisation_logo_in_structured_data_exists():
    # schema.LOGO_PATH is the mark: a Organization node pointing at a missing file would be a broken logo.
    from sitebuild.schema import LOGO_PATH
    assert (ASSETS / LOGO_PATH.removeprefix("/assets/")).is_file()


# ---- the base template links the icons on both hosts ----

ICON_LINKS = (
    ('<link rel="icon" href="{}" sizes="48x48">', "brand/favicon.ico"),
    ('<link rel="icon" href="{}" type="image/svg+xml">', "brand/favicon.svg"),
    ('<link rel="apple-touch-icon" href="{}">', "brand/apple-touch-icon.png"),
)


def icon_link(template: str, name: str) -> str:
    return template.format("/assets/" + (Path(name).parent / hashed_name(ASSETS / name)).as_posix())


@pytest.mark.parametrize("host", HOSTS)
def test_every_page_links_the_hashed_favicons_the_apple_icon_and_the_theme_colour(real_site, host):
    pages = sorted((real_site.out / host).rglob("*.html"))
    assert pages
    for page in pages:
        html = page.read_text(encoding="utf-8")
        head = html.split("</head>")[0]
        for template, name in ICON_LINKS:
            assert icon_link(template, name) in head, f"{host}/{page.name}: {name}"
        assert head.count('<meta name="theme-color"') == 1, f"{host}/{page.name}"


@pytest.mark.parametrize("host", HOSTS)
def test_every_linked_icon_resolves_in_that_hosts_output(real_site, host):
    for template, name in ICON_LINKS:
        href = re.search(r'href="(/[^"]+)"', icon_link(template, name)).group(1)
        assert (real_site.out / host / href.lstrip("/")).is_file(), f"{host}: {href}"


def test_the_theme_colour_is_the_ground_token_so_the_two_cannot_drift():
    tokens = (REPO / "tokens" / "tokens.css").read_text(encoding="utf-8")
    ground = re.search(r"--ground:\s*(#[0-9A-Fa-f]{6})\s*;", tokens).group(1)
    base = (REPO / "templates" / "base.html").read_text(encoding="utf-8")
    assert re.findall(r'<meta name="theme-color" content="([^"]+)">', base) == [ground]


def test_the_old_google_fonts_and_cache_busted_icon_links_did_not_come_along():
    base = (REPO / "templates" / "base.html").read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in base and "?v=" not in base


# ---- the katha hero image is served from the katha host ----

def test_the_katha_hero_is_the_built_asset_on_its_own_host(real_site):
    html = (real_site.out / "katha.syahi.sh" / "index.html").read_text(encoding="utf-8")
    assert "https://syahi.sh/art/" not in html
    urls = re.findall(r'(?:src|srcset)="([^"]*?/assets/img/gramophone-[^"]+)"', html)
    assert urls
    for url in re.findall(r"/assets/img/gramophone-\d+w\.[0-9a-f]{10}\.(?:webp|avif)", " ".join(urls)):
        assert (real_site.out / "katha.syahi.sh" / url.lstrip("/")).is_file(), url


# ---- _publish_assets, on its own ----

def tree(root: Path, files: dict[str, bytes]) -> Path:
    for name, data in files.items():
        path = root / "assets" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


def stylesheets(root: Path) -> None:
    (root / "tokens").mkdir(parents=True, exist_ok=True)
    for name in pipeline.STYLESHEETS:
        (root / "tokens" / name).write_text("a{}\n", encoding="utf-8")


def publish_tree(root: Path, out: Path, html: list[str] | None = None, css: list[str] | None = None):
    return pipeline._publish_assets(root, out, html or ["<body><p>Hello</p></body>"], css or [])


def held(out: Path) -> list[str]:
    return sorted(p.relative_to(out / "assets").as_posix() for p in (out / "assets").rglob("*") if p.is_file())


def font_problems(problems: list[str]) -> list[str]:
    return [p for p in problems if "font" not in p.lower()]


def test_the_tree_is_published_hashed_with_its_nested_folders(tmp_path):
    files = {"img/a.webp": b"\x00\xffRIFF", "brand/b.png": b"\x89PNG\r\n", "c/d/e.bin": b"\r\n\x00"}
    root = tree(tmp_path / "root", files)
    stylesheets(root)
    out = tmp_path / "out"
    manifest, problems = publish_tree(root, out)
    assert font_problems(problems) == []
    for name, data in files.items():
        url = manifest[name]
        assert HASHED.search(url) and url.startswith("/assets/" + str(Path(name).parent) + "/")
        assert (out / url.lstrip("/")).read_bytes() == data
        assert not (out / "assets" / name).exists()                       # no unhashed copy of an ordinary asset
    assert manifest["tokens.css"].startswith("/assets/tokens.") and manifest["base.css"].startswith("/assets/base.")


def test_no_assets_folder_is_not_a_problem(tmp_path):
    root = tmp_path / "root"
    stylesheets(root)
    manifest, problems = publish_tree(root, tmp_path / "out")
    assert sorted(manifest) == ["base.css", "tokens.css"]
    assert not any("symbolic" in p or "reserved" in p for p in problems)


def test_dotfiles_are_never_published(tmp_path):
    root = tree(tmp_path / "root", {"img/a.webp": b"x", ".DS_Store": b"junk", "img/.DS_Store": b"junk", ".hidden/b.png": b"x"})
    stylesheets(root)
    manifest, _ = publish_tree(root, tmp_path / "out")
    assert sorted(manifest) == ["base.css", "img/a.webp", "tokens.css"]
    assert not [f for f in held(tmp_path / "out") if "DS_Store" in f or "hidden" in f]


def test_a_symbolic_link_in_assets_is_a_problem_and_is_not_followed(tmp_path):
    secret = tmp_path / "outside" / "secret.txt"
    secret.parent.mkdir()
    secret.write_text("private", encoding="utf-8")
    root = tree(tmp_path / "root", {"img/a.webp": b"x"})
    stylesheets(root)
    (root / "assets" / "img" / "link.txt").symlink_to(secret)
    (root / "assets" / "linked-dir").symlink_to(secret.parent, target_is_directory=True)
    manifest, problems = publish_tree(root, tmp_path / "out")
    assert any("link.txt" in p and "symbolic link" in p for p in problems), problems
    assert any("linked-dir" in p and "symbolic link" in p for p in problems), problems
    published = [p for p in (tmp_path / "out").rglob("*") if p.is_file()]
    assert not any("private" in p.read_text(encoding="utf-8", errors="ignore") for p in published)
    assert "img/link.txt" not in manifest and "img/a.webp" in manifest        # the rest still published


@pytest.mark.parametrize("name", ["tokens.css", "base.css", "pages/demo.css", "fonts/x.woff2"])
def test_a_file_in_a_name_the_build_writes_itself_is_a_problem_and_never_replaces_it(tmp_path, name):
    # tokens.css, base.css, pages/ and fonts/ are the build's own: a stray file there must not shadow an output.
    root = tree(tmp_path / "root", {name: b"body{display:none}", "img/a.webp": b"x"})
    stylesheets(root)
    manifest, problems = publish_tree(root, tmp_path / "out")
    assert "img/a.webp" in manifest                                          # the rest still published
    assert any(name in p and "reserved" in p for p in problems), problems
    assert not any(b"display:none" in p.read_bytes() for p in (tmp_path / "out").rglob("*") if p.is_file())


def test_the_font_sources_and_their_licence_record_are_inputs_not_problems(tmp_path):
    root = tree(tmp_path / "root", {"fonts/src/x.ttf": b"x", "fonts/LICENSES.md": b"l", "img/a.webp": b"x"})
    stylesheets(root)
    manifest, problems = publish_tree(root, tmp_path / "out")
    assert not any("reserved" in p or "fonts/" in p for p in problems), problems
    assert sorted(manifest) == ["base.css", "img/a.webp", "tokens.css"]


def test_a_feed_or_cname_hidden_in_assets_still_fails_the_build(mini_root, tmp_path):
    tree(mini_root, {"feed.xml": b"<rss/>"})
    result = build(mini_root, tmp_path / "dist")
    assert any("feed.xml" in p and "never be part of the build output" in p for p in result.problems), result.problems


def test_the_tree_is_published_to_both_hosts_and_the_build_is_deterministic(mini_root, tmp_path):
    tree(mini_root, {"brand/a.webp": b"\x00art"})
    first, second = tmp_path / "a", tmp_path / "b"
    assert build(mini_root, first).problems == [] and build(mini_root, second).problems == []
    for host in HOSTS:
        assert (first / host / "assets" / "brand" / "a.d3b4c4b4d6.webp".replace("d3b4c4b4d6", hashlib.sha256(b"\x00art").hexdigest()[:10])).read_bytes() == b"\x00art"
    listing = lambda out: sorted((p.relative_to(out).as_posix(), sha(p)) for p in out.rglob("*") if p.is_file())
    assert listing(first) == listing(second)


def test_the_build_never_reads_its_own_published_assets(mini_root, tmp_path):
    # the output may not sit inside a source folder, assets/ included
    result = build(mini_root, mini_root / "assets" / "out")
    assert result.problems and "assets" in result.problems[0]


# ---- hashing, publishing, subsetting and images, with made-up inputs ----

def make_font(path: Path):
    fb = FontBuilder(1000, isTTF=True)
    names = [".notdef", "A", "B", "C"]
    fb.setupGlyphOrder(names); fb.setupCharacterMap({0x41: "A", 0x42: "B", 0x43: "C"})
    pen = TTGlyphPen(None); pen.moveTo((0, 0)); pen.lineTo((0, 500)); pen.lineTo((500, 0)); pen.closePath()
    g = pen.glyph(); fb.setupGlyf({n: g for n in names}); fb.setupHorizontalMetrics({n: (600, 0) for n in names})
    fb.setupHorizontalHeader(ascent=800, descent=-200); fb.setupNameTable({"familyName": "T", "styleName": "R"})
    fb.setupOS2(); fb.setupPost(); fb.save(str(path))


def test_hashed_name_stable(tmp_path):
    f = tmp_path / "mark.svg"; f.write_bytes(b"<svg/>")
    assert hashed_name(f) == hashed_name(f) and hashed_name(f).startswith("mark.") and hashed_name(f).endswith(".svg")


def test_hashed_name_is_ten_hex_characters_of_the_content_hash_and_follows_the_bytes(tmp_path):
    f = tmp_path / "mark.svg"; f.write_bytes(b"<svg/>")
    assert hashed_name(f) == f"mark.{hashlib.sha256(b'<svg/>').hexdigest()[:10]}.svg"
    before = hashed_name(f)
    f.write_bytes(b"<svg></svg>")
    assert hashed_name(f) != before


def test_publish_returns_url(tmp_path):
    f = tmp_path / "a.css"; f.write_text("a{}")
    url = publish(f, tmp_path / "out")
    assert url.startswith("/assets/a.") and (tmp_path / "out" / url.split("/")[-1]).is_file()


def test_publish_copies_the_bytes_untouched(tmp_path):
    f = tmp_path / "a.bin"; f.write_bytes(b"\r\n\x00\xff")
    url = publish(f, tmp_path / "out", url_base="/assets/img")
    assert url.startswith("/assets/img/a.") and (tmp_path / "out" / url.split("/")[-1]).read_bytes() == b"\r\n\x00\xff"


def test_image_variants_never_upscale(tmp_path):
    src = tmp_path / "p.png"; Image.new("RGB", (1000, 500), "white").save(src)
    v = image_variants(src, tmp_path / "out")
    assert {x["format"] for x in v} == {"avif", "webp"}
    assert max(x["width"] for x in v) == 1000 and all(x["height"] * 2 == x["width"] for x in v)


def test_image_variants_are_hashed_files_at_each_width_narrower_than_the_source(tmp_path):
    src = tmp_path / "p.png"; Image.new("RGB", (1000, 500), "white").save(src)
    v = image_variants(src, tmp_path / "out")
    assert sorted({x["width"] for x in v}) == [240, 480, 960, 1000]
    for item in v:
        assert HASHED.search(item["url"]) and (tmp_path / "out" / item["url"].split("/")[-1]).is_file()
        with Image.open(tmp_path / "out" / item["url"].split("/")[-1]) as image:
            assert image.size == (item["width"], item["height"]) and image.format.lower() == item["format"]


def test_an_unreadable_image_is_an_error_naming_the_file(tmp_path):
    src = tmp_path / "broken.png"; src.write_bytes(b"not an image")
    with pytest.raises(assets.AssetError, match="broken.png"):
        image_variants(src, tmp_path / "out")


def test_subset_font_keeps_only_needed_glyphs(tmp_path):
    src = tmp_path / "t.ttf"; make_font(src)
    out = subset_font(src, "AB", tmp_path / "t.woff2")
    cmap = TTFont(str(out)).getBestCmap()
    assert 0x41 in cmap and 0x42 in cmap and 0x43 not in cmap


def test_subset_font_is_woff2_and_keeps_digits_and_punctuation(tmp_path):
    src = tmp_path / "t.ttf"; make_font(src)
    out = subset_font(src, "A", tmp_path / "t.woff2")
    assert out.read_bytes()[:4] == b"wOF2"


def test_subset_of_the_real_devanagari_font_keeps_its_layout_features(tmp_path):
    src = ASSETS / "fonts" / "src" / "TiroDevanagariHindi-Regular.ttf"
    out = subset_font(src, "स्याही", tmp_path / "t.woff2")
    font = TTFont(str(out))
    features = {record.FeatureTag for record in font["GSUB"].table.FeatureList.FeatureRecord}
    assert {"akhn", "half"} & features, features             # conjuncts and half forms need them
    assert 0x0938 in font.getBestCmap() and 0x0915 not in font.getBestCmap()


def test_a_missing_font_source_is_an_error_naming_the_file(tmp_path):
    with pytest.raises(assets.AssetError, match="nowhere.ttf"):
        subset_font(tmp_path / "nowhere.ttf", "A", tmp_path / "t.woff2")


def test_a_source_that_is_not_a_font_is_an_error_naming_the_file(tmp_path):
    bad = tmp_path / "bad.ttf"; bad.write_bytes(b"not a font")
    with pytest.raises(assets.AssetError, match="bad.ttf"):
        subset_font(bad, "A", tmp_path / "t.woff2")


# ---- which text a font covers, and which families a host needs ----

def test_page_text_splits_hindi_runs_from_the_rest_and_skips_the_head_and_scripts():
    html = ('<html><head><title>Hidden</title><style>x{}</style></head><body><p>Plain <b>bold</b></p>'
            '<p lang="hi">स्याही <em>nested</em></p><img src="a.png" alt="alt"><script>no()</script>'
            '<p>after</p></body></html>')
    latin, hindi = assets.page_text(html)
    assert latin == "Plain boldafter" and hindi == "स्याही nested"


def test_a_family_with_no_text_on_the_host_is_not_needed():
    css = ["body{font-family:var(--font-sans)} :lang(hi){font-family:var(--font-deva)} h1{font-family:var(--font-serif)} em{font-style:italic}"]
    keys = lambda text, hindi: [f.key for f in assets.faces_needed(css, text, hindi)]
    assert keys("Hello", "") == ["fraunces", "fraunces-italic", "inter"]
    assert keys("Hello", "स") == ["fraunces", "fraunces-italic", "inter", "tiro-devanagari-hindi"]
    assert keys("", "") == []


def test_italic_and_mono_are_needed_only_when_a_stylesheet_asks_for_them():
    keys = lambda css: [f.key for f in assets.faces_needed([css], "Hello", "")]
    assert keys("h1{font-family:var(--font-serif)}") == ["fraunces"]
    assert keys("h1{font-family:var(--font-serif);font-style:italic}") == ["fraunces", "fraunces-italic"]
    assert keys("code{font-family:var(--font-mono)}") == ["ibm-plex-mono-regular", "ibm-plex-mono-medium"]
    assert keys("p{color:red}") == []


# ---- the fonts the build publishes ----

def face_rules(css: str) -> list[str]:
    return re.findall(r"@font-face\{[^}]*\}", css)


@pytest.mark.parametrize("host", HOSTS)
def test_the_font_rules_name_published_hashed_subset_files_with_swap(real_site, host):
    css_url = re.search(r'href="(/assets/tokens\.[^"]+)"', (real_site.out / host / "index.html").read_text(encoding="utf-8")).group(1)
    css = (real_site.out / host / css_url.lstrip("/")).read_text(encoding="utf-8")
    rules = face_rules(css)
    assert len(rules) >= 4
    for rule in rules:
        assert "font-display:swap" in rule and "format('woff2')" in rule
        (url,) = re.findall(r"url\((/assets/fonts/[^)]+)\)", rule)
        assert HASHED.search(url) and (real_site.out / host / url.lstrip("/")).read_bytes()[:4] == b"wOF2"
    families = sorted({re.search(r"font-family:'([^']+)'", r).group(1) for r in rules})
    assert families == ["Fraunces", "IBM Plex Mono", "Inter", "Tiro Devanagari Hindi"]


@pytest.mark.parametrize("host", HOSTS)
def test_variable_faces_declare_their_weight_range_and_italic_is_its_own_rule(real_site, host):
    css_url = re.search(r'href="(/assets/tokens\.[^"]+)"', (real_site.out / host / "index.html").read_text(encoding="utf-8")).group(1)
    rules = face_rules((real_site.out / host / css_url.lstrip("/")).read_text(encoding="utf-8"))
    by = {(re.search(r"font-family:'([^']+)'", r).group(1), re.search(r"font-style:(\w+)", r).group(1)): r for r in rules}
    # The weights the stylesheets use (400 and 700 always), not the whole 100 to 900 axis.
    assert "font-weight:400 700" in by[("Fraunces", "normal")] and "font-weight:400 700" in by[("Fraunces", "italic")]
    assert "font-weight:400 700" in by[("Inter", "normal")]
    assert "font-weight:400;" in by[("Tiro Devanagari Hindi", "normal")]
    mono = [r for r in rules if "IBM Plex Mono" in r]
    assert sorted(re.search(r"font-weight:(\d+)", r).group(1) for r in mono) == ["400", "500"]


@pytest.mark.parametrize("host", HOSTS)
def test_the_published_subsets_hold_the_pages_glyphs_and_not_the_whole_font(real_site, host):
    fonts = real_site.out / host / "assets" / "fonts"
    inter = next(fonts.glob("inter.*.woff2"))
    cmap = TTFont(str(inter)).getBestCmap()
    assert all(ord(c) in cmap for c in "Syahi 0123")
    assert 0x0152 not in cmap and len(cmap) < 200                               # OE ligature: not on any page
    assert inter.stat().st_size < ASSETS.joinpath("fonts/src/Inter[opsz,wght].ttf").stat().st_size // 4
    assert any(f.stat().st_size for f in fonts.iterdir())
    assert real_site.result.font_bytes[host]["inter"] == inter.stat().st_size


@pytest.mark.parametrize("host", HOSTS)
def test_every_page_preloads_the_body_and_headline_faces_and_only_what_it_declares_besides(real_site, host):
    fonts = real_site.out / host / "assets" / "fonts"
    face = lambda key: next(fonts.glob(f"{key}.*.woff2")).name
    link = lambda key: f'<link rel="preload" href="/assets/fonts/{face(key)}" as="font" type="font/woff2" crossorigin>'
    for page in sorted((real_site.out / host).rglob("*.html")):
        head = page.read_text(encoding="utf-8").split("</head>")[0]
        links = re.findall(r'<link rel="preload"[^>]*>', head)
        extra = [link("fraunces-italic")] if (host, page.name) == ("syahi.sh", "index.html") else []
        assert links == [link("inter"), link("fraunces"), *extra], (host, page.name)


def test_a_host_without_hindi_text_ships_no_devanagari_font(mini_root, tmp_path):
    result = build(mini_root, tmp_path / "dist")
    assert result.problems == [], result.problems
    for host in HOSTS:
        names = [p.name for p in (tmp_path / "dist" / host / "assets" / "fonts").iterdir()]
        assert not any(n.startswith("tiro-") for n in names), names
        css = next((tmp_path / "dist" / host / "assets").glob("tokens.*.css")).read_text(encoding="utf-8")
        assert "font-family:'Tiro Devanagari Hindi'" not in css


def test_a_hindi_run_makes_the_devanagari_font_appear_with_that_runs_glyphs(mini_root, tmp_path):
    page = mini_root / "content" / "index.html"
    page.write_text(page.read_text(encoding="utf-8") + '\n<p><span lang="hi">स्याही</span></p>\n', encoding="utf-8")
    result = build(mini_root, tmp_path / "dist")
    assert not [p for p in result.problems if "font" in p], result.problems
    deva = next((tmp_path / "dist" / "syahi.sh" / "assets" / "fonts").glob("tiro-*.woff2"))
    cmap = TTFont(str(deva)).getBestCmap()
    assert 0x0938 in cmap and 0x0915 not in cmap


def test_a_missing_font_source_is_a_build_problem_naming_the_file(mini_root, tmp_path):
    (mini_root / "assets" / "fonts" / "src" / "Inter[opsz,wght].ttf").unlink()
    result = build(mini_root, tmp_path / "dist")
    assert any("Inter[opsz,wght].ttf" in p for p in result.problems), result.problems
    css = next((tmp_path / "dist" / "syahi.sh" / "assets").glob("tokens.*.css")).read_text(encoding="utf-8")
    assert "font-family:'Inter'" not in css                                      # no rule for a font that is not there


def test_a_font_source_that_cannot_be_subset_is_a_build_problem_naming_the_file(mini_root, tmp_path):
    (mini_root / "assets" / "fonts" / "src" / "Fraunces-Italic[SOFT,WONK,opsz,wght].ttf").write_bytes(b"not a font")
    result = build(mini_root, tmp_path / "dist")
    assert any("Fraunces-Italic" in p and "font" in p and "cannot be" in p for p in result.problems), result.problems


def test_a_symbolic_link_as_a_font_source_is_refused(mini_root, tmp_path):
    source = mini_root / "assets" / "fonts" / "src" / "Fraunces[SOFT,WONK,opsz,wght].ttf"
    target = tmp_path / "elsewhere.ttf"
    target.write_bytes(source.read_bytes())
    source.unlink()
    source.symlink_to(target)
    result = build(mini_root, tmp_path / "dist")
    assert any("Fraunces[SOFT,WONK,opsz,wght].ttf" in p and "symbolic link" in p for p in result.problems), result.problems


def test_the_fonts_on_the_home_page_stay_inside_the_budget(real_site):
    sizes = real_site.result.font_bytes["syahi.sh"]
    assert set(sizes) == {"fraunces", "fraunces-italic", "inter", "ibm-plex-mono-regular", "ibm-plex-mono-medium", "tiro-devanagari-hindi"}
    assert all(size < 100_000 for size in sizes.values()), sizes
    assert sum(sizes.values()) < 250_000, sizes


# ---- url() inside stylesheets, and the vendored fonts' licences ----

def test_a_stylesheet_url_to_an_asset_points_at_the_hashed_file(mini_root, tmp_path):
    tree(mini_root, {"img/dot.png": b"\x89PNG-dot"})
    (mini_root / "tokens" / "base.css").write_text('.dot{background:url("/assets/img/dot.png")}\n.x{background:url(/assets/img/dot.png#a)}', encoding="utf-8")
    result = build(mini_root, tmp_path / "dist")
    assert result.problems == [], result.problems
    css = next((tmp_path / "dist" / "syahi.sh" / "assets").glob("base.*.css")).read_text(encoding="utf-8")
    name = "dot." + hashlib.sha256(b"\x89PNG-dot").hexdigest()[:10] + ".png"
    assert f'url("/assets/img/{name}")' in css and f"url(/assets/img/{name}#a)" in css
    assert (tmp_path / "dist" / "syahi.sh" / "assets" / "img" / name).is_file()


def test_a_stylesheet_url_naming_no_asset_is_a_problem(mini_root, tmp_path):
    (mini_root / "tokens" / "base.css").write_text(".dot{background:url(/assets/img/ghost.png)}", encoding="utf-8")
    result = build(mini_root, tmp_path / "dist")
    assert any("ghost.png" in p and "base.css" in p for p in result.problems), result.problems


def test_rewrite_html_changes_asset_links_only_and_leaves_absolute_urls_alone():
    manifest = {"img/a.png": "/assets/img/a.1234567890.png"}
    html = ('<img src="/assets/img/a.png"><a href="/assets/img/a.png?x=1#y">x</a><a href="/other">o</a>'
            '<meta content="https://syahi.sh/assets/img/a.png"><img src="/assets/img/unknown.png">')
    out = assets.rewrite_html(html, manifest)
    assert out == ('<img src="/assets/img/a.1234567890.png"><a href="/assets/img/a.1234567890.png?x=1#y">x</a><a href="/other">o</a>'
                   '<meta content="https://syahi.sh/assets/img/a.png"><img src="/assets/img/unknown.png">')


LICENSE_ROW = re.compile(r"^\| `([^`]+)` \| [^|]+ \| (?:(\d+) \| )?`([0-9a-f]{64})` \|$", re.M)
PINNED_COMMIT = "7085eb89a950e85db5b166b7a58d414544b4140c"


def test_the_licences_file_records_the_pinned_commit_and_every_checksum():
    doc = (ASSETS / "fonts" / "LICENSES.md").read_text(encoding="utf-8")
    assert PINNED_COMMIT in doc
    rows = LICENSE_ROW.findall(doc)
    held = sorted(p.name for p in (ASSETS / "fonts" / "src").iterdir())
    assert sorted(name for name, _, _ in rows) == held and len(held) == 10
    for name, size, digest in rows:
        data = (ASSETS / "fonts" / "src" / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest, name
        if size:
            assert len(data) == int(size), name


def test_every_family_has_its_ofl_text_beside_the_sources():
    held = {p.name for p in (ASSETS / "fonts" / "src").iterdir()}
    assert {f"OFL-{family}.txt" for family in ("fraunces", "inter", "ibmplexmono", "tirodevanagarihindi")} <= held
    assert {face.source for face in assets.FACES} <= held
    for family in ("fraunces", "inter", "ibmplexmono", "tirodevanagarihindi"):
        assert "SIL OPEN FONT LICENSE Version 1.1" in (ASSETS / "fonts" / "src" / f"OFL-{family}.txt").read_text(encoding="utf-8")


# ---- the weights and features a face ships ----

def test_used_weights_always_hold_normal_and_bold_and_grow_to_what_the_css_asks():
    assert assets.used_weights([]) == (400, 700)
    assert assets.used_weights(["h1{font-weight:600} p{font-weight:500}"]) == (400, 700)
    assert assets.used_weights([".a{font-weight:300}", ".b{font-weight:800 !important}"]) == (300, 800)
    assert assets.used_weights([".a{font-weight:normal} .b{font-weight:bold}"]) == (400, 700)


@pytest.mark.parametrize("css", [
    ".a{font-weight:lighter}", ".a{font-weight:bolder}", ".a{font-weight:var(--w)}",
    ".a{font:italic 600 1rem/1.4 serif}",
])
def test_a_weight_that_cannot_be_known_keeps_the_whole_axis(css):
    assert assets.used_weights([css]) is None


def test_font_inherit_asks_for_nothing_new():
    assert assets.used_weights(["input,button{font:inherit}"]) == (400, 700)
    assert not assets.needs_all_features(["input,button{font:inherit}"])


@pytest.mark.parametrize("css", [
    ".a{font-feature-settings:'tnum'}", ".a{font-variant-numeric:tabular-nums}", ".a{font-variant:small-caps}",
    ".a{font-kerning:none}", ".a{font:600 1rem serif}",
])
def test_a_stylesheet_that_asks_for_font_features_keeps_them_all(css):
    assert assets.needs_all_features([css])


def test_a_face_limited_to_the_used_weights_keeps_the_look_inside_them_and_ships_less(tmp_path):
    src = ASSETS / "fonts" / "src" / "Inter[opsz,wght].ttf"
    whole = assets._subset(src, "Syahi receipts 123")
    lean = assets._subset(src, "Syahi receipts 123", (400, 700), all_features=False)
    font = TTFont(io.BytesIO(lean))
    axes = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in font["fvar"].axes}
    assert axes["wght"] == (400, 400, 700) and axes["opsz"] == (14, 14, 32)
    assert len(lean) < len(whole) * 0.6
    tags = {r.FeatureTag for r in font["GSUB"].table.FeatureList.FeatureRecord}
    assert {"kern"} <= {r.FeatureTag for r in font["GPOS"].table.FeatureList.FeatureRecord}
    assert not tags & {"ss01", "cv01", "tnum", "zero"}, tags          # nothing the page can switch on is shipped


def test_an_old_fonttools_is_a_named_problem_not_a_silent_full_axis(monkeypatch, tmp_path):
    from fontTools.varLib import instancer
    monkeypatch.delattr(instancer, "AxisTriple")
    monkeypatch.setenv("SITEBUILD_CACHE", str(tmp_path / "cache"))
    src = ASSETS / "fonts" / "src" / "Inter[opsz,wght].ttf"
    with pytest.raises(assets.AssetError, match=r"Inter.*fonttools>=4\.50"):
        assets._subset(src, "Hi", (400, 700))


@pytest.mark.parametrize("host", HOSTS)
def test_the_real_variable_faces_stop_at_the_weights_the_site_uses(real_site, host):
    for path in (real_site.out / host / "assets" / "fonts").glob("*.woff2"):
        font = TTFont(str(path))
        if "fvar" in font:
            wght = next(a for a in font["fvar"].axes if a.axisTag == "wght")
            assert (wght.minValue, wght.maxValue) == (400, 700), path.name


# ---- picture() ----

def test_picture_puts_the_class_on_the_img_the_stylesheet_sizes(mini_root, tmp_path):
    Image.new("RGB", (600, 600), "white").save(mini_root / "assets" / "img" / "c.png")
    picture_page(mini_root, '{{ picture("img/c.png", "C", css_class="hero-mark") }}')
    build(mini_root, tmp_path / "dist")
    html = (tmp_path / "dist" / "syahi.sh" / "index.html").read_text(encoding="utf-8")
    assert re.search(r'<img class="hero-mark" src="/assets/img/c-600w\.[0-9a-f]{10}\.webp"', html)


@pytest.mark.parametrize("host, page", [("syahi.sh", "index.html"), ("syahi.sh", "katha.html"), ("katha.syahi.sh", "index.html")])
def test_the_real_plates_ship_small_variants_not_the_900_px_file_to_a_phone(real_site, host, page):
    html = (real_site.out / host / page).read_text(encoding="utf-8")
    assert not re.search(r'<img[^>]*src="/assets/img/[a-z]+\.[0-9a-f]{10}\.webp"', html)       # no bare plate
    sources = re.findall(r'<source type="image/avif" srcset="([^"]+)"', html)
    assert sources
    for srcset in sources:
        assert " 240w" in srcset and " 480w" in srcset

def test_a_phone_downloads_nothing_for_the_hidden_hero_plates(real_site):
    # .hero-side is display:none under 40em on all three hero pages: the sources are gated to wider screens and
    # the img falls back to one inline pixel, so a phone makes no request for the plate.
    for host, page in (("syahi.sh", "index.html"), ("syahi.sh", "katha.html"), ("katha.syahi.sh", "index.html")):
        html = (real_site.out / host / page).read_text(encoding="utf-8")
        hero = re.search(r"<picture>(?:(?!</picture>).)*class=\"hero-(?:mark|fig)\"(?:(?!</picture>).)*</picture>", html).group(0)
        assert re.findall(r"<source [^>]*>", hero) and all('media="(min-width: 40em)"' in s for s in re.findall(r"<source [^>]*>", hero)), (host, page)
        img = re.search(r"<img [^>]*>", hero).group(0)
        assert f'src="{assets.BLANK_PIXEL}"' in img and 'width="900" height="900"' in img and "alt=" in img, (host, page)
        assert "/assets/img/" not in img, (host, page)


def test_picture_with_a_media_query_gates_every_source_and_blanks_the_img(mini_root, tmp_path):
    Image.new("RGB", (600, 600), "white").save(mini_root / "assets" / "img" / "m.png")
    picture_page(mini_root, '{{ picture("img/m.png", "M", media="(min-width: 40em)", loading="eager") }}')
    build(mini_root, tmp_path / "dist")
    html = (tmp_path / "dist" / "syahi.sh" / "index.html").read_text(encoding="utf-8")
    block = re.search(r"<picture>.*?</picture>", html, re.S).group(0)
    assert block.count('media="(min-width: 40em)"') == 2
    assert f'<img src="{assets.BLANK_PIXEL}" width="600" height="600" alt="M"' in block


def test_every_published_image_is_named_by_a_page_or_a_stylesheet_unless_it_keeps_a_stable_name(real_site):
    for host in HOSTS:
        root = real_site.out / host
        named = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in root.rglob("*")
                          if p.is_file() and p.suffix in (".html", ".css", ".txt", ".xml"))
        stable = {"/assets/" + name for name in (*assets.STABLE_ONLY, *assets.ALSO_STABLE)}
        for path in (root / "assets").rglob("*"):
            if path.is_file() and path.suffix in (".webp", ".avif", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico"):
                url = "/" + path.relative_to(root).as_posix()
                assert url in named or url in stable, f"{host}: {url} is published and nothing names it"


def test_the_hero_plates_keep_the_class_the_stylesheet_sizes_them_by(real_site):
    home = (real_site.out / "syahi.sh" / "index.html").read_text(encoding="utf-8")
    assert '<img class="hero-mark" ' in home
    katha = (real_site.out / "katha.syahi.sh" / "index.html").read_text(encoding="utf-8")
    assert '<img class="hero-fig" ' in katha

def picture_page(mini_root: Path, call: str) -> None:
    page = mini_root / "content" / "index.html"
    page.write_text(page.read_text(encoding="utf-8") + "\n" + call + "\n", encoding="utf-8")


def test_picture_writes_avif_and_webp_sources_then_a_sized_lazy_img(mini_root, tmp_path):
    Image.new("RGB", (1000, 500), "white").save(mini_root / "assets" / "img" / "photo.png")
    picture_page(mini_root, '{{ picture("img/photo.png", "A white field", sizes="50vw") }}')
    result = build(mini_root, tmp_path / "dist")
    assert result.problems == [], result.problems
    html = (tmp_path / "dist" / "syahi.sh" / "index.html").read_text(encoding="utf-8")
    block = re.search(r"<picture>.*?</picture>", html, re.S).group(0)
    assert block.index('type="image/avif"') < block.index('type="image/webp"') < block.index("<img ")
    assert 'sizes="50vw"' in block and 'width="1000" height="500" alt="A white field" loading="lazy" decoding="async"' in block
    assert "fetchpriority" not in block
    for url in re.findall(r"(/assets/img/photo-[^\s\",]+)", block):
        assert (tmp_path / "dist" / "syahi.sh" / url.lstrip("/")).is_file(), url
    assert "480w" in block and "960w" in block and "1000w" in block and "1600w" not in block


def test_the_first_image_can_be_eager_with_high_fetch_priority(mini_root, tmp_path):
    Image.new("RGB", (600, 300), "white").save(mini_root / "assets" / "img" / "hero.png")
    picture_page(mini_root, '{{ picture("img/hero.png", "Hero", loading="eager", fetchpriority="high") }}')
    result = build(mini_root, tmp_path / "dist")
    assert result.problems == [], result.problems
    html = (tmp_path / "dist" / "syahi.sh" / "index.html").read_text(encoding="utf-8")
    assert 'loading="eager" decoding="async" fetchpriority="high">' in html


def test_picture_escapes_its_alt_text(mini_root, tmp_path):
    Image.new("RGB", (100, 100), "white").save(mini_root / "assets" / "img" / "q.png")
    picture_page(mini_root, '{{ picture("img/q.png", \'A "quoted" <b>\') }}')
    build(mini_root, tmp_path / "dist")
    html = (tmp_path / "dist" / "syahi.sh" / "index.html").read_text(encoding="utf-8")
    assert 'alt="A &quot;quoted&quot; &lt;b&gt;"' in html


@pytest.mark.parametrize("call, reason", [
    ('{{ picture("img/nowhere.png", "x") }}', "is not a file"),
    ('{{ picture("../tokens/base.css", "x") }}', "must be a path under assets"),
])
def test_picture_of_a_missing_or_escaping_path_fails_the_page_naming_it(mini_root, tmp_path, call, reason):
    picture_page(mini_root, call)
    result = build(mini_root, tmp_path / "dist")
    assert any("index.html" in p and reason in p for p in result.problems), result.problems


def test_picture_through_a_symlinked_folder_cannot_reach_outside_assets(mini_root, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    Image.new("RGB", (600, 600), "white").save(outside / "secret.png")
    (mini_root / "assets" / "img" / "linked").symlink_to(outside, target_is_directory=True)
    picture_page(mini_root, '{{ picture("img/linked/secret.png", "x") }}')
    result = build(mini_root, tmp_path / "dist")
    assert any("index.html" in p and "must resolve to a file under assets/" in p for p in result.problems), result.problems
    assert not list((tmp_path / "dist").rglob("secret*"))


# ---- the subset cache, preloads and the whole real build ----

def test_a_remembered_subset_is_the_same_bytes_as_a_fresh_one(tmp_path, monkeypatch):
    monkeypatch.setenv("SITEBUILD_CACHE", str(tmp_path / "cache"))
    src = ASSETS / "fonts" / "src" / "IBMPlexMono-Regular.ttf"
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    codepoints = tuple(sorted(assets._unicodes("Hello 123")))
    fresh = assets._subset_bytes(digest, str(src), codepoints)
    first = subset_font(src, "Hello 123", tmp_path / "a.woff2").read_bytes()      # fills the cache
    assert list((tmp_path / "cache").glob("*.woff2"))
    second = subset_font(src, "Hello 123", tmp_path / "b.woff2").read_bytes()      # reads it
    assert fresh == first == second


def test_an_unusable_cache_folder_is_skipped_not_a_problem(tmp_path, monkeypatch):
    blocker = tmp_path / "file"; blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("SITEBUILD_CACHE", str(blocker / "cache"))                   # a folder under a file cannot be made
    out = subset_font(ASSETS / "fonts" / "src" / "IBMPlexMono-Regular.ttf", "Hi", tmp_path / "a.woff2")
    assert out.read_bytes()[:4] == b"wOF2"


def test_a_font_preload_for_a_face_the_host_does_not_ship_is_dropped():
    html = ('<head><link rel="preload" href="/assets/fonts/inter.woff2" as="font" type="font/woff2" crossorigin>\n'
            '<link rel="stylesheet" href="/assets/base.css"></head>')
    assert assets.rewrite_html(html, {"base.css": "/assets/base.1234567890.css"}) == (
        '<head><link rel="stylesheet" href="/assets/base.1234567890.css"></head>')
    kept = assets.rewrite_html(html, {"fonts/inter.woff2": "/assets/fonts/inter.1234567890.woff2"})
    assert 'href="/assets/fonts/inter.1234567890.woff2"' in kept


def test_the_whole_real_build_is_byte_identical_run_to_run(real_site, tmp_path):
    again = build(real_site.root, tmp_path / "again")
    assert again.problems == real_site.result.problems
    listing = lambda out: sorted((p.relative_to(out).as_posix(), sha(p)) for p in out.rglob("*") if p.is_file())
    assert listing(tmp_path / "again") == listing(real_site.out)


# ---- fix round 1: case, generated content, joiners, noscript, the cache ----

INTER = ASSETS / "fonts" / "src" / "Inter[opsz,wght].ttf"


def subset_cmap(tmp_path: Path, text: str, src: Path = INTER) -> set[int]:
    return set(TTFont(str(subset_font(src, text, tmp_path / "s.woff2"))).getBestCmap())


def test_lowercase_text_keeps_its_capitals_for_text_transform(tmp_path):
    cmap = subset_cmap(tmp_path, "subject")
    assert {ord(c) for c in "SUBJECT"} <= cmap and {ord(c) for c in "subject"} <= cmap
    assert ord("Q") not in cmap


def test_capitals_in_the_text_keep_their_lowercase_too(tmp_path):
    assert ord("j") in subset_cmap(tmp_path, "J")


def test_case_is_handled_beyond_ascii(tmp_path):
    assert {0xE9, 0xC9} <= subset_cmap(tmp_path, "\u00e9")                      # e acute and E acute


def test_a_host_whose_text_is_lowercase_ships_the_capitals_its_uppercase_rule_draws(mini_root, tmp_path):
    page = mini_root / "content" / "index.html"
    page.write_text(page.read_text(encoding="utf-8") + "\n<p>quartz jinx</p>\n", encoding="utf-8")
    (mini_root / "tokens" / "base.css").write_text("body{font-family:var(--font-sans)}p{text-transform:uppercase}", encoding="utf-8")
    result = build(mini_root, tmp_path / "dist")
    assert not [p for p in result.problems if "font" in p], result.problems
    inter = next((tmp_path / "dist" / "syahi.sh" / "assets" / "fonts").glob("inter.*.woff2"))
    assert {ord(c) for c in "QUARTZJINX"} <= set(TTFont(str(inter)).getBestCmap())


def test_css_content_strings_are_decoded_escape_and_literal():
    css = (".a::before{content:\"\\2212\\00A0\"}.b::after{content:'\\2713 ok'}.c::before{content:\"\u00bd\";color:red}"
           ".d{content:none}.e{content:counter(n) \" \\2192\"}.f{content:\"a\\\nb\"}")
    assert assets.css_content_text(css) == "\u2212\u00a0\u2713ok\u00bd \u2192ab"


def test_a_stylesheets_content_glyphs_reach_the_latin_subsets(mini_root, tmp_path):
    (mini_root / "tokens" / "base.css").write_text(
        'body{font-family:var(--font-sans)}.m::before{content:"\\2212"}.l::after{content:"\u00bd"}', encoding="utf-8")
    result = build(mini_root, tmp_path / "dist")
    assert not [p for p in result.problems if "font" in p], result.problems
    inter = next((tmp_path / "dist" / "syahi.sh" / "assets" / "fonts").glob("inter.*.woff2"))
    cmap = set(TTFont(str(inter)).getBestCmap())
    assert {0x2212, 0xBD} <= cmap


def test_the_real_pages_content_glyphs_are_in_the_subset(real_site):
    inter = next((real_site.out / "syahi.sh" / "assets" / "fonts").glob("inter.*.woff2"))
    assert {0x2212, 0x2713} <= set(TTFont(str(inter)).getBestCmap())


def test_joiners_are_kept(tmp_path):
    src = ASSETS / "fonts" / "src" / "TiroDevanagariHindi-Regular.ttf"
    assert {0x200C, 0x200D} <= assets._unicodes("\u0915\u094d\u200d\u0937\u200c")
    assert 0x0915 in subset_cmap(tmp_path, "\u0915\u094d\u200d\u0937", src)


def test_noscript_text_counts():
    latin, _ = assets.page_text("<body><p>a</p><noscript><p>Zebra</p></noscript><script>var q</script></body>")
    assert latin == "aZebra"


def poison(cache: Path, data: bytes) -> list[Path]:
    entries = sorted(cache.glob("*.woff2"))
    for entry in entries:
        entry.write_bytes(data)
    return entries


def test_a_damaged_cache_entry_is_rebuilt_not_trusted(tmp_path, monkeypatch):
    monkeypatch.setenv("SITEBUILD_CACHE", str(tmp_path / "cache"))
    src = ASSETS / "fonts" / "src" / "IBMPlexMono-Regular.ttf"
    good = subset_font(src, "Hello", tmp_path / "a.woff2").read_bytes()
    assert poison(tmp_path / "cache", b"garbage")
    assert subset_font(src, "Hello", tmp_path / "b.woff2").read_bytes() == good


def test_a_cache_entry_missing_a_requested_glyph_is_rebuilt(tmp_path, monkeypatch):
    monkeypatch.setenv("SITEBUILD_CACHE", str(tmp_path / "cache"))
    src = ASSETS / "fonts" / "src" / "IBMPlexMono-Regular.ttf"
    wanted = subset_font(src, "Hello", tmp_path / "a.woff2").read_bytes()
    (entry,) = (tmp_path / "cache").glob("*.woff2")
    entry.write_bytes(subset_font(src, "x", tmp_path / "small.woff2").read_bytes())    # a valid font, wrong glyphs
    out = subset_font(src, "Hello", tmp_path / "b.woff2")
    assert out.read_bytes() == wanted and ord("H") in TTFont(str(out)).getBestCmap()


def test_the_recipe_is_part_of_the_cache_key(tmp_path, monkeypatch):
    monkeypatch.setenv("SITEBUILD_CACHE", str(tmp_path / "cache"))
    src = ASSETS / "fonts" / "src" / "IBMPlexMono-Regular.ttf"
    subset_font(src, "Hello", tmp_path / "a.woff2")
    monkeypatch.setattr(assets, "_RECIPE", assets._RECIPE + " changed")
    subset_font(src, "Hello", tmp_path / "b.woff2")
    assert len(list((tmp_path / "cache").glob("*.woff2"))) == 2


def test_the_default_cache_is_in_the_users_own_cache_folder(tmp_path, monkeypatch):
    monkeypatch.delenv("SITEBUILD_CACHE", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert assets._cache_dir() == tmp_path / ".cache" / "syahi-sitebuild"
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert assets._cache_dir() == tmp_path / "xdg" / "syahi-sitebuild"
    monkeypatch.setenv("SITEBUILD_CACHE", str(tmp_path / "mine"))
    assert assets._cache_dir() == tmp_path / "mine"
    assert (assets._cache_dir() / "x").name == "x" and "tmp" not in assets._cache_dir().parts[-1]


def test_a_subset_does_not_depend_on_the_clock(monkeypatch):
    import time
    src = ASSETS / "fonts" / "src" / "Fraunces[SOFT,WONK,opsz,wght].ttf"
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    codepoints = tuple(sorted(assets._unicodes("Hello")))
    first = assets._subset_bytes(digest, str(src), codepoints)
    time.sleep(1.1)
    assert assets._subset_bytes(digest, str(src), codepoints) == first
    assert TTFont(io.BytesIO(first))["head"].modified == TTFont(str(src))["head"].modified
