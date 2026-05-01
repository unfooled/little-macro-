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

## Publishing to GitHub

Do **not** commit `roblox_cookies.json` or personal coordinates if you prefer; they are listed in `.gitignore`. Commit:

- `roblox_stonk_automation.py`
- `setup_experiences.py`, `setup_login.py`, `bulk_create_gamepasses.py`
- `requirements.txt`, `README.md`, `.gitignore`, `stonk_rotation_config.json.example`

## License

Use at your own risk; not affiliated with Roblox.
