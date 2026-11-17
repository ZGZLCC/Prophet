$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "找不到项目虚拟环境：$python"
}

$distPath = Join-Path $PSScriptRoot "dist-native"
& $python -m PyInstaller --noconfirm --clean --distpath $distPath (Join-Path $PSScriptRoot "Prophet.spec")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$bundle = Join-Path $distPath "Prophet"
Copy-Item -LiteralPath (Join-Path $PSScriptRoot ".env.example") -Destination $bundle -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "README.md") -Destination $bundle -Force
& (Join-Path $bundle "Prophet.exe") --self-test
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "已生成：$bundle"
