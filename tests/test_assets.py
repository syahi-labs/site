# tests/test_assets.py
#
# Task 9a: the shared assets (art, brand mark, default share image, favicons) come from the live site at
# 446f625 as bytes, `_publish_assets` copies the assets/ tree into each host's output (unhashed, until
# Task 7 replaces the seam with the hashed pipeline), and the base template links the icons for both hosts.
import hashlib
import re
import struct
from pathlib import Path

import pytest

from sitebuild import pipeline
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
    held = sorted(p.relative_to(ASSETS).as_posix() for p in ASSETS.rglob("*") if p.is_file() and not p.name.startswith("."))
    assert held == sorted(SOURCES)


def test_the_brand_images_have_the_sizes_the_pages_declare():
    assert png_size(ASSETS / "brand" / "og-default.png") == (1200, 630)
    assert png_size(ASSETS / "brand" / "mark-512.png") == (512, 512)
    assert png_size(ASSETS / "brand" / "icon-192.png") == (192, 192)
    assert png_size(ASSETS / "brand" / "apple-touch-icon.png") == (180, 180)


# ---- the build publishes them to both hosts ----

@pytest.mark.parametrize("host", HOSTS)
def test_the_build_publishes_every_asset_byte_for_byte(real_site, host):
    for name in SOURCES:
        published = real_site.out / host / "assets" / name
        assert published.is_file(), f"{host}: {name}"
        assert sha(published) == SOURCES[name], f"{host}: {name}"


@pytest.mark.parametrize("host", HOSTS)
def test_the_stylesheets_are_still_published_beside_the_tree(real_site, host):
    for name in ("tokens.css", "base.css"):
        assert (real_site.out / host / "assets" / name).read_bytes() == (REPO / "tokens" / name).read_bytes()


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
    '<link rel="icon" href="/assets/brand/favicon.ico" sizes="48x48">',
    '<link rel="icon" href="/assets/brand/favicon.svg" type="image/svg+xml">',
    '<link rel="apple-touch-icon" href="/assets/brand/apple-touch-icon.png">',
)


@pytest.mark.parametrize("host", HOSTS)
def test_every_page_links_the_favicons_the_apple_icon_and_the_theme_colour(real_site, host):
    pages = sorted((real_site.out / host).glob("*.html"))
    assert pages
    for page in pages:
        html = page.read_text(encoding="utf-8")
        head = html.split("</head>")[0]
        for link in ICON_LINKS:
            assert link in head, f"{host}/{page.name}: {link}"
        assert head.count('<meta name="theme-color"') == 1, f"{host}/{page.name}"


@pytest.mark.parametrize("host", HOSTS)
def test_every_linked_icon_resolves_in_that_hosts_output(real_site, host):
    for link in ICON_LINKS:
        href = re.search(r'href="(/[^"]+)"', link).group(1)
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
    assert 'src="/assets/img/gramophone.webp"' in html
    assert "https://syahi.sh/art/" not in html
    assert (real_site.out / "katha.syahi.sh" / "assets" / "img" / "gramophone.webp").is_file()


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


def test_the_tree_is_copied_as_bytes_with_its_nested_folders(tmp_path):
    root = tree(tmp_path / "root", {"img/a.webp": b"\x00\xffRIFF", "brand/b.png": b"\x89PNG\r\n", "c/d/e.bin": b"\r\n\x00"})
    stylesheets(root)
    host_out = tmp_path / "out"
    assert pipeline._publish_assets(root, host_out) == []
    for name, data in {"img/a.webp": b"\x00\xffRIFF", "brand/b.png": b"\x89PNG\r\n", "c/d/e.bin": b"\r\n\x00"}.items():
        assert (host_out / "assets" / name).read_bytes() == data
    assert (host_out / "assets" / "tokens.css").is_file() and (host_out / "assets" / "base.css").is_file()


def test_no_assets_folder_is_not_a_problem(tmp_path):
    root = tmp_path / "root"
    stylesheets(root)
    assert pipeline._publish_assets(root, tmp_path / "out") == []
    assert sorted(p.name for p in (tmp_path / "out" / "assets").iterdir()) == ["base.css", "tokens.css"]


def test_dotfiles_are_never_published(tmp_path):
    root = tree(tmp_path / "root", {"img/a.webp": b"x", ".DS_Store": b"junk", "img/.DS_Store": b"junk", ".hidden/b.png": b"x"})
    stylesheets(root)
    assert pipeline._publish_assets(root, tmp_path / "out") == []
    published = sorted(p.relative_to(tmp_path / "out" / "assets").as_posix() for p in (tmp_path / "out" / "assets").rglob("*") if p.is_file())
    assert published == ["base.css", "img/a.webp", "tokens.css"]


def test_a_symbolic_link_in_assets_is_a_problem_and_is_not_followed(tmp_path):
    secret = tmp_path / "outside" / "secret.txt"
    secret.parent.mkdir()
    secret.write_text("private", encoding="utf-8")
    root = tree(tmp_path / "root", {"img/a.webp": b"x"})
    stylesheets(root)
    (root / "assets" / "img" / "link.txt").symlink_to(secret)
    (root / "assets" / "linked-dir").symlink_to(secret.parent, target_is_directory=True)
    problems = pipeline._publish_assets(root, tmp_path / "out")
    assert any("link.txt" in p and "symbolic link" in p for p in problems), problems
    assert any("linked-dir" in p and "symbolic link" in p for p in problems), problems
    published = [p for p in (tmp_path / "out").rglob("*") if p.is_file()]
    assert not any("private" in p.read_text(encoding="utf-8", errors="ignore") for p in published)
    assert not (tmp_path / "out" / "assets" / "img" / "link.txt").exists()
    assert (tmp_path / "out" / "assets" / "img" / "a.webp").is_file()          # the rest still published


@pytest.mark.parametrize("name", ["tokens.css", "base.css", "pages/demo.css"])
def test_a_file_in_a_name_the_build_writes_itself_is_a_problem_and_never_replaces_it(tmp_path, name):
    # tokens.css, base.css and pages/ are the build's own: a stray file there must not shadow a real stylesheet.
    root = tree(tmp_path / "root", {name: b"body{display:none}", "img/a.webp": b"x"})
    stylesheets(root)
    problems = pipeline._publish_assets(root, tmp_path / "out")
    assert any(name in p and "reserved" in p for p in problems), problems
    assert (tmp_path / "out" / "assets" / "img" / "a.webp").is_file()          # the rest still published
    shadowed = tmp_path / "out" / "assets" / name
    assert not shadowed.exists() or shadowed.read_text(encoding="utf-8") == "a{}\n"


def test_a_feed_or_cname_hidden_in_assets_still_fails_the_build(mini_root, tmp_path):
    tree(mini_root, {"feed.xml": b"<rss/>"})
    result = build(mini_root, tmp_path / "dist")
    assert any("feed.xml" in p and "never be part of the build output" in p for p in result.problems), result.problems


def test_the_tree_is_published_to_both_hosts_and_the_build_is_deterministic(mini_root, tmp_path):
    tree(mini_root, {"img/a.webp": b"\x00art"})
    first, second = tmp_path / "a", tmp_path / "b"
    assert build(mini_root, first).problems == [] and build(mini_root, second).problems == []
    for host in HOSTS:
        assert (first / host / "assets" / "img" / "a.webp").read_bytes() == b"\x00art"
    listing = lambda out: sorted((p.relative_to(out).as_posix(), sha(p)) for p in out.rglob("*") if p.is_file())
    assert listing(first) == listing(second)


def test_the_build_never_reads_its_own_published_assets(mini_root, tmp_path):
    # the output may not sit inside a source folder, assets/ included
    result = build(mini_root, mini_root / "assets" / "out")
    assert result.problems and "assets" in result.problems[0]
