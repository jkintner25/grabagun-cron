#!/usr/bin/env python3
import os
import sys
from datetime import datetime
from contextlib import suppress
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

URL = "https://www.grabagun.com/giveaway"

def required(name: str) -> str:
    v = os.getenv(name)
    if not v or not v.strip():
        print(f"Missing required env var: {name}", file=sys.stderr)
        sys.exit(2)
    return v.strip()

# --- Form data (override via env vars in your cloud host) ---
FIRST_NAME = required("GG_FIRST_NAME")
LAST_NAME  = required("GG_LAST_NAME")
EMAIL      = required("GG_EMAIL")
PHONE      = required("GG_PHONE")
STREET     = required("GG_STREET")
CITY       = required("GG_CITY")
STATE_LBL  = required("GG_STATE")
ZIP        = required("GG_ZIP")

# Headless by default in cron/cloud; set GG_HEADLESS=false to watch it locally.
HEADLESS = True

# Optional persistent storage dir (keep cookies to reduce popups across runs)
# Leave empty/None to use a fresh context per run (typical in cloud cron jobs).
# USER_DATA_DIR = os.getenv("GG_STORAGE_DIR")  # e.g., "/data/grabagun"

def log(msg):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)

def try_click(page, selectors, timeout=2000):
    for sel in selectors:
        try:
            loc = sel(page) if callable(sel) else page.locator(sel)
            loc.first.click(timeout=timeout)
            return True
        except PWTimeoutError:
            continue
        except Exception:
            continue
    return False

def check_checkbox_if_present(page, selectors, timeout=2000):
    for sel in selectors:
        try:
            loc = sel(page) if callable(sel) else page.locator(sel)
            loc.first.wait_for(state="attached", timeout=timeout)
            with suppress(Exception):
                if not loc.first.is_checked():
                    loc.first.check(timeout=timeout, force=True)
            return True
        except PWTimeoutError:
            continue
        except Exception:
            continue
    return False

def dismiss_popups(page):
    # first popup often appears a few seconds after load
    page.wait_for_timeout(3000)

    # Age gate checkbox
    check_checkbox_if_present(page, [
        "#age-verification-remember",
        "[name='remember_me']",
        "input[type='checkbox'][id*='age'][id*='remember']",
    ], timeout=1500)

    # Age gate "Yes" button
    try_click(page, [
        lambda p: p.get_by_role("button", name="Yes"),
        "button:has-text('Yes')",
        "button.action.primary:has-text('Yes')",
        "button.action.primary",
    ], timeout=2000)

    # Give time for the next popup to render
    page.wait_for_timeout(2500)

    # “No, thanks” close button (ltk popup)
    try_click(page, [
        "button.ltkpopup-close.ltkpopup-close-button",
        "button:has-text('No, thanks')",
        lambda p: p.get_by_role("button", name="No, thanks"),
        "button:has(span:has-text('No, thanks'))",
    ], timeout=2000)

def fill_and_submit(page):
    page.wait_for_selector("form#giveaway_form", timeout=15000)

    page.fill("#first_name", FIRST_NAME)
    page.fill("#last_name", LAST_NAME)
    page.fill("#email", EMAIL)

    with suppress(Exception):
        page.fill("#telephone", PHONE)

    page.fill("#street", STREET)
    page.fill("#city", CITY)

    with suppress(Exception):
        page.select_option("#state", label=STATE_LBL)

    page.fill("#zip_code", ZIP)

    # Agree to terms
    check_checkbox_if_present(page, [
        "#terms_and_conditions",
        "input[name='giveaway[accept_tc]']",
    ], timeout=2000)

    # Submit
    clicked = try_click(page, [
        "#send2",
        "button#send2",
        "button[type='submit'] >> text=Sign Up",
        "button.action.primary:has-text('Sign Up')",
        lambda p: p.get_by_role("button", name="Sign Up"),
        "form#giveaway_form button[type='submit']",
    ], timeout=3000)

    if not clicked:
        # Fallback: submit via JS
        page.evaluate("""() => { const f = document.querySelector('form#giveaway_form'); if (f) f.submit(); }""")

def run_once():
    with sync_playwright() as p:
        chromium = p.chromium
        args = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        context = None

        if USER_DATA_DIR:
            context = chromium.launch_persistent_context(
                USER_DATA_DIR,
                headless=HEADLESS,
                viewport={"width": 1366, "height": 900},
                args=args,
            )
        else:
            browser = chromium.launch(headless=HEADLESS, args=args)
            context = browser.new_context(viewport={"width": 1366, "height": 900})

        page = context.new_page()
        exit_code = 0

        try:
            log("Navigating to giveaway page…")
            page.goto(URL, wait_until="domcontentloaded", timeout=45000)

            dismiss_popups(page)
            fill_and_submit(page)

            page.wait_for_timeout(6000)  # allow any server-side processing/redirects
            log("Submission attempt finished.")
        except Exception as e:
            log(f"ERROR: {e!r}")
            exit_code = 2
        finally:
            with suppress(Exception):
                page.close()
            with suppress(Exception):
                context.close()

        return exit_code

if __name__ == "__main__":
    # ⚠️ Respect the site’s Official Rules/ToS. Many promotions disallow automation.
    sys.exit(run_once())


