#!/usr/bin/env python3
"""
One-time Roblox login: opens browser, you sign in, cookies saved to roblox_cookies.json
in this folder (same file the main bot uses).

Requires: pip install playwright && playwright install chromium

Usage:
  python setup_login.py
"""

import os
import sys
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(BASE_DIR, "roblox_stonk_automation.py")


def main():
    if not os.path.isfile(MAIN):
        print(f"Missing {MAIN}", file=sys.stderr)
        sys.exit(1)
    os.chdir(BASE_DIR)
    rc = subprocess.call([sys.executable, MAIN, "--setup"])
    sys.exit(rc)


if __name__ == "__main__":
    main()
