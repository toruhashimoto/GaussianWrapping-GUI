@echo off
REM ASCII-only on purpose: cmd.exe parses .bat in the OEM codepage.
REM GaussianWrapping GUI - one-shot installer bootstrap.
REM Finds a python (conda base preferred) and hands off to install.py.
REM All arguments are forwarded, e.g.:  install.bat --env-name gwgui --arch 12.0
setlocal
set "BOOT_PY="
for %%P in ("%USERPROFILE%\miniconda3\python.exe" "%USERPROFILE%\anaconda3\python.exe" "C:\ProgramData\miniconda3\python.exe") do (
  if not defined BOOT_PY if exist %%P set "BOOT_PY=%%~P"
)
if not defined BOOT_PY (
  where python >nul 2>nul && set "BOOT_PY=python"
)
if not defined BOOT_PY (
  echo [ERROR] No python found. Install Miniconda first:
  echo         https://docs.conda.io/en/latest/miniconda.html
  if not defined GWGUI_NO_PAUSE pause
  exit /b 1
)
"%BOOT_PY%" "%~dp0install.py" %*
if errorlevel 1 (
  echo.
  echo [ERROR] Install failed. Fix the issue above and re-run install.bat
  echo         ^(completed steps are skipped automatically^).
  if not defined GWGUI_NO_PAUSE pause
  exit /b 1
)
if not defined GWGUI_NO_PAUSE pause
exit /b 0
