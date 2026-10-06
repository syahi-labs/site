"""Build the syahi.sh site: `python build.py [--root DIR] [--out DIR] [--release]`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sitebuild.content import ContentError, load_pages


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the syahi.sh static site.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent,
                        help="site repo root (default: this repo)")
    parser.add_argument("--out", type=Path, default=None,
                        help="output directory (default: ROOT/dist)")
    parser.add_argument("--release", action="store_true",
                        help="release build: strict checks")
    args = parser.parse_args(argv)
    args.root = args.root.resolve()
    args.out = (args.out or args.root / "dist").resolve()
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        pages = load_pages(args.root / "content")
    except ContentError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    print(f"loaded {len(pages)} page(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
