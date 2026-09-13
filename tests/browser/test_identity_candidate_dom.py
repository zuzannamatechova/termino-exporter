from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page

from termino_exporter.identity_candidate import (
    known_detail_state,
    new_channel_token,
    private_state_command,
    register_private_state,
)

pytestmark = pytest.mark.browser


def _identity_calendar() -> str:
    return """
    <!doctype html><html><body>
      <div>
        <div><div><span>10</span><span>11</span></div></div>
        <div><div><div role="gridcell"></div></div></div>
        <div><div id="events">
          <div data-event-key="TEST-EVENT-01" data-private-name="TEST OSOBA">
            <span>TEST UDÁLOST</span>
          </div>
          <div data-event-key="TEST-EVENT-02" data-private-name="test@example.invalid">
            <span>TEST UDÁLOST</span>
          </div>
        </div></div>
      </div>
      <script>window.syntheticClicks = 0;
        document.addEventListener("click", () => { window.syntheticClicks += 1; });
      </script>
    </body></html>
    """


def _rendered(*payloads: object) -> str:
    return json.dumps(payloads, ensure_ascii=False)


def test_three_censuses_keep_values_and_runtime_names_inside_browser(
    synthetic_page: Page,
) -> None:
    synthetic_page.set_content(_identity_calendar())
    token = new_channel_token()

    baseline = register_private_state(synthetic_page, token)
    opened = private_state_command(synthetic_page, token, "OPEN_CENSUS")
    closed = private_state_command(synthetic_page, token, "CLOSE_CENSUS")
    cleared = private_state_command(synthetic_page, token, "CLEAR")

    assert isinstance(baseline, dict) and baseline["code"] == "ID0_BASELINE_REGISTERED"
    assert isinstance(opened, dict) and opened["code"] == "ID0_OPEN_CENSUS_OK"
    assert isinstance(closed, dict) and closed["code"] == "ID0_CLOSE_CENSUS_OK"
    assert cleared == {"code": "ID0_PRIVATE_STATE_CLEARED", "cleared": True}
    rendered = _rendered(baseline, opened, closed, cleared)
    for private in (
        "TEST-EVENT-01",
        "TEST-EVENT-02",
        "data-private-name",
        "TEST OSOBA",
        "test@example.invalid",
    ):
        assert private not in rendered
    assert synthetic_page.evaluate("() => window.syntheticClicks") == 0
    lost = private_state_command(synthetic_page, token, "CLOSE_CENSUS")
    assert isinstance(lost, dict) and lost["code"] == "ID0_BROWSER_STATE_LOST"


def test_reordering_is_set_stable_but_not_order_stable(synthetic_page: Page) -> None:
    synthetic_page.set_content(_identity_calendar())
    token = new_channel_token()
    register_private_state(synthetic_page, token)
    synthetic_page.evaluate(
        "() => { const root = document.querySelector('#events'); "
        "root.insertBefore(root.children[1], root.children[0]); }"
    )
    private_state_command(synthetic_page, token, "OPEN_CENSUS")
    closed = private_state_command(synthetic_page, token, "CLOSE_CENSUS")
    assert isinstance(closed, dict)
    candidate = next(
        item for item in closed["candidates"] if item["attribute_name"] == "data-event-key"
    )
    assert candidate["value_set_stable_after_manual_open"] is True
    assert candidate["order_stable_after_manual_open"] is False
    assert candidate["technically_stable"] is True
    assert synthetic_page.evaluate("() => window.syntheticClicks") == 0


def test_changed_value_is_rejected_without_publishing_value(synthetic_page: Page) -> None:
    synthetic_page.set_content(_identity_calendar())
    token = new_channel_token()
    register_private_state(synthetic_page, token)
    synthetic_page.evaluate(
        "() => document.querySelector('#events').children[0]"
        ".setAttribute('data-event-key', 'TEST-EVENT-CHANGED')"
    )
    private_state_command(synthetic_page, token, "OPEN_CENSUS")
    closed = private_state_command(synthetic_page, token, "CLOSE_CENSUS")
    assert isinstance(closed, dict)
    candidate = next(
        item for item in closed["candidates"] if item["attribute_name"] == "data-event-key"
    )
    assert candidate["technically_stable"] is False
    assert "ID0_CANDIDATE_VALUE_SET_CHANGED" in candidate["rejection_codes"]
    assert "TEST-EVENT-CHANGED" not in _rendered(closed)


@pytest.mark.parametrize(
    ("mutation", "rejection"),
    [
        (
            "document.querySelector('#events').children[0].removeAttribute('data-event-key')",
            "ID0_CANDIDATE_MISSING",
        ),
        (
            "document.querySelector('#events').children[1].setAttribute('data-event-key', "
            "document.querySelector('#events').children[0].getAttribute('data-event-key'))",
            "ID0_CANDIDATE_DUPLICATED",
        ),
    ],
)
def test_missing_and_duplicate_candidates_are_sanitized_rejections(
    synthetic_page: Page, mutation: str, rejection: str
) -> None:
    synthetic_page.set_content(_identity_calendar())
    token = new_channel_token()
    register_private_state(synthetic_page, token)
    synthetic_page.evaluate(f"() => {mutation}")
    private_state_command(synthetic_page, token, "OPEN_CENSUS")
    closed = private_state_command(synthetic_page, token, "CLOSE_CENSUS")
    assert isinstance(closed, dict)
    candidate = next(
        item for item in closed["candidates"] if item["attribute_name"] == "data-event-key"
    )
    assert candidate["technically_stable"] is False
    assert rejection in candidate["rejection_codes"]


def test_root_attribute_limit_fails_before_private_state_registration(
    synthetic_page: Page,
) -> None:
    synthetic_page.set_content(_identity_calendar())
    synthetic_page.evaluate(
        """() => { const root = document.querySelector('#events').children[0];
          for (let index = 0; index < 33; index += 1) root.setAttribute('x-' + index, 'x'); }"""
    )
    result = register_private_state(synthetic_page, new_channel_token())
    assert isinstance(result, dict)
    assert result["code"] == "ID0_ATTRIBUTE_LIMIT_EXCEEDED"


def test_execution_context_loss_fails_closed(synthetic_page: Page) -> None:
    synthetic_page.set_content(_identity_calendar())
    token = new_channel_token()
    register_private_state(synthetic_page, token)
    synthetic_page.goto("about:blank")
    result = private_state_command(synthetic_page, token, "OPEN_CENSUS")
    assert isinstance(result, dict)
    assert result["code"] == "ID0_BROWSER_STATE_LOST"


def test_known_detail_absent_open_absent_sequence_uses_structural_resolver(
    synthetic_page: Page,
) -> None:
    synthetic_page.set_content(_identity_calendar())
    assert known_detail_state(synthetic_page) == "KNOWN_DETAIL_ABSENT"
    synthetic_page.evaluate(
        """() => {
          const detail = document.createElement("section");
          detail.id = "synthetic-detail";
          detail.innerHTML = `
            <div><button><svg></svg></button></div>
            <div style="height:40px;overflow-y:scroll">
              <div>Datum</div><div>13. 9. 2026</div>
              <div>Čas</div><div>10:00</div>
              <div style="height:120px">TEST UDÁLOST</div>
            </div>
            <div><button>Upravit</button><button>Odstranit</button>
              <button>Zkopírovat rezervaci</button></div>`;
          document.body.appendChild(detail);
        }"""
    )
    assert known_detail_state(synthetic_page) == "KNOWN_DETAIL_PRESENT"
    synthetic_page.evaluate(
        """() => {
          const duplicate = document.createElement('div'); duplicate.textContent = 'Datum';
          const content = document.querySelector('#synthetic-detail > div:nth-child(2)');
          content.appendChild(duplicate);
        }"""
    )
    assert known_detail_state(synthetic_page) == "UNKNOWN_OR_AMBIGUOUS"
    synthetic_page.evaluate("() => document.querySelector('#synthetic-detail').remove()")
    assert known_detail_state(synthetic_page) == "KNOWN_DETAIL_ABSENT"
    assert synthetic_page.evaluate("() => window.syntheticClicks") == 0
