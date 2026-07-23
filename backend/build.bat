@echo off
setlocal
cd /d "%~dp0"

echo.
echo   Building Pharos.exe...
echo.

echo   [1/3] Installing dependencies...
pip install -e . pyinstaller --quiet
if errorlevel 1 (
    echo   ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo   [2/3] Building executable (1-2 minutes)...
pyinstaller breachelens.spec --noconfirm --clean
if errorlevel 1 (
    echo   ERROR: Build failed.
    pause
    exit /b 1
)

echo   [3/3] Done!
echo.
echo   Pharos.exe is at: dist\Pharos.exe
echo   Double-click to run. Delete to uninstall.
echo.
pause
