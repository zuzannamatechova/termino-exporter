"""Command-line interface for Termino Exporter."""

import argparse
import math
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
from termino_exporter.calendar_diagnosis import CalendarDiagnosisError, diagnose_calendar
from termino_exporter.close_diagnosis import CloseDiagnosisError
from termino_exporter.diagnosis import DiagnosisError
from termino_exporter.identity_candidate import IdentityCandidateError
from termino_exporter.identity_output import publish_identity_result
from termino_exporter.identity_supervisor import run_identity_supervisor
from termino_exporter.inspection import InspectionError, inspect_one_reservation
from termino_exporter.single_event import SingleEventError, inspect_single_event

DEFAULT_URL = "https://local.termino.eu/"
DEFAULT_TIMEOUT_SECONDS = 30.0
ID0_COMMAND = "diagnose-event-identity-candidates"
ID0_HELP = """použití: termino-exporter diagnose-event-identity-candidates --dummy-only [volby]

Explicitně test-only Phase 4C-ID0 technická diagnostika allowlisted atributů.

volby:
  -h, --help                 zobrazí tuto pevnou nápovědu a skončí
  --dummy-only               povinné potvrzení dummy/test-only použití
  --url URL                  adresa kalendáře
  --profile-dir CESTA        vyhrazený lokální profil prohlížeče
  --timeout-seconds SEKUNDY  limit startu a navigace, nejvýše 300
"""


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
    if not math.isfinite(seconds) or seconds <= 0:
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
            "Spustí viditelný prohlížeč a pouze pro čtení vypíše strukturované hodnoty "
            "jednoho ručně otevřeného detailu rezervace."
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
    calendar_parser = subparsers.add_parser(
        "diagnose-calendar",
        help="bezpečně diagnostikuje aktuální kalendářní pohled",
        description=(
            "Spustí viditelný prohlížeč a bez klikání vypíše pouze agregované strukturální "
            "údaje celého aktuálně zobrazeného kalendáře."
        ),
        add_help=False,
    )
    calendar_parser._positionals.title = "poziční argumenty"
    calendar_parser._optionals.title = "volby"
    calendar_parser.add_argument(
        "-h", "--help", action="help", help="zobrazí tuto nápovědu a skončí"
    )
    calendar_parser.add_argument(
        "--url",
        type=_web_url,
        default=DEFAULT_URL,
        help=f"adresa kalendáře (výchozí: {DEFAULT_URL})",
    )
    calendar_parser.add_argument(
        "--profile-dir",
        type=Path,
        default=None,
        help="cesta k vyhrazenému lokálnímu profilu prohlížeče",
    )
    calendar_parser.add_argument(
        "--timeout-seconds",
        type=_positive_seconds,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"časový limit operací v sekundách (výchozí: {DEFAULT_TIMEOUT_SECONDS:g})",
    )
    single_event_parser = subparsers.add_parser(
        "inspect-single-event",
        help="bezpečně otevře a zpracuje jedinou testovací událost v pohledu Den",
        description=(
            "Spustí viditelný prohlížeč a pouze v ručně zvoleném pohledu Den bezpečně "
            "otevře právě jednu strukturálně ověřenou testovací událost."
        ),
        add_help=False,
    )
    single_event_parser._positionals.title = "poziční argumenty"
    single_event_parser._optionals.title = "volby"
    single_event_parser.add_argument(
        "-h", "--help", action="help", help="zobrazí tuto nápovědu a skončí"
    )
    single_event_parser.add_argument(
        "--url",
        type=_web_url,
        default=DEFAULT_URL,
        help=f"adresa kalendáře (výchozí: {DEFAULT_URL})",
    )
    single_event_parser.add_argument(
        "--profile-dir",
        type=Path,
        default=None,
        help="cesta k vyhrazenému lokálnímu profilu prohlížeče",
    )
    single_event_parser.add_argument(
        "--timeout-seconds",
        type=_positive_seconds,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"časový limit operací v sekundách (výchozí: {DEFAULT_TIMEOUT_SECONDS:g})",
    )
    identity_parser = subparsers.add_parser(
        ID0_COMMAND,
        help="dummy-only technicky ověří allowlisted candidate atributy bez schválení identity",
        add_help=False,
    )
    identity_parser.add_argument("-h", "--help", action="store_true")
    identity_parser.add_argument("--dummy-only", action="store_true")
    identity_parser.add_argument("--url", default=DEFAULT_URL)
    identity_parser.add_argument("--profile-dir", type=Path, default=None)
    identity_parser.add_argument("--timeout-seconds", default=DEFAULT_TIMEOUT_SECONDS)
    return parser


def _id0_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument("--dummy-only", action="store_true")
    parser.add_argument("--url")
    parser.add_argument("--profile-dir")
    parser.add_argument("--timeout-seconds")
    try:
        args, unknown = parser.parse_known_args(argv)
        if unknown:
            raise ValueError
        url = DEFAULT_URL if args.url is None else _web_url(args.url)
        timeout = (
            DEFAULT_TIMEOUT_SECONDS
            if args.timeout_seconds is None
            else _positive_seconds(args.timeout_seconds)
        )
        if timeout > 300:
            raise ValueError
        profile = default_profile_dir() if args.profile_dir is None else Path(args.profile_dir)
        if len(url.encode("utf-8")) > 2048 or len(str(profile).encode("utf-8")) > 8192:
            raise ValueError
        return argparse.Namespace(
            dummy_only=args.dummy_only, url=url, timeout_seconds=timeout, profile_dir=profile
        )
    except (argparse.ArgumentError, argparse.ArgumentTypeError, TypeError, ValueError):
        raise IdentityCandidateError("ID0_INVALID_ARGUMENTS") from None


def _fixed_id0_error(code: str) -> int:
    try:
        text = f"Chyba: {code}\n"
        if not code.isascii() or len(text.encode("utf-8")) > 128:
            text = "Chyba: ID0_INTERNAL_ERROR\n"
        sys.stderr.write(text)
        sys.stderr.flush()
    except Exception:
        pass
    if code == "ID0_INTERRUPTED":
        return 130
    if code == "ID0_INVALID_ARGUMENTS":
        return 2
    return 1


def _run_identity_command(argv: Sequence[str]) -> int:
    if argv in (["--help"], ["-h"]):
        try:
            if len(ID0_HELP.splitlines()) > 64 or len(ID0_HELP.encode("utf-8")) > 32_768:
                return _fixed_id0_error("ID0_OUTPUT_LIMIT_EXCEEDED")
            sys.stdout.write(ID0_HELP)
            sys.stdout.flush()
            return 0
        except Exception:
            return 1
    try:
        args = _id0_arguments(argv)
        if not args.dummy_only:
            raise IdentityCandidateError("ID0_DUMMY_ONLY_ACK_REQUIRED")
        result = run_identity_supervisor(
            url=args.url,
            profile_dir=args.profile_dir,
            timeout_seconds=args.timeout_seconds,
            stdout=sys.stdout,
        )
        publish_identity_result(result, sys.stdout)
        return 0
    except KeyboardInterrupt:
        return _fixed_id0_error("ID0_INTERRUPTED")
    except IdentityCandidateError as error:
        if getattr(error, "terminal_write_attempted", False):
            return 1
        return _fixed_id0_error(error.code)
    except Exception:
        return _fixed_id0_error("ID0_INTERNAL_ERROR")


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


def _run_diagnose_calendar(args: argparse.Namespace) -> int:
    try:
        requested_profile = (
            args.profile_dir if args.profile_dir is not None else default_profile_dir()
        )
        diagnose_calendar(
            url=args.url,
            profile_dir=safe_profile_dir(requested_profile),
            timeout_seconds=args.timeout_seconds,
        )
    except (BrowserError, CalendarDiagnosisError, ProfilePathError) as error:
        print(f"Chyba: {error}", file=sys.stderr)
        return 1
    return 0


def _run_inspect_single_event(args: argparse.Namespace) -> int:
    try:
        requested_profile = (
            args.profile_dir if args.profile_dir is not None else default_profile_dir()
        )
        inspect_single_event(
            url=args.url,
            profile_dir=safe_profile_dir(requested_profile),
            timeout_seconds=args.timeout_seconds,
        )
    except SingleEventError as error:
        print(f"Chyba: {error}", file=sys.stderr)
        return 1
    except BrowserError:
        print("Chyba: BROWSER_ERROR", file=sys.stderr)
        return 1
    except ProfilePathError:
        print("Chyba: UNSAFE_PROFILE_DIR", file=sys.stderr)
        return 1
    except InspectionError:
        print("Chyba: EVENT_DETAIL_PROCESSING_FAILED", file=sys.stderr)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    actual_argv = list(sys.argv[1:] if argv is None else argv)
    if actual_argv and actual_argv[0] == ID0_COMMAND:
        return _run_identity_command(actual_argv[1:])
    parser = create_parser()
    args = parser.parse_args(actual_argv)
    if args.command == "inspect-one":
        return _run_inspect_one(args)
    if args.command == "diagnose-calendar":
        return _run_diagnose_calendar(args)
    if args.command == "inspect-single-event":
        return _run_inspect_single_event(args)
    parser.print_help()
    return 0
