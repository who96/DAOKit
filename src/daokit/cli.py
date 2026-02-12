from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

from .bootstrap import RepositoryInitError, initialize_repository


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="daokit", description="DAOKit command line interface")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a DAOKit repository skeleton",
    )
    init_parser.add_argument(
        "--root",
        default=".",
        help="Target directory for initialization (default: current directory)",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        root = Path(args.root)
        try:
            result = initialize_repository(root)
        except RepositoryInitError as exc:
            print(f"Initialization failed: {exc}", file=sys.stderr)
            return 1
        print(f"Initialized DAOKit skeleton at: {root.resolve()}")
        if result.created:
            print("Created:")
            for item in result.created:
                print(f"  + {item}")
        if result.skipped:
            print("Unchanged:")
            for item in result.skipped:
                print(f"  = {item}")
        return 0

    parser.error(f"unsupported command: {args.command}")
    return 2
