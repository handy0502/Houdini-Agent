param(
    [string]$HoudiniVersion = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SideFxRoot = Join-Path $env:ProgramFiles "Side Effects Software"

$Installs = Get-ChildItem -LiteralPath $SideFxRoot -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^Houdini (\d+)\.(\d+)\.(\d+)$' } |
    ForEach-Object {
        $null = $_.Name -match '^Houdini (\d+)\.(\d+)\.(\d+)$'
        [pscustomobject]@{
            Directory = $_.FullName
            Version = [version]("{0}.{1}.{2}" -f $Matches[1], $Matches[2], $Matches[3])
        }
    } |
    Where-Object { $_.Version -ge [version]'19.5.0' } |
    Sort-Object Version -Descending

if ($HoudiniVersion) {
    $Installs = $Installs | Where-Object {
        $_.Version.ToString().StartsWith($HoudiniVersion + ".") -or
        $_.Version.ToString() -eq $HoudiniVersion
    }
}

$Install = $Installs | Select-Object -First 1
if (-not $Install) {
    throw "No compatible Houdini installation found (requires 19.5+)."
}

$Hfs = $Install.Directory
$HoudiniExe = Join-Path $Hfs "bin\houdini.exe"
$PythonHome = Get-ChildItem -LiteralPath $Hfs -Directory |
    Where-Object {
        $_.Name -match '^python\d+$' -and
        (Test-Path -LiteralPath (Join-Path $_.FullName "python.exe")) -and
        (Test-Path -LiteralPath (Join-Path $_.FullName "pythonw.exe"))
    } |
    Sort-Object { [int]($_.Name -replace '^python', '') } -Descending |
    Select-Object -First 1

if (-not (Test-Path -LiteralPath $HoudiniExe) -or -not $PythonHome) {
    throw "The selected Houdini installation is incomplete: $Hfs"
}

$PythonExe = Join-Path $PythonHome.FullName "python.exe"
$PythonwExe = Join-Path $PythonHome.FullName "pythonw.exe"
$SitePackages = Join-Path $PythonHome.FullName "lib\site-packages"
$UiForced = Join-Path $PythonHome.FullName "lib\site-packages-ui-forced"
$Forced = Join-Path $PythonHome.FullName "lib\site-packages-forced"

# The regular Python bundled with Houdini does not add its Qt paths by itself.
# Keep it outside Houdini (so `import hou` stays unavailable) while reusing the
# matching PySide6 runtime for the standalone Agent window.
$env:HFS = $Hfs
$env:PATH = (Join-Path $Hfs "bin") + ";" + $env:PATH
$PythonPaths = @($UiForced, $Forced, $SitePackages) | Where-Object { Test-Path -LiteralPath $_ }
if ($env:PYTHONPATH) {
    $PythonPaths += $env:PYTHONPATH
}
$env:PYTHONPATH = $PythonPaths -join ";"

Push-Location $RepoRoot
try {
    & $PythonExe -B -c "from houdini_agent.launcher.houdini_discovery import install_all_packages; print(install_all_packages(r'$($RepoRoot.Replace("'", "''"))'))"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install the Houdini Agent bridge package."
    }

    & $PythonExe -B -c "from houdini_agent.bridge.client import BridgeClient; import sys; sys.exit(0 if BridgeClient().ping() else 1)"
    $BridgeReady = $LASTEXITCODE -eq 0
    if (-not $BridgeReady) {
        Start-Process -FilePath $HoudiniExe -WorkingDirectory $Hfs
        Write-Host "Started a new Houdini process so the updated bridge package can load."
    }

    Start-Process -FilePath $PythonwExe -ArgumentList @((Join-Path $RepoRoot "launcher.py")) -WorkingDirectory $RepoRoot
    Write-Host "Started Houdini Agent with Houdini $($Install.Version)."
    Write-Host "Bridge endpoint: 127.0.0.1:45172 (auto-fallback through 45192)."
} finally {
    Pop-Location
}
