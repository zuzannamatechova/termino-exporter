from __future__ import annotations

import json

import pytest
from playwright.sync_api import ElementHandle, Page

from termino_exporter.calendar_diagnosis import (
    CALENDAR_DIAGNOSIS_SCRIPT,
    CalendarDiagnosisError,
    deserialize_calendar_snapshot,
    read_calendar_snapshot,
    resolve_calendar_snapshot,
)
from termino_exporter.handles import safe_dispose_handle
from termino_exporter.single_event import (
    SingleEventError,
    create_single_event_plan,
    find_single_event_handle,
)

pytestmark = pytest.mark.browser


def _branches(columns: int, body: str) -> str:
    return "".join(f"<div data-test='column-{index}'>{body}</div>" for index in range(columns))


def _calendar_html(
    columns: int,
    *,
    event_counts: tuple[int, ...] | None = None,
    second_grid: bool = False,
    second_event_layer: bool = False,
    nested_grid_wrappers: int = 0,
    event_style: str = "",
    mutable_event_slots: bool = False,
) -> str:
    counts = event_counts or ((1,) + (0,) * (columns - 1))
    time_layer = _branches(columns, "<span>10</span><span>11</span>")
    helper_layer = _branches(columns, "")
    grid_columns = _branches(columns, "<div role='gridcell'></div>")
    grid_layer = f"<div data-test='grid-layer'>{grid_columns}</div>"
    for depth in range(nested_grid_wrappers):
        grid_layer = f"<div data-test='grid-wrapper-{depth}'>{grid_layer}</div>"

    event_columns = []
    for column, count in enumerate(counts):
        if mutable_event_slots and column == 0:
            blocks = (
                f"<div data-test='event-a' style='{event_style}'><span>TEST UDÁLOST</span></div>"
                "<div data-test='event-b'><span></span></div>"
            )
        else:
            blocks = "".join(
                f"<div data-test='event-{column}-{index}' style='{event_style}'>"
                "<span>TEST UDÁLOST</span></div>"
                for index in range(count)
            )
        event_columns.append(f"<div data-test='events-{column}'>{blocks}</div>")
    event_layer = f"<div data-test='event-layer'>{''.join(event_columns)}</div>"
    duplicate_grid = (
        f"<div data-test='second-grid'>{_branches(columns, '<div role="gridcell"></div>')}</div>"
        if second_grid
        else ""
    )
    duplicate_events = (
        f"<div data-test='second-events'>{''.join(event_columns)}</div>"
        if second_event_layer
        else ""
    )
    return (
        "<!doctype html><html><body>"
        "<div data-test='calendar-root'>"
        f"<div data-test='time-layer'>{time_layer}</div>"
        f"<div data-test='helper-layer'>{helper_layer}</div>"
        f"{grid_layer}{duplicate_grid}{event_layer}{duplicate_events}"
        "</div>"
        "<script>window.syntheticClicks = 0; "
        "document.addEventListener('click', () => { window.syntheticClicks += 1; });</script>"
        "</body></html>"
    )


def _set_calendar(page: Page, columns: int, **options: object) -> None:
    page.set_content(_calendar_html(columns, **options))


def _click_count(page: Page) -> int:
    return page.evaluate("() => window.syntheticClicks")


def _assert_private_values_absent(payload: object) -> None:
    rendered = json.dumps(payload, ensure_ascii=False)
    assert "TEST UDÁLOST" not in rendered
    assert "data-test" not in rendered
    assert "event-layer" not in rendered


def _selected_event(page: Page) -> ElementHandle:
    snapshot = read_calendar_snapshot(page)
    plan = create_single_event_plan(snapshot)
    return find_single_event_handle(page, plan)


def test_flattened_day_resolves_one_event_without_private_payload(
    synthetic_page: Page,
) -> None:
    _set_calendar(synthetic_page, 1, nested_grid_wrappers=3)

    payload = synthetic_page.evaluate(CALENDAR_DIAGNOSIS_SCRIPT)
    snapshot = deserialize_calendar_snapshot(payload)
    diagnosis = resolve_calendar_snapshot(snapshot)

    assert diagnosis.column_count == 1
    assert diagnosis.columns[0].event_block_count == 1
    assert _click_count(synthetic_page) == 0
    _assert_private_values_absent(payload)


@pytest.mark.parametrize(("columns", "counts"), [(3, (1, 0, 2)), (7, (1, 1, 0, 0, 0, 0, 0))])
def test_multi_column_views_resolve_anonymous_counts(
    synthetic_page: Page,
    columns: int,
    counts: tuple[int, ...],
) -> None:
    _set_calendar(synthetic_page, columns, event_counts=counts)

    payload = synthetic_page.evaluate(CALENDAR_DIAGNOSIS_SCRIPT)
    diagnosis = resolve_calendar_snapshot(deserialize_calendar_snapshot(payload))

    assert diagnosis.column_count == columns
    assert tuple(column.event_block_count for column in diagnosis.columns) == counts
    assert _click_count(synthetic_page) == 0
    _assert_private_values_absent(payload)


def test_two_independent_grid_identities_are_ambiguous(synthetic_page: Page) -> None:
    _set_calendar(synthetic_page, 1, second_grid=True)

    with pytest.raises(CalendarDiagnosisError, match="^GRIDCELL_LAYER_AMBIGUOUS$"):
        resolve_calendar_snapshot(read_calendar_snapshot(synthetic_page))


def test_two_event_layers_are_ambiguous(synthetic_page: Page) -> None:
    _set_calendar(synthetic_page, 1, second_event_layer=True)

    with pytest.raises(CalendarDiagnosisError, match="^EVENT_LAYER_AMBIGUOUS$"):
        resolve_calendar_snapshot(read_calendar_snapshot(synthetic_page))


@pytest.mark.parametrize("style", ["display:none", "visibility:hidden", "visibility:collapse"])
def test_hidden_event_is_not_counted(synthetic_page: Page, style: str) -> None:
    _set_calendar(synthetic_page, 1, event_style=style)

    with pytest.raises(CalendarDiagnosisError, match="^EVENT_LAYER_EMPTY_OR_NOT_FOUND$"):
        resolve_calendar_snapshot(read_calendar_snapshot(synthetic_page))
    assert _click_count(synthetic_page) == 0


def test_handle_mode_returns_the_real_synthetic_event_without_click(synthetic_page: Page) -> None:
    _set_calendar(synthetic_page, 1)
    handle = _selected_event(synthetic_page)
    try:
        assert handle.evaluate("element => element.getAttribute('data-test')") == "event-0-0"
        assert _click_count(synthetic_page) == 0
    finally:
        safe_dispose_handle(handle)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            "document.querySelector('[data-test=event-a] span').textContent = ''",
            "SINGLE_EVENT_HANDLE_NOT_FOUND",
        ),
        (
            "document.querySelector('[data-test=event-b] span').textContent = 'TEST UDÁLOST'",
            "SINGLE_EVENT_HANDLE_AMBIGUOUS",
        ),
        (
            "document.querySelector('[data-test=event-a]').style.visibility = 'hidden'",
            "SINGLE_EVENT_HANDLE_NOT_FOUND",
        ),
        ("document.querySelector('[data-test=event-a]').remove()", "CALENDAR_STRUCTURE_CHANGED"),
    ],
)
def test_handle_mode_rejects_missing_ambiguous_or_detached_event(
    synthetic_page: Page,
    mutation: str,
    code: str,
) -> None:
    _set_calendar(synthetic_page, 1, mutable_event_slots=True)
    plan = create_single_event_plan(read_calendar_snapshot(synthetic_page))
    synthetic_page.evaluate(f"() => {{ {mutation}; }}")

    with pytest.raises(SingleEventError, match=f"^{code}$"):
        find_single_event_handle(synthetic_page, plan)
    assert _click_count(synthetic_page) == 0


def test_handle_mode_rejects_changed_fingerprint(synthetic_page: Page) -> None:
    _set_calendar(synthetic_page, 1)
    plan = create_single_event_plan(read_calendar_snapshot(synthetic_page))
    synthetic_page.evaluate(
        "() => document.querySelector('[data-test=event-layer]')"
        ".appendChild(document.createElement('div'))"
    )

    with pytest.raises(SingleEventError, match="^CALENDAR_STRUCTURE_CHANGED$"):
        find_single_event_handle(synthetic_page, plan)
    assert _click_count(synthetic_page) == 0
