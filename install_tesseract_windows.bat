@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "HINT=%~dp0stonk_tesseract_path.txt"
set "TESS="

echo ============================================
echo  Tesseract OCR - Windows helper
echo ============================================
echo.
echo This script will:
echo   - Look for tesseract.exe in common folders
echo   - If missing, try winget ^(UB-Mannheim Tesseract^)
echo   - Write stonk_tesseract_path.txt for the Python bot
echo.

if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "TESS=%ProgramFiles%\Tesseract-OCR\tesseract.exe"
if not defined TESS if exist "%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe" set "TESS=%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe"
if not defined TESS if exist "%LocalAppData%\Programs\Tesseract-OCR\tesseract.exe" set "TESS=%LocalAppData%\Programs\Tesseract-OCR\tesseract.exe"

if defined TESS goto :write_hint

echo Tesseract not found in standard locations.
echo.

where winget >nul 2>nul
if errorlevel 1 goto :no_winget

echo [winget] Installing UB-Mannheim Tesseract OCR ^(installer may appear^)...
winget install -e --id UB-Mannheim.TesseractOCR --accept-package-agreements --accept-source-agreements
echo.

set "TESS="
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "TESS=%ProgramFiles%\Tesseract-OCR\tesseract.exe"
if not defined TESS if exist "%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe" set "TESS=%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe"
if not defined TESS if exist "%LocalAppData%\Programs\Tesseract-OCR\tesseract.exe" set "TESS=%LocalAppData%\Programs\Tesseract-OCR\tesseract.exe"

if defined TESS goto :write_hint

echo winget finished but tesseract.exe was not found yet.
echo Close this window, open a NEW Command Prompt, and run this script again.
echo Or install from the wiki page that will open.
start "" "https://github.com/UB-Mannheim/tesseract/wiki"
pause
exit /b 1

:no_winget
echo winget is not available ^(install "App Installer" from Microsoft Store, or use Windows 11^).
echo Opening the official download page — install, then run this script again.
start "" "https://github.com/UB-Mannheim/tesseract/wiki"
pause
exit /b 1

:write_hint
(echo !TESS!)>"%HINT%"
echo [OK] Found: !TESS!
echo [OK] Wrote: %HINT%
echo.
echo roblox_stonk_automation.py reads stonk_tesseract_path.txt automatically.
echo Optional: set user env var TESSERACT_CMD to the same path, or set TESSERACT_PATH in the .py file.
echo.
pause
exit /b 0
