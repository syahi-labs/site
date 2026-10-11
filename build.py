"""Build the syahi.sh site: `python build.py [--root DIR] [--out DIR] [--release]`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sitebuild.pipeline import build


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
    result = build(args.root, args.out, release=args.release)
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for problem in result.problems:
        print(f"error: {problem}", file=sys.stderr)
    noted = f", {len(result.warnings)} warning(s)" if result.warnings else ""
    if result.problems:
        print(f"build failed: {len(result.problems)} problem(s){noted}", file=sys.stderr)
        return 1
    print(f"built {len(result.pages)} page(s) for {', '.join(result.outputs)} into {args.out}{noted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
