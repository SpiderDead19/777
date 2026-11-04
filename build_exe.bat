@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title Сборка ИИ-Снабженец 3.0

echo ========================================
echo   Сборка ИИ-Снабженец 3.0 для Windows
echo ========================================
echo.

set "PY_CMD="
py -3 -c "import sys; assert sys.version_info >= (3, 11)" >nul 2>nul
if not errorlevel 1 set "PY_CMD=py -3"

if not defined PY_CMD (
    python -c "import sys; assert sys.version_info >= (3, 11)" >nul 2>nul
    if not errorlevel 1 set "PY_CMD=python"
)

if not defined PY_CMD (
    echo ОШИБКА: рабочий Python 3.11 или новее не найден.
    echo Установите Python с сайта python.org и отметьте Add Python to PATH.
    echo Также готовый EXE можно собрать и скачать в GitHub Actions.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Создаю виртуальное окружение...
    %PY_CMD% -m venv .venv
    if errorlevel 1 goto :error
)

set "VPY=.venv\Scripts\python.exe"
echo Устанавливаю зависимости...
"%VPY%" -m pip install --upgrade pip
if errorlevel 1 goto :error
"%VPY%" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :error

echo.
echo Собираю EXE. Это может занять несколько минут...
"%VPY%" -m PyInstaller --noconfirm --clean --onefile --name "AI-Snabzhenets" ^
  --collect-all streamlit ^
  --collect-all pdfplumber ^
  --collect-all rapidfuzz ^
  --collect-all openpyxl ^
  --add-data "online_app.py;." ^
  --add-data "online_core.py;." ^
  --add-data "pdf_parser.py;." ^
  --add-data ".streamlit;.streamlit" ^
  launcher.py
if errorlevel 1 goto :error

echo.
echo ========================================
echo ГОТОВО
echo EXE: %CD%\dist\AI-Snabzhenets.exe
echo ========================================
explorer "%CD%\dist"
pause
exit /b 0

:error
echo.
echo СБОРКА НЕ ВЫПОЛНЕНА. Текст ошибки находится выше.
pause
exit /b 1
