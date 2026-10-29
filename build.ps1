$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$runtime = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $runtime)) {
    Write-Host '创建 Python 虚拟环境…'
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw '无法创建 Python 环境。' }
    $runtime = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
}

Write-Host '安装开发依赖…'
& $runtime -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip 升级失败。' }
& $runtime -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败。' }

Write-Host '运行测试…'
$env:QT_QPA_PLATFORM = 'offscreen'
& $runtime -m pytest -q
if ($LASTEXITCODE -ne 0) { throw '测试失败，停止构建。' }

Write-Host '检查代码风格…'
& $runtime -m ruff check .
if ($LASTEXITCODE -ne 0) { throw 'ruff 未通过，停止构建。' }

$version = (& $runtime -c "from version import __version__; print(__version__)").Trim()
if ($LASTEXITCODE -ne 0 -or -not $version) { throw '无法读取版本号。' }

Write-Host "打包 Shiguang v$version…"
& $runtime -m PyInstaller --noconfirm --clean --onedir --windowed --name Shiguang `
    --collect-all playwright `
    --exclude-module matplotlib --exclude-module spacy --exclude-module torch `
    --exclude-module numpy --exclude-module PyQt6.QtWebEngineCore `
    app.py
if ($LASTEXITCODE -ne 0) { throw '打包失败。' }

# 此 Windows Qt 构建使用系统 ICU，避免私有 DLL 遮蔽系统版本。
$privateDlls = Join-Path $PSScriptRoot 'dist\Shiguang\_internal'
foreach ($dll in @('icuuc.dll', 'icudt78.dll')) {
    $candidate = Join-Path $privateDlls $dll
    if (Test-Path -LiteralPath $candidate) { Remove-Item -LiteralPath $candidate -Force }
}

$out = Join-Path $PSScriptRoot 'dist\Shiguang'
Copy-Item -LiteralPath 'docs\USAGE.md' -Destination (Join-Path $out '使用说明.md') -Force
Copy-Item -LiteralPath 'README.md' -Destination (Join-Path $out 'README.md') -Force
Copy-Item -LiteralPath 'LICENSE' -Destination $out -Force
Copy-Item -LiteralPath 'THIRD_PARTY_NOTICES.md' -Destination $out -Force

$zip = Join-Path $PSScriptRoot "dist\Shiguang-v$version-win64.zip"
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path (Join-Path $out '*') -DestinationPath $zip -CompressionLevel Optimal
if ($LASTEXITCODE -ne 0) { throw '压缩发布包失败。' }

Write-Host ''
Write-Host "完成：$zip"
