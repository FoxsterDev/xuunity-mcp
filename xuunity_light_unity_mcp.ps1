# Stock Windows PowerShell 5.1 ships with ExecutionPolicy=Restricted and refuses
# to run any .ps1 file. Use the .cmd flavor of this launcher instead, or invoke:
#   powershell -NoProfile -ExecutionPolicy Bypass -File <path-to-this-script> <args>
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$launcher = Join-Path $scriptDir "templates/server_launcher.py"
if ([string]::IsNullOrWhiteSpace($env:XUUNITY_LIGHT_UNITY_MCP_LAUNCHER_NAME)) {
    $env:XUUNITY_LIGHT_UNITY_MCP_LAUNCHER_NAME = Split-Path -Leaf $MyInvocation.MyCommand.Path
}
if ([string]::IsNullOrWhiteSpace($env:PYTHONUTF8)) {
    $env:PYTHONUTF8 = "1"
}

if (-not [string]::IsNullOrWhiteSpace($env:PYTHON)) {
    if ($env:PYTHON -eq "py -3") {
        & py -3 $launcher @args
    } else {
        & $env:PYTHON $launcher @args
    }
    exit $LASTEXITCODE
}

$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
    & $py.Source -3 $launcher @args
    exit $LASTEXITCODE
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    & $python.Source $launcher @args
    exit $LASTEXITCODE
}

$python3 = Get-Command python3 -ErrorAction SilentlyContinue
if ($python3) {
    & $python3.Source $launcher @args
    exit $LASTEXITCODE
}

Write-Error "Python 3 was not found. Install Python 3 or set PYTHON to its executable path."
exit 1
