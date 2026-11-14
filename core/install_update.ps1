param(
    [Parameter(Mandatory = $true)][int]$AppPid,
    [Parameter(Mandatory = $true)][string]$InstallerPath,
    [Parameter(Mandatory = $true)][string]$InstallDir,
    [Parameter(Mandatory = $true)][string]$LogPath,
    [Parameter(Mandatory = $true)][string]$RollbackDir
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$transcriptStarted = $false
$backupReady = $false
$installExe = Join-Path $InstallDir "ORI.exe"

function Invoke-RobocopyChecked {
    param([string]$From, [string]$To, [switch]$Mirror)
    $copyArgs = @($From, $To, "/E", "/COPY:DAT", "/DCOPY:DAT", "/R:2", "/W:1", "/NP", "/NFL", "/NDL")
    if ($Mirror) { $copyArgs += "/MIR" }
    & robocopy @copyArgs
    $code = $LASTEXITCODE
    if ($code -ge 8) { throw "Robocopy failed with exit code $code ($From -> $To)." }
    Write-Output "Robocopy completed with code $code."
}

try {
    New-Item -ItemType Directory -Path (Split-Path -Parent $LogPath) -Force | Out-Null
    Start-Transcript -Path $LogPath -Append | Out-Null
    $transcriptStarted = $true
    Write-Output "ORI installer updater started: $(Get-Date -Format o)"
    if (!(Test-Path -LiteralPath $InstallerPath -PathType Leaf)) { throw "Verified installer is missing: $InstallerPath" }
    if (!(Test-Path -LiteralPath $installExe -PathType Leaf)) { throw "Installed ORI.exe is missing: $installExe" }
    if (!(Test-Path -LiteralPath (Join-Path $InstallDir "unins000.exe") -PathType Leaf)) {
        throw "This copy is not registered as an installed ORI setup. Run ORI-Setup.exe once before using in-app updates."
    }

    Write-Output "Waiting up to 120 seconds for ORI PID $AppPid to exit."
    if (Get-Process -Id $AppPid -ErrorAction SilentlyContinue) {
        Wait-Process -Id $AppPid -Timeout 120 -ErrorAction SilentlyContinue
    }
    if (Get-Process -Id $AppPid -ErrorAction SilentlyContinue) {
        throw "ORI PID $AppPid did not close within 120 seconds."
    }

    if (Test-Path -LiteralPath $RollbackDir) { Remove-Item -LiteralPath $RollbackDir -Recurse -Force }
    New-Item -ItemType Directory -Path $RollbackDir -Force | Out-Null
    Invoke-RobocopyChecked -From $InstallDir -To $RollbackDir
    if (!(Test-Path -LiteralPath (Join-Path $RollbackDir "ORI.exe") -PathType Leaf)) {
        throw "Rollback copy of ORI.exe was not created."
    }
    $backupReady = $true

    Write-Output "Running the SHA-256-verified ORI Setup installer silently."
    $arguments = @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
        "/CLOSEAPPLICATIONS", "/DIR=`"$InstallDir`""
    )
    $setup = Start-Process -FilePath $InstallerPath -ArgumentList $arguments -Wait -PassThru
    if ($setup.ExitCode -ne 0) { throw "ORI Setup exited with code $($setup.ExitCode)." }
    if (!(Test-Path -LiteralPath $installExe -PathType Leaf)) { throw "Setup completed but ORI.exe is missing." }
    if (!(Test-Path -LiteralPath (Join-Path $InstallDir "unins000.exe") -PathType Leaf)) {
        throw "Setup completed but the ORI uninstaller was not registered."
    }

    $token = [Guid]::NewGuid().ToString("N")
    $readyDir = Join-Path $env:LOCALAPPDATA "ORI\updates\startup"
    New-Item -ItemType Directory -Path $readyDir -Force | Out-Null
    $readyFile = Join-Path $readyDir ($token + ".ready")
    Remove-Item -LiteralPath $readyFile -Force -ErrorAction SilentlyContinue
    $newProcess = Start-Process -FilePath $installExe -ArgumentList @("--ori-update-token=$token") -WorkingDirectory $InstallDir -PassThru

    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline -and !(Test-Path -LiteralPath $readyFile)) {
        if (!(Get-Process -Id $newProcess.Id -ErrorAction SilentlyContinue)) {
            throw "Updated ORI exited before reporting startup ready (PID $($newProcess.Id))."
        }
        Start-Sleep -Milliseconds 250
    }
    if (!(Test-Path -LiteralPath $readyFile)) {
        throw "Updated ORI did not report startup readiness within 45 seconds."
    }
    Start-Sleep -Seconds 5
    if (!(Get-Process -Id $newProcess.Id -ErrorAction SilentlyContinue)) {
        throw "Updated ORI exited shortly after reporting startup ready."
    }
    Remove-Item -LiteralPath $readyFile -Force -ErrorAction SilentlyContinue
    Write-Output "UPDATE SUCCESS. Setup completed and ORI startup was verified (PID $($newProcess.Id))."
}
catch {
    Write-Output "UPDATE FAILED: $($_.Exception.Message)"
    if ($backupReady -and (Test-Path -LiteralPath (Join-Path $RollbackDir "ORI.exe") -PathType Leaf)) {
        try {
            Write-Output "Restoring the previous installed program files."
            Invoke-RobocopyChecked -From $RollbackDir -To $InstallDir -Mirror
            Start-Process -FilePath $installExe -WorkingDirectory $InstallDir | Out-Null
            Write-Output "ROLLBACK SUCCESS. Previous ORI was restored and launched."
        }
        catch {
            Write-Output "ROLLBACK FAILED: $($_.Exception.Message)"
        }
    }
    exit 1
}
finally {
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
}
