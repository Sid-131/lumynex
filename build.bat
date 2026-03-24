@echo off
:: Lumynex build script
:: Produces dist\Lumynex.exe — single-file, UAC requireAdministrator

setlocal

echo ============================================================
echo  Lumynex Build
echo ============================================================

:: 1. Generate icon (requires PyQt5)
echo [1/3] Generating icon...
python assets\generate_icon.py
if errorlevel 1 (
    echo  ERROR: Icon generation failed. Check that PyQt5 is installed.
    exit /b 1
)

:: 2. Run PyInstaller
echo [2/3] Running PyInstaller...
python -m PyInstaller lumynex.spec --clean --noconfirm
if errorlevel 1 (
    echo  ERROR: PyInstaller build failed.
    exit /b 1
)

:: 3. Report
echo [3/3] Done.
echo.
echo  Output: dist\Lumynex.exe
echo.
dir dist\Lumynex.exe

endlocal
