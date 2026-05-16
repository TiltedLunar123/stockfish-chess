@echo off
REM Build a standalone Windows .exe with Nuitka.
REM Output: dist\StockfishChess.exe (~16 MB, single file, no Python needed).
REM
REM Requirements:
REM   pip install nuitka
REM   Nuitka auto-downloads MinGW64 on first run (~150 MB, cached).
REM
REM Run from the repo root:
REM   build.bat

cd /d "%~dp0"

REM Use a non-virtualised cache directory so the bundled compiler can find
REM its own headers. Some Windows package containers virtualise AppData,
REM which breaks the C include search path.
if "%NUITKA_CACHE_DIR%"=="" set "NUITKA_CACHE_DIR=C:\temp\nuitka_cache"

python -m nuitka ^
  --standalone ^
  --onefile ^
  --windows-console-mode=disable ^
  --enable-plugin=tk-inter ^
  --output-filename=StockfishChess.exe ^
  --output-dir=dist ^
  --assume-yes-for-downloads ^
  --remove-output ^
  --product-name="Stockfish Chess" ^
  --file-description="Modern desktop chess GUI built around Stockfish" ^
  --product-version=0.1.0.0 ^
  --file-version=0.1.0.0 ^
  --copyright="MIT License" ^
  main.py

if errorlevel 1 (
    echo.
    echo Build FAILED.
    exit /b 1
)

echo.
echo Build OK: dist\StockfishChess.exe
