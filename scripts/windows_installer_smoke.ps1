# Windows CI smoke test for the packaged installer. No network changes.
# The test creates an isolated temporary installation, checks bundled EXE,
# invokes read-only diagnostics, and uninstalls through Inno Setup.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Every external EXE is time-bounded. A hung GUI, UAC dialog or Inno
# uninstaller must fail the CI job, not consume the runner for an hour.
function Invoke-Bounded {
    param(
        [Parameter(Mandatory=$true)][string]$Label,
        [Parameter(Mandatory=$true)][string]$FilePath,
        [Parameter(Mandatory=$true)][string]$Arguments,
        [int]$TimeoutSeconds = 90
    )
    Write-Host "SMOKE START: $Label (timeout ${TimeoutSeconds}s)"
    $proc = Start-Process -FilePath $FilePath -ArgumentList $Arguments -PassThru
    try {
        if (-not $proc.WaitForExit([int]($TimeoutSeconds * 1000))) {
            try {
                # PowerShell 7 / .NET supports killing the process tree.
                $proc.Kill($true)
                [void]$proc.WaitForExit(5000)
            }
            catch {
                Write-Warning "Could not fully terminate $Label : $_"
            }
            throw "SMOKE TIMEOUT: $Label exceeded ${TimeoutSeconds}s; check Inno dialogs and application child processes"
        }
        $proc.Refresh()
        $exitCode = [int]$proc.ExitCode
        Write-Host "SMOKE DONE: $Label (exit $exitCode)"
        return [pscustomobject]@{ ExitCode = $exitCode }
    }
    finally {
        $proc.Dispose()
    }
}


$installer = (Resolve-Path 'dist/VORQELI-Connect-Setup.exe').Path
$installDir = Join-Path $env:RUNNER_TEMP 'VORQELI Installer Smoke'
$reportFile = Join-Path $env:RUNNER_TEMP 'vorqeli-installed-doctor.json'
$uninstall = Join-Path $installDir 'unins000.exe'
$installed = Join-Path $installDir 'VORQELI-Connect.exe'
$uninstallExit = $null

if (Test-Path $installDir) {
    throw 'Smoke-test destination must not already exist'
}

try {
    $args = '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG="' + (Join-Path $env:RUNNER_TEMP 'vorqeli-smoke-setup.log') + '" /DIR="' + $installDir + '"'
    $process = Invoke-Bounded -Label 'initial-install' -FilePath $installer -Arguments $args -TimeoutSeconds 120
    if ($process.ExitCode -ne 0) {
        throw "Installer failed with code $($process.ExitCode)"
    }
    if (-not (Test-Path $installed)) {
        throw 'Installed EXE is missing'
    }
    foreach ($resource in @('LICENSE', 'NOTICE.md', 'QUICK_START.md')) {
        if (-not (Test-Path (Join-Path $installDir $resource))) {
            throw "Required installed resource is missing: $resource"
        }
    }
    $process = Invoke-Bounded -Label 'installed-self-test' -FilePath $installed -Arguments '--self-test' -TimeoutSeconds 90
    if ($process.ExitCode -ne 0) {
        throw "Installed EXE self-test failed: $($process.ExitCode)"
    }
    $args = '--doctor --doctor-output "' + $reportFile + '"'
    $process = Invoke-Bounded -Label 'installed-diagnostics' -FilePath $installed -Arguments $args -TimeoutSeconds 90
    if ($process.ExitCode -ne 0) {
        throw "Installed EXE doctor test failed: $($process.ExitCode)"
    }
    if (-not (Test-Path $reportFile)) {
        throw 'Installed EXE did not write diagnostic report'
    }
    $report = Get-Content -Raw $reportFile | ConvertFrom-Json
    if ($report.schema -ne 1 -or $report.platform -ne 'windows') {
        throw 'Unexpected installed diagnostic schema or platform'
    }
    if ($report.PSObject.Properties.Name -contains 'telegram_secret') {
        throw 'A Telegram secret field appeared in the report'
    }
    # Simulate an already-open VORQELI window using its named instance mutex.
    # Cleanup must fail CLOSED, not delete startup settings / DNS while the app runs.
    $mutex = [System.Threading.Mutex]::new($false, 'Local\VORQELI-Connect-Instance')
    try {
        $process = Invoke-Bounded -Label 'blocked-cleanup-check' -FilePath $installed -Arguments '--uninstall-cleanup' -TimeoutSeconds 60
        if ($process.ExitCode -ne 8) {
            throw "Uninstall safety guard must block a live instance (got $($process.ExitCode))"
        }
        # The installer must also refuse to overwrite a still-running app.
        $args = '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG="' + (Join-Path $env:RUNNER_TEMP 'vorqeli-smoke-setup.log') + '" /DIR="' + $installDir + '"'
        $upgrade = Invoke-Bounded -Label 'blocked-in-place-upgrade' -FilePath $installer -Arguments $args -TimeoutSeconds 60
        if ($upgrade.ExitCode -eq 0) {
            throw 'Installer unexpectedly accepted an upgrade while the app mutex was held'
        }
        if (-not (Test-Path $installed)) {
            throw 'Failed upgrade damaged the already installed EXE'
        }
        # Uninstallation must also abort while the GUI mutex exists. Inno
        # Setup calls --uninstall-cleanup before deleting a single installed
        # executable; this exercises that contract with a real Inno EXE.
        $blockedLog = Join-Path $env:RUNNER_TEMP 'vorqeli-smoke-blocked-uninstall.log'
        $blockedArgs = '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG="' + $blockedLog + '"'
        $blockedRemoval = Invoke-Bounded -Label 'blocked-uninstall' -FilePath $uninstall `
            -Arguments $blockedArgs -TimeoutSeconds 60
        if ($blockedRemoval.ExitCode -eq 0) {
            throw 'Uninstaller ignored the active VORQELI instance mutex'
        }
        if (-not (Test-Path $installed)) {
            throw 'Blocked uninstall removed the installed executable'
        }
    }
    finally {
        $mutex.Dispose()
    }
    # The previously blocked update MUST succeed after the process exits,
    # without uninstalling the previous version or losing its settings.
    $upgrade = Invoke-Bounded -Label 'unblocked-in-place-upgrade' -FilePath $installer -Arguments $args -TimeoutSeconds 120
    if ($upgrade.ExitCode -ne 0) {
        throw "In-place upgrade failed after releasing app mutex: $($upgrade.ExitCode)"
    }
    if (-not (Test-Path $installed)) {
        throw 'Upgraded executable missing'
    }
    $expectedHash = (Get-FileHash -LiteralPath 'dist/VORQELI-Connect.exe' -Algorithm SHA256).Hash
    $installedHash = (Get-FileHash -LiteralPath $installed -Algorithm SHA256).Hash
    if ($installedHash -ne $expectedHash) {
        throw 'Installed app differs from the newly built executable'
    }
    $postUpgrade = Invoke-Bounded -Label 'upgraded-self-test' -FilePath $installed -Arguments '--self-test' -TimeoutSeconds 90
    if ($postUpgrade.ExitCode -ne 0) {
        throw "Upgraded EXE self-test failed: $($postUpgrade.ExitCode)"
    }
    Write-Host 'Install, running-app guards and in-place upgrade passed.' 
}
finally {
    if (Test-Path $uninstall) {
        $process = Invoke-Bounded -Label 'final-uninstall' -FilePath $uninstall -Arguments '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART' -TimeoutSeconds 120
        $uninstallExit = $process.ExitCode
    }
}
if ($null -eq $uninstallExit) {
    throw 'Inno Setup uninstaller was not generated'
}
if ($uninstallExit -ne 0) {
    throw "Uninstaller failed: $uninstallExit"
}
if (Test-Path $installed) {
    throw 'Uninstaller left installed EXE behind'
}
Write-Host 'VORQELI installer smoke test complete.'
