@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "LAUNCHER=%SCRIPT_DIR%run_installed_or_refresh_xuunity_mcp.py"

if defined PYTHON (
  if "%PYTHON%"=="py -3" (
    py -3 "%LAUNCHER%" %*
  ) else (
    "%PYTHON%" "%LAUNCHER%" %*
  )
  exit /b %ERRORLEVEL%
)

if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
  "%SCRIPT_DIR%.venv\Scripts\python.exe" "%LAUNCHER%" %*
  exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 "%LAUNCHER%" %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python "%LAUNCHER%" %*
  exit /b %ERRORLEVEL%
)

where python3 >nul 2>nul
if %ERRORLEVEL%==0 (
  python3 "%LAUNCHER%" %*
  exit /b %ERRORLEVEL%
)

echo Python 3 was not found. Install Python 3 or set PYTHON to its executable path. 1>&2
exit /b 1
