"""Find the content-hashed files a build publishes, by the name they had before they were hashed."""
import re
from pathlib import Path

HASH = r"[0-9a-f]{10}"


def hashed_file(host_dir: Path, name: str) -> Path:
    """The one file under host_dir/assets that is `name` with a content hash before its extension.

    `name` is the path under assets/, e.g. "tokens.css" or "pages/home.css". Fails if there is none or more than one.
    """
    path = Path(name)
    folder = host_dir / "assets" / path.parent
    pattern = re.compile(rf"{re.escape(path.stem)}\.{HASH}{re.escape(path.suffix)}")
    found = sorted(p for p in folder.iterdir() if pattern.fullmatch(p.name)) if folder.is_dir() else []
    assert len(found) == 1, f"{host_dir.name}: expected one hashed {name}, found {[p.name for p in found]}"
    return found[0]


def hashed_url(host_dir: Path, name: str) -> str:
    """The URL a page uses for `name` (a path under assets/)."""
    return "/" + hashed_file(host_dir, name).relative_to(host_dir).as_posix()


_HASHED_URL = re.compile(rf"(/assets/[^\"'\s)]*?)\.{HASH}(\.[a-z0-9]+)")


_VARIANT = re.compile(r"(/assets/img/[a-z0-9-]+?)-\d+w(\.[a-z0-9]+)")


def unhash(text: str) -> str:
    """`text` with the content hash taken out of every /assets/ URL, to compare a built page with its source.

    A plate a page shows through picture() is named by its widest variant (`inkpot-900w.<hash>.webp`); that is
    the source file's own name here too, because the variant is the same plate at the same size.
    """
    return _VARIANT.sub(r"\1\2", _HASHED_URL.sub(r"\1\2", text))
