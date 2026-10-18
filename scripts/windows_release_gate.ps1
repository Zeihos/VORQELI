# Manual release-candidate gate. NEVER modifies the system or executes EXE files.
# Run only after signing BOTH files, regenerating SHA256SUMS.txt and independently
# verifying that the expected publisher certificate thumbprint is trustworthy.
[CmdletBinding()]
param(
    [string]$ArtifactsDir = 'dist',
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-fA-F0-9]{40}$')]
    [string]$TrustedSignerThumbprint
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Fail([string]$message) {
    throw "VORQELI RELEASE BLOCKED: $message"
}

$folder = (Resolve-Path -LiteralPath $ArtifactsDir -ErrorAction Stop).Path
$names = @('VORQELI-Connect.exe', 'VORQELI-Connect-Setup.exe')
$hashFile = Join-Path $folder 'SHA256SUMS.txt'
if (-not (Test-Path -LiteralPath $hashFile -PathType Leaf)) { Fail 'SHA256SUMS.txt is missing' }
$lines = @(Get-Content -LiteralPath $hashFile -Encoding UTF8 | Where-Object { $_.Trim() })
if ($lines.Count -ne $names.Count) { Fail 'Checksum manifest must contain exactly two nonempty entries' }
$expected = @{}
foreach ($line in $lines) {
    if ($line -cnotmatch '^([a-fA-F0-9]{64})  (VORQELI-Connect(?:-Setup)?\.exe)$') {
        Fail 'Invalid checksum entry or unknown file name'
    }
    $digest = $Matches[1].ToLowerInvariant()
    $name = $Matches[2]
    if ($expected.ContainsKey($name)) { Fail "Duplicate checksum entry: $name" }
    $expected[$name] = $digest
}

$pin = $TrustedSignerThumbprint.ToUpperInvariant()
foreach ($name in $names) {
    if (-not $expected.ContainsKey($name)) { Fail "Missing checksum: $name" }
    $file = Join-Path $folder $name
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { Fail "Missing release file: $name" }
    if ((Get-Item -LiteralPath $file).Length -le 0) { Fail "Empty release file: $name" }

    $actual = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -cne $expected[$name]) { Fail "SHA-256 mismatch: $name" }

    $sig = Get-AuthenticodeSignature -LiteralPath $file
    if ($sig.Status -ne 'Valid' -or $null -eq $sig.SignerCertificate) {
        Fail "Untrusted or missing Authenticode signature: $name (status $($sig.Status))"
    }
    $actualThumbprint = ($sig.SignerCertificate.Thumbprint -replace '\s+', '').ToUpperInvariant()
    if ($actualThumbprint -cne $pin) { Fail "Publisher thumbprint mismatch: $name" }
    Write-Host "OK: $name — SHA-256, valid Authenticode signature, pinned publisher"
}
Write-Host 'RELEASE CANDIDATE CRYPTOGRAPHIC GATE PASSED (Windows E2E acceptance still required).'
