[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Repository = "saamad705241-cyber/ORI-Desktop"
$ApiVersion = "2022-11-28"

function Write-Step {
    param([string]$Message)
    Write-Host "[ORI UPDATE] $Message" -ForegroundColor Cyan
}

function Quote-ProcessArgument {
    param([string]$Value)
    return '"' + $Value.Replace('"', '\"') + '"'
}

try {
    Write-Step "Looking for the running ORI desktop application."
    $oriProcesses = @(Get-Process -Name "ORI" -ErrorAction SilentlyContinue)
    if ($oriProcesses.Count -ne 1) {
        if ($oriProcesses.Count -eq 0) {
            throw "ORI.exe is not running. Open the installed ORI 3.5.0 window, then run this bootstrap command again."
        }
        throw "More than one ORI.exe process is running. Close extra ORI windows and run this command again."
    }

    $oriProcess = $oriProcesses[0]
    $appPid = [int]$oriProcess.Id
    $exePath = ""
    try { $exePath = [string]$oriProcess.Path } catch {}
    if ([string]::IsNullOrWhiteSpace($exePath)) {
        try { $exePath = [string]$oriProcess.MainModule.FileName } catch {}
    }
    if ([string]::IsNullOrWhiteSpace($exePath) -or !(Test-Path -LiteralPath $exePath -PathType Leaf)) {
        throw "Windows did not provide the running ORI.exe path. Run PowerShell as the same Windows user that opened ORI."
    }

    $installDir = Split-Path -Parent $exePath
    if (!(Test-Path -LiteralPath (Join-Path $installDir "ORI.exe") -PathType Leaf)) {
        throw "The detected ORI installation folder is invalid: $installDir"
    }
    Write-Step "Detected ORI PID $appPid in: $installDir"

    Write-Step "Checking the latest official GitHub release."
    $apiUrl = "https://api.github.com/repos/$Repository/releases/latest"
    $headers = @{
        Accept = "application/vnd.github+json"
        "X-GitHub-Api-Version" = $ApiVersion
        "User-Agent" = "ORI-Desktop-One-Time-Updater"
    }
    $release = Invoke-RestMethod -Uri $apiUrl -Headers $headers -Method Get -TimeoutSec 30
    $tag = [string]$release.tag_name
    if ($tag -notmatch '^v\d+\.\d+\.\d+$') {
        throw "The official release tag is not a stable version: $tag"
    }
    $version = $tag.Substring(1)
    $zipName = "ORI-$version-Windows.zip"
    $checksumName = "$zipName.sha256"
    $assets = @($release.assets)
    $zipAsset = $assets | Where-Object { $_.name -eq $zipName } | Select-Object -First 1
    $checksumAsset = $assets | Where-Object { $_.name -eq $checksumName } | Select-Object -First 1
    if (!$zipAsset -or !$checksumAsset) {
        throw "Release $tag is missing its Windows ZIP or SHA-256 checksum."
    }
    foreach ($asset in @($zipAsset, $checksumAsset)) {
        $uri = [Uri]$asset.browser_download_url
        if ($uri.Scheme -ne "https" -or $uri.Host -ne "github.com") {
            throw "Release asset URL is not an official HTTPS GitHub URL: $($asset.name)"
        }
    }

    $stateRoot = Join-Path $env:LOCALAPPDATA "ORI\updates\bootstrap-$tag"
    $downloadRoot = Join-Path $stateRoot "downloads"
    $extractRoot = Join-Path $stateRoot "extracted"
    $zipPath = Join-Path $downloadRoot $zipName
    $checksumPath = Join-Path $downloadRoot $checksumName
    New-Item -ItemType Directory -Path $downloadRoot -Force | Out-Null
    if (Test-Path -LiteralPath $extractRoot) {
        Remove-Item -LiteralPath $extractRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $extractRoot -Force | Out-Null

    Write-Step "Downloading $zipName. This is a one-time bootstrap; no manual ZIP extraction is needed."
    Invoke-WebRequest -Uri $zipAsset.browser_download_url -OutFile $zipPath -UseBasicParsing -TimeoutSec 300
    Invoke-WebRequest -Uri $checksumAsset.browser_download_url -OutFile $checksumPath -UseBasicParsing -TimeoutSec 60

    $checksumText = Get-Content -LiteralPath $checksumPath -Raw
    $digestMatch = [Regex]::Match($checksumText, '(?i)\b([a-f0-9]{64})\b')
    if (!$digestMatch.Success) {
        throw "The release checksum file does not contain a SHA-256 digest."
    }
    $actualHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $expectedHash = $digestMatch.Groups[1].Value.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
        Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
        throw "SHA-256 verification failed. The downloaded package was discarded."
    }
    Write-Step "SHA-256 verified."

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
        $requiredEntry = $archive.Entries | Where-Object { $_.FullName -eq "ORI/ORI.exe" } | Select-Object -First 1
        $helperEntry = $archive.Entries | Where-Object { $_.FullName -eq "ORI/core/apply_update.ps1" } | Select-Object -First 1
        if (!$requiredEntry -or !$helperEntry) {
            throw "The official release ZIP is missing ORI/ORI.exe or its PowerShell update helper."
        }
    }
    finally {
        $archive.Dispose()
    }

    Write-Step "Extracting the verified release."
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractRoot -Force
    $sourceDir = Join-Path $extractRoot "ORI"
    $helperPath = Join-Path $sourceDir "core\apply_update.ps1"
    if (!(Test-Path -LiteralPath (Join-Path $sourceDir "ORI.exe") -PathType Leaf)) {
        throw "The extracted release does not contain ORI.exe."
    }
    if (!(Test-Path -LiteralPath $helperPath -PathType Leaf)) {
        throw "The extracted release does not contain the verified PowerShell installer."
    }

    $helperState = Join-Path $env:LOCALAPPDATA "ORI\updates\install-helper"
    New-Item -ItemType Directory -Path $helperState -Force | Out-Null
    $logPath = Join-Path $helperState "bootstrap-$version-$appPid.log"
    $rollbackDir = Join-Path $helperState "rollback-$version-$appPid"
    $windowsPowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

    $helperArguments = @(
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy", "Bypass",
        "-File", $helperPath,
        "-AppPid", [string]$appPid,
        "-SourceDir", $sourceDir,
        "-InstallDir", $installDir,
        "-LogPath", $logPath,
        "-RollbackDir", $rollbackDir
    )
    $argumentLine = (($helperArguments | ForEach-Object { Quote-ProcessArgument ([string]$_) }) -join " ")

    Write-Step "Starting the verified installer. ORI will close, update, verify its executable and restart."
    $installer = Start-Process -FilePath $windowsPowerShell -ArgumentList $argumentLine -WindowStyle Hidden -PassThru
    Start-Sleep -Milliseconds 700
    if ($installer.HasExited) {
        throw "The update helper exited before installation began. Check: $logPath"
    }

    $closeRequested = $oriProcess.CloseMainWindow()
    if (!$closeRequested) {
        Write-Warning "Windows could not close ORI automatically. Close the ORI window manually within 120 seconds; the installer is waiting."
    }
    else {
        Write-Step "Close request sent to ORI. The helper will wait for the old process to exit."
        $null = $oriProcess.WaitForExit(20000)
    }

    Write-Host ""
    Write-Host "Bootstrap installer started for ORI $version." -ForegroundColor Green
    Write-Host "Install log: $logPath"
    Write-Host "If ORI does not reopen, send this log file. Do not repeatedly run the updater."
}
catch {
    Write-Host ""
    Write-Host "ORI bootstrap update did not start: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
