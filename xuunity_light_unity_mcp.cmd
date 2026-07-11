@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "XUUNITY_TARGET=%SCRIPT_DIR%templates\server_launcher.py"
if not defined XUUNITY_LIGHT_UNITY_MCP_LAUNCHER_NAME set "XUUNITY_LIGHT_UNITY_MCP_LAUNCHER_NAME=%~nx0"
if not defined PYTHONUTF8 set "PYTHONUTF8=1"
set "XUUNITY_PYTHON_CMD="

if not defined PYTHON goto xuunity_try_py

set "XUUNITY_PYTHON_OVERRIDE=%PYTHON:"=%"
if /i "%XUUNITY_PYTHON_OVERRIDE%"=="py -3" goto xuunity_override_is_py
call :xuunity_probe "%XUUNITY_PYTHON_OVERRIDE%"
if errorlevel 1 goto xuunity_override_failed
set "XUUNITY_PYTHON_CMD="%XUUNITY_PYTHON_OVERRIDE%""
goto xuunity_run

:xuunity_override_is_py
call :xuunity_probe py -3
if errorlevel 1 goto xuunity_override_failed
set "XUUNITY_PYTHON_CMD=py -3"
goto xuunity_run

:xuunity_override_failed
echo PYTHON is set to "%XUUNITY_PYTHON_OVERRIDE%" but it is not a working Python 3.10+ interpreter. 1>&2
exit /b 9009

:xuunity_try_py
call :xuunity_probe py -3
if errorlevel 1 goto xuunity_try_python
set "XUUNITY_PYTHON_CMD=py -3"
goto xuunity_run

:xuunity_try_python
call :xuunity_probe python
if errorlevel 1 goto xuunity_try_python3
set "XUUNITY_PYTHON_CMD=python"
goto xuunity_run

:xuunity_try_python3
call :xuunity_probe python3
if errorlevel 1 goto xuunity_not_found
set "XUUNITY_PYTHON_CMD=python3"
goto xuunity_run

:xuunity_not_found
echo Python 3.10 or newer was not found. Install it from https://www.python.org/downloads/ and reopen the terminal, or set PYTHON to a Python 3.10+ interpreter. 1>&2
echo Note: on a fresh Windows the "python" command is often the Microsoft Store stub, which cannot run scripts and is rejected by this launcher. 1>&2
exit /b 9009

:xuunity_probe
%* -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 2)" >nul 2>nul
goto :eof

:xuunity_run
%XUUNITY_PYTHON_CMD% "%XUUNITY_TARGET%" %*
