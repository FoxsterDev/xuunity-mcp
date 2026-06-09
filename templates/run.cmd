@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
if not defined XUUNITY_LIGHT_UNITY_MCP_SERVER (
  set "XUUNITY_LIGHT_UNITY_MCP_SERVER=%SCRIPT_DIR%server.py"
)

if defined PYTHON (
  "%PYTHON%" "%XUUNITY_LIGHT_UNITY_MCP_SERVER%" %*
  exit /b %ERRORLEVEL%
)

if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
  "%SCRIPT_DIR%.venv\Scripts\python.exe" "%XUUNITY_LIGHT_UNITY_MCP_SERVER%" %*
  exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 "%XUUNITY_LIGHT_UNITY_MCP_SERVER%" %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python "%XUUNITY_LIGHT_UNITY_MCP_SERVER%" %*
  exit /b %ERRORLEVEL%
)

where python3 >nul 2>nul
if %ERRORLEVEL%==0 (
  python3 "%XUUNITY_LIGHT_UNITY_MCP_SERVER%" %*
  exit /b %ERRORLEVEL%
)

echo Python 3 was not found. Install Python 3 or set PYTHON to its executable path. 1>&2
exit /b 1
