param(
    [Parameter(Mandatory = $true)][int]$AppPid,
    [Parameter(Mandatory = $true)][string]$UninstallerPath,
    [Parameter(Mandatory = $true)][string]$LogPath
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$started = $false
try {
    New-Item -ItemType Directory -Path (Split-Path -Parent $LogPath) -Force | Out-Null
    Start-Transcript -Path $LogPath -Append | Out-Null
    $started = $true
    Write-Output "ORI uninstaller launcher started: $(Get-Date -Format o)"
    if (!(Test-Path -LiteralPath $UninstallerPath -PathType Leaf)) {
        throw "ORI uninstaller was not found: $UninstallerPath"
    }
    if (Get-Process -Id $AppPid -ErrorAction SilentlyContinue) {
        Wait-Process -Id $AppPid -Timeout 120 -ErrorAction SilentlyContinue
    }
    if (Get-Process -Id $AppPid -ErrorAction SilentlyContinue) {
        throw "ORI did not close within 120 seconds. Uninstall was not started."
    }
    Write-Output "Launching the ORI uninstall wizard. User data under LocalAppData\ORI is not removed."
    $uninstaller = Start-Process -FilePath $UninstallerPath -ArgumentList @("/LOG=$LogPath") -PassThru -Wait
    Write-Output "ORI uninstaller exited with code $($uninstaller.ExitCode)."
}
catch {
    Write-Output "UNINSTALL LAUNCH FAILED: $($_.Exception.Message)"
    exit 1
}
finally {
    if ($started) { Stop-Transcript | Out-Null }
}
