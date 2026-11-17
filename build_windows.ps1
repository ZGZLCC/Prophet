param(
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"

# 优先使用项目虚拟环境；CI 上没有 .venv，回退到 PATH 上的 python
if (-not $Python) {
    $candidate = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    $Python = if (Test-Path -LiteralPath $candidate) { $candidate } else { "python" }
}
if (-not (Test-Path -LiteralPath $Python)) {
    $resolved = Get-Command $Python -ErrorAction SilentlyContinue
    if (-not $resolved) {
        throw "找不到可用的 Python：$Python。请先创建 .venv 或用 -Python 指定解释器。"
    }
    $Python = $resolved.Source
}
Write-Host "使用 Python：$Python"

$distPath = Join-Path $PSScriptRoot "dist-native"
& $Python -m PyInstaller --noconfirm --clean --distpath $distPath (Join-Path $PSScriptRoot "Prophet.spec")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$bundle = Join-Path $distPath "Prophet"
Copy-Item -LiteralPath (Join-Path $PSScriptRoot ".env.example") -Destination $bundle -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "README.md") -Destination $bundle -Force

# 窗口程序自检失败时可能弹模态框，必须有超时，否则构建会一直等下去
$exe = Join-Path $bundle "Prophet.exe"
$proc = Start-Process -FilePath $exe -ArgumentList "--self-test" -PassThru -NoNewWindow
if (-not $proc.WaitForExit(180000)) {
    $proc.Kill()
    throw "打包自检超过 180 秒未结束，已终止：$exe"
}
if ($proc.ExitCode -ne 0) {
    throw "打包自检失败，退出码 $($proc.ExitCode)：$exe --self-test"
}
Write-Host "已生成：$bundle"
