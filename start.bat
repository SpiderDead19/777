@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title ИИ Снабженец

echo ==========================================
echo        ИИ Снабженец - запуск
echo ==========================================
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON=py"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PYTHON=python"
    ) else (
        echo ОШИБКА: Python не найден.
        echo Установите Python 3.11 или новее и отметьте Add Python to PATH.
        echo.
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Создаю виртуальное окружение...
    %PYTHON% -m venv .venv
    if errorlevel 1 goto :error
)

echo Проверяю и устанавливаю зависимости...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto :error

echo.
echo Запускаю ИИ Снабженец...
echo Браузер откроется автоматически.
echo Для остановки программы закройте это окно.
echo.
".venv\Scripts\python.exe" -m streamlit run app.py
exit /b 0

:error
echo.
echo Не удалось запустить программу. Проверьте подключение к интернету и установку Python.
echo.
pause
exit /b 1
