from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page, Route, sync_playwright


@pytest.fixture(scope="session")
def synthetic_browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def synthetic_page(synthetic_browser: Browser) -> Iterator[Page]:
    context = synthetic_browser.new_context()
    context.route("**/*", lambda route: _abort_route(route))
    page = context.new_page()
    try:
        yield page
    finally:
        try:
            page.close()
        finally:
            context.close()


def _abort_route(route: Route) -> None:
    route.abort()
