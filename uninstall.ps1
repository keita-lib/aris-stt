# ARIS STT uninstaller
# 使い方（PowerShell）: irm https://raw.githubusercontent.com/keita-lib/aris-stt/main/uninstall.ps1 | iex
# 設定とログも消す場合は、実行前に $env:ARIS_STT_PURGE = "1" を設定する

$ErrorActionPreference = "Continue"
$AppName = "ARIS STT"

Get-Process aris-stt -ErrorAction SilentlyContinue | Stop-Process -Force
Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object CommandLine -match 'aris_stt' |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

foreach ($dir in @([Environment]::GetFolderPath("Programs"), [Environment]::GetFolderPath("Startup"))) {
    Remove-Item (Join-Path $dir "$AppName.lnk") -ErrorAction SilentlyContinue
}

if (Get-Command uv -ErrorAction SilentlyContinue) { uv tool uninstall aris-stt }

if ($env:ARIS_STT_PURGE -eq "1") {
    Remove-Item "$env:APPDATA\aris-stt", "$env:LOCALAPPDATA\aris-stt" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "設定とログも削除しました。"
}

Write-Host "$AppName をアンインストールしました。" -ForegroundColor Green
Write-Host "ダウンロード済みの音声認識モデルは $env:USERPROFILE\.cache\huggingface\hub に残っています（不要なら削除してください）。"
