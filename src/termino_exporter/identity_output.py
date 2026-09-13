"""Bounded terminal output for the Phase 4C-ID0 diagnostic."""

from __future__ import annotations

from typing import Protocol

from termino_exporter.identity_candidate import (
    CANDIDATE_ATTRIBUTE_ALLOWLIST,
    IdentityCandidateDiagnosticResult,
    IdentityCandidateError,
)

MAX_STDOUT_LINES = 64
MAX_STDOUT_BYTES = 32_768


class TextWriter(Protocol):
    def write(self, text: str) -> int: ...

    def flush(self) -> None: ...


def _flag(value: bool) -> str:
    return "true" if value else "false"


def format_identity_result(result: IdentityCandidateDiagnosticResult) -> tuple[str, str]:
    """Return informational block and separate last terminal line after bounds checks."""
    lines = [
        f"event_count: {result.event_count}",
        f"candidate_count: {result.candidate_count}",
        f"technically_stable_candidate_count: {result.technically_stable_candidate_count}",
        f"ignored_root_attribute_count: {result.ignored_root_attribute_count}",
    ]
    for observation in sorted(result.observations, key=lambda item: item.attribute_name):
        if observation.attribute_name not in CANDIDATE_ATTRIBUTE_ALLOWLIST:
            raise IdentityCandidateError("ID0_INVALID_SANITIZED_PAYLOAD")
        lines.append(
            "candidate: "
            + observation.attribute_name
            + " baseline_present="
            + _flag(observation.baseline_present_all)
            + " baseline_nonempty="
            + _flag(observation.baseline_nonempty_all)
            + " baseline_shape="
            + _flag(observation.baseline_shape_all)
            + " baseline_unique="
            + _flag(observation.baseline_unique)
            + " open_present="
            + _flag(observation.open_present_all)
            + " open_nonempty="
            + _flag(observation.open_nonempty_all)
            + " open_shape="
            + _flag(observation.open_shape_all)
            + " open_unique="
            + _flag(observation.open_unique)
            + " close_present="
            + _flag(observation.close_present_all)
            + " close_nonempty="
            + _flag(observation.close_nonempty_all)
            + " close_shape="
            + _flag(observation.close_shape_all)
            + " close_unique="
            + _flag(observation.close_unique)
            + " open_set_stable="
            + _flag(observation.value_set_stable_after_manual_open)
            + " close_set_stable="
            + _flag(observation.value_set_stable_after_manual_close)
            + " open_order_stable="
            + _flag(observation.order_stable_after_manual_open)
            + " close_order_stable="
            + _flag(observation.order_stable_after_manual_close)
            + " technically_stable="
            + _flag(observation.technically_stable)
            + " rejection_codes="
            + (",".join(observation.rejection_codes) or "none")
        )
    continuity = result.dom_continuity
    lines.extend(
        [
            "same_dom_node_set_after_manual_open: "
            + _flag(continuity.same_dom_node_set_after_manual_open),
            "same_dom_node_order_after_manual_open: "
            + _flag(continuity.same_dom_node_order_after_manual_open),
            "same_dom_node_set_after_manual_close: "
            + _flag(continuity.same_dom_node_set_after_manual_close),
            "same_dom_node_order_after_manual_close: "
            + _flag(continuity.same_dom_node_order_after_manual_close),
            "manual_open_acknowledged: true",
            "manual_close_acknowledged: true",
            "baseline_known_detail_absent_confirmed: true",
            "manual_open_known_detail_confirmed: true",
            "manual_close_known_detail_absent_confirmed: true",
            "identity_approved: false",
            "blocker_code: EVENT_STABLE_IDENTITY_UNKNOWN",
            "tool_click_count: 0",
            "candidate_values_printed: false",
        ]
    )
    informational = "\n".join(lines) + "\n"
    terminal = result.terminal_code + "\n"
    combined = informational + terminal
    if (
        len(combined.splitlines()) > MAX_STDOUT_LINES
        or len(combined.encode("utf-8")) > MAX_STDOUT_BYTES
    ):
        raise IdentityCandidateError("ID0_OUTPUT_LIMIT_EXCEEDED")
    return informational, terminal


def publish_identity_result(result: IdentityCandidateDiagnosticResult, stdout: TextWriter) -> None:
    """Publish terminal success last and never emit a competing code afterward."""
    informational, terminal = format_identity_result(result)
    write = stdout.write
    flush = stdout.flush
    try:
        if write(informational) != len(informational):
            raise OSError
        flush()
    except Exception as error:
        raise IdentityCandidateError("ID0_OUTPUT_FAILED") from error
    try:
        if write(terminal) != len(terminal):
            raise OSError
        flush()
    except Exception as error:
        failure = IdentityCandidateError("ID0_OUTPUT_FAILED")
        failure.terminal_write_attempted = True
        raise failure from error
