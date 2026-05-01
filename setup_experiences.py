#!/usr/bin/env python3
"""
Write stonk_rotation_config.json from three Create dashboard / experience links.

Defaults: 50 passes cap, 50 passes cap, 23 passes cap (third experience).
Run once per machine (or after you change games).

Usage:
  python setup_experiences.py
"""

import json
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_FILE = os.path.join(BASE_DIR, "stonk_rotation_config.json")


def extract_universe_id(text: str) -> str:
    s = (text or "").strip()
    if s.isdigit():
        return s
    m = re.search(r"/experiences/(\d+)", s)
    if m:
        return m.group(1)
    raise ValueError("Could not find universe id. Paste a link like:\n"
                      "https://create.roblox.com/dashboard/creations/experiences/1234567890/monetization/passes")


def prompt_link(label: str) -> str:
    while True:
        raw = input(f"{label} (paste URL or universe id): ").strip()
        if not raw:
            print("Required.")
            continue
        try:
            return extract_universe_id(raw)
        except ValueError as e:
            print(e)


def main():
    print("Configure the 3 experiences for rotation / offsale reset / sale caps.\n")
    u1 = prompt_link("Experience 1 (first game)")
    u2 = prompt_link("Experience 2 (second game)")
    u3 = prompt_link("Experience 3 (third game)")

    print("\nPass sale caps (max on-sale before rotating to next universe).")
    print("Press Enter for defaults: 50, 50, 23")
    c1 = input("Cap for experience 1 [50]: ").strip() or "50"
    c2 = input("Cap for experience 2 [50]: ").strip() or "50"
    c3 = input("Cap for experience 3 [23]: ").strip() or "23"
    caps = [int(c1), int(c2), int(c3)]

    pages = input("\nPages per in-game cycle before reset [12]: ").strip() or "12"
    wait_h = input("Hours to wait after full cycle before repeating [1]: ").strip() or "1"
    wait_sec = int(float(wait_h) * 3600)

    cfg = {
        "pages_per_cycle": int(pages),
        "cycle_wait_seconds": wait_sec,
        "sale_caps": caps,
        "offsale_universe_ids": [u1, u2, u3],
    }
    with open(OUT_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"\nSaved -> {OUT_FILE}")
    print(json.dumps(cfg, indent=2))


if __name__ == "__main__":
    main()
