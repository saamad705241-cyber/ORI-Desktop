param(
 [Parameter(Mandatory=$true)][int]$AppPid,
 [Parameter(Mandatory=$true)][string]$InstallerPath,
 [Parameter(Mandatory=$true)][string]$InstallDir,
 [Parameter(Mandatory=$true)][string]$ExpectedVersion,
 [Parameter(Mandatory=$true)][string]$ExpectedSha256,
 [Parameter(Mandatory=$true)][string]$LogPath,
 [Parameter(Mandatory=$true)][string]$RollbackDir,
 [Parameter(Mandatory=$true)][string]$InstallHelperPath,
 [Parameter(Mandatory=$true)][string]$BackendLogPath
)
$ErrorActionPreference = "Stop"
$installExe = [System.IO.Path]::GetFullPath((Join-Path $InstallDir "ORI.exe"))
$script:state = "installing"
$script:backend = $null
$script:app = $null
$script:started = $false
function Set-Status {
 param([string]$Heading,[string]$Detail,[int]$Value=-1,[switch]$Busy)
 if ($script:heading) { $script:heading.Text = $Heading }
 if ($script:detail) { $script:detail.Text = $Detail }
 if ($script:bar) {
  if ($Busy) { $script:bar.Style = [System.Windows.Forms.ProgressBarStyle]::Marquee; $script:bar.MarqueeAnimationSpeed = 24 }
  else { $script:bar.Style = [System.Windows.Forms.ProgressBarStyle]::Continuous; $script:bar.MarqueeAnimationSpeed = 0; $script:bar.Value = [Math]::Max(0,[Math]::Min(100,$Value)) }
 }
 [System.Windows.Forms.Application]::DoEvents()
}
function Quote-Arg {
 param([string]$Value)
 '"' + ($Value -replace '(\\*)"', '$1$1\"' -replace '(\\+)$', '$1$1') + '"'
}
function Read-InstallLog {
 if (!(Test-Path -LiteralPath $BackendLogPath)) { return }
 try {
  $log = (Get-Content -LiteralPath $BackendLogPath -Tail 24) -join [Environment]::NewLine
  if ($log -match "Running the SHA-256-verified") { Set-Status "Installing ORI $ExpectedVersion" "Windows Setup is replacing program files. Keep this window open." -1 -Busy }
  elseif ($log -match "Robocopy completed") { Set-Status "Backup created" "The previous ORI files are saved for rollback." 36 }
  elseif ($log -match "Waiting up to") { Set-Status "Preparing update" "Closing ORI and checking the current installation." 16 }
  elseif ($log -match "uninstall registration confirms") { Set-Status "Verifying installation" "Checking the new version registered with Windows." 92 }
 } catch { }
}
function Launch-UpdatedOri {
 if ($script:state -notin @("ready","launch-failed")) { return }
 $script:state = "launching"
 $script:launch.Enabled = $false
 $script:launch.Text = "STARTING..."
 Set-Status "Starting ORI $ExpectedVersion" "Checking startup token, version and executable path." -1 -Busy
 $token = [Guid]::NewGuid().ToString("N")
 $readyDir = Join-Path $env:LOCALAPPDATA "ORI\updates\startup"
 New-Item -ItemType Directory -Path $readyDir -Force | Out-Null
 $readyFile = Join-Path $readyDir ($token + ".ready")
 Remove-Item -LiteralPath $readyFile -Force -ErrorAction SilentlyContinue
 try {
  $script:app = Start-Process -FilePath $installExe -ArgumentList @("--ori-update-token=$token") -WorkingDirectory $InstallDir -PassThru
  $until = (Get-Date).AddSeconds(90)
  $startup = $null
  while ((Get-Date) -lt $until) {
   [System.Windows.Forms.Application]::DoEvents()
   if (Test-Path -LiteralPath $readyFile) { try { $startup = Get-Content -LiteralPath $readyFile -Raw | ConvertFrom-Json; break } catch { } }
   if (!(Get-Process -Id $script:app.Id -ErrorAction SilentlyContinue)) { throw "ORI exited before confirming startup." }
   Start-Sleep -Milliseconds 200
  }
  if (!$startup) { throw "ORI did not confirm startup within 90 seconds." }
  if ([int]$startup.pid -ne [int]$script:app.Id) { throw "ORI startup PID did not match." }
  if ([string]$startup.version -ne $ExpectedVersion) { throw "ORI reported version $($startup.version), expected $ExpectedVersion." }
  $reported = [System.IO.Path]::GetFullPath([string]$startup.executable)
  if (![string]::Equals($reported,$installExe,[System.StringComparison]::OrdinalIgnoreCase)) { throw "ORI started from an unexpected path: $reported" }
  for ($n=1; $n -le 15; $n++) {
   [System.Windows.Forms.Application]::DoEvents()
   if (!(Get-Process -Id $script:app.Id -ErrorAction SilentlyContinue)) { throw "ORI exited during the 15-second stability check." }
   Set-Status "Checking ORI startup" "Version verified. Stability check $n/15." -1 -Busy
   Start-Sleep -Seconds 1
  }
  Remove-Item -LiteralPath $readyFile -Force -ErrorAction SilentlyContinue
  if (Test-Path -LiteralPath $RollbackDir) { Remove-Item -LiteralPath $RollbackDir -Recurse -Force -ErrorAction SilentlyContinue }
  $script:state = "done"
  Set-Status "ORI $ExpectedVersion is ready" "The update and startup checks are complete." 100
  $script:launch.Text = "DONE"
  $script:launch.Enabled = $true
 } catch {
  if ($script:app -and (Get-Process -Id $script:app.Id -ErrorAction SilentlyContinue)) { try { Stop-Process -Id $script:app.Id -Force -ErrorAction SilentlyContinue } catch { } }
  $script:state = "launch-failed"
  Set-Status "ORI could not finish starting" "$($_.Exception.Message) The previous version backup has been kept. Retry Launch ORI." 100
  $script:launch.Text = "RETRY LAUNCH"
  $script:launch.Enabled = $true
 }
}
try {
 Add-Type -AssemblyName System.Windows.Forms
 Add-Type -AssemblyName System.Drawing
 [System.Windows.Forms.Application]::EnableVisualStyles()
 New-Item -ItemType Directory -Path (Split-Path -Parent $LogPath) -Force | Out-Null
 Start-Transcript -Path $LogPath -Append | Out-Null
 $script:started = $true
 $form = New-Object System.Windows.Forms.Form
 $form.Text = "ORI Update Assistant"
 $form.StartPosition = "CenterScreen"
 $form.ClientSize = New-Object System.Drawing.Size(540,300)
 $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
 $form.MaximizeBox = $false
 $form.BackColor = [System.Drawing.Color]::FromArgb(10,14,12)
 $form.ForeColor = [System.Drawing.Color]::FromArgb(235,245,239)
 $form.Font = New-Object System.Drawing.Font("Segoe UI",9)
 $brand = New-Object System.Windows.Forms.Label
 $brand.Text = "ORI  /  UPDATE ASSISTANT"
 $brand.Location = New-Object System.Drawing.Point(28,24)
 $brand.Size = New-Object System.Drawing.Size(480,28)
 $brand.Font = New-Object System.Drawing.Font("Segoe UI",14,[System.Drawing.FontStyle]::Bold)
 $brand.ForeColor = [System.Drawing.Color]::FromArgb(96,255,157)
 $form.Controls.Add($brand)
 $script:heading = New-Object System.Windows.Forms.Label
 $script:heading.Text = "Preparing ORI $ExpectedVersion"
 $script:heading.Location = New-Object System.Drawing.Point(30,78)
 $script:heading.Size = New-Object System.Drawing.Size(480,28)
 $script:heading.Font = New-Object System.Drawing.Font("Segoe UI",11,[System.Drawing.FontStyle]::Bold)
 $form.Controls.Add($script:heading)
 $script:detail = New-Object System.Windows.Forms.Label
 $script:detail.Text = "Your current ORI installation will be backed up before updating."
 $script:detail.Location = New-Object System.Drawing.Point(30,112)
 $script:detail.Size = New-Object System.Drawing.Size(480,44)
 $script:detail.ForeColor = [System.Drawing.Color]::FromArgb(170,190,180)
 $script:detail.AutoEllipsis = $true
 $form.Controls.Add($script:detail)
 $script:bar = New-Object System.Windows.Forms.ProgressBar
 $script:bar.Location = New-Object System.Drawing.Point(30,174)
 $script:bar.Size = New-Object System.Drawing.Size(480,13)
 $script:bar.Value = 8
 $form.Controls.Add($script:bar)
 $version = New-Object System.Windows.Forms.Label
 $version.Text = "TARGET VERSION  $ExpectedVersion"
 $version.Location = New-Object System.Drawing.Point(30,202)
 $version.Size = New-Object System.Drawing.Size(260,22)
 $version.ForeColor = [System.Drawing.Color]::FromArgb(130,150,140)
 $form.Controls.Add($version)
 $script:launch = New-Object System.Windows.Forms.Button
 $script:launch.Text = "INSTALLING..."
 $script:launch.Location = New-Object System.Drawing.Point(350,230)
 $script:launch.Size = New-Object System.Drawing.Size(160,38)
 $script:launch.Enabled = $false
 $script:launch.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
 $script:launch.BackColor = [System.Drawing.Color]::FromArgb(37,190,105)
 $script:launch.ForeColor = [System.Drawing.Color]::FromArgb(4,16,10)
 $script:launch.add_Click({
  if ($script:state -in @("ready","launch-failed")) { Launch-UpdatedOri }
  elseif ($script:state -eq "done" -or $script:state -eq "failed") { $form.Close() }
 })
 $form.Controls.Add($script:launch)
 $form.add_FormClosing({ if ($script:state -in @("installing","launching")) { $_.Cancel = $true } })
 $form.Show()
 [System.Windows.Forms.Application]::DoEvents()
 if ($ExpectedVersion -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$') { throw "Target version is invalid." }
 if ([System.IO.Path]::GetFileName($InstallerPath) -ne "ORI-Setup-$ExpectedVersion.exe") { throw "Installer filename does not match target version." }
 if (!(Test-Path -LiteralPath $InstallerPath -PathType Leaf) -or !(Test-Path -LiteralPath $InstallHelperPath -PathType Leaf)) { throw "The verified Setup installer or install helper is missing." }
 $hash = (Get-FileHash -LiteralPath $InstallerPath -Algorithm SHA256).Hash
 if (![string]::Equals($hash,$ExpectedSha256,[System.StringComparison]::OrdinalIgnoreCase)) { throw "Installer SHA-256 verification failed in the Update Assistant." }
 Set-Status "Preparing protected installation" "Starting the rollback-capable Windows Setup helper." 12
 $powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
 $parts = @("-NoLogo","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass",
  "-File",(Quote-Arg $InstallHelperPath),"-AppPid",$AppPid.ToString(),
  "-InstallerPath",(Quote-Arg $InstallerPath),"-InstallDir",(Quote-Arg $InstallDir),
  "-ExpectedVersion",$ExpectedVersion,"-ExpectedSha256",$ExpectedSha256,
  "-LogPath",(Quote-Arg $BackendLogPath),"-RollbackDir",(Quote-Arg $RollbackDir),
  "-NoDialog","-NoLaunch")
 if (Test-Path -LiteralPath $BackendLogPath) { Remove-Item -LiteralPath $BackendLogPath -Force }
 $script:backend = Start-Process -FilePath $powershell -ArgumentList ($parts -join " ") -WindowStyle Hidden -PassThru
 while (!$script:backend.HasExited) {
  [System.Windows.Forms.Application]::DoEvents()
  $script:backend.Refresh()
  Read-InstallLog
  Start-Sleep -Milliseconds 140
 }
 Read-InstallLog
 if ($script:backend.ExitCode -ne 0) {
  $tail = ""
  try { $tail = (Get-Content -LiteralPath $BackendLogPath -Tail 8) -join [Environment]::NewLine } catch { }
  throw "Windows Setup could not complete (exit $($script:backend.ExitCode)). $tail"
 }
 if (!(Test-Path -LiteralPath $installExe -PathType Leaf)) { throw "The new ORI.exe was not found after Setup." }
 Set-Status "Update installed successfully" "ORI $ExpectedVersion is ready. Click LAUNCH ORI when you are ready." 100
 $script:state = "ready"
 $script:launch.Text = "LAUNCH ORI"
 $script:launch.Enabled = $true
 while ($form.Visible) { [System.Windows.Forms.Application]::DoEvents(); Start-Sleep -Milliseconds 80 }
} catch {
 $reason = [string]$_.Exception.Message
 if ($script:heading) {
  Set-Status "Update could not be completed" "$reason Check the update log for details." 100
  $script:state = "failed"
  if ($script:launch) { $script:launch.Text = "CLOSE"; $script:launch.Enabled = $true }
  if ($form -and $form.Visible) {
   while ($form.Visible) { [System.Windows.Forms.Application]::DoEvents(); Start-Sleep -Milliseconds 80 }
  }
 } else {
  Write-Error $reason
 }
 exit 1
} finally {
 if ($script:started) { Stop-Transcript | Out-Null }
}