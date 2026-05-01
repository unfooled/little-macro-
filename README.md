# Roblox Stonk Automation

Desktop helper for in-game sell flow + Create dashboard gamepass automation (Playwright).

## Requirements

- **Python 3.10+** (3.11+ recommended)
- **Tesseract OCR** (for price/symbol OCR)
  - Windows: [Tesseract installer](https://github.com/UB-Mannheim/tesseract/wiki)
  - macOS: `brew install tesseract`
- **Chromium for Playwright**: after `pip install`, run `playwright install chromium`

## Install

**Windows (one double-click):** run `install_dependencies.bat` in this folder (upgrades pip, installs `requirements.txt`, runs `playwright install chromium`).

**Manual (any OS):**

```bash
cd roblox-stonk-automation
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
playwright install chromium
```

## First-time setup (no cookies in repo)

1. **Configure the 3 experiences** (universe IDs + sale caps 50 / 50 / 23 by default):

   ```bash
   python setup_experiences.py
   ```

   This writes `stonk_rotation_config.json`. You can copy `stonk_rotation_config.json.example` and edit by hand instead.

2. **Log in to Roblox once** (saves `roblox_cookies.json` locally — gitignored):

   ```bash
   python setup_login.py
   ```

   Or: `python roblox_stonk_automation.py --setup`

3. **Optional: bulk-create empty gamepasses** (uses rotation config if present):

   ```bash
   python bulk_create_gamepasses.py
   ```

4. **Run the main GUI**:

   ```bash
   python roblox_stonk_automation.py
   ```

## Windows notes

- If Tesseract is not on `PATH`, set `TESSERACT_PATH` in `roblox_stonk_automation.py` to your `tesseract.exe` full path.
- Grant **Accessibility** (and if needed **Input Monitoring**) to Terminal / Python so mouse/keyboard automation works.
- Use `python` or `py` as appropriate on your PC.

## Page range, page indicator, and anti-AFK (optional)

The GUI can limit which symbol pages you visit (**Start page** / **End page**, inclusive) and optionally OCR the small “current / total” text next to pagination. After a full cycle, the long wait (`cycle_wait_seconds` in `stonk_rotation_config.json`, often 1 hour) triggers a **click on “outside ID box”** every **15 minutes** so Roblox does not idle-kick you.

**What to update on your machine (not in git):**

| File | What to add or check |
|------|----------------------|
| `stonk_settings.json` | `page_start` and `page_end` (integers). If missing, the app defaults start to `1` and end to `pages_per_cycle` from rotation config. |
| `stonk_coordinates.json` | Optional `page_indicator_region`: `[left, top, width, height]` for the “2 / 4” style text. Omit if you only rely on click-counting. |
| Coordinates in the GUI | **⑤ Click Outside ID Box** must be set for anti-AFK clicks during the long wait. |

Re-open the GUI after editing JSON, or use **Save Config** so values stay in sync.

## Publishing to GitHub

Do **not** commit `roblox_cookies.json` or personal coordinates if you prefer; they are listed in `.gitignore`. Commit:

- `roblox_stonk_automation.py`
- `setup_experiences.py`, `setup_login.py`, `bulk_create_gamepasses.py`
- `requirements.txt`, `README.md`, `.gitignore`, `stonk_rotation_config.json.example`

## License

Use at your own risk; not affiliated with Roblox.
