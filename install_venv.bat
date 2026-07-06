@echo off
REM ASCII-only on purpose: cmd.exe parses .bat in the OEM codepage.
REM GaussianWrapping GUI - conda-free lightweight installer bootstrap.
REM Requires Python 3.11, CUDA 12.8, and VS2022 Build Tools.
REM All arguments are forwarded, e.g.: install_venv.bat --venv .venv --arch 12.0
setlocal

where py >nul 2>nul
if not errorlevel 1 (
  py -3.11 -c "import sys" >nul 2>nul
  if not errorlevel 1 (
    py -3.11 "%~dp0install_venv.py" %*
    goto :done
  )
)

where python >nul 2>nul
if not errorlevel 1 (
  python "%~dp0install_venv.py" %*
  goto :done
)

echo [ERROR] No Python found. Install Python 3.11 first:
echo         https://www.python.org/downloads/release/python-311/
if not defined GWGUI_NO_PAUSE pause
exit /b 1

:done
if errorlevel 1 (
  echo.
  echo [ERROR] Lightweight install failed. Fix the issue above and re-run install_venv.bat
  echo         ^(completed steps are skipped automatically^).
  if not defined GWGUI_NO_PAUSE pause
  exit /b 1
)
if not defined GWGUI_NO_PAUSE pause
exit /b 0
