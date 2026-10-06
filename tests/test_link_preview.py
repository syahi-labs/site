# tests/test_link_preview.py
#
# The tags that make a shared link look right: og:image with its pixel size, twitter:card and twitter:image.
# Today's pages had all of them; the shared base lost them, a regression this restores. An image's size is read
# from the file at build time, never written in the template: the default image's, and the page's own image's
# when a page names one (`og_image` in its front matter).
import re
import struct
import zlib
from pathlib import Path

import pytest

from sitebuild.pipeline import build

REPO = Path(__file__).resolve().parents[1]
DEFAULT_IMAGE = Path("assets") / "brand" / "og-default.png"
HOSTS = ("syahi.sh", "katha.syahi.sh")


def png(width: int, height: int) -> bytes:
    """A real, valid, solid-colour PNG of the given size (RGB, 8 bit)."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))
    row = b"\x00" + b"\x80\x80\x80" * width
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b""))


def metas(html: str) -> dict[str, str]:
    head = html.split("</head>")[0]
    found = {}
    for key, name, content in re.findall(r'<meta (name|property)="([^"]+)" content="([^"]*)">', head):
        found[name] = content
    return found


def real_png_size(path: Path) -> tuple[int, int]:
    return struct.unpack(">II", path.read_bytes()[16:24])


# ---- the real site ----

@pytest.mark.parametrize("host", HOSTS)
def test_every_page_asks_for_the_large_image_card(real_site, host):
    pages = sorted((real_site.out / host).glob("*.html"))
    assert pages
    for page in pages:
        tags = metas(page.read_text(encoding="utf-8"))
        assert tags["twitter:card"] == "summary_large_image", page.name
        assert tags["twitter:image"] == tags["og:image"], page.name
        assert tags["twitter:image"].startswith(f"https://{host}/"), page.name   # absolute, on its own host


def own_images() -> dict[str, str]:
    """The built file name and the og_image of each page of the main host that names an image of its own."""
    from sitebuild.content import load_pages
    return {("index" if page.slug == "/" else page.slug.strip("/").replace("/", "-")) + ".html": page.og_image
            for page in load_pages(REPO / "content") if page.og_image}


@pytest.mark.parametrize("host", HOSTS)
def test_the_default_image_carries_its_real_pixel_size(real_site, host):
    width, height = real_png_size(REPO / DEFAULT_IMAGE)
    assert (width, height) == (1200, 630)
    own = own_images() if host == "syahi.sh" else {}
    for page in sorted((real_site.out / host).glob("*.html")):
        if page.name in own:
            continue                                      # a page's own image is the next test's
        tags = metas(page.read_text(encoding="utf-8"))
        assert tags["og:image"].endswith("/assets/brand/og-default.png"), page.name
        assert (tags["og:image:width"], tags["og:image:height"]) == (str(width), str(height)), page.name


def test_a_page_with_its_own_image_carries_that_images_real_size(real_site):
    # Signet's share image is today's og.png; today's page declared its 1200 by 630, and so does the port.
    own = own_images()
    assert own == {"signet.html": "/assets/brand/og-signet.png"}
    for name, image in own.items():
        tags = metas((real_site.out / "syahi.sh" / name).read_text(encoding="utf-8"))
        assert tags["og:image"] == f"https://syahi.sh{image}" and tags["twitter:image"] == tags["og:image"]
        assert tags["twitter:card"] == "summary_large_image"
        width, height = real_png_size(REPO / image.lstrip("/"))
        assert (width, height) == (1200, 630)
        assert (tags["og:image:width"], tags["og:image:height"]) == (str(width), str(height))


@pytest.mark.parametrize("host", HOSTS)
def test_every_page_declares_the_real_pixel_size_of_the_file_it_names(real_site, host):
    out = real_site.out / host
    for page in sorted(out.glob("*.html")):
        tags = metas(page.read_text(encoding="utf-8"))
        image = out / tags["og:image"].removeprefix(f"https://{host}/")
        assert image.is_file(), (page.name, tags["og:image"])
        assert (tags["og:image:width"], tags["og:image:height"]) == tuple(map(str, real_png_size(image))), page.name


def test_the_size_is_not_written_in_the_template():
    base = (REPO / "templates" / "base.html").read_text(encoding="utf-8")
    assert "1200" not in base and "630" not in base
    assert "og_image_width" in base or "og_image_size" in base


def test_the_tags_sit_in_the_head_in_one_group(real_site):
    head = (real_site.out / "syahi.sh" / "contact.html").read_text(encoding="utf-8").split("</head>")[0]
    order = [head.index(f'"{name}"') for name in ("og:image", "og:image:width", "og:image:height", "twitter:card", "twitter:image")]
    assert order == sorted(order)


# ---- the size follows the file ----

def set_default_image(root: Path, width: int, height: int) -> None:
    (root / DEFAULT_IMAGE).write_bytes(png(width, height))


def test_the_tags_follow_whatever_size_the_default_image_is(mini_root, tmp_path):
    set_default_image(mini_root, 1000, 500)
    assert build(mini_root, tmp_path / "dist").problems == []
    for host in HOSTS:
        tags = metas((tmp_path / "dist" / host / "index.html").read_text(encoding="utf-8"))
        assert (tags["og:image:width"], tags["og:image:height"]) == ("1000", "500")


def use_own_image(root: Path, image: str) -> Path:
    page = root / "content" / "signet.html"
    page.write_text(page.read_text(encoding="utf-8").replace("\nlayout: page\n", f"\nlayout: page\nog_image: {image}\n", 1), encoding="utf-8")
    return page


def test_a_page_with_its_own_og_image_carries_that_images_size_and_keeps_the_card(mini_root, tmp_path):
    use_own_image(mini_root, "/assets/brand/mark-512.png")
    assert build(mini_root, tmp_path / "dist").problems == []
    tags = metas((tmp_path / "dist" / "syahi.sh" / "signet.html").read_text(encoding="utf-8"))
    assert tags["og:image"] == "https://syahi.example/assets/brand/mark-512.png"
    assert tags["twitter:image"] == tags["og:image"] and tags["twitter:card"] == "summary_large_image"
    assert (tags["og:image:width"], tags["og:image:height"]) == ("512", "512")     # the file's, not the default's
    home = metas((tmp_path / "dist" / "syahi.sh" / "index.html").read_text(encoding="utf-8"))
    assert (home["og:image:width"], home["og:image:height"]) == ("1200", "630")    # the other pages keep the default's


def test_the_own_image_size_follows_whatever_size_the_file_is(mini_root, tmp_path):
    (mini_root / "assets" / "brand" / "card.png").write_bytes(png(800, 400))
    use_own_image(mini_root, "/assets/brand/card.png")
    assert build(mini_root, tmp_path / "dist").problems == []
    tags = metas((tmp_path / "dist" / "syahi.sh" / "signet.html").read_text(encoding="utf-8"))
    assert (tags["og:image:width"], tags["og:image:height"]) == ("800", "400")


def test_an_own_image_on_another_host_has_no_file_to_read_so_it_has_no_size(mini_root, tmp_path):
    use_own_image(mini_root, "https://cdn.syahi.example/card.png")
    assert build(mini_root, tmp_path / "dist").problems == []
    tags = metas((tmp_path / "dist" / "syahi.sh" / "signet.html").read_text(encoding="utf-8"))
    assert tags["og:image"] == "https://cdn.syahi.example/card.png" and tags["twitter:card"] == "summary_large_image"
    assert "og:image:width" not in tags and "og:image:height" not in tags


def test_a_missing_own_image_is_a_problem_naming_the_page_and_the_file(mini_root, tmp_path):
    page = use_own_image(mini_root, "/assets/brand/gone.png")
    result = build(mini_root, tmp_path / "dist")
    assert any(str(page) in p and "og_image" in p and "/assets/brand/gone.png" in p for p in result.problems), result.problems
    assert (tmp_path / "dist" / "syahi.sh" / "index.html").is_file()               # the other pages are still built
    assert not (tmp_path / "dist" / "syahi.sh" / "signet.html").exists()


def test_an_unreadable_own_image_is_a_problem_naming_the_page_and_the_file(mini_root, tmp_path):
    (mini_root / "assets" / "brand" / "card.png").write_bytes(b"not an image")
    page = use_own_image(mini_root, "/assets/brand/card.png")
    result = build(mini_root, tmp_path / "dist")
    assert any(str(page) in p and "og_image" in p and "/assets/brand/card.png" in p for p in result.problems), result.problems


@pytest.mark.parametrize("bad", ["/assets/../site.yaml", "/../site.yaml", "/assets/brand/../../site.yaml"])
def test_an_own_image_cannot_climb_out_of_the_site_root(mini_root, tmp_path, bad):
    page = use_own_image(mini_root, bad)
    result = build(mini_root, tmp_path / "dist")
    assert any(str(page) in p and "og_image" in p for p in result.problems), result.problems


def test_a_missing_default_image_leaves_the_size_out_without_failing_the_build(mini_root, tmp_path):
    (mini_root / DEFAULT_IMAGE).unlink()
    result = build(mini_root, tmp_path / "dist")
    tags = metas((tmp_path / "dist" / "syahi.sh" / "index.html").read_text(encoding="utf-8"))
    assert "og:image:width" not in tags and "og:image:height" not in tags
    assert tags["twitter:card"] == "summary_large_image" and tags["twitter:image"] == tags["og:image"]
    assert not any("og-default" in p and "size" in p for p in result.problems)


def test_an_unreadable_default_image_is_a_problem_naming_the_file(mini_root, tmp_path):
    (mini_root / DEFAULT_IMAGE).write_bytes(b"not an image")
    result = build(mini_root, tmp_path / "dist")
    assert any("og-default.png" in p and "size" in p for p in result.problems), result.problems
