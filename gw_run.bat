@echo off
REM ASCII-only on purpose: cmd.exe parses .bat in the OEM codepage.
REM GaussianWrapping CLI (faithful pass-through to upstream scripts).
REM Usage: gw_run.bat run -s DATASET -m OUTPUT [--rasterizer ours^|radegs]
REM        [--vram 8^|12^|16^|24^|48^|96] [any upstream flag...]
REM        gw_run.bat doctor
REM        gw_run.bat check -s DATASET
setlocal
if not exist "%~dp0launch_env.bat" (
  echo [ERROR] launch_env.bat not found. Run install.bat first.
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
"%PY%" "%~dp0gw.py" %*
exit /b %errorlevel%
