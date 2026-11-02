@echo off
setlocal
cd /d "%~dp0"
title Build AI Snabzhenets EXE

echo ========================================
echo   Building AI Snabzhenets for Windows
echo ========================================
echo.

where py >nul 2>nul
if errorlevel 1 (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python is not installed or not in PATH.
        echo Install Python 3.11 or newer, then run this file again.
        pause
        exit /b 1
    )
    set "PY=python"
) else (
    set "PY=py"
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY% -m venv .venv
    if errorlevel 1 goto :error
)

set "VPY=.venv\Scripts\python.exe"
echo Installing dependencies...
"%VPY%" -m pip install --upgrade pip
if errorlevel 1 goto :error
"%VPY%" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :error

echo.
echo Building EXE. This may take several minutes...
"%VPY%" -m PyInstaller --noconfirm --clean --onefile --name "AI-Snabzhenets" ^
  --collect-all streamlit ^
  --collect-all pdfplumber ^
  --collect-all rapidfuzz ^
  --collect-all openpyxl ^
  --add-data "app.py;." ^
  --add-data "pdf_parser.py;." ^
  --add-data "matcher.py;." ^
  launcher.py
if errorlevel 1 goto :error

echo.
echo ========================================
echo DONE
 echo EXE: %CD%\dist\AI-Snabzhenets.exe
echo ========================================
explorer "%CD%\dist"
pause
exit /b 0

:error
echo.
echo BUILD FAILED. See the error above.
pause
exit /b 1
