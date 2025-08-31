#!/usr/bin/env python3
import os
import sys
import re
from pathlib import Path
from datetime import datetime
from contextlib import suppress
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

URL = "https://www.grabagun.com/giveaway"

# --- Form data from env (or defaults) ---
FIRST_NAME = os.getenv("GG_FIRST_NAME", "Dan")
LAST_NAME  = os.getenv("GG_LAST_NAME", "Smith")
EMAIL      = os.getenv("GG_EMAIL", "dansmith@email.com")
PHONE      = os.getenv("GG_PHONE", "505-252-5252")
STREET     = os.getenv("GG_STREET", "1234 Street St")
CITY       = os.getenv("GG_CITY", "City")
STATE_LBL  = os.getenv("GG_STATE", "Alabama")
ZIP        = os.getenv("GG_ZIP", "90210")

# Always run headless in cron
HEADLESS = True

# Optional: persistent storage to reduce popups (set GG_STORAGE_DIR in Render to enable)
USER_DATA_DIR = os.getenv("GG_STORAGE_DIR")  # e.g., "/data" (mounted volume). Leave unset for non-persistent.

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
    page.wait_for_timeout(3000)
    check_checkbox_if_present(page, [
        "#age-verification-remember",
        "[name='remember_me']",
        "input[type='checkbox'][id*='age'][id*='remember']",
    ], timeout=1500)

    try_click(page, [
        lambda p: p.get_by_role("button", name="Yes"),
        "button:has-text('Yes')",
        "button.action.primary:has-text('Yes')",
        "button.action.primary",
    ], timeout=2000)

    page.wait_for_timeout(2500)

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

    check_checkbox_if_present(page, [
        "#terms_and_conditions",
        "input[name='giveaway[accept_tc]']",
    ], timeout=2000)

    clicked = try_click(page, [
        "#send2",
        "button#send2",
        "button[type='submit'] >> text=Sign Up",
        "button.action.primary:has-text('Sign Up')",
        lambda p: p.get_by_role("button", name="Sign Up"),
        "form#giveaway_form button[type='submit']",
    ], timeout=3000)

    if not clicked:
        page.evaluate("""() => { const f = document.querySelector('form#giveaway_form'); if (f) f.submit(); }""")

def verify_submission(page, total_timeout_ms=25000):
    """
    Returns one of: 'success', 'cooldown', 'unknown'
    Success: success URL or clear thank-you text.
    Cooldown: rate-limit text (already submitted / one entry per 6 hours).
    Unknown: neither detected.
    """
    import re
    from playwright.sync_api import TimeoutError as PWTimeoutError

    # Patterns we consider success or cooldown
    THANK_PATTERNS = [
        r"\bthank\s*you\b",
        r"\b(entry\s+submitted|entry\s+received)\b",
        r"\bsuccess(?:fully)?\b",
        r"\bgood\s*luck\b",
    ]
    COOLDOWN_PATTERNS = [
        r"\balready\s+(?:entered|submitted)\b",
        r"\bone\s+entry\s+per\b",
        r"\blimit\s+one\s+entry\b",
        r"\b(6|six)\s*hour\b",
        r"\bper\s*6\s*hours\b",
        r"\btoo\s+many\s+entries\b",
    ]

    def see_any(patterns, timeout_each=2500):
        for pat in patterns:
            try:
                page.get_by_text(re.compile(pat, re.I)).wait_for(
                    state="visible", timeout=timeout_each
                )
                return True
            except PWTimeoutError:
                continue
        return False

    # 1) Prefer URL-based confirmation (redirect)
    try:
        page.wait_for_url(re.compile(r"giveaway-success-entry"), timeout=10000)
    except PWTimeoutError:
        pass
    if "giveaway-success-entry" in page.url:
        return "success"

    # 2) Watch the network for the form POST (XHR or navigation)
    #    then give the DOM a beat to update and check messages.
    try:
        resp = page.wait_for_response(
            lambda r: ("giveaway/index/submitEntry" in r.url) and (200 <= r.status < 400),
            timeout=10000,
        )
        # small grace for DOM update after response
        page.wait_for_timeout(1000)
    except PWTimeoutError:
        resp = None

    # 3) Content-based checks (success)
    if see_any(THANK_PATTERNS, timeout_each=2000):
        return "success"

    # 4) Content-based checks (cooldown / rate-limit)
    if see_any(COOLDOWN_PATTERNS, timeout_each=2000):
        return "cooldown"

    return "unknown"


def run_once():
    from contextlib import suppress
    from pathlib import Path
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        chromium = p.chromium
        args = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]

        # Choose persistent or ephemeral context
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

        try:
            log("Navigating to giveaway page…")
            page.goto(URL, wait_until="domcontentloaded", timeout=45000)

            dismiss_popups(page)
            fill_and_submit(page)

            log("Waiting for submission result…")
            status = verify_submission(page, total_timeout_ms=25000)

            if status == "success":
                log("✅ Submission confirmed (success URL or thank-you text).")
                return 0
            elif status == "cooldown":
                log("🟡 Already submitted within 6 hours — treating as success for cron.")
                return 0
            else:
                log("❌ No clear confirmation. Capturing artifacts…")
                ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                Path("/app").mkdir(parents=True, exist_ok=True)
                page.screenshot(path=f"/app/failure-{ts}.png", full_page=True)
                with open(f"/app/failure-{ts}.html", "w", encoding="utf-8") as f:
                    f.write(page.content())
                log(f"Saved /app/failure-{ts}.png and /app/failure-{ts}.html")
                return 2

        except Exception as e:
            log(f"ERROR: {e!r}")
            return 2

        finally:
            with suppress(Exception):
                page.close()
            with suppress(Exception):
                context.close()

if __name__ == "__main__":
    sys.exit(run_once())




