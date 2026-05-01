"""
Roblox Stonk Automation — GUI Edition
======================================

SETUP INSTRUCTIONS:
-------------------
1. Install dependencies:
   pip install pyautogui opencv-python pytesseract playwright pyperclip Pillow pynput

2. Install Playwright's Chromium:
   playwright install chromium

3. Install Tesseract OCR:
   - macOS:  brew install tesseract
   - Linux:  sudo apt install tesseract-ocr
   - Windows: run install_tesseract_windows.bat, or https://github.com/UB-Mannheim/tesseract/wiki

4. One-time Roblox login (saves session cookies):
   python3 roblox_stonk_automation.py --setup

5. Run the GUI:
   python3 roblox_stonk_automation.py

HOW TO USE:
-----------
  • Pick each click coordinate using the 📍 PICK buttons.
  • Pick your PRICE region using 📐 PICK PRICE REGION (only the number area).
  • Set your delays and hit ▶ START.
  • Ctrl+M = emergency stop anywhere.
"""

import os
import re
import sys
import time
import json
import random
import string
import shutil
import platform
import threading
import subprocess
import tkinter as tk
from typing import Callable, Optional, Tuple
from tkinter import ttk, messagebox

# ── Auto-install pynput if missing ───────────────────────────────────────────
try:
    from pynput import keyboard as pynput_kb
    from pynput import mouse as pynput_mouse_ctrl
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pynput"])
    from pynput import keyboard as pynput_kb
    from pynput import mouse as pynput_mouse_ctrl

import pyautogui
import pyperclip

try:
    import pytesseract
    from PIL import Image
    import cv2
    import numpy as np
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

try:
    import pygetwindow as gw
    HAS_PYGETWINDOW = True
except ImportError:
    HAS_PYGETWINDOW = False

from playwright.sync_api import sync_playwright

pyautogui.FAILSAFE = True
IS_MAC = platform.system() == "Darwin"

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_FILE = os.path.join(BASE_DIR, "roblox_cookies.json")
LEGACY_CONFIG_FILE = os.path.join(BASE_DIR, "stonk_config.json")
SETTINGS_FILE = os.path.join(BASE_DIR, "stonk_settings.json")
COORDS_FILE = os.path.join(BASE_DIR, "stonk_coordinates.json")
PROGRESS_FILE = os.path.join(BASE_DIR, "stonk_progress.json")
SYMBOLS_DIR = os.path.join(BASE_DIR, "symbols")
GAMEPASS_JS_FILE = os.path.join(BASE_DIR, "gamepass_creator.js")
ROTATION_FILE = os.path.join(BASE_DIR, "stonk_rotation_config.json")
ROBux_LOGO_FILE = os.path.join(BASE_DIR, "ocr_ignore_robux_logo.png")
TESSERACT_HINT_FILE = os.path.join(BASE_DIR, "stonk_tesseract_path.txt")

# Windows: set full path to tesseract.exe here if nothing else finds it. Leave "" on macOS/Linux.
TESSERACT_PATH = r""


def _resolved_tesseract_cmd() -> str:
    """
    Resolve tesseract.exe for pytesseract: inline TESSERACT_PATH, env TESSERACT_CMD,
    stonk_tesseract_path.txt (one line), common Windows install dirs, then PATH.
    """
    p0 = (TESSERACT_PATH or "").strip().strip('"')
    if p0:
        np = os.path.normpath(p0)
        if os.path.isfile(np):
            return np
    env_v = (os.environ.get("TESSERACT_CMD") or "").strip().strip('"')
    if env_v:
        ne = os.path.normpath(env_v)
        if os.path.isfile(ne):
            return ne
    try:
        if os.path.isfile(TESSERACT_HINT_FILE):
            with open(TESSERACT_HINT_FILE, encoding="utf-8", errors="ignore") as hf:
                line = (hf.readline() or "").strip().strip('"')
            if line:
                nl = os.path.normpath(line)
                if os.path.isfile(nl):
                    return nl
    except OSError:
        pass
    if platform.system() == "Windows":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pfx = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        for root in (
            os.path.join(pf, "Tesseract-OCR"),
            os.path.join(pfx, "Tesseract-OCR"),
        ):
            exe = os.path.join(root, "tesseract.exe")
            if os.path.isfile(exe):
                return exe
        local = os.environ.get("LocalAppData", "")
        if local:
            exe = os.path.join(local, "Programs", "Tesseract-OCR", "tesseract.exe")
            if os.path.isfile(exe):
                return exe
    w = shutil.which("tesseract")
    if w:
        nw = os.path.normpath(w)
        if os.path.isfile(nw):
            return nw
    return ""


TESSERACT_CMD = _resolved_tesseract_cmd()

# ── Sell step definitions ─────────────────────────────────────────────────────
SELL_STEPS = [
    {"key": "sell_btn",   "label": "① Sell Button"},
    {"key": "robux_opt",  "label": "② Robux Option"},
    {"key": "qty_btn",    "label": "③ Quantity (–1)"},
    {"key": "id_input",   "label": "④ ID Input Box"},
    {"key": "id_commit_click", "label": "⑤ Click Outside ID Box (commit)"},
    {"key": "sell_btn_2", "label": "⑥ Sell Button (again)"},
    {"key": "final_ok",   "label": "⑦ Final Confirm"},
    {"key": "final_ok_2", "label": "⑧ Final Confirm (2nd)"},
    {"key": "back_out_btn", "label": "⑨ Back Out / Close Game UI"},
    {"key": "next_page_btn", "label": "⑩ Next Page (symbols)"},
]
ALL_COORD_KEYS = [s["key"] for s in SELL_STEPS]


# ============================================================
# BROWSER / PLAYWRIGHT HELPERS
# ============================================================

def _new_browser_context(playwright):
    browser = playwright.chromium.launch(
        headless=False,
        args=["--start-maximized", "--no-first-run"],
    )
    context = browser.new_context(no_viewport=True)
    return browser, context


def save_cookies(context):
    cookies = context.cookies()
    with open(COOKIES_FILE, "w") as f:
        json.dump(cookies, f, indent=2)
    print(f"[COOKIES] Saved {len(cookies)} cookies → {COOKIES_FILE}")


def load_cookies(context):
    if not os.path.exists(COOKIES_FILE):
        raise RuntimeError(
            "No cookie file found. Run setup first:\n"
            "  python3 roblox_stonk_automation.py --setup"
        )
    with open(COOKIES_FILE) as f:
        cookies = json.load(f)
    context.add_cookies(cookies)
    print(f"[COOKIES] Loaded {len(cookies)} cookies.")


def setup():
    """One-time login flow — saves cookies to disk."""
    print("\n[SETUP] Opening browser — please log into Roblox.")
    print("[SETUP] Close the browser when done and cookies will be saved.\n")
    with sync_playwright() as p:
        browser, context = _new_browser_context(p)
        page = context.new_page()
        page.goto("https://www.roblox.com/login", wait_until="domcontentloaded")
        print("[SETUP] Waiting for login (up to 2 minutes)...")
        try:
            page.wait_for_url(lambda url: "login" not in url, timeout=120_000)
        except Exception:
            pass
        time.sleep(3)
        try:
            page.goto("https://www.roblox.com/home", wait_until="domcontentloaded", timeout=10_000)
            time.sleep(2)
        except Exception:
            pass
        save_cookies(context)
        browser.close()
    print("\n[SETUP] Done! Run normally now:\n  python3 roblox_stonk_automation.py\n")


# ============================================================
# REACT-SAFE INPUT
# ============================================================

def react_fill(page, locator, value: str):
    """
    Fill a MUI/React input without React overwriting it.
    Uses the native HTMLInputElement value setter + fires input/change events
    so React's synthetic event system picks up the value properly.
    Falls back to keyboard typing if the JS approach doesn't stick.
    """
    locator.scroll_into_view_if_needed()
    locator.click()
    time.sleep(0.2)
    locator.evaluate(
        """(el, val) => {
            const setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            setter.call(el, val);
            el.dispatchEvent(new Event('input',  { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
        value,
    )
    time.sleep(0.3)
    if locator.input_value() != value:
        print(f"    [react_fill] JS setter didn't stick — falling back to keyboard...")
        locator.click()
        page.keyboard.press("Control+a")
        page.keyboard.press("Delete")
        page.keyboard.type(value, delay=50)
        time.sleep(0.3)


# ============================================================
# GAMEPASS CREATION (browser automation)
# ============================================================

def _random_pass_name() -> str:
    return "".join(random.choices(string.ascii_uppercase, k=random.choice([3, 4])))


def create_gamepass_and_get_id(universe_id: str, price: int, log_fn=None) -> str:
    """
    Creates a Roblox gamepass at the given price and returns its ID.
    log_fn is an optional callable(str) for GUI status updates.
    """
    def log(msg):
        print(msg)
        if log_fn:
            log_fn(msg)

    if not os.path.exists(COOKIES_FILE):
        raise RuntimeError("Cookies file missing. Run setup first.")
    pass_name = _random_pass_name()
    log(f"[WEB] (PY) Creating pass '{pass_name}' @ {price} Robux...")
    return _create_gamepass_and_get_id_python(universe_id, price, pass_name, log_fn=log_fn)


def _create_gamepass_and_get_id_python(universe_id: str, price: int, pass_name: str, log_fn=None) -> str:
    def log(msg):
        print(msg)
        if log_fn:
            log_fn(msg)

    create_pass_url = (
        f"https://create.roblox.com/dashboard/creations/experiences/"
        f"{universe_id}/passes/create"
    )
    passes_list_url = (
        f"https://create.roblox.com/dashboard/creations/experiences/"
        f"{universe_id}/monetization/passes"
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-first-run"])
        context = browser.new_context()
        load_cookies(context)
        page = context.new_page()

        log("[WEB/PY] Navigating to create-pass page...")
        page.goto(create_pass_url, wait_until="domcontentloaded", timeout=40_000)
        if "login" in page.url.lower():
            browser.close()
            raise RuntimeError("Cookies expired — run --setup again.")
        time.sleep(2.5)

        name_input = page.locator("textarea#name, textarea[name='name']").first
        name_input.wait_for(timeout=20_000)
        name_input.click()
        name_input.fill(pass_name)
        time.sleep(0.4)

        create_btn = page.locator(
            "span.web-blox-css-tss-1283320-Button-textContainer:has-text('Create Pass'),"
            "button:has-text('Create Pass')"
        ).first
        create_btn.wait_for(timeout=10_000)
        create_btn.click(force=True)
        time.sleep(3.5)

        page.goto(passes_list_url, wait_until="domcontentloaded", timeout=30_000)
        time.sleep(2.5)
        # IMPORTANT: pick the exact newly-created pass by unique generated name,
        # never the first Offsale row (can point to older pass).
        exact_row = page.locator(f"tr:has-text('{pass_name}')").first
        exact_row.wait_for(timeout=20_000)
        exact_row.locator("span.text-body-medium, span[class*='text-truncate']").first.click()
        page.wait_for_load_state("domcontentloaded", timeout=25_000)
        time.sleep(2.0)

        sales_link = page.locator("a[href*='/sales']:has-text('Sales')").first
        sales_link.wait_for(timeout=15_000)
        sales_link.click()
        page.wait_for_load_state("domcontentloaded", timeout=25_000)
        time.sleep(1.5)

        toggle = page.locator("input[aria-label='Item for Sale']").first
        toggle.wait_for(timeout=15_000)
        page.evaluate("el => el.click()", toggle.element_handle())
        time.sleep(1.5)

        price_input = page.locator("input#price, input[name='price']").first
        price_input.wait_for(timeout=10_000)
        react_fill(page, price_input, str(price))
        time.sleep(0.4)
        if price_input.get_attribute("aria-invalid") == "true":
            react_fill(page, price_input, str(price))
            time.sleep(0.4)

        save_btn = page.locator(
            "span.web-blox-css-tss-1283320-Button-textContainer:has-text('Save Changes'),"
            "button:has-text('Save Changes')"
        ).first
        save_btn.wait_for(timeout=10_000)
        save_btn.click()
        page.wait_for_load_state("domcontentloaded", timeout=25_000)
        time.sleep(1.5)

        proceed_btn = page.locator(
            "span.web-blox-css-tss-1283320-Button-textContainer:has-text('Proceed'),"
            "button:has-text('Proceed')"
        ).first
        try:
            proceed_btn.wait_for(timeout=8_000)
            proceed_btn.click(force=True)
            page.wait_for_load_state("domcontentloaded", timeout=25_000)
            time.sleep(1.5)
        except Exception:
            pass

        current_url = page.url
        match = re.search(r"/passes/(\d+)", current_url)
        if not match:
            browser.close()
            raise RuntimeError(f"Gamepass ID not found in URL: {current_url}")
        gamepass_id = match.group(1)
        save_cookies(context)
        browser.close()
        log(f"[WEB/PY] ✅ Gamepass ID: {gamepass_id}")
        return gamepass_id


def load_rotation_config() -> dict:
    default_cfg = {
        "pages_per_cycle": 12,
        "cycle_wait_seconds": 3600,
        "sale_caps": [50, 50, 20],
        "offsale_universe_ids": [
            "7359114548",
            "7359114548",
            "7359114548",
        ],
    }
    if not os.path.exists(ROTATION_FILE):
        with open(ROTATION_FILE, "w") as f:
            json.dump(default_cfg, f, indent=2)
        return default_cfg
    try:
        with open(ROTATION_FILE) as f:
            data = json.load(f)
        cfg = dict(default_cfg)
        cfg.update(data if isinstance(data, dict) else {})
        ids = cfg.get("offsale_universe_ids") or []
        cfg["offsale_universe_ids"] = [str(x).strip() for x in ids if str(x).strip()]
        caps = cfg.get("sale_caps") or []
        cfg["sale_caps"] = [int(x) for x in caps if int(x) > 0]
        cfg["pages_per_cycle"] = int(cfg.get("pages_per_cycle", 12))
        cfg["cycle_wait_seconds"] = int(cfg.get("cycle_wait_seconds", 3600))
        return cfg
    except Exception:
        return default_cfg


def set_all_gamepasses_offsale(universe_id: str, log_fn=None, max_to_process: int = 180):
    def log(msg):
        print(msg)
        if log_fn:
            log_fn(msg)

    processed = 0
    list_url = (
        f"https://create.roblox.com/dashboard/creations/experiences/"
        f"{universe_id}/monetization/passes"
    )
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-first-run"])
        context = browser.new_context()
        load_cookies(context)
        page = context.new_page()

        page.goto(list_url, wait_until="domcontentloaded", timeout=45_000)
        time.sleep(2.0)

        # Roblox UI can show on-sale as a Robux icon + numeric price instead of literal "Onsale".
        onsale_selector = "tr:has(span[aria-label='Robux'])"
        while processed < max_to_process:
            rows = page.locator(onsale_selector)
            count = rows.count()
            if count == 0:
                break

            row = rows.first
            name_span = row.locator("span.text-body-medium, span[class*='text-truncate']").first
            name_span.wait_for(timeout=10_000)
            name_span.click()
            page.wait_for_load_state("domcontentloaded", timeout=25_000)
            time.sleep(1.2)

            sales_link = page.locator("a[href*='/sales']:has-text('Sales')").first
            sales_link.wait_for(timeout=15_000)
            sales_link.click()
            page.wait_for_load_state("domcontentloaded", timeout=25_000)
            time.sleep(1.0)

            toggle = page.locator("input[aria-label='Item for Sale']").first
            toggle.wait_for(timeout=15_000)
            checked = toggle.is_checked()
            if checked:
                page.evaluate("el => el.click()", toggle.element_handle())
                time.sleep(0.6)

            save_btn = page.locator(
                "span.web-blox-css-tss-1283320-Button-textContainer:has-text('Save Changes'),"
                "button:has-text('Save Changes')"
            ).first
            save_btn.wait_for(timeout=10_000)
            save_btn.click()
            page.wait_for_load_state("domcontentloaded", timeout=25_000)
            time.sleep(1.0)

            proceed_btn = page.locator(
                "span.web-blox-css-tss-1283320-Button-textContainer:has-text('Proceed'),"
                "button:has-text('Proceed')"
            ).first
            try:
                proceed_btn.wait_for(timeout=5_000)
                proceed_btn.click(force=True)
                page.wait_for_load_state("domcontentloaded", timeout=25_000)
            except Exception:
                pass

            processed += 1
            log(f"[OFFSALE] Universe {universe_id}: set offsale {processed}")
            page.goto(list_url, wait_until="domcontentloaded", timeout=45_000)
            time.sleep(1.5)

        save_cookies(context)
        browser.close()
    log(f"[OFFSALE] Universe {universe_id}: complete ({processed} processed)")


def count_onsale_gamepasses(universe_id: str) -> int:
    list_url = (
        f"https://create.roblox.com/dashboard/creations/experiences/"
        f"{universe_id}/monetization/passes"
    )
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-first-run"])
        context = browser.new_context()
        load_cookies(context)
        page = context.new_page()
        page.goto(list_url, wait_until="domcontentloaded", timeout=45_000)
        time.sleep(1.5)
        count = page.locator("tr:has(span[aria-label='Robux'])").count()
        save_cookies(context)
        browser.close()
        return count


def update_gamepass_price(gamepass_id: str, universe_id: str, new_price: int, log_fn=None):
    def log(msg):
        print(msg)
        if log_fn:
            log_fn(msg)

    sales_url = (
        f"https://create.roblox.com/dashboard/creations/experiences/"
        f"{universe_id}/monetization/passes/{gamepass_id}/sales"
    )
    list_url = (
        f"https://create.roblox.com/dashboard/creations/experiences/"
        f"{universe_id}/monetization/passes"
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-first-run"])
        context = browser.new_context()
        load_cookies(context)
        page = context.new_page()

        def goto_sales_for_target_pass():
            page.goto(list_url, wait_until="domcontentloaded", timeout=45_000)
            time.sleep(1.2)
            id_row = page.locator(f"tr:has-text('{gamepass_id}')").first
            id_row.wait_for(timeout=20_000)
            id_row.locator("span.text-body-medium, span[class*='text-truncate']").first.click()
            page.wait_for_load_state("domcontentloaded", timeout=25_000)
            time.sleep(0.8)
            sales_link = page.locator("a[href*='/sales']:has-text('Sales')").first
            sales_link.wait_for(timeout=15_000)
            sales_link.click()
            page.wait_for_load_state("domcontentloaded", timeout=25_000)
            time.sleep(0.8)

        def read_price_from_list() -> int:
            page.goto(list_url, wait_until="domcontentloaded", timeout=45_000)
            time.sleep(1.2)
            row = page.locator(f"tr:has-text('{gamepass_id}')").first
            row.wait_for(timeout=20_000)
            price_cell_text = row.locator("td").nth(3).inner_text(timeout=8_000)
            digits = re.sub(r"\D", "", price_cell_text or "")
            return int(digits) if digits else -1

        log(f"[WEB] Updating pass {gamepass_id} price -> {new_price}")
        page.goto(sales_url, wait_until="domcontentloaded", timeout=40_000)
        if "login" in page.url.lower():
            browser.close()
            raise RuntimeError("Cookies expired — run --setup again.")
        time.sleep(1.5)

        toggle = page.locator("input[aria-label='Item for Sale']").first
        try:
            toggle.wait_for(timeout=15_000)
        except Exception:
            # Fallback path: sometimes direct sales URL does not fully mount controls.
            page.goto(list_url, wait_until="domcontentloaded", timeout=45_000)
            time.sleep(1.8)
            # Open ONLY the target pass id row. Never fallback to first row.
            id_row = page.locator(f"tr:has-text('{gamepass_id}')").first
            id_row.wait_for(timeout=20_000)
            id_row.locator("span.text-body-medium, span[class*='text-truncate']").first.click()
            page.wait_for_load_state("domcontentloaded", timeout=25_000)
            time.sleep(1.0)
            sales_link = page.locator("a[href*='/sales']:has-text('Sales')").first
            sales_link.wait_for(timeout=15_000)
            sales_link.click()
            page.wait_for_load_state("domcontentloaded", timeout=25_000)
            time.sleep(1.0)
            toggle = page.locator("input[aria-label='Item for Sale']").first
            toggle.wait_for(timeout=15_000)
        if not toggle.is_checked():
            page.evaluate("el => el.click()", toggle.element_handle())
            time.sleep(0.6)

        price_input = page.locator("input#price, input[name='price']").first
        price_input.wait_for(timeout=12_000)
        target_price = int(new_price)
        react_fill(page, price_input, str(target_price))
        time.sleep(0.4)
        if price_input.get_attribute("aria-invalid") == "true":
            react_fill(page, price_input, str(target_price))
            time.sleep(0.4)

        # Blur field to trigger UI state updates.
        try:
            page.keyboard.press("Tab")
            time.sleep(0.2)
        except Exception:
            pass

        save_btn = page.locator(
            "span.web-blox-css-tss-1283320-Button-textContainer:has-text('Save Changes'),"
            "button:has-text('Save Changes')"
        ).first
        save_btn.wait_for(timeout=10_000)

        # Wait briefly for button enabled state.
        enabled = False
        for _ in range(20):
            if save_btn.is_enabled():
                enabled = True
                break
            time.sleep(0.2)

        # Always use forced nudge flow (more reliable than normal save path).
        nudge_price = target_price + 1
        react_fill(page, price_input, str(nudge_price))
        time.sleep(0.25)
        react_fill(page, price_input, str(target_price))
        time.sleep(0.35)
        try:
            page.keyboard.press("Tab")
            time.sleep(0.2)
        except Exception:
            pass

        if not save_btn.is_enabled():
            raise RuntimeError("Save Changes stayed disabled after price update attempts.")

        save_btn.click()
        page.wait_for_load_state("domcontentloaded", timeout=25_000)
        time.sleep(1.0)

        proceed_btn = page.locator(
            "span.web-blox-css-tss-1283320-Button-textContainer:has-text('Proceed'),"
            "button:has-text('Proceed')"
        ).first
        try:
            proceed_btn.wait_for(timeout=6_000)
            proceed_btn.click(force=True)
            page.wait_for_load_state("domcontentloaded", timeout=25_000)
        except Exception:
            pass

        # Verify persisted list price. If mismatch, force one extra nudge-save.
        persisted_price = read_price_from_list()
        if persisted_price != target_price:
            log(f"[WEB] Persisted price mismatch ({persisted_price} != {target_price}), forcing re-save...")
            page.goto(sales_url, wait_until="domcontentloaded", timeout=40_000)
            time.sleep(1.0)
            price_input = page.locator("input#price, input[name='price']").first
            try:
                price_input.wait_for(timeout=12_000)
            except Exception:
                # Some pages fail to mount sales controls directly; navigate through list->sales.
                goto_sales_for_target_pass()
                price_input = page.locator("input#price, input[name='price']").first
                price_input.wait_for(timeout=12_000)
            react_fill(page, price_input, str(target_price + 1))
            time.sleep(0.25)
            react_fill(page, price_input, str(target_price))
            time.sleep(0.35)
            try:
                page.keyboard.press("Tab")
            except Exception:
                pass
            save_btn = page.locator(
                "span.web-blox-css-tss-1283320-Button-textContainer:has-text('Save Changes'),"
                "button:has-text('Save Changes')"
            ).first
            save_btn.wait_for(timeout=10_000)
            if not save_btn.is_enabled():
                raise RuntimeError("Save Changes disabled during forced re-save.")
            save_btn.click()
            page.wait_for_load_state("domcontentloaded", timeout=25_000)
            time.sleep(0.8)
            persisted_price = read_price_from_list()
            if persisted_price != target_price:
                raise RuntimeError(f"Price update did not persist ({persisted_price} != {target_price}).")

        save_cookies(context)
        browser.close()


# ============================================================
# OCR — extract price from screen region
# ============================================================

def ocr_extract_price(region: tuple) -> int:
    """
    region = (left, top, width, height) in screen pixels.
    Captures that region, runs Tesseract, returns the last number found.
    """
    if not HAS_OCR:
        raise RuntimeError("OCR libraries not installed. pip install pytesseract opencv-python Pillow")
    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

    region = _normalize_region(region)
    left, top, width, height = region
    # Ignore left-side icon area (Robux logo can be OCR'd as digit 6).
    crop_left = left + int(width * 0.28)
    crop_width = max(10, width - int(width * 0.28))
    screenshot = pyautogui.screenshot(region=(crop_left, top, crop_width, height))
    rgb = np.array(screenshot)
    gray = cv2.cvtColor(rgb, cv2.COLOR_BGR2GRAY)
    # Optional template masking: if user saves a logo crop to ROBux_LOGO_FILE, mask matches.
    if os.path.exists(ROBux_LOGO_FILE):
        try:
            tpl = cv2.imread(ROBux_LOGO_FILE, cv2.IMREAD_GRAYSCALE)
            if tpl is not None:
                th, tw = tpl.shape[:2]
                if th > 2 and tw > 2 and gray.shape[0] >= th and gray.shape[1] >= tw:
                    match = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
                    ys, xs = np.where(match >= 0.70)
                    for y, x in zip(ys, xs):
                        cv2.rectangle(gray, (x, y), (x + tw, y + th), 255, -1)
        except Exception:
            pass
    up = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    blur = cv2.GaussianBlur(up, (3, 3), 0)
    th1 = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    th2 = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

    configs = [
        "--psm 7 -c tessedit_char_whitelist=0123456789,.",
        "--psm 6 -c tessedit_char_whitelist=0123456789,.",
        "--psm 11 -c tessedit_char_whitelist=0123456789,.",
    ]
    variants = [up, th1, th2]
    raw_join = []
    candidates = []
    for img in variants:
        pil_img = Image.fromarray(img)
        for cfg in configs:
            raw = pytesseract.image_to_string(pil_img, config=cfg)
            raw_join.append(raw.strip())
            nums = re.findall(r"\d[\d,\.]*", raw)
            for n in nums:
                digits = re.sub(r"\D", "", n)
                if digits:
                    conf_bias = 0
                    if "," in n or "." in n:
                        conf_bias += 80
                    conf_bias += min(40, len(digits) * 10)
                    candidates.append((int(digits), conf_bias))

    print(f"[OCR] Raw text: {' | '.join([r for r in raw_join if r])!r}")
    # Keep realistic gamepass values and prefer cleaner numeric captures.
    filtered = [(n, s) for (n, s) in candidates if 1 <= n <= 1000000]
    if not filtered:
        raise ValueError("OCR found no numeric price in PRICE REGION.")
    filtered.sort(key=lambda t: (t[1], t[0]), reverse=True)
    price = filtered[0][0]
    pyperclip.copy(str(price))
    print(f"[OCR] Price: {price} Robux")
    return price


def ocr_extract_result_value(region: tuple) -> int:
    """
    OCR for the in-game result value (the red bar number under pasted ID).
    Returns detected integer, defaults to 0 when unreadable.
    """
    if not HAS_OCR:
        return 0
    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    try:
        left, top, width, height = _normalize_region(region)
        # Ignore left side where Robux icon can appear; read numeric text area.
        crop_left = left + int(width * 0.35)
        crop_width = max(8, width - int(width * 0.35))
        screenshot = pyautogui.screenshot(region=(crop_left, top, crop_width, height))
        gray = cv2.cvtColor(np.array(screenshot), cv2.COLOR_BGR2GRAY)
        if os.path.exists(ROBux_LOGO_FILE):
            try:
                tpl = cv2.imread(ROBux_LOGO_FILE, cv2.IMREAD_GRAYSCALE)
                if tpl is not None:
                    th, tw = tpl.shape[:2]
                    if th > 2 and tw > 2 and gray.shape[0] >= th and gray.shape[1] >= tw:
                        match = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
                        ys, xs = np.where(match >= 0.70)
                        for y, x in zip(ys, xs):
                            cv2.rectangle(gray, (x, y), (x + tw, y + th), 255, -1)
            except Exception:
                pass
        up = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        th = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        raw = pytesseract.image_to_string(
            Image.fromarray(th),
            config="--psm 7 -c tessedit_char_whitelist=0123456789",
        )
        digits = re.findall(r"\d+", raw)
        if not digits:
            return 0
        return int(digits[-1])
    except Exception:
        return 0


def ocr_read_page_indicator(region: tuple) -> Tuple[Optional[int], Optional[int]]:
    """
    OCR a small UI area that shows current page vs total, e.g. "2 / 4" or "Page 2 of 4".
    Returns (current_page, total_pages) or (None, None) if unreadable.
    """
    if not HAS_OCR:
        return (None, None)
    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    try:
        left, top, width, height = _normalize_region(region)
        screenshot = pyautogui.screenshot(region=(left, top, width, height))
        gray = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)
        up = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        th = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        pil_img = Image.fromarray(th)
        raw = pytesseract.image_to_string(
            pil_img,
            config="--psm 6 -c tessedit_char_whitelist=0123456789/|OoFfPpAaEe ",
        )
        raw_n = re.sub(r"\s+", " ", (raw or "").strip())
        if not raw_n:
            return (None, None)
        # "2 / 4" — allow OCR slash as | or l
        m = re.search(r"(\d{1,3})\s*[/|lI]\s*(\d{1,3})", raw_n, re.I)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 1 <= a <= 999 and 1 <= b <= 999:
                return (a, b)
        m = re.search(r"(?:page\s*)?(\d{1,3})\s+of\s+(\d{1,3})", raw_n, re.I)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 1 <= a <= 999 and 1 <= b <= 999:
                return (a, b)
        nums = re.findall(r"\d{1,3}", raw_n)
        if len(nums) >= 2:
            a, b = int(nums[0]), int(nums[1])
            if a <= b and 1 <= a <= 999 and 1 <= b <= 999:
                return (a, b)
    except Exception:
        pass
    return (None, None)


# ============================================================
# IN-GAME MOUSE CLICKS (using pynput for cross-platform support)
# ============================================================

def _mouse_click(x: int, y: int, delay_ms: int = 150):
    x = int(round(x))
    y = int(round(y))
    d = max(0.01, float(delay_ms) / 1000.0)
    # Primary: pynput click (matches your working script).
    try:
        from pynput import mouse as _m
        mc = _m.Controller()
        mc.position = (x, y)
        time.sleep(d)
        mc.press(_m.Button.left)
        time.sleep(d)
        mc.release(_m.Button.left)
        return
    except Exception:
        pass

    # Fallback: pyautogui click backend.
    pyautogui.moveTo(x, y, duration=0)
    time.sleep(d)
    pyautogui.mouseDown()
    time.sleep(d)
    pyautogui.mouseUp()


def _paste_text(text: str):
    pyperclip.copy(text)
    pyautogui.hotkey("command" if IS_MAC else "ctrl", "v")


def _normalize_region(region: tuple):
    left, top, width, height = region
    left = int(round(left))
    top = int(round(top))
    width = int(round(width))
    height = int(round(height))
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid region size: {region}")
    return left, top, width, height


def bring_roblox_to_foreground():
    if HAS_PYGETWINDOW and hasattr(gw, "getWindowsWithTitle"):
        try:
            windows = gw.getWindowsWithTitle("Roblox")
            if windows:
                win = windows[0]
                win.restore()
                win.activate()
                time.sleep(1.5)
                return
        except Exception:
            pass
    # macOS fallback: activate Roblox via AppleScript
    if IS_MAC:
        try:
            import subprocess
            subprocess.run(
                ["osascript", "-e", 'tell application "Roblox" to activate'],
                check=False,
                capture_output=True,
                text=True,
            )
            time.sleep(1.0)
        except Exception:
            pass


def _sanitize_symbol_name(raw: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", raw.upper())


def _collect_symbols_from_page(scan_region: tuple):
    """
    OCR-read symbol names in scan region and save cropped images.
    Returns sorted list of dicts: {"name": str, "x": int, "y": int}
    """
    if not HAS_OCR:
        raise RuntimeError("OCR libs missing. Install: pytesseract opencv-python Pillow")
    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    os.makedirs(SYMBOLS_DIR, exist_ok=True)

    left, top, width, height = _normalize_region(scan_region)
    shot = pyautogui.screenshot(region=(left, top, width, height))
    bgr = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    data = pytesseract.image_to_data(
        th,
        config="--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        output_type=pytesseract.Output.DICT,
    )

    found = []
    seen = set()
    for i, txt in enumerate(data.get("text", [])):
        name = _sanitize_symbol_name(txt)
        if len(name) < 2 or len(name) > 8:
            continue
        if not re.match(r"^[A-Z0-9]+$", name):
            continue

        x = int(data["left"][i])
        y = int(data["top"][i])
        w = int(data["width"][i])
        h = int(data["height"][i])
        if w <= 2 or h <= 2:
            continue

        key = (name, x // 8, y // 8)
        if key in seen:
            continue
        seen.add(key)

        pad = 4
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(width, x + w + pad)
        y2 = min(height, y + h + pad)
        crop = bgr[y1:y2, x1:x2]
        if crop.size > 0:
            out = os.path.join(SYMBOLS_DIR, f"{name}.png")
            if not os.path.exists(out):
                cv2.imwrite(out, crop)

        found.append({
            "name": name,
            "x": left + x + (w // 2),
            "y": top + y + (h // 2),
        })

    found.sort(key=lambda a: (a["y"], a["x"]))
    return found


def detect_and_click_next_symbol(scan_region: tuple, completed: set, post_click_wait: float):
    """
    Reads all symbols from current page, saves symbol images,
    clicks first symbol not in completed set.
    Returns (clicked_symbol_name, page_symbols_names)
    """
    symbols = _collect_symbols_from_page(scan_region)
    if not symbols:
        return None, []

    page_names = []
    for s in symbols:
        if s["name"] not in page_names:
            page_names.append(s["name"])

    for s in symbols:
        if s["name"] in completed:
            continue
        _mouse_click(s["x"], s["y"], 120)
        time.sleep(max(0.05, float(post_click_wait)))
        return s["name"], page_names

    return None, page_names


# ============================================================
# FULL AUTOMATION CYCLE
# ============================================================

def run_one_cycle(coords: dict, ocr_region: tuple, scan_region: tuple, verify_region: tuple, universe_id: str,
                  post_click_wait: float, ocr_wait: float, click_delay_ms: int,
                  completed_symbols: set, log_fn=None, should_continue=None,
                  no_symbol_nav: Optional[Callable[[], str]] = None):
    """
    One full sell cycle:
      1. Click game symbol
      2. Click sell button
      3. Click robux option
      4. Click quantity button
      5. Wait + OCR price from screen
      6. Create gamepass in browser
      7. Paste ID back into game
      8. Confirm

    Returns (gamepass_id, price, symbol_name, nav_status) where nav_status is
    "ok" | "next_page" | "cycle_end". If no_symbol_nav returns "cycle_end" when
    the page has no pending symbols, next-page is not clicked.
    """
    def log(msg):
        print(msg)
        if log_fn:
            log_fn(msg)

    def ok():
        return True if should_continue is None else bool(should_continue())

    def sleep_check(seconds: float):
        end = time.time() + max(0.0, float(seconds))
        while time.time() < end:
            if not ok():
                raise RuntimeError("Stopped")
            time.sleep(0.05)

    def click(key):
        if not ok():
            raise RuntimeError("Stopped")
        x, y = coords[key]
        _mouse_click(x, y, click_delay_ms)
        sleep_check(max(0.05, float(post_click_wait)))

    bring_roblox_to_foreground()

    log("[GAME] Scanning page symbols via OCR...")
    symbol_name, page_names = detect_and_click_next_symbol(scan_region, completed_symbols, post_click_wait)
    if page_names:
        log(f"[GAME] Symbols on page: {', '.join(page_names)}")
    if not symbol_name:
        log("[GAME] All listed symbols on this page already done (or no new ones found).")
        nav = "next"
        if no_symbol_nav:
            try:
                nav = str(no_symbol_nav() or "next").lower()
            except Exception:
                nav = "next"
        if nav == "cycle_end":
            log("[GAME] End page reached — finishing cycle (no next-page click).")
            return None, None, None, "cycle_end"
        click("next_page_btn")
        return None, None, None, "next_page"
    log(f"[GAME] Clicked symbol: {symbol_name}")

    log("[GAME] Clicking Sell button...")
    click("sell_btn")
    log("[GAME] Clicking Robux option...")
    click("robux_opt")

    log("[GAME] Clicking quantity button...")
    click("qty_btn")

    log("[GAME] Waiting for price to appear...")
    sleep_check(max(0.4, ocr_wait))

    log("[OCR] Reading price from screen...")
    price = ocr_extract_price(ocr_region)
    log(f"[OCR] Price detected: {price} Robux")

    log("[WEB] Creating gamepass...")
    gamepass_id = create_gamepass_and_get_id(universe_id, price, log_fn=log_fn)

    bring_roblox_to_foreground()
    sleep_check(0.5)

    log(f"[GAME] Pasting gamepass ID: {gamepass_id}")
    click("id_input")
    sleep_check(0.3)
    _paste_text(gamepass_id)
    sleep_check(0.3)
    click("id_commit_click")
    sleep_check(3.0)

    # Fail-safe: if game still shows 0 after ID paste, fix price and retry.
    max_fix_attempts = 6
    last_retry_price = None
    for attempt in range(1, max_fix_attempts + 1):
        if not ok():
            raise RuntimeError("Stopped")
        shown_value = ocr_extract_result_value(verify_region)
        log(f"[CHECK] In-game value after paste: {shown_value}")
        if shown_value > 0:
            log("[CHECK] Value changed from 0, continuing.")
            break
        log(f"[CHECK] Value still 0 (attempt {attempt}/{max_fix_attempts}) — re-reading target price...")
        new_price = ocr_extract_price(ocr_region)
        # Heuristic for Robux-logo OCR confusion:
        # if same value repeats and starts with 6, alternate between:
        # - original OCR value (e.g. 6641)
        # - stripped-leading-6 value (e.g. 641 / 1153)
        # This handles both 4-digit->3-digit and 5-digit->4-digit cases.
        s = str(new_price)
        if s.startswith("6") and len(s) >= 4:
            stripped = int(s[1:])
            # Try stripped value earlier so first correction cycle can fix icon-leading 6.
            if attempt == 1:
                log(f"[CHECK] Suspected icon-leading-6 OCR ({new_price}); trying stripped price {stripped} first")
                new_price = stripped
            elif last_retry_price is not None and new_price == last_retry_price:
                if attempt % 2 == 0:
                    log(f"[CHECK] Repeated OCR value {new_price}; trying stripped-leading-6 price {stripped}")
                    new_price = stripped
                else:
                    log(f"[CHECK] Repeated OCR value {new_price}; keeping original this attempt, stripped candidate={stripped}")
        last_retry_price = new_price
        log(f"[CHECK] Updating pass {gamepass_id} to {new_price} Robux and waiting propagation...")
        update_gamepass_price(gamepass_id, universe_id, new_price, log_fn=log_fn)
        bring_roblox_to_foreground()
        # Roblox propagation can be slow.
        wait_secs = 10
        log(f"[CHECK] Waiting {wait_secs}s for Roblox sync...")
        sleep_check(wait_secs)
        click("id_input")
        sleep_check(0.2)
        _paste_text(gamepass_id)
        sleep_check(0.3)
        click("id_commit_click")
        sleep_check(3.0)
    else:
        raise RuntimeError("Gamepass value stayed 0 after retries; skipping this symbol for safety.")

    log("[GAME] Clicking Sell button again...")
    click("sell_btn_2")

    log("[GAME] Clicking final confirm...")
    click("final_ok")
    sleep_check(max(0.2, float(post_click_wait)))

    log("[GAME] Clicking final confirm again...")
    click("final_ok_2")
    sleep_check(1)

    log("[GAME] Clicking Back Out...")
    click("back_out_btn")
    sleep_check(0.5)

    log(f"✅ Cycle done! {symbol_name} -> Pass {gamepass_id} @ {price} Robux")
    return gamepass_id, price, symbol_name, "ok"


# ============================================================
# GUI
# ============================================================

class StonkAutomationApp:

    # ── Colours / fonts (dark theme matching reference) ───────────────────────
    BG      = "#0f0f13"
    CARD    = "#1a1a24"
    ACCENT  = "#00e5ff"
    ACCENT2 = "#ff3c6e"
    TXT     = "#e8e8f0"
    MUTED   = "#555570"
    BTN_BG  = "#252535"
    FONT    = ("Consolas", 10)
    FONT_SM = ("Consolas", 9)
    FONT_LG = ("Consolas", 12, "bold")

    def __init__(self, root):
        self.root = root
        self.root.title("Stonk Automation")
        self.root.geometry("760x920")
        self.root.minsize(700, 760)
        self.root.resizable(True, True)
        self.root.configure(bg=self.BG)

        # State
        self.coords      = {k: None for k in ALL_COORD_KEYS}
        self.ocr_region  = None          # (left, top, width, height)
        self.verify_region = None        # (left, top, width, height) value-under-ID region
        self.scan_region = None          # (left, top, width, height) symbol search area
        self.running     = False
        self.picking     = False
        self.pick_key    = None
        self.pick_overlay   = None
        self._ctrl_held     = False
        self._region_step   = 0          # 0=idle 1=waiting TL 2=waiting BR
        self._region_tl     = None       # (x, y) top-left corner
        self._scan_step      = 0
        self._scan_tl        = None
        self._verify_step    = 0
        self._verify_tl      = None
        self._page_ind_step  = 0
        self._page_ind_tl    = None
        self._mouse_listener = None
        self.completed_symbols = set()
        self.current_page = 1
        self.page_indicator_region = None  # optional OCR "2 / 4" area
        self.rotation_cfg = load_rotation_config()
        self.sale_universe_idx = 0
        self._last_hotkey_ts = {"toggle": 0.0, "stop": 0.0}
        self._hotkey_cooldown_s = 0.45

        self.load_config()
        self.build_ui()
        self._setup_hotkeys()

    # ── Config ────────────────────────────────────────────────────────────────

    def load_config(self):
        settings_data = {}
        coords_data = {}
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE) as f:
                    settings_data = json.load(f)
            if os.path.exists(COORDS_FILE):
                with open(COORDS_FILE) as f:
                    coords_data = json.load(f)
            elif os.path.exists(LEGACY_CONFIG_FILE):
                with open(LEGACY_CONFIG_FILE) as f:
                    legacy = json.load(f)
                settings_data = legacy
                coords_data = legacy

            self.coords.update({
                k: tuple(v) if v else None
                for k, v in coords_data.get("coords", {}).items()
            })
            ocr = coords_data.get("ocr_region")
            self.ocr_region = tuple(ocr) if ocr else None
            vr = coords_data.get("verify_region")
            self.verify_region = tuple(vr) if vr else None
            scan = coords_data.get("scan_region")
            self.scan_region = tuple(scan) if scan else None
            pi = coords_data.get("page_indicator_region")
            self.page_indicator_region = tuple(pi) if pi else None
            self._cfg = settings_data
        except Exception:
            pass
        self._load_progress()

    def save_config(self, quiet: bool = False):
        with open(SETTINGS_FILE, "w") as f:
            json.dump({
                "universe_id": self.universe_var.get(),
                "post_click_wait": self.post_click_wait_var.get(),
                "proc_delay":  self.proc_delay_var.get(),
                "click_ms":    self.click_ms_var.get(),
                "loops":       self.loops_var.get(),
                "start_delay": self.start_delay_var.get(),
                "page_start":  int(self.page_start_var.get()),
                "page_end":    int(self.page_end_var.get()),
            }, f, indent=2)
        with open(COORDS_FILE, "w") as f:
            json.dump({
                "coords":      {k: list(v) if v else None for k, v in self.coords.items()},
                "ocr_region":  list(self.ocr_region) if self.ocr_region else None,
                "verify_region": list(self.verify_region) if self.verify_region else None,
                "scan_region": list(self.scan_region) if self.scan_region else None,
                "page_indicator_region": list(self.page_indicator_region) if self.page_indicator_region else None,
            }, f, indent=2)
        if not quiet and hasattr(self, "status_var"):
            self.status_var.set("💾 Config saved.")

    def _auto_save_config(self):
        try:
            self.save_config(quiet=True)
        except Exception:
            pass

    def _load_progress(self):
        if not os.path.exists(PROGRESS_FILE):
            return
        try:
            with open(PROGRESS_FILE) as f:
                data = json.load(f)
            self.completed_symbols = set(data.get("completed_symbols", []))
            self.current_page = int(data.get("current_page", 1))
        except Exception:
            self.completed_symbols = set()
            self.current_page = 1

    def _save_progress(self):
        with open(PROGRESS_FILE, "w") as f:
            json.dump({
                "completed_symbols": sorted(self.completed_symbols),
                "current_page": self.current_page,
            }, f, indent=2)

    def reset_symbols_progress(self):
        self.completed_symbols = set()
        ps, _ = self._effective_page_bounds()
        self.current_page = ps
        self._save_progress()
        self.status_var.set(f"🧹 Symbol progress reset (page counter → start page {ps}).")

    def reset_all_gamepasses_offsale(self):
        if self.running:
            messagebox.showwarning("Stonk Bot", "Stop the script before running offsale reset.")
            return
        if not messagebox.askyesno("Reset All Offsale", "Make all configured gamepasses Offsale now?"):
            return

        def worker():
            ids = self.rotation_cfg.get("offsale_universe_ids", [])
            for uid in ids:
                try:
                    self.root.after(0, lambda u=uid: self.status_var.set(f"♻ Resetting Offsale for {u}..."))
                    set_all_gamepasses_offsale(uid, log_fn=lambda m: self.root.after(0, lambda x=m: self.status_var.set(x)))
                except Exception as e:
                    self.root.after(0, lambda err=e: messagebox.showerror("Offsale Reset Error", str(err)))
                    return
            self.root.after(0, lambda: self.status_var.set("♻ Offsale reset complete for all configured games."))

        threading.Thread(target=worker, daemon=True).start()

    def _handle_cycle_completion(self, ui_log):
        wait_seconds = max(0, int(self.rotation_cfg.get("cycle_wait_seconds", 3600)))
        universe_ids = self.rotation_cfg.get("offsale_universe_ids", [])
        ps, pe = self._effective_page_bounds()

        ui_log(f"[CYCLE] Finished page range (end page {pe}, start was {ps}). Resetting offsale stock...")
        for uid in universe_ids:
            if not self.running:
                return
            try:
                set_all_gamepasses_offsale(uid, log_fn=ui_log)
            except Exception as e:
                ui_log(f"[CYCLE] Offsale reset failed for {uid}: {e}")

        self.completed_symbols = set()
        self.current_page = ps
        self.sale_universe_idx = 0
        self._save_progress()

        if wait_seconds > 0 and self.running:
            ui_log(f"[CYCLE] Waiting {wait_seconds}s before next cycle (anti-AFK every 15 min on outside-ID click if set)…")
            self._interruptible_sleep_cycle_wait(wait_seconds, ui_log)

    def _sale_plan(self):
        ids = [str(x).strip() for x in self.rotation_cfg.get("offsale_universe_ids", []) if str(x).strip()]
        if not ids:
            uid = self.universe_var.get().strip()
            return [(uid, 50)] if uid else []

        caps = self.rotation_cfg.get("sale_caps", [50, 50, 20])
        caps = [int(x) for x in caps if int(x) > 0]
        if not caps:
            caps = [50, 50, 20]
        while len(caps) < len(ids):
            caps.append(caps[-1] if caps else 50)
        return list(zip(ids, caps[:len(ids)]))

    def _select_universe_for_sale(self, ui_log):
        plan = self._sale_plan()
        if not plan:
            raise RuntimeError("No universe IDs configured for sale.")

        def check_once():
            checked = 0
            while checked < len(plan):
                idx = self.sale_universe_idx % len(plan)
                uid, cap = plan[idx]
                onsale_count = count_onsale_gamepasses(uid)
                if onsale_count < cap:
                    self.sale_universe_idx = idx
                    ui_log(f"[POOL] Using universe {uid} ({onsale_count}/{cap} on sale)")
                    return uid
                ui_log(f"[POOL] Universe {uid} is full ({onsale_count}/{cap}), switching...")
                self.sale_universe_idx = idx + 1
                checked += 1
            return None

        selected = check_once()
        if selected:
            return selected

        ui_log("[POOL] All universes are full. Running offsale reset + cooldown cycle...")
        self._handle_cycle_completion(ui_log)
        if not self.running:
            return None
        self.sale_universe_idx = 0
        selected = check_once()
        if not selected:
            raise RuntimeError("All universes still full after reset/wait cycle.")
        return selected

    def _effective_page_bounds(self):
        ps = max(1, int(self.page_start_var.get()))
        pe = max(ps, int(self.page_end_var.get()))
        return ps, pe

    def _no_symbol_nav(self) -> str:
        _, pe = self._effective_page_bounds()
        if self.current_page >= pe:
            return "cycle_end"
        return "next"

    def _read_page_indicator_tuple(self) -> Tuple[Optional[int], Optional[int]]:
        if not self.page_indicator_region:
            return (None, None)
        try:
            return ocr_read_page_indicator(self.page_indicator_region)
        except Exception:
            return (None, None)

    def _sync_current_page_from_indicator(self, ui_log=None):
        cur, _tot = self._read_page_indicator_tuple()
        if cur is not None:
            self.current_page = cur
            if ui_log:
                ui_log(f"[PAGE] OCR page indicator → page {self.current_page}")

    def _ensure_page_start(self, ui_log):
        ps, pe = self._effective_page_bounds()
        if self.current_page > pe:
            ui_log(f"[PAGE] Saved page {self.current_page} > end {pe}; clamping to start {ps}.")
            self.current_page = ps
            self._save_progress()
            return
        if ps <= 1:
            self._sync_current_page_from_indicator(ui_log)
            return
        post_w = max(0.05, float(self.post_click_wait_var.get()))
        click_ms = int(self.click_ms_var.get())
        for _ in range(48):
            if not self.running:
                return
            self._sync_current_page_from_indicator(None)
            if self.current_page >= ps:
                ui_log(f"[PAGE] At start page ≥ {ps} (current {self.current_page}).")
                return
            cur, _ = self._read_page_indicator_tuple()
            if cur is not None and cur >= ps:
                self.current_page = cur
                self._save_progress()
                ui_log(f"[PAGE] OCR shows page {cur} — start range satisfied.")
                return
            ui_log(f"[PAGE] Advancing toward start page {ps} (from {self.current_page})…")
            x, y = self.coords["next_page_btn"]
            _mouse_click(x, y, click_ms)
            time.sleep(post_w)
            self.current_page += 1
            self._sync_current_page_from_indicator(ui_log)
            self._save_progress()
        ui_log("[PAGE] Could not reach start page in 48 next-clicks; continuing anyway.")

    def _interruptible_sleep_cycle_wait(self, seconds: int, ui_log):
        """Long post-cycle wait with periodic anti-AFK click (same spot as ID commit)."""
        end = time.time() + max(0, int(seconds))
        next_afk = time.time() + 900.0  # 15 minutes
        click_ms = int(self.click_ms_var.get())
        commit = self.coords.get("id_commit_click")
        while self.running and time.time() < end:
            if time.time() >= next_afk and commit:
                try:
                    bring_roblox_to_foreground()
                    time.sleep(0.35)
                    _mouse_click(int(commit[0]), int(commit[1]), click_ms)
                    ui_log("[CYCLE] Anti-AFK: clicked outside ID box (15 min).")
                except Exception as ex:
                    ui_log(f"[CYCLE] Anti-AFK click failed: {ex}")
                next_afk = time.time() + 900.0
            time.sleep(0.05)

    # ── UI ────────────────────────────────────────────────────────────────────

    def build_ui(self):
        BG, CARD, ACCENT, ACCENT2 = self.BG, self.CARD, self.ACCENT, self.ACCENT2
        TXT, MUTED, BTN_BG        = self.TXT, self.MUTED, self.BTN_BG
        FONT, FONT_SM             = self.FONT, self.FONT_SM

        ttk.Style().theme_use("clam")

        # Scrollable main container (so lower options are reachable on small windows)
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        main = tk.Frame(canvas, bg=BG)
        canvas_window = canvas.create_window((0, 0), window=main, anchor="nw")

        def _on_main_configure(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        main.bind("<Configure>", _on_main_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(main, bg=BG, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="STONK AUTOMATION", font=("Consolas", 18, "bold"),
                 fg=ACCENT, bg=BG).pack()
        tk.Label(hdr, text="roblox gamepass sell bot", font=FONT_SM,
                 fg=MUTED, bg=BG).pack()
        tk.Frame(main, bg=ACCENT, height=1).pack(fill="x")

        # ── Universe ID ───────────────────────────────────────────────────────
        uid_frame = tk.Frame(main, bg=CARD, padx=18, pady=8)
        uid_frame.pack(fill="x")
        tk.Label(uid_frame, text="UNIVERSE ID:", font=FONT_SM, fg=MUTED, bg=CARD).pack(side="left", padx=(0, 10))
        cfg_uid = getattr(self, "_cfg", {}).get("universe_id", "7359114548")
        self.universe_var = tk.StringVar(value=cfg_uid)
        tk.Entry(uid_frame, textvariable=self.universe_var,
                 font=FONT, bg=BTN_BG, fg=ACCENT,
                 insertbackground=ACCENT, relief="flat", width=20).pack(side="left")

        # ── OCR Region picker ─────────────────────────────────────────────────
        tk.Frame(main, bg=MUTED, height=1).pack(fill="x", pady=(6, 0))
        ocr_outer = tk.Frame(main, bg=BG, padx=18, pady=10)
        ocr_outer.pack(fill="x")

        tk.Label(ocr_outer, text="PRICE REGION", font=FONT_SM,
                 fg=MUTED, bg=BG).pack(anchor="w", pady=(0, 6))

        ocr_row = tk.Frame(ocr_outer, bg=CARD, padx=12, pady=8)
        ocr_row.pack(fill="x")

        self.ocr_region_var = tk.StringVar(value=self._region_str())
        tk.Label(ocr_row, textvariable=self.ocr_region_var,
                 font=FONT_SM, fg=ACCENT, bg=CARD, width=32, anchor="w").pack(side="left", padx=(0, 10))

        tk.Button(ocr_row, text="📐 PICK PRICE REGION",
                  font=FONT_SM, bg=BTN_BG, fg=ACCENT,
                  activebackground=ACCENT, activeforeground=BG,
                  relief="flat", padx=10, pady=3, cursor="hand2",
                  command=self.start_region_pick).pack(side="left", padx=(0, 6))

        tk.Button(ocr_row, text="✕", font=FONT_SM, bg=BTN_BG, fg=ACCENT2,
                  activebackground=ACCENT2, activeforeground=BG,
                  relief="flat", padx=8, pady=3, cursor="hand2",
                  command=self.clear_region).pack(side="left")

        tk.Label(ocr_outer,
                 text="Pick ONLY where the price number appears (exclude labels/other words).",
                 font=FONT_SM, fg=MUTED, bg=BG, wraplength=480, justify="left").pack(anchor="w", pady=(4, 0))

        tk.Frame(main, bg=MUTED, height=1).pack(fill="x", pady=(6, 0))
        verify_outer = tk.Frame(main, bg=BG, padx=18, pady=10)
        verify_outer.pack(fill="x")
        tk.Label(verify_outer, text="RESULT VALUE REGION (RED BAR)", font=FONT_SM, fg=MUTED, bg=BG).pack(anchor="w", pady=(0, 6))
        verify_row = tk.Frame(verify_outer, bg=CARD, padx=12, pady=8)
        verify_row.pack(fill="x")
        self.verify_region_var = tk.StringVar(value=self._verify_str())
        tk.Label(verify_row, textvariable=self.verify_region_var, font=FONT_SM, fg=ACCENT, bg=CARD,
                 width=32, anchor="w").pack(side="left", padx=(0, 10))
        tk.Button(verify_row, text="🎯 PICK RESULT REGION", font=FONT_SM, bg=BTN_BG, fg=ACCENT,
                  activebackground=ACCENT, activeforeground=BG, relief="flat", padx=10, pady=3,
                  cursor="hand2", command=self.start_verify_pick).pack(side="left", padx=(0, 6))
        tk.Button(verify_row, text="✕", font=FONT_SM, bg=BTN_BG, fg=ACCENT2,
                  activebackground=ACCENT2, activeforeground=BG, relief="flat", padx=8, pady=3,
                  cursor="hand2", command=self.clear_verify_region).pack(side="left")
        tk.Label(verify_outer,
                 text="Pick the small number area below ID input (where it turns red 0 on mismatch).",
                 font=FONT_SM, fg=MUTED, bg=BG, wraplength=480, justify="left").pack(anchor="w", pady=(4, 0))

        tk.Frame(main, bg=MUTED, height=1).pack(fill="x", pady=(6, 0))
        scan_outer = tk.Frame(main, bg=BG, padx=18, pady=10)
        scan_outer.pack(fill="x")
        tk.Label(scan_outer, text="SYMBOL SCAN WINDOW", font=FONT_SM, fg=MUTED, bg=BG).pack(anchor="w", pady=(0, 6))
        scan_row = tk.Frame(scan_outer, bg=CARD, padx=12, pady=8)
        scan_row.pack(fill="x")
        self.scan_region_var = tk.StringVar(value=self._scan_str())
        tk.Label(scan_row, textvariable=self.scan_region_var, font=FONT_SM, fg=ACCENT, bg=CARD,
                 width=32, anchor="w").pack(side="left", padx=(0, 10))
        tk.Button(scan_row, text="🖼 PICK WINDOW", font=FONT_SM, bg=BTN_BG, fg=ACCENT,
                  activebackground=ACCENT, activeforeground=BG, relief="flat", padx=10, pady=3,
                  cursor="hand2", command=self.start_scan_pick).pack(side="left", padx=(0, 6))
        tk.Button(scan_row, text="✕", font=FONT_SM, bg=BTN_BG, fg=ACCENT2,
                  activebackground=ACCENT2, activeforeground=BG, relief="flat", padx=8, pady=3,
                  cursor="hand2", command=self.clear_scan_region).pack(side="left")
        tk.Label(scan_outer,
                 text="Click top-left and bottom-right of the visible symbols area. Script will click symbols from images in symbols/.",
                 font=FONT_SM, fg=MUTED, bg=BG, wraplength=480, justify="left").pack(anchor="w", pady=(4, 0))

        tk.Frame(main, bg=MUTED, height=1).pack(fill="x", pady=(6, 0))
        page_outer = tk.Frame(main, bg=BG, padx=18, pady=10)
        page_outer.pack(fill="x")
        tk.Label(page_outer, text="PAGE RANGE & NEXT-PAGE INDICATOR (optional)", font=FONT_SM,
                 fg=MUTED, bg=BG).pack(anchor="w", pady=(0, 6))
        cfg_pages = getattr(self, "_cfg", {})
        _ppc_default = max(1, int(self.rotation_cfg.get("pages_per_cycle", 12)))
        self.page_start_var = tk.IntVar(value=int(cfg_pages.get("page_start", 1)))
        self.page_end_var = tk.IntVar(value=int(cfg_pages.get("page_end", _ppc_default)))
        page_row = tk.Frame(page_outer, bg=CARD, padx=12, pady=8)
        page_row.pack(fill="x")

        def _labeled_page_spin(parent, label, var, lo, hi):
            f = tk.Frame(parent, bg=CARD, padx=8, pady=4)
            f.pack(side="left", padx=(0, 10))
            tk.Label(f, text=label, font=FONT_SM, fg=MUTED, bg=CARD).pack(anchor="w")
            tk.Spinbox(f, textvariable=var, from_=lo, to=hi, increment=1, width=5, font=FONT,
                       bg=BTN_BG, fg=ACCENT, buttonbackground=BTN_BG, relief="flat",
                       insertbackground=ACCENT).pack()

        _labeled_page_spin(page_row, "Start page (1 = first)", self.page_start_var, 1, 99)
        _labeled_page_spin(page_row, "End page (inclusive)", self.page_end_var, 1, 99)

        ind_row = tk.Frame(page_outer, bg=CARD, padx=12, pady=8)
        ind_row.pack(fill="x", pady=(6, 0))
        self.page_indicator_region_var = tk.StringVar(value=self._page_ind_str())
        tk.Label(ind_row, textvariable=self.page_indicator_region_var,
                 font=FONT_SM, fg=ACCENT, bg=CARD, width=32, anchor="w").pack(side="left", padx=(0, 10))
        tk.Button(ind_row, text="📄 PICK PAGE TEXT REGION", font=FONT_SM, bg=BTN_BG, fg=ACCENT,
                  activebackground=ACCENT, activeforeground=BG, relief="flat", padx=10, pady=3,
                  cursor="hand2", command=self.start_page_indicator_pick).pack(side="left", padx=(0, 6))
        tk.Button(ind_row, text="✕", font=FONT_SM, bg=BTN_BG, fg=ACCENT2,
                  activebackground=ACCENT2, activeforeground=BG, relief="flat", padx=8, pady=3,
                  cursor="hand2", command=self.clear_page_indicator_region).pack(side="left")
        tk.Label(page_outer,
                 text="Calibrate the small “2 / 4” (current / total) text under next-page if shown. "
                      "Leave unset to track pages by next-clicks only. End page stops the cycle without clicking next again.",
                 font=FONT_SM, fg=MUTED, bg=BG, wraplength=520, justify="left").pack(anchor="w", pady=(4, 0))

        # ── Sell steps ────────────────────────────────────────────────────────
        tk.Frame(main, bg=MUTED, height=1).pack(fill="x", pady=(6, 0))
        steps_outer = tk.Frame(main, bg=BG, padx=18, pady=10)
        steps_outer.pack(fill="x")
        tk.Label(steps_outer, text="CLICK SEQUENCE", font=FONT_SM,
                 fg=MUTED, bg=BG).pack(anchor="w", pady=(0, 6))

        self.step_widgets = {}
        for step in SELL_STEPS:
            row = tk.Frame(steps_outer, bg=CARD, pady=7, padx=10)
            row.pack(fill="x", pady=3)
            row.columnconfigure(1, weight=1)

            tk.Label(row, text=step["label"], font=FONT,
                     fg=TXT, bg=CARD, width=22, anchor="w").grid(row=0, column=0, sticky="w")

            coord_var = tk.StringVar(value=self._coord_str(step["key"]))
            tk.Label(row, textvariable=coord_var, font=FONT_SM,
                     fg=ACCENT, bg=CARD, width=16, anchor="w").grid(row=0, column=1, padx=8)

            tk.Button(row, text="📍 PICK", font=FONT_SM,
                      bg=BTN_BG, fg=ACCENT,
                      activebackground=ACCENT, activeforeground=BG,
                      relief="flat", padx=10, pady=3, cursor="hand2",
                      command=lambda k=step["key"]: self.start_pick(k)).grid(row=0, column=2)

            tk.Button(row, text="✕", font=FONT_SM,
                      bg=BTN_BG, fg=ACCENT2,
                      activebackground=ACCENT2, activeforeground=BG,
                      relief="flat", padx=8, pady=3, cursor="hand2",
                      command=lambda k=step["key"], v=coord_var: self.clear_coord(k, v)).grid(row=0, column=3, padx=(4, 0))

            self.step_widgets[step["key"]] = coord_var

        # ── Timing ────────────────────────────────────────────────────────────
        tk.Frame(main, bg=MUTED, height=1).pack(fill="x", pady=(6, 0))
        timing_outer = tk.Frame(main, bg=BG, padx=18, pady=10)
        timing_outer.pack(fill="x")
        tk.Label(timing_outer, text="TIMING", font=FONT_SM, fg=MUTED, bg=BG).pack(anchor="w", pady=(0, 6))

        timing_row = tk.Frame(timing_outer, bg=BG)
        timing_row.pack(fill="x")

        cfg = getattr(self, "_cfg", {})

        def labeled_spin(parent, label, var, from_, to, inc):
            f = tk.Frame(parent, bg=CARD, padx=10, pady=7)
            f.pack(side="left", padx=(0, 8))
            tk.Label(f, text=label, font=FONT_SM, fg=MUTED, bg=CARD).pack(anchor="w")
            tk.Spinbox(f, textvariable=var, from_=from_, to=to, increment=inc,
                       width=7, font=FONT, bg=BTN_BG, fg=ACCENT,
                       buttonbackground=BTN_BG, relief="flat",
                       insertbackground=ACCENT).pack()

        self.post_click_wait_var = tk.DoubleVar(value=cfg.get("post_click_wait", cfg.get("delay", 0.9)))
        self.proc_delay_var = tk.DoubleVar(value=cfg.get("proc_delay", 3.0))
        self.loops_var     = tk.IntVar(value=cfg.get("loops",         0))
        self.start_delay_var = tk.IntVar(value=int(cfg.get("start_delay", 3)))

        labeled_spin(timing_row, "Wait after each click (s)", self.post_click_wait_var, 0.1, 10.0, 0.1)
        labeled_spin(timing_row, "OCR wait (s)",       self.proc_delay_var, 0.5, 30.0, 0.5)
        labeled_spin(timing_row, "Loops (0 = ∞)",      self.loops_var,      0,   9999, 1)
        labeled_spin(timing_row, "Start delay (s)",    self.start_delay_var, 0,   20,   1)

        slider_frame = tk.Frame(timing_outer, bg=CARD, padx=10, pady=8)
        slider_frame.pack(fill="x", pady=(8, 0))
        tk.Label(slider_frame, text="Mouse click speed (ms)", font=FONT_SM,
                 fg=MUTED, bg=CARD).pack(side="left", padx=(0, 10))
        self.click_ms_var = tk.IntVar(value=cfg.get("click_ms", 150))
        tk.Scale(slider_frame, from_=50, to=1000, orient="horizontal",
                 variable=self.click_ms_var, bg=CARD, fg=TXT, troughcolor=BTN_BG,
                 highlightthickness=0, font=FONT_SM, activebackground=ACCENT,
                 sliderrelief="flat", length=240, resolution=10).pack(side="left")
        tk.Label(slider_frame, textvariable=self.click_ms_var,
                 font=FONT_SM, fg=ACCENT, bg=CARD, width=5).pack(side="left")
        tk.Label(slider_frame, text="ms", font=FONT_SM, fg=MUTED, bg=CARD).pack(side="left")

        # ── Status bar ────────────────────────────────────────────────────────
        self.status_var = tk.StringVar(value="Ready — set coordinates and region, then press START")
        self.loop_var   = tk.StringVar(value="Loops: 0")
        status_bar = tk.Frame(main, bg=CARD, padx=18, pady=8)
        status_bar.pack(fill="x")
        tk.Label(status_bar, textvariable=self.loop_var,   font=FONT_SM, fg=MUTED,  bg=CARD).pack(side="right")
        tk.Label(status_bar, textvariable=self.status_var, font=FONT_SM, fg=ACCENT, bg=CARD).pack(side="left")

        # ── Controls ──────────────────────────────────────────────────────────
        ctrl = tk.Frame(main, bg=BG, padx=18, pady=14)
        ctrl.pack(fill="x")

        self.start_btn = tk.Button(
            ctrl, text="▶  START",
            font=self.FONT_LG, bg=ACCENT, fg=BG,
            activebackground="#00b8cc", activeforeground=BG,
            relief="flat", padx=24, pady=10, cursor="hand2",
            command=self.toggle_run
        )
        self.start_btn.pack(side="left", padx=(0, 10))

        tk.Button(
            ctrl, text="⏱ START + SWITCH",
            font=FONT, bg=BTN_BG, fg=TXT,
            activebackground="#333348", activeforeground=TXT,
            relief="flat", padx=14, pady=10, cursor="hand2",
            command=self.start_and_switch
        ).pack(side="left", padx=(0, 6))

        tk.Button(ctrl, text="💾 Save Config",
                  font=FONT, bg=BTN_BG, fg=TXT,
                  activebackground="#333348", activeforeground=TXT,
                  relief="flat", padx=14, pady=10, cursor="hand2",
                  command=self.save_config).pack(side="left", padx=(0, 6))

        tk.Button(ctrl, text="🔑 Re-Login",
                  font=FONT, bg=BTN_BG, fg=TXT,
                  activebackground="#333348", activeforeground=TXT,
                  relief="flat", padx=14, pady=10, cursor="hand2",
                  command=lambda: threading.Thread(target=setup, daemon=True).start()
                  ).pack(side="left")

        tk.Button(ctrl, text="🧹 Reset Symbols",
                  font=FONT, bg=BTN_BG, fg=TXT,
                  activebackground="#333348", activeforeground=TXT,
                  relief="flat", padx=14, pady=10, cursor="hand2",
                  command=self.reset_symbols_progress).pack(side="left", padx=(6, 0))

        ctrl2 = tk.Frame(main, bg=BG, padx=18, pady=0)
        ctrl2.pack(fill="x", pady=(0, 12))
        tk.Button(ctrl2, text="♻ Reset ALL Offsale",
                  font=FONT, bg=BTN_BG, fg=TXT,
                  activebackground="#333348", activeforeground=TXT,
                  relief="flat", padx=14, pady=10, cursor="hand2",
                  command=self.reset_all_gamepasses_offsale).pack(side="left")

        hotkey_hint = "⚠  Ctrl+N start/stop  •  Ctrl+M stop"
        tk.Label(ctrl, text=hotkey_hint,
                 font=FONT_SM, fg=ACCENT2, bg=BG).pack(side="right")

        self.pick_overlay = None

        # Autosave on editable values
        for var in (self.universe_var, self.post_click_wait_var, self.proc_delay_var, self.click_ms_var, self.loops_var, self.start_delay_var,
                    self.page_start_var, self.page_end_var):
            var.trace_add("write", lambda *_: self._auto_save_config())

    # ── Hotkeys ───────────────────────────────────────────────────────────────

    def _setup_hotkeys(self):
        # App-level hotkeys always available while this window is focused.
        self.root.bind_all("<Control-n>", lambda _e: self._hotkey_toggle())
        self.root.bind_all("<Control-m>", lambda _e: self._hotkey_stop())
        self.root.bind_all("<Control-M>", lambda _e: self._hotkey_stop())
        self.root.bind_all("<Command-m>", lambda _e: self._hotkey_stop())

        # Global listener allows start/stop while game window is focused.
        def on_press(key):
            if key in (pynput_kb.Key.ctrl_l, pynput_kb.Key.ctrl_r):
                self._ctrl_held = True
            try:
                if self._ctrl_held and key.char == 'm':
                    self._hotkey_stop()
                if self._ctrl_held and key.char == 'n':
                    self._hotkey_toggle()
            except AttributeError:
                pass

        def on_release(key):
            if key in (pynput_kb.Key.ctrl_l, pynput_kb.Key.ctrl_r):
                self._ctrl_held = False

        try:
            listener = pynput_kb.Listener(on_press=on_press, on_release=on_release)
            listener.daemon = True
            listener.start()
        except Exception:
            pass

    def _hotkey_allowed(self, key_name: str) -> bool:
        now = time.time()
        last = self._last_hotkey_ts.get(key_name, 0.0)
        if now - last < self._hotkey_cooldown_s:
            return False
        self._last_hotkey_ts[key_name] = now
        return True

    def _hotkey_toggle(self):
        if not self._hotkey_allowed("toggle"):
            return
        self.root.after(0, self.toggle_run)

    def _hotkey_stop(self):
        if not self._hotkey_allowed("stop"):
            return
        self.root.after(0, self.emergency_stop)

    # ── Coord picking ─────────────────────────────────────────────────────────

    def _coord_str(self, key):
        c = self.coords.get(key)
        return f"({c[0]}, {c[1]})" if c else "not set"

    def clear_coord(self, key, var):
        self.coords[key] = None
        var.set("not set")
        self._auto_save_config()

    def start_pick(self, key):
        if self.running:
            messagebox.showwarning("Stonk Bot", "Stop the script before picking coordinates.")
            return
        self.pick_key = key
        self.picking  = True
        self._show_overlay(
            f"🎯  Move mouse to  '{key}'  →  CLICK to confirm   |   Esc to cancel"
        )
        self.root.after(400, self._start_mouse_listener_pick)

    def _show_overlay(self, text: str):
        if self.pick_overlay and self.pick_overlay.winfo_exists():
            self.pick_overlay.destroy()
        ov = tk.Toplevel(self.root)
        ov.overrideredirect(True)
        ov.attributes("-topmost", True)
        ov.attributes("-alpha", 0.88)
        ov.configure(bg=self.CARD)
        sw = self.root.winfo_screenwidth()
        ov.geometry(f"520x52+{sw//2 - 260}+16")
        tk.Label(ov, text=text, font=self.FONT,
                 fg=self.ACCENT, bg=self.CARD, padx=16, pady=14).pack()
        self.pick_overlay = ov
        ov.bind("<Escape>", lambda e: self._cancel_any_pick())
        ov.focus_force()
        self._track_mouse_pos()

    def _track_mouse_pos(self):
        if (self.picking or self._region_step > 0 or self._verify_step > 0 or self._scan_step > 0 or self._page_ind_step > 0) and \
                self.pick_overlay and self.pick_overlay.winfo_exists():
            x, y = pyautogui.position()
            self.status_var.set(f"Mouse at ({x}, {y})  |  Click = confirm   Esc = cancel")
            self.root.after(50, self._track_mouse_pos)

    def _start_mouse_listener_pick(self):
        from pynput import mouse as pm
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass

        def on_click(x, y, button, pressed):
            if pressed and button == pm.Button.left:
                if self.picking:
                    self.root.after(0, self._confirm_pick)
                    return False

        self._mouse_listener = pm.Listener(on_click=on_click)
        self._mouse_listener.daemon = True
        self._mouse_listener.start()

    def _confirm_pick(self):
        x, y = pyautogui.position()
        key  = self.pick_key
        self.coords[key] = (x, y)
        if key in self.step_widgets:
            self.step_widgets[key].set(f"({x}, {y})")
        self.status_var.set(f"✓ '{key}' set to ({x}, {y})")
        self.picking = False
        self._close_overlay()
        self._auto_save_config()

    def _cancel_any_pick(self):
        self.picking       = False
        self._region_step  = 0
        self._region_tl    = None
        self._verify_step  = 0
        self._verify_tl    = None
        self._scan_step    = 0
        self._scan_tl      = None
        self._page_ind_step = 0
        self._page_ind_tl   = None
        self.status_var.set("Pick cancelled.")
        self._close_overlay()

    def _close_overlay(self):
        if self.pick_overlay and self.pick_overlay.winfo_exists():
            self.pick_overlay.destroy()
        self.pick_overlay = None

    # ── OCR Region picking (2-click: TL then BR) ──────────────────────────────

    def _region_str(self):
        if not self.ocr_region:
            return "not set"
        l, t, w, h = self.ocr_region
        return f"({l}, {t})  →  ({l+w}, {t+h})  [{w}×{h}]"

    def clear_region(self):
        self.ocr_region = None
        self.ocr_region_var.set("not set")
        self._auto_save_config()

    def _verify_str(self):
        if not self.verify_region:
            return "not set"
        l, t, w, h = self.verify_region
        return f"({l}, {t})  →  ({l+w}, {t+h})  [{w}×{h}]"

    def clear_verify_region(self):
        self.verify_region = None
        self.verify_region_var.set("not set")
        self._auto_save_config()

    def start_verify_pick(self):
        if self.running:
            messagebox.showwarning("Stonk Bot", "Stop the script before picking a region.")
            return
        self._verify_step = 1
        self._verify_tl = None
        self._show_overlay("🎯 Click TOP-LEFT of result value area   |   Esc to cancel")
        self.root.after(400, self._start_mouse_listener_verify)

    def _start_mouse_listener_verify(self):
        from pynput import mouse as pm
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass

        def on_click(x, y, button, pressed):
            if pressed and button == pm.Button.left and self._verify_step > 0:
                self.root.after(0, lambda cx=x, cy=y: self._verify_click(cx, cy))
                return False

        self._mouse_listener = pm.Listener(on_click=on_click)
        self._mouse_listener.daemon = True
        self._mouse_listener.start()

    def _verify_click(self, x, y):
        if self._verify_step == 1:
            self._verify_tl = (x, y)
            self._verify_step = 2
            self._show_overlay("🎯 Now click BOTTOM-RIGHT of result value area   |   Esc to cancel")
            self.root.after(400, self._start_mouse_listener_verify)
            return
        if self._verify_step == 2:
            tl = self._verify_tl
            left = min(tl[0], x)
            top = min(tl[1], y)
            width = abs(x - tl[0])
            height = abs(y - tl[1])
            self.verify_region = (left, top, width, height)
            self.verify_region_var.set(self._verify_str())
            self.status_var.set(f"✓ Result value region set: {self._verify_str()}")
            self._verify_step = 0
            self._verify_tl = None
            self._close_overlay()
            self._auto_save_config()

    def start_region_pick(self):
        if self.running:
            messagebox.showwarning("Stonk Bot", "Stop the script before picking a region.")
            return
        self._region_step = 1
        self._region_tl   = None
        self._show_overlay("📐  Click the TOP-LEFT corner of the game window price area   |   Esc to cancel")
        self.root.after(400, self._start_mouse_listener_region)

    def _start_mouse_listener_region(self):
        from pynput import mouse as pm
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass

        def on_click(x, y, button, pressed):
            if pressed and button == pm.Button.left and self._region_step > 0:
                self.root.after(0, lambda cx=x, cy=y: self._region_click(cx, cy))
                return False

        self._mouse_listener = pm.Listener(on_click=on_click)
        self._mouse_listener.daemon = True
        self._mouse_listener.start()

    def _region_click(self, x, y):
        if self._region_step == 1:
            self._region_tl   = (x, y)
            self._region_step = 2
            self._show_overlay("📐  Now click the BOTTOM-RIGHT corner of the price area   |   Esc to cancel")
            self.root.after(400, self._start_mouse_listener_region)

        elif self._region_step == 2:
            tl = self._region_tl
            left   = min(tl[0], x)
            top    = min(tl[1], y)
            width  = abs(x - tl[0])
            height = abs(y - tl[1])
            self.ocr_region = (left, top, width, height)
            self.ocr_region_var.set(self._region_str())
            self.status_var.set(f"✓ OCR region set: {self._region_str()}")
            self._region_step = 0
            self._region_tl   = None
            self._close_overlay()
            self._auto_save_config()

    # ── Symbol scan window picking ────────────────────────────────────────────
    def _scan_str(self):
        if not self.scan_region:
            return "not set"
        l, t, w, h = self.scan_region
        return f"({l}, {t})  →  ({l+w}, {t+h})  [{w}×{h}]"

    def clear_scan_region(self):
        self.scan_region = None
        self.scan_region_var.set("not set")
        self._auto_save_config()

    def start_scan_pick(self):
        if self.running:
            messagebox.showwarning("Stonk Bot", "Stop the script before picking a window.")
            return
        self._scan_step = 1
        self._scan_tl = None
        self._show_overlay("🖼 Click TOP-LEFT of symbol scan window   |   Esc to cancel")
        self.root.after(400, self._start_mouse_listener_scan)

    def _start_mouse_listener_scan(self):
        from pynput import mouse as pm
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass

        def on_click(x, y, button, pressed):
            if pressed and button == pm.Button.left and self._scan_step > 0:
                self.root.after(0, lambda cx=x, cy=y: self._scan_click(cx, cy))
                return False

        self._mouse_listener = pm.Listener(on_click=on_click)
        self._mouse_listener.daemon = True
        self._mouse_listener.start()

    def _scan_click(self, x, y):
        if self._scan_step == 1:
            self._scan_tl = (x, y)
            self._scan_step = 2
            self._show_overlay("🖼 Now click BOTTOM-RIGHT of symbol scan window   |   Esc to cancel")
            self.root.after(400, self._start_mouse_listener_scan)
            return
        if self._scan_step == 2:
            tl = self._scan_tl
            left = min(tl[0], x)
            top = min(tl[1], y)
            width = abs(x - tl[0])
            height = abs(y - tl[1])
            self.scan_region = (left, top, width, height)
            self.scan_region_var.set(self._scan_str())
            self.status_var.set(f"✓ Symbol scan window set: {self._scan_str()}")
            self._scan_step = 0
            self._scan_tl = None
            self._close_overlay()
            self._auto_save_config()

    def _page_ind_str(self):
        if not self.page_indicator_region:
            return "not set"
        l, t, w, h = self.page_indicator_region
        return f"({l}, {t})  →  ({l+w}, {t+h})  [{w}×{h}]"

    def clear_page_indicator_region(self):
        self.page_indicator_region = None
        self.page_indicator_region_var.set("not set")
        self._auto_save_config()

    def start_page_indicator_pick(self):
        if self.running:
            messagebox.showwarning("Stonk Bot", "Stop the script before picking a region.")
            return
        self._page_ind_step = 1
        self._page_ind_tl = None
        self._show_overlay("📄 Click TOP-LEFT of the “current / total” page text   |   Esc to cancel")
        self.root.after(400, self._start_mouse_listener_page_ind)

    def _start_mouse_listener_page_ind(self):
        from pynput import mouse as pm
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass

        def on_click(x, y, button, pressed):
            if pressed and button == pm.Button.left and self._page_ind_step > 0:
                self.root.after(0, lambda cx=x, cy=y: self._page_ind_click(cx, cy))
                return False

        self._mouse_listener = pm.Listener(on_click=on_click)
        self._mouse_listener.daemon = True
        self._mouse_listener.start()

    def _page_ind_click(self, x, y):
        if self._page_ind_step == 1:
            self._page_ind_tl = (x, y)
            self._page_ind_step = 2
            self._show_overlay("📄 Now click BOTTOM-RIGHT of the page text region   |   Esc to cancel")
            self.root.after(400, self._start_mouse_listener_page_ind)
            return
        if self._page_ind_step == 2:
            tl = self._page_ind_tl
            left = min(tl[0], x)
            top = min(tl[1], y)
            width = abs(x - tl[0])
            height = abs(y - tl[1])
            self.page_indicator_region = (left, top, width, height)
            self.page_indicator_region_var.set(self._page_ind_str())
            self.status_var.set(f"✓ Page indicator region: {self._page_ind_str()}")
            self._page_ind_step = 0
            self._page_ind_tl = None
            self._close_overlay()
            self._auto_save_config()

    # ── Run control ───────────────────────────────────────────────────────────

    def emergency_stop(self):
        if self.running:
            self.running = False
            self.root.after(0, lambda: (
                self.start_btn.configure(text="▶  START", bg=self.ACCENT, fg=self.BG),
                self.status_var.set("⛔ Stopped via Ctrl+M")
            ))

    def toggle_run(self):
        if self.running:
            self.running = False
            self.start_btn.configure(text="▶  START", bg=self.ACCENT, fg=self.BG)
            self.status_var.set("Stopped.")
            return

        if not self._validate_before_start():
            return

        self.running = True
        self.start_btn.configure(text="■  STOP", bg=self.ACCENT2, fg=self.BG)
        self._show_countdown(3)

    def _validate_before_start(self):
        # Validate coords
        missing_coords = [s["label"] for s in SELL_STEPS if not self.coords.get(s["key"])]
        if missing_coords:
            self.root.lift()
            messagebox.showerror("Stonk Bot",
                "These coordinates are not set:\n\n" + "\n".join(missing_coords))
            return False

        if not self.ocr_region:
            self.root.lift()
            messagebox.showerror("Stonk Bot", "Price region is not set.\nClick 📐 PICK PRICE REGION first.")
            return False
        if not self.verify_region:
            self.root.lift()
            messagebox.showerror("Stonk Bot", "Result value region is not set.\nClick 🎯 PICK RESULT REGION first.")
            return False
        if not self.scan_region:
            self.root.lift()
            messagebox.showerror("Stonk Bot", "Symbol scan window is not set.\nClick 🖼 PICK WINDOW first.")
            return False

        if not self.universe_var.get().strip():
            self.root.lift()
            messagebox.showerror("Stonk Bot", "Universe ID is empty.")
            return False

        if not os.path.exists(COOKIES_FILE):
            self.root.lift()
            messagebox.showerror("Stonk Bot",
                "No Roblox cookies found.\nClick 🔑 Re-Login first.")
            return False
        return True

    def start_and_switch(self):
        if self.running:
            return
        if not self._validate_before_start():
            return
        self.running = True
        self.start_btn.configure(text="■  STOP", bg=self.ACCENT2, fg=self.BG)
        delay = int(max(0, self.start_delay_var.get()))
        self.status_var.set(f"Switch to Roblox now... starting in {delay}s")
        self.root.after(200, bring_roblox_to_foreground)
        self._show_countdown(delay)

    def _show_countdown(self, n):
        if not self.running:
            return
        if n == 0:
            self.status_var.set("Running…")
            threading.Thread(target=self._run_loop, daemon=True).start()
            return
        self.status_var.set(f"Starting in {n}…")
        self.root.after(1000, lambda: self._show_countdown(n - 1))

    def _run_loop(self):
        max_loops = self.loops_var.get()
        iteration = 0

        while self.running:
            if max_loops > 0 and iteration >= max_loops:
                self.root.after(0, lambda i=iteration: (
                    self.status_var.set(f"Done — {i} loops completed."),
                    self.start_btn.configure(text="▶  START", bg=self.ACCENT, fg=self.BG)
                ))
                self.running = False
                break

            iteration += 1
            self.root.after(0, lambda i=iteration: (
                self.loop_var.set(f"Loops: {i}"),
                self.status_var.set(f"Loop {i}{f'/{max_loops}' if max_loops else ''} running…")
            ))

            def ui_log(msg):
                self.root.after(0, lambda m=msg: self.status_var.set(m))

            try:
                selected_universe_id = self._select_universe_for_sale(ui_log)
                if not selected_universe_id:
                    self.running = False
                    break
                self._ensure_page_start(ui_log)
                if not self.running:
                    break
                gamepass_id, price, symbol_name, nav = run_one_cycle(
                    coords       = self.coords,
                    ocr_region   = self.ocr_region,
                    verify_region = self.verify_region,
                    scan_region  = self.scan_region,
                    universe_id  = selected_universe_id,
                    post_click_wait = self.post_click_wait_var.get(),
                    ocr_wait     = self.proc_delay_var.get(),
                    click_delay_ms = self.click_ms_var.get(),
                    completed_symbols = self.completed_symbols,
                    log_fn       = ui_log,
                    should_continue = lambda: self.running,
                    no_symbol_nav = self._no_symbol_nav,
                )
                if symbol_name:
                    self.completed_symbols.add(symbol_name)
                    self._save_progress()
                else:
                    if nav == "cycle_end":
                        self._handle_cycle_completion(ui_log)
                    elif nav == "next_page":
                        self.current_page += 1
                        self._sync_current_page_from_indicator(ui_log)
                        self._save_progress()
            except Exception as e:
                if str(e) == "Stopped":
                    self.running = False
                    self.root.after(0, lambda: (
                        self.start_btn.configure(text="▶  START", bg=self.ACCENT, fg=self.BG),
                        self.status_var.set("⛔ Stopped.")
                    ))
                    break
                if "Gamepass value stayed 0 after retries" in str(e):
                    self.root.after(0, lambda msg=str(e): self.status_var.set(f"⚠ {msg} — continuing next symbol."))
                    continue
                def show_err(err=e):
                    self.root.lift()
                    self.root.focus_force()
                    self.status_var.set(f"Error: {err}")
                    self.start_btn.configure(text="▶  START", bg=self.ACCENT, fg=self.BG)
                    messagebox.showerror("Stonk Bot Error",
                        f"{err}\n\nIf clicks aren't registering on macOS:\n"
                        "System Settings → Privacy & Security → Accessibility\n"
                        "AND Input Monitoring\n"
                        "then allow Terminal / Python / Cursor helper.")
                self.root.after(0, show_err)
                self.running = False
                break

            if self.running and max_loops != 1:
                self._interruptible_sleep(2)

        if self.running:
            self.running = False
            self.root.after(0, lambda: (
                self.start_btn.configure(text="▶  START", bg=self.ACCENT, fg=self.BG),
                self.status_var.set("Finished.")
            ))

    def _interruptible_sleep(self, seconds):
        end = time.time() + seconds
        while self.running and time.time() < end:
            time.sleep(0.05)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__": 
    if "--setup" in sys.argv:
        setup()
    else:
        root = tk.Tk()
        app  = StonkAutomationApp(root)
        root.mainloop()
