param(
    [Parameter(Mandatory = $true)][int]$AppPid,
    [Parameter(Mandatory = $true)][string]$InstallerPath,
    [Parameter(Mandatory = $true)][string]$InstallDir,
    [Parameter(Mandatory = $true)][string]$ExpectedVersion,
    [Parameter(Mandatory = $true)][string]$LogPath,
    [Parameter(Mandatory = $true)][string]$RollbackDir,
    [string]$ExpectedSha256 = "",
    [switch]$NoDialog,
    [switch]$NoLaunch
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$transcriptStarted = $false
$backupReady = $false
$newProcess = $null
$installDir = [System.IO.Path]::GetFullPath($InstallDir)
$installExe = [System.IO.Path]::GetFullPath((Join-Path $installDir "ORI.exe"))

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
    Write-Output "Target version: $ExpectedVersion"
    Write-Output "Install directory: $installDir"
    if ($ExpectedVersion -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$') { throw "ExpectedVersion must be a stable MAJOR.MINOR.PATCH value." }
    if ([System.IO.Path]::GetFileName($InstallerPath) -ne "ORI-Setup-$ExpectedVersion.exe") { throw "Installer filename does not match target version $ExpectedVersion." }
    if (!(Test-Path -LiteralPath $InstallerPath -PathType Leaf)) { throw "Verified installer is missing: $InstallerPath" }
    if (![string]::IsNullOrWhiteSpace($ExpectedSha256)) {
        if ($ExpectedSha256 -notmatch "^[a-fA-F0-9]{64}$") { throw "ExpectedSha256 is not a valid digest." }
        $initialHash = (Get-FileHash -LiteralPath $InstallerPath -Algorithm SHA256).Hash
        if (![string]::Equals($initialHash, $ExpectedSha256, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Installer SHA-256 verification failed before installation."
        }
    }
    if (!(Test-Path -LiteralPath $installExe -PathType Leaf)) { throw "Installed ORI.exe is missing: $installExe" }
    if (!(Test-Path -LiteralPath (Join-Path $InstallDir "unins000.exe") -PathType Leaf)) {
        throw "This copy is not registered as an installed ORI setup. Run ORI-Setup.exe once before using in-app updates."
    }
    $previousUninstallEntry = Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*" -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -eq "ORI Personal AI Desktop Assistant" } |
        Select-Object -First 1
    if (!$previousUninstallEntry) {
        throw "The previous ORI Windows uninstall registration could not be found; update was not started."
    }
    $previousUninstallKey = [string]$previousUninstallEntry.PSPath
    $previousRegisteredVersion = [string]$previousUninstallEntry.DisplayVersion
    if ([string]::IsNullOrWhiteSpace($previousUninstallKey) -or [string]::IsNullOrWhiteSpace($previousRegisteredVersion)) {
        throw "The previous ORI Windows uninstall registration is incomplete; update was not started."
    }
    Write-Output "Previous Windows registration captured: ORI $previousRegisteredVersion."

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

    if (![string]::IsNullOrWhiteSpace($ExpectedSha256)) {
        $currentHash = (Get-FileHash -LiteralPath $InstallerPath -Algorithm SHA256).Hash
        if (![string]::Equals($currentHash, $ExpectedSha256, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Installer SHA-256 changed before execution."
        }
    }
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

    $uninstallEntry = Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*" -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -eq "ORI Personal AI Desktop Assistant" } |
        Select-Object -First 1
    if (!$uninstallEntry -or [string]$uninstallEntry.DisplayVersion -ne $ExpectedVersion) {
        $registeredVersion = if ($uninstallEntry) { [string]$uninstallEntry.DisplayVersion } else { "missing" }
        throw "Windows registered ORI version $registeredVersion, expected $ExpectedVersion."
    }
    Write-Output "Windows uninstall registration confirms ORI $ExpectedVersion."

    if ($NoLaunch) {
        Write-Output "UPDATE SUCCESS. ORI $ExpectedVersion installed and verified; waiting for the user to launch ORI."
        exit 0
    }

    $token = [Guid]::NewGuid().ToString("N")
    $readyDir = Join-Path $env:LOCALAPPDATA "ORI\updates\startup"
    New-Item -ItemType Directory -Path $readyDir -Force | Out-Null
    $readyFile = Join-Path $readyDir ($token + ".ready")
    Remove-Item -LiteralPath $readyFile -Force -ErrorAction SilentlyContinue
    $newProcess = Start-Process -FilePath $installExe -ArgumentList @("--ori-update-token=$token") -WorkingDirectory $InstallDir -PassThru

    $deadline = (Get-Date).AddSeconds(90)
    $startup = $null
    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $readyFile) {
            try { $startup = Get-Content -LiteralPath $readyFile -Raw | ConvertFrom-Json -ErrorAction Stop; break }
            catch { Write-Output "Startup marker is not complete yet: $($_.Exception.Message)" }
        }
        if (!(Get-Process -Id $newProcess.Id -ErrorAction SilentlyContinue)) {
            throw "Updated ORI exited before reporting startup ready (PID $($newProcess.Id))."
        }
        Start-Sleep -Milliseconds 250
    }
    if (!$startup) { throw "Updated ORI did not report startup readiness within 90 seconds." }
    if ([int]$startup.pid -ne [int]$newProcess.Id) {
        throw "Startup marker came from PID $($startup.pid), but Windows launched PID $($newProcess.Id)."
    }
    if ([string]$startup.version -ne $ExpectedVersion) {
        throw "The launched application reported version $($startup.version), expected $ExpectedVersion."
    }
    if ([string]::IsNullOrWhiteSpace([string]$startup.executable)) {
        throw "The updated application did not report its executable path."
    }
    $reportedExecutable = [System.IO.Path]::GetFullPath([string]$startup.executable)
    if (![string]::Equals($reportedExecutable, $installExe, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "The startup handshake came from $reportedExecutable, not the installed executable $installExe."
    }
    Write-Output "Startup handshake verified: ORI $($startup.version), PID $($startup.pid), executable $reportedExecutable."
    for ($i = 0; $i -lt 15; $i++) {
        if (!(Get-Process -Id $newProcess.Id -ErrorAction SilentlyContinue)) {
            throw "Updated ORI exited during the 15-second post-start stability check."
        }
        Start-Sleep -Seconds 1
    }
    $newProcess.Refresh()
    if ($newProcess.HasExited -or !(Get-Process -Id $newProcess.Id -ErrorAction SilentlyContinue)) {
        throw "Updated ORI exited at the end of the 15-second post-start stability check."
    }
    Write-Output "Final process-liveness check passed after the full 15-second stability window."
    Remove-Item -LiteralPath $readyFile -Force -ErrorAction SilentlyContinue
    Write-Output "UPDATE SUCCESS. ORI $ExpectedVersion installed and relaunched from the registered install directory (PID $($newProcess.Id))."
}
catch {
    $failure = [string]$_.Exception.Message
    Write-Output "UPDATE FAILED: $failure"
    if ($newProcess -and (Get-Process -Id $newProcess.Id -ErrorAction SilentlyContinue)) {
        try { Stop-Process -Id $newProcess.Id -Force -ErrorAction Stop; Start-Sleep -Milliseconds 500 }
        catch { Write-Output "Could not stop unverified updated process: $($_.Exception.Message)" }
    }
    if ($backupReady -and (Test-Path -LiteralPath (Join-Path $RollbackDir "ORI.exe") -PathType Leaf)) {
        try {
            Write-Output "Restoring the previous installed program files."
            Invoke-RobocopyChecked -From $RollbackDir -To $InstallDir -Mirror
            Set-ItemProperty -LiteralPath $previousUninstallKey -Name DisplayVersion -Value $previousRegisteredVersion
            Write-Output "Restored Windows uninstall DisplayVersion to $previousRegisteredVersion."
            Start-Process -FilePath $installExe -WorkingDirectory $InstallDir | Out-Null
            Write-Output "ROLLBACK SUCCESS. Previous ORI files and Windows version registration were restored and launched."
        }
        catch {
            Write-Output "ROLLBACK FAILED: $($_.Exception.Message)"
        }
    }
    if (!$NoDialog) {
        try {
            Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
            [System.Windows.Forms.MessageBox]::Show(
                "ORI $ExpectedVersion could not be installed and verified.`r`n`r`nThe previous build was restored when possible.`r`n`r`nReason: $failure`r`n`r`nPlease share this log with the developer:`r`n$LogPath",
                "ORI update could not be completed",
                [System.Windows.Forms.MessageBoxButtons]::OK,
                [System.Windows.Forms.MessageBoxIcon]::Warning
            ) | Out-Null
        }
        catch { Write-Output "Could not display update failure details: $($_.Exception.Message)" }
    }
    else {
        Write-Output "Update failure dialog suppressed by the automated test runner."
    }
    exit 1
}
finally {
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
}
