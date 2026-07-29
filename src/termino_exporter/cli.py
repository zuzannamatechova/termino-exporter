"""Command-line interface for Termino Exporter."""

import argparse
import sys
from collections.abc import Sequence
from importlib.metadata import version
from io import TextIOWrapper


def create_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="termino-exporter",
        usage="termino-exporter [-h] [--version]",
        description="Automatizace prohlížeče zatím není implementována.",
        add_help=False,
    )
    parser._positionals.title = "poziční argumenty"
    parser._optionals.title = "volby"
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        help="zobrazí tuto nápovědu a skončí",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version('termino-exporter')}",
        help="zobrazí verzi programu a skončí",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""
    if isinstance(sys.stdout, TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = create_parser()
    args = parser.parse_args(argv)
    del args
    parser.print_help()
    return 0
