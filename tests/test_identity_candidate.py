from io import StringIO
from unittest.mock import MagicMock

import pytest

from termino_exporter import identity_output
from termino_exporter.identity_candidate import (
    BLOCKER_CODE,
    CANDIDATE_ATTRIBUTE_ALLOWLIST,
    IdentityCandidateError,
    deserialize_final_observation,
    deserialize_final_result,
    sanitize_browser_projection,
    validate_candidate_allowlist,
)
from termino_exporter.identity_output import format_identity_result, publish_identity_result


def _candidate(name: str, *, stable: bool = True) -> dict[str, object]:
    result: dict[str, object] = {"attribute_name": name, "rejection_codes": []}
    for prefix in ("baseline", "open", "close"):
        for suffix in ("present_all", "nonempty_all", "shape_all", "unique"):
            result[f"{prefix}_{suffix}"] = stable
    result.update(
        value_set_stable_after_manual_open=stable,
        value_set_stable_after_manual_close=stable,
        order_stable_after_manual_open=stable,
        order_stable_after_manual_close=stable,
        technically_stable=stable,
    )
    if not stable:
        result["rejection_codes"] = [
            "ID0_CANDIDATE_MISSING",
            "ID0_CANDIDATE_EMPTY",
            "ID0_CANDIDATE_VALUE_SHAPE_REJECTED",
            "ID0_CANDIDATE_DUPLICATED",
            "ID0_CANDIDATE_VALUE_SET_CHANGED",
        ]
    return result


def _payloads() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    baseline = {
        "code": "ID0_BASELINE_REGISTERED",
        "stage": "BASELINE_REGISTERED",
        "event_count": 2,
        "candidate_count": 2,
        "ignored_root_attribute_count": 4,
        "candidates": [
            {
                "attribute_name": name,
                "present_all": True,
                "nonempty_all": True,
                "shape_all": True,
                "unique": True,
            }
            for name in CANDIDATE_ATTRIBUTE_ALLOWLIST
        ],
    }
    opened = {
        "code": "ID0_OPEN_CENSUS_OK",
        "stage": "OPEN_CENSUS_DONE",
        "event_count": 2,
        "same_dom_node_set": True,
        "same_dom_node_order": True,
    }
    closed = {
        "code": "ID0_CLOSE_CENSUS_OK",
        "stage": "CLOSE_CENSUS_DONE",
        "event_count": 2,
        "candidate_count": 2,
        "ignored_root_attribute_count": 4,
        "candidates": [_candidate(name) for name in CANDIDATE_ATTRIBUTE_ALLOWLIST],
        "same_dom_node_set": True,
        "same_dom_node_order": True,
    }
    return baseline, opened, closed


def test_allowlist_is_exact_source_controlled_contract() -> None:
    validate_candidate_allowlist()
    assert CANDIDATE_ATTRIBUTE_ALLOWLIST == ("data-event-id", "data-event-key")


def test_runtime_candidate_name_is_rejected_without_publication() -> None:
    private_name = "runtime-private-name"
    payload = _candidate(private_name)
    with pytest.raises(IdentityCandidateError, match="^ID0_INVALID_SANITIZED_PAYLOAD$") as caught:
        deserialize_final_observation(payload)
    assert private_name not in repr(caught.value)


def test_runtime_name_cannot_cross_baseline_projection_boundary() -> None:
    baseline, _, _ = _payloads()
    baseline["candidates"] = [
        {
            "attribute_name": "runtime-private-name",
            "present_all": True,
            "nonempty_all": True,
            "shape_all": True,
            "unique": True,
        },
        {
            "attribute_name": "data-event-key",
            "present_all": True,
            "nonempty_all": True,
            "shape_all": True,
            "unique": True,
        },
    ]
    with pytest.raises(IdentityCandidateError) as caught:
        sanitize_browser_projection(baseline, "baseline")
    assert "runtime-private-name" not in repr(caught.value)


def test_immutable_result_keeps_identity_unapproved_and_blocker_active() -> None:
    result = deserialize_final_result(*_payloads())
    assert result.technically_stable_candidate_count == 2
    assert result.identity_approved is False
    assert result.blocker_code == BLOCKER_CODE
    assert "PROVEN" not in repr(result)


def test_output_is_bounded_sanitized_and_terminal_code_is_last() -> None:
    result = deserialize_final_result(*_payloads())
    informational, terminal = format_identity_result(result)
    assert terminal == "ID0_TECHNICALLY_STABLE_CANDIDATES_FOUND_UNAPPROVED\n"
    assert "candidate_values_printed: false" in informational
    stream = StringIO()
    publish_identity_result(result, stream)
    assert stream.getvalue().endswith(terminal)


def test_output_byte_bound_fails_with_fixed_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(identity_output, "MAX_STDOUT_BYTES", 1)
    with pytest.raises(IdentityCandidateError, match="^ID0_OUTPUT_LIMIT_EXCEEDED$"):
        format_identity_result(deserialize_final_result(*_payloads()))


def test_terminal_write_failure_does_not_request_second_public_code() -> None:
    result = deserialize_final_result(*_payloads())
    stream = MagicMock()
    stream.write.side_effect = [len(format_identity_result(result)[0]), OSError("TEST OSOBA")]
    with pytest.raises(IdentityCandidateError) as caught:
        publish_identity_result(result, stream)
    assert caught.value.terminal_write_attempted is True
    assert "TEST OSOBA" not in str(caught.value)
