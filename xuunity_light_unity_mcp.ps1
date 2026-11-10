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

function Test-XUUnityPython([string[]]$Command) {
    $ErrorActionPreference = "Continue"
    try {
        [string[]]$rest = @()
        if ($Command.Length -gt 1) { $rest = $Command[1..($Command.Length - 1)] }
        $exe = $Command[0]
        & $exe @rest -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 2)" *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

$neutralDir = $env:XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR
if ([string]::IsNullOrWhiteSpace($neutralDir)) {
    if (-not [string]::IsNullOrWhiteSpace($env:APPDATA)) {
        $neutralDir = Join-Path $env:APPDATA "xuunity-mcp"
    } elseif (-not [string]::IsNullOrWhiteSpace($env:XDG_DATA_HOME)) {
        $neutralDir = Join-Path $env:XDG_DATA_HOME "xuunity-mcp"
    } elseif ($IsMacOS) {
        $neutralDir = Join-Path $HOME "Library/Application Support/xuunity-mcp"
    } else {
        $neutralDir = Join-Path $HOME ".local/share/xuunity-mcp"
    }
}

[string[]]$pythonCmd = @()
$skipped = @()
if (-not [string]::IsNullOrWhiteSpace($env:PYTHON)) {
    [string[]]$explicit = @($env:PYTHON.Trim('"'))
    if ($env:PYTHON -eq "py -3") { $explicit = @("py", "-3") }
    if (-not (Test-XUUnityPython $explicit)) {
        [Console]::Error.WriteLine("PYTHON is set to ""$($env:PYTHON)"", which is not a working Python 3.10+ interpreter.")
        exit 1
    }
    $pythonCmd = $explicit
} else {
    foreach ($candidate in @(
        (Join-Path $scriptDir ".venv\Scripts\python.exe"),
        (Join-Path $scriptDir ".venv/bin/python"),
        (Join-Path $neutralDir ".venv\Scripts\python.exe"),
        (Join-Path $neutralDir ".venv/bin/python")
    )) {
        if (-not (Test-Path $candidate)) { continue }
        if (Test-XUUnityPython @($candidate)) { $pythonCmd = @($candidate); break }
        $skipped += $candidate
    }
    if ($pythonCmd.Length -eq 0) {
        foreach ($name in @("py", "python", "python3")) {
            $found = Get-Command $name -ErrorAction SilentlyContinue
            if (-not $found) { continue }
            [string[]]$command = @($found.Source)
            if ($name -eq "py") { $command = @($found.Source, "-3") }
            if (Test-XUUnityPython $command) { $pythonCmd = $command; break }
            $skipped += $name
        }
    }
}

if ($pythonCmd.Length -eq 0) {
    [Console]::Error.WriteLine("Python 3.10 or newer was not found. Tried: $($skipped -join ', '). Set PYTHON to the absolute path of a Python 3.10+ interpreter.")
    [Console]::Error.WriteLine("Note: on a fresh Windows the ""python"" command is often the Microsoft Store stub, which cannot run scripts and is rejected by this launcher.")
    exit 1
}
if ($skipped.Count -gt 0) {
    [Console]::Error.WriteLine("xuunity launcher: python=$($pythonCmd -join ' '); skipped: $($skipped -join ' ')")
}

[string[]]$pythonRest = @()
if ($pythonCmd.Length -gt 1) { $pythonRest = $pythonCmd[1..($pythonCmd.Length - 1)] }
$pythonExe = $pythonCmd[0]
& $pythonExe @pythonRest $launcher @args
exit $LASTEXITCODE
