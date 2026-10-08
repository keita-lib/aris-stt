# ARIS STT installer
# 使い方（PowerShell）: irm https://raw.githubusercontent.com/keita-lib/aris-stt/main/install.ps1 | iex
# Copyright (c) 2026 Keita Nakamori / QUETTA ROBOTICS — CC BY-ND 4.0

$ErrorActionPreference = "Stop"
$AppName = "ARIS STT"
# 入れる元。テスト時は環境変数 ARIS_STT_SOURCE にローカルのフォルダを指定できる
$Source = if ($env:ARIS_STT_SOURCE) { $env:ARIS_STT_SOURCE } else { "https://github.com/keita-lib/aris-stt/archive/refs/heads/main.zip" }

Write-Host "== $AppName をインストールします ==" -ForegroundColor Cyan

# 1. uv（Python とパッケージの管理ツール）。無ければ入れる
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv をインストールしています..."
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

# 2. NVIDIA の GPU があれば GPU 版、無ければ CPU 版
$hasNvidia = [bool](Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match "NVIDIA" })
$spec = if ($hasNvidia) { "aris-stt[gpu] @ $Source" } else { "aris-stt @ $Source" }
Write-Host ("GPU: " + $(if ($hasNvidia) { "NVIDIA あり → GPU 版（large-v3）" } else { "なし → CPU 版（small）" }))

# 3. 起動中なら止めてから入れ直す
Get-Process aris-stt -ErrorAction SilentlyContinue | Stop-Process -Force
Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object CommandLine -match 'aris_stt' |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Write-Host "ARIS STT をインストールしています（数分かかることがあります）..."
# 同じバージョン番号のまま中身が変わった場合も、キャッシュを使わず本体を作り直す
uv tool install --python 3.12 --force --reinstall-package aris-stt $spec
if ($LASTEXITCODE -ne 0) { throw "インストールに失敗しました" }

$bin = (uv tool dir --bin).Trim()
$exe = Join-Path $bin "aris-stt.exe"
if (-not (Test-Path $exe)) { throw "実行ファイルが見つかりません: $exe" }

# 4. スタートメニューと、ログオン時の自動起動にショートカットを置く
$shell = New-Object -ComObject WScript.Shell
$targets = @(
    [Environment]::GetFolderPath("Programs"),
    [Environment]::GetFolderPath("Startup")
)
foreach ($dir in $targets) {
    $lnk = $shell.CreateShortcut((Join-Path $dir "$AppName.lnk"))
    $lnk.TargetPath = $exe
    $lnk.Description = "$AppName — voice input by Keita Nakamori / QUETTA ROBOTICS"
    $lnk.Save()
}

# 5. 起動
Start-Process $exe
Write-Host ""
Write-Host "インストールが完了しました。" -ForegroundColor Green
Write-Host "・画面右下のタスクトレイにマイクのアイコンが出ます（設定・一時停止・終了はここから）"
Write-Host "・初回はモデルのダウンロードがあります（GPU 版 約3GB / CPU 版 約0.5GB）"
Write-Host "・「無変換」または Ctrl+Alt+Space で話し始め、もう一度押すと書き込みます"
Write-Host "・キーの変更: トレイのマイクのアイコン →「⚙ 設定...」"
Write-Host "・詳しい設定: $env:APPDATA\aris-stt\config.toml"
Write-Host "・アンインストール: irm https://raw.githubusercontent.com/keita-lib/aris-stt/main/uninstall.ps1 | iex"
