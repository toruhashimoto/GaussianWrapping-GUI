@echo off
REM ASCII-only on purpose: cmd.exe parses .bat in the OEM codepage.
REM GaussianWrapping GUI launcher (local web UI, opens in browser).
setlocal
if not exist "%~dp0launch_env.bat" (
  echo [ERROR] launch_env.bat not found. Run install.bat first.
  pause
  exit /b 1
)
call "%~dp0launch_env.bat"
if exist "%VCVARS%" call "%VCVARS%" >nul 2>nul
set "CUDA_PATH=%CUDA_HOME%"
set "PATH=%CUDA_HOME%\bin;%PATH%"
set "DISTUTILS_USE_SDK=1"
set "VSLANG=1033"
set "NVCC_APPEND_FLAGS=-DUSE_CUDA"
set "PYTHONUTF8=1"
"%PY%" "%~dp0gui.py"
if errorlevel 1 (
  echo.
  echo [ERROR] GUI exited with an error.
  pause
)
exit /b %errorlevel%
