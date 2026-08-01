"""Command-line interface for Termino Exporter."""

import argparse
import sys
from collections.abc import Sequence
from importlib.metadata import version
from io import TextIOWrapper
from pathlib import Path
from typing import Never
from urllib.parse import urlparse

from termino_exporter.browser import (
    BrowserError,
    ProfilePathError,
    default_profile_dir,
    safe_profile_dir,
)
from termino_exporter.close_diagnosis import CloseDiagnosisError
from termino_exporter.diagnosis import DiagnosisError
from termino_exporter.inspection import InspectionError, inspect_one_reservation

DEFAULT_URL = "https://local.termino.eu/"
DEFAULT_TIMEOUT_SECONDS = 30.0


class CzechArgumentParser(argparse.ArgumentParser):
    """Argument parser with Czech headings and error prefix."""

    def format_usage(self) -> str:
        return super().format_usage().replace("usage:", "použití:", 1)

    def format_help(self) -> str:
        return super().format_help().replace("usage:", "použití:", 1)

    def error(self, message: str) -> Never:
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: chyba: {message}\n")


def _positive_seconds(value: str) -> float:
    seconds = float(value)
    if seconds <= 0:
        raise argparse.ArgumentTypeError("časový limit musí být větší než nula")
    return seconds


def _web_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise argparse.ArgumentTypeError("URL musí být platná adresa HTTP nebo HTTPS")
    return value


def create_parser() -> CzechArgumentParser:
    """Create the command-line argument parser."""
    parser = CzechArgumentParser(
        prog="termino-exporter",
        description="Lokální nástroj pro bezpečné čtení rezervací z Termino.",
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
    subparsers = parser.add_subparsers(dest="command", title="příkazy")
    inspect_parser = subparsers.add_parser(
        "inspect-one",
        help="bezpečně prohlédne jednu ručně vybranou rezervaci",
        description=(
            "Spustí viditelný prohlížeč a pouze pro čtení vypíše momentálně dostupný "
            "text jednoho ručně otevřeného detailu rezervace."
        ),
        add_help=False,
    )
    inspect_parser._positionals.title = "poziční argumenty"
    inspect_parser._optionals.title = "volby"
    inspect_parser.add_argument(
        "-h",
        "--help",
        action="help",
        help="zobrazí tuto nápovědu a skončí",
    )
    inspect_parser.add_argument(
        "--url",
        type=_web_url,
        default=DEFAULT_URL,
        help=f"adresa kalendáře (výchozí: {DEFAULT_URL})",
    )
    inspect_parser.add_argument(
        "--profile-dir",
        type=Path,
        default=None,
        help="cesta k vyhrazenému lokálnímu profilu prohlížeče",
    )
    inspect_parser.add_argument(
        "--timeout-seconds",
        type=_positive_seconds,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"časový limit operací v sekundách (výchozí: {DEFAULT_TIMEOUT_SECONDS:g})",
    )
    diagnostic_group = inspect_parser.add_mutually_exclusive_group()
    diagnostic_group.add_argument(
        "--diagnose-dialog",
        action="store_true",
        help="vypíše pouze bezpečnou strukturální diagnostiku ručně otevřeného detailu",
    )
    diagnostic_group.add_argument(
        "--diagnose-close",
        action="store_true",
        help="vypíše pouze bezpečnou strukturální diagnostiku tlačítek detailu",
    )
    return parser


def _run_inspect_one(args: argparse.Namespace) -> int:
    try:
        requested_profile = (
            args.profile_dir if args.profile_dir is not None else default_profile_dir()
        )
        profile_dir = safe_profile_dir(requested_profile)
        inspect_one_reservation(
            url=args.url,
            profile_dir=profile_dir,
            timeout_seconds=args.timeout_seconds,
            diagnose_dialog=args.diagnose_dialog,
            diagnose_close=args.diagnose_close,
        )
    except (
        BrowserError,
        CloseDiagnosisError,
        DiagnosisError,
        InspectionError,
        ProfilePathError,
    ) as error:
        print(f"Chyba: {error}", file=sys.stderr)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    parser = create_parser()
    args = parser.parse_args(argv)
    if args.command == "inspect-one":
        return _run_inspect_one(args)
    parser.print_help()
    return 0
