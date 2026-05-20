@echo off
REM Build a standalone Windows .exe with PyInstaller.
REM Output: dist\StockfishChess.exe (single-file, windowed, no Python needed).
REM
REM Requirements:
REM   pip install -r requirements.txt
REM   pip install pyinstaller
REM
REM Run from the repo root:
REM   build.bat

cd /d "%~dp0"

REM Wipe previous build artifacts so PyInstaller starts clean.
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

python -m PyInstaller --noconfirm --clean StockfishChess.spec

if errorlevel 1 (
    echo.
    echo Build FAILED.
    exit /b 1
)

echo.
echo Build OK: dist\StockfishChess.exe
