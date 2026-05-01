@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================
echo  Roblox Stonk Automation - install deps
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python not found on PATH.
  echo Install Python 3.10+ from https://www.python.org/downloads/
  echo Make sure "Add python.exe to PATH" is checked during setup.
  pause
  exit /b 1
)

echo [1/4] Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 goto :fail

echo.
echo [2/4] Installing Python packages from requirements.txt...
python -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto :fail

echo.
echo [3/4] Installing Playwright Chromium browser...
python -m playwright install chromium
if errorlevel 1 goto :fail

echo.
echo [4/4] Done.
echo.
echo Next steps:
echo   1. Windows OCR: double-click install_tesseract_windows.bat ^(winget + path hint file^)
echo      Or install manually: https://github.com/UB-Mannheim/tesseract/wiki
echo   2. Run:  python setup_login.py
echo   3. Run:  python setup_experiences.py
echo   4. Run:  python roblox_stonk_automation.py
echo.
pause
exit /b 0

:fail
echo.
echo ERROR: A step failed. Read messages above.
pause
exit /b 1
