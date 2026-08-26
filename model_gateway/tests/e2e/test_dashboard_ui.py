"""
Playwright E2E Web Browser Test Suite for vllm_serv Dashboard (052-fix-dashboard-ui-regressions-and-playwright-e2e).
Strict Real-Execution Browser Verification per Constitution v1.6.0.
"""

import time
import pytest
import uvicorn
import multiprocessing
from playwright.sync_api import Page, expect

SERVER_PORT = 8899
BASE_URL = f"http://127.0.0.1:{SERVER_PORT}"


def run_server():
    from src.api.server import app
    uvicorn.run(app, host="127.0.0.1", port=SERVER_PORT, log_level="warning")


@pytest.fixture(scope="module", autouse=True)
def test_server():
    proc = multiprocessing.Process(target=run_server, daemon=True)
    proc.start()
    time.sleep(1.5)  # Wait for server to bind
    yield
    proc.terminate()


def test_tab_navigation(page: Page):
    """US2/AC1: Test clicking through all 4 SPA tabs and verifying panel visibility."""
    page.goto(BASE_URL)
    page.wait_for_selector("#tab-monitoring")

    # Default tab is Live Metrics (#tab-monitoring)
    assert page.is_visible("#tab-monitoring")

    # Click Model & Config tab
    page.click('.tab-btn[data-tab="control"]')
    assert page.is_visible("#tab-control")

    # Click AI Playground tab
    page.click('.tab-btn[data-tab="playground"]')
    assert page.is_visible("#tab-playground")

    # Click Audit & API Keys tab
    page.click('.tab-btn[data-tab="audit"]')
    assert page.is_visible("#tab-audit")

    # Return to Live Metrics
    page.click('.tab-btn[data-tab="monitoring"]')
    assert page.is_visible("#tab-monitoring")


def test_admin_modal_open_and_cancel(page: Page):
    """US1/AC1: Test Admin Login button opens modal and Cancel button closes modal without error."""
    page.goto(BASE_URL)
    page.wait_for_selector("#admin-login-btn")

    # Verify modal initially hidden
    assert "hidden" in page.get_attribute("#admin-modal", "class")

    # Open modal
    page.click("#admin-login-btn")
    assert "hidden" not in page.get_attribute("#admin-modal", "class")

    # Click Cancel (modalCloseBtn)
    page.click("#modal-close-btn")
    assert "hidden" in page.get_attribute("#admin-modal", "class")


def test_admin_modal_authentication_flow(page: Page):
    """US1/AC1: Test filling secret key and authenticating."""
    page.goto(BASE_URL)

    # Open modal
    page.click("#admin-login-btn")
    page.fill("#admin-secret-input", "admin_secret_123")
    page.click("#modal-login-btn")

    # Modal should close and button text updates to 'Authenticated'
    assert "hidden" in page.get_attribute("#admin-modal", "class")
    assert "Authenticated" in page.text_content("#admin-login-btn")


def test_form_submit_reload_prevention(page: Page):
    """US1/AC2: Test submitting manual-form does NOT cause page reload or tab reset."""
    page.goto(BASE_URL)
    
    # Go to Model & Config tab
    page.click('.tab-btn[data-tab="control"]')
    assert page.is_visible("#tab-control")

    # Submit form
    page.click('#manual-form button[type="submit"]')

    # Verify we are STILL on tab-control and page did not reset to tab-monitoring
    time.sleep(0.5)
    assert page.is_visible("#tab-control")
    assert not page.is_visible("#tab-monitoring")
