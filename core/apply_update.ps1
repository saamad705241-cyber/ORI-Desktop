param(
    [Parameter(Mandatory = $true)][int]$AppPid,
    [Parameter(Mandatory = $true)][string]$SourceDir,
    [Parameter(Mandatory = $true)][string]$InstallDir,
    [Parameter(Mandatory = $true)][string]$LogPath,
    [Parameter(Mandatory = $true)][string]$RollbackDir
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$transcriptStarted = $false
$backupReady = $false
$installExe = Join-Path $InstallDir "ORI.exe"
$sourceExe = Join-Path $SourceDir "ORI.exe"
$rollbackExe = Join-Path $RollbackDir "ORI.exe"

function Invoke-VerifiedRobocopy {
    param([string]$From, [string]$To)
    $preserveNames = @("memory", "downloads", "screenshots", "logs", (Join-Path "config" "certs"))
    $excludeDirs = @(
        foreach ($name in $preserveNames) {
            $candidate = Join-Path $From $name
            if (Test-Path -LiteralPath $candidate -PathType Container) { $candidate }
        }
    )
    $copyArgs = @($From, $To, "/E", "/COPY:DAT", "/DCOPY:DAT", "/R:3", "/W:2", "/NP", "/NFL", "/NDL", "/XF", "api_keys.json", "*.log")
    if ($excludeDirs.Count -gt 0) {
        $copyArgs += "/XD"
        $copyArgs += $excludeDirs
    }
    & robocopy @copyArgs
    $copyExitCode = $LASTEXITCODE
    if ($copyExitCode -ge 8) {
        throw "Robocopy failed with exit code $copyExitCode while copying '$From' to '$To'."
    }
    Write-Output "Robocopy completed with code $copyExitCode (0-7 are successful copy outcomes)."
}

try {
    $logParent = Split-Path -Parent $LogPath
    New-Item -ItemType Directory -Path $logParent -Force | Out-Null
    Start-Transcript -Path $LogPath -Append | Out-Null
    $transcriptStarted = $true
    Write-Output "ORI self-update helper started: $(Get-Date -Format o)"
    Write-Output "Source: $SourceDir"
    Write-Output "Install: $InstallDir"
    if (!(Test-Path -LiteralPath $sourceExe -PathType Leaf)) { throw "Staged ORI.exe is missing: $sourceExe" }
    if (!(Test-Path -LiteralPath $installExe -PathType Leaf)) { throw "Installed ORI.exe is missing: $installExe" }

    Write-Output "Waiting up to 120 seconds for ORI PID $AppPid to exit."
    if (Get-Process -Id $AppPid -ErrorAction SilentlyContinue) {
        Wait-Process -Id $AppPid -Timeout 120 -ErrorAction SilentlyContinue
    }
    if (Get-Process -Id $AppPid -ErrorAction SilentlyContinue) {
        throw "ORI PID $AppPid did not close within 120 seconds. Close ORI and retry."
    }

    Write-Output "ORI exited. Creating rollback copy."
    if (Test-Path -LiteralPath $RollbackDir) { Remove-Item -LiteralPath $RollbackDir -Recurse -Force }
    New-Item -ItemType Directory -Path $RollbackDir -Force | Out-Null
    Invoke-VerifiedRobocopy -From $InstallDir -To $RollbackDir
    if (!(Test-Path -LiteralPath $rollbackExe -PathType Leaf)) { throw "Rollback copy of ORI.exe was not created." }
    $backupReady = $true

    try {
        Write-Output "Copying staged program files."
        Invoke-VerifiedRobocopy -From $SourceDir -To $InstallDir
        $sourceHash = (Get-FileHash -LiteralPath $sourceExe -Algorithm SHA256).Hash
        $installedHash = (Get-FileHash -LiteralPath $installExe -Algorithm SHA256).Hash
        if ($sourceHash -ne $installedHash) { throw "Installed ORI.exe SHA-256 does not match the staged executable." }
        Write-Output "Installed ORI.exe SHA-256 verified."
        $newProcess = Start-Process -FilePath $installExe -WorkingDirectory $InstallDir -PassThru
        Start-Sleep -Seconds 5
        if (!(Get-Process -Id $newProcess.Id -ErrorAction SilentlyContinue)) {
            throw "Updated ORI exited immediately after launch (PID $($newProcess.Id))."
        }
        Write-Output "SELF-UPDATE SUCCESS. Updated ORI process PID=$($newProcess.Id)"
    }
    catch {
        Write-Output "UPDATE FAILED: $($_.Exception.Message)"
        if ($backupReady -and (Test-Path -LiteralPath $rollbackExe -PathType Leaf)) {
            try {
                Write-Output "Restoring previous program files."
                Invoke-VerifiedRobocopy -From $RollbackDir -To $InstallDir
                $restoredHash = (Get-FileHash -LiteralPath $installExe -Algorithm SHA256).Hash
                $backupHash = (Get-FileHash -LiteralPath $rollbackExe -Algorithm SHA256).Hash
                if ($restoredHash -ne $backupHash) { throw "Rollback executable hash does not match backup." }
                Start-Process -FilePath $installExe -WorkingDirectory $InstallDir | Out-Null
                Write-Output "ROLLBACK SUCCESS. Previous ORI build restored and restarted."
            }
            catch {
                Write-Output "ROLLBACK FAILED: $($_.Exception.Message)"
            }
        }
        throw
    }
}
catch {
    Write-Output "SELF-UPDATE FAILED: $($_.Exception.Message)"
    exit 1
}
finally {
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
}
