@echo off
setlocal
cd /d "%~dp0"
pip install -e . pyinstaller --quiet
if errorlevel 1 exit /b 1
pyinstaller breachelens.spec --noconfirm --clean
if errorlevel 1 exit /b 1
echo Pharos.exe is at dist\Pharos.exe
pause
