#!/usr/bin/env python3
"""
Bulk-create empty gamepasses per experience (for stock before running the bot).

Uses roblox_cookies.json from setup_login.py / main --setup.

If stonk_rotation_config.json exists with offsale_universe_ids + sale_caps,
uses those (3 games, counts = caps). Otherwise prompts for 3 links and 50/50/23.

Usage:
  python bulk_create_gamepasses.py
"""

import json
import os
import random
import re
import string
import sys
import time

from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_FILE = os.path.join(BASE_DIR, "roblox_cookies.json")
ROTATION_FILE = os.path.join(BASE_DIR, "stonk_rotation_config.json")
PROGRESS_FILE = os.path.join(BASE_DIR, "bulk_create_progress.json")


def random_name() -> str:
    return "".join(random.choices(string.ascii_uppercase, k=random.choice([3, 4, 5])))


def extract_universe_id(url_or_id: str) -> str:
    s = (url_or_id or "").strip()
    if s.isdigit():
        return s
    m = re.search(r"/experiences/(\d+)", s)
    if m:
        return m.group(1)
    raise ValueError("Could not parse universe id from input.")


def load_cookies(context):
    if not os.path.exists(COOKIES_FILE):
        raise RuntimeError(f"Missing {COOKIES_FILE}. Run: python setup_login.py")
    with open(COOKIES_FILE) as f:
        context.add_cookies(json.load(f))


def save_cookies(context):
    with open(COOKIES_FILE, "w") as f:
        json.dump(context.cookies(), f, indent=2)


def load_plan_from_rotation():
    if not os.path.exists(ROTATION_FILE):
        return None
    with open(ROTATION_FILE) as f:
        data = json.load(f)
    ids = [str(x).strip() for x in data.get("offsale_universe_ids", []) if str(x).strip()]
    caps = data.get("sale_caps") or [50, 50, 23]
    caps = [int(x) for x in caps]
    while len(caps) < len(ids):
        caps.append(caps[-1] if caps else 50)
    if len(ids) < 1:
        return None
    return list(zip(ids, caps[: len(ids)]))


def prompt_plan():
    print("Paste 3 experience links (or universe ids). Type 0 to skip a slot.")
    plan = []

    def one(prompt, default_cap):
        while True:
            raw = input(prompt).strip()
            if raw == "0":
                return None
            if not raw:
                continue
            try:
                uid = extract_universe_id(raw)
                return (uid, default_cap)
            except ValueError:
                print("Invalid. Try again.")

    a = one("Game 1 (50 passes default): ", 50)
    if a:
        plan.append(a)
    b = one("Game 2 (50 passes default): ", 50)
    if b:
        plan.append(b)
    c = one("Game 3 (23 passes default): ", 23)
    if c:
        plan.append(c)
    return plan if plan else None


def _create_one_pass_with_retry(page, create_url: str, pass_name: str, retries: int = 3):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            page.goto(create_url, wait_until="domcontentloaded", timeout=45_000)
            if "login" in page.url.lower():
                raise RuntimeError("Cookies expired. Run setup_login.py again.")

            name_input = page.locator("textarea#name, textarea[name='name']").first
            name_input.wait_for(timeout=25_000)
            name_input.click()
            name_input.fill(pass_name)
            time.sleep(0.3)

            create_btn = page.locator(
                "span.web-blox-css-tss-1283320-Button-textContainer:has-text('Create Pass'),"
                "button:has-text('Create Pass')"
            ).first
            create_btn.wait_for(timeout=12_000)
            create_btn.click(force=True)
            page.wait_for_timeout(1800)
            return
        except Exception as e:
            last_error = e
            print(f"  [WARN] Attempt {attempt}/{retries} failed: {e}")
            page.wait_for_timeout(1500)
    raise RuntimeError(f"Could not create pass '{pass_name}' after {retries} attempts: {last_error}")


def create_passes(universe_id: str, count: int, already_done: int = 0):
    create_url = (
        f"https://create.roblox.com/dashboard/creations/experiences/"
        f"{universe_id}/passes/create"
    )
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-first-run"])
        context = browser.new_context()
        load_cookies(context)
        page = context.new_page()
        for i in range(already_done + 1, count + 1):
            pname = random_name()
            print(f"[{i}/{count}] Creating pass: {pname}")
            _create_one_pass_with_retry(page, create_url, pname, retries=3)
            yield i
        save_cookies(context)
        browser.close()


def _load_progress():
    if not os.path.exists(PROGRESS_FILE):
        return None
    try:
        with open(PROGRESS_FILE) as f:
            d = json.load(f)
        if isinstance(d, dict):
            return d
    except Exception:
        pass
    return None


def _save_progress(d):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(d, f, indent=2)


def _clear_progress():
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)


def main():
    progress = _load_progress()
    if progress:
        ans = input("Resume previous bulk run? [Y/n]: ").strip().lower()
        if ans in ("", "y", "yes"):
            plan = progress["plan"]
            done = progress["done"]
        else:
            progress = None
            _clear_progress()
    else:
        progress = None

    if not progress:
        plan = load_plan_from_rotation()
        if not plan:
            plan = prompt_plan()
        if not plan:
            print("No plan. Exiting.")
            sys.exit(1)
        done = {str(i): 0 for i in range(len(plan))}
        _save_progress({"plan": plan, "done": done})

    for idx, (uid, target) in enumerate(plan, start=1):
        key = str(idx - 1)
        already = int(done.get(key, 0))
        if already >= int(target):
            print(f"[SKIP] Game {idx} done ({already}/{target})")
            continue
        print(f"\n[RUN] Game {idx} universe={uid} create {target} (resume {already})")
        for n in create_passes(uid, int(target), already_done=already):
            done[key] = n
            _save_progress({"plan": plan, "done": done})

    _clear_progress()
    print("\n[DONE] Bulk create finished.")


if __name__ == "__main__":
    main()
