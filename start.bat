@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title ИИ-Снабженец 3.0

echo ==========================================
echo        ИИ-Снабженец 3.0 - запуск
echo ==========================================
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
    echo Либо скачайте готовый AI-Snabzhenets.exe из GitHub Actions.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Создаю виртуальное окружение...
    %PY_CMD% -m venv .venv
    if errorlevel 1 goto :error
)

echo Проверяю и устанавливаю зависимости...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto :error

echo.
echo Запускаю ИИ-Снабженец 3.0...
echo Браузер откроется автоматически.
echo Для остановки программы закройте это окно.
echo.
set "SNAB_LOCAL_MODE=1"
".venv\Scripts\python.exe" -m streamlit run online_app.py --server.address 127.0.0.1 --server.headless true
exit /b 0

:error
echo.
echo Не удалось запустить программу. Текст ошибки находится выше.
echo.
pause
exit /b 1
