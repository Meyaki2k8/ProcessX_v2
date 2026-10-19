@echo off
setlocal
cd /d "%~dp0.."

echo [1/3] Dependencies
python -m pip install --upgrade pyinstaller PyQt6 psutil || goto :fail

echo [2/3] PyInstaller (onedir, no console, admin manifest)
rmdir /s /q build 2>nul
rmdir /s /q "dist\ProcessX v2.0" 2>nul
python -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name "ProcessX v2.0" ^
  --icon "assets\Meyaki.ico" ^
  --add-data "assets;assets" ^
  --version-file "installer\version_info.txt" ^
  --uac-admin ^
  main.py || goto :fail

echo [3/3] NSIS installer
set "MAKENSIS=%ProgramFiles(x86)%\NSIS\makensis.exe"
if not exist "%MAKENSIS%" set "MAKENSIS=%ProgramFiles%\NSIS\makensis.exe"
if not exist "%MAKENSIS%" (
  echo NSIS not found. Install NSIS 3.x from https://nsis.sourceforge.io/Download
  goto :fail
)
"%MAKENSIS%" "installer\ProcessX.nsi" || goto :fail

echo.
echo Done: dist\ProcessX_v2.0_Setup.exe
exit /b 0

:fail
echo BUILD FAILED
exit /b 1
