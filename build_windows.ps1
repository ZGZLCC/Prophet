param(
    [string]$Python = ""
)

# ASCII-only on purpose: Windows PowerShell 5.1 decodes BOM-less scripts as ANSI,
# so any non-ASCII text here risks mojibake or parse errors depending on the locale.

$ErrorActionPreference = "Stop"

# Prefer the project virtualenv; fall back to python on PATH (CI has no .venv).
if (-not $Python) {
    $candidate = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    $Python = if (Test-Path -LiteralPath $candidate) { $candidate } else { "python" }
}
if (-not (Test-Path -LiteralPath $Python)) {
    $resolved = Get-Command $Python -ErrorAction SilentlyContinue
    if (-not $resolved) {
        throw "No usable Python found: $Python. Create .venv or pass -Python <path>."
    }
    $Python = $resolved.Source
}
Write-Host "Using Python: $Python"

$distPath = Join-Path $PSScriptRoot "dist-native"
& $Python -m PyInstaller --noconfirm --clean --distpath $distPath (Join-Path $PSScriptRoot "Prophet.spec")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$bundle = Join-Path $distPath "Prophet"
Copy-Item -LiteralPath (Join-Path $PSScriptRoot ".env.example") -Destination $bundle -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "README.md") -Destination $bundle -Force

# The bundle is a windowed app: without redirection its self-test output is lost,
# and a modal dialog on failure would block the build forever. Capture and time out.
$exe = Join-Path $bundle "Prophet.exe"
$logDir = Join-Path $PSScriptRoot "build"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stdoutLog = Join-Path $logDir "self-test.out.log"
$stderrLog = Join-Path $logDir "self-test.err.log"

# Windows PowerShell 5.1 leaves ExitCode empty for a non -Wait Start-Process, and
# -Wait cannot time out. So do not trust the exit code: require the success marker.
$proc = Start-Process -FilePath $exe -ArgumentList "--self-test" -PassThru -NoNewWindow `
    -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
if (-not $proc.WaitForExit(180000)) {
    $proc.Kill()
    throw "Self-test did not finish within 180s: $exe"
}

$selfTestOutput = @()
if (Test-Path -LiteralPath $stdoutLog) { $selfTestOutput += Get-Content -LiteralPath $stdoutLog -Encoding UTF8 }
if (Test-Path -LiteralPath $stderrLog) { $selfTestOutput += Get-Content -LiteralPath $stderrLog -Encoding UTF8 }

if (-not ($selfTestOutput -match "native desktop self-check passed")) {
    Write-Host "--- self-test stdout ---"
    if (Test-Path -LiteralPath $stdoutLog) { Get-Content -LiteralPath $stdoutLog -Encoding UTF8 }
    Write-Host "--- self-test stderr ---"
    if (Test-Path -LiteralPath $stderrLog) { Get-Content -LiteralPath $stderrLog -Encoding UTF8 }
    throw "Packaged self-test did not report success: $exe --self-test"
}
Write-Host "Bundle ready: $bundle"
