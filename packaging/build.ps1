# exe 版（PyInstaller）をビルドして zip にする
# 使い方: .\packaging\build.ps1 -Variant cpu   または   -Variant gpu
# Copyright (c) 2026 Keita Nakamori / QUETTA ROBOTICS — CC BY-ND 4.0
param([ValidateSet("cpu", "gpu")][string]$Variant = "cpu")

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$version = (Select-String -Path "$root\pyproject.toml" -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
$venv = "$root\build\venv-$Variant"
$py = "$venv\Scripts\python.exe"

uv venv $venv --python 3.12 --allow-existing
$pkgs = @("$root", "pyinstaller")
if ($Variant -eq "gpu") { $pkgs += "nvidia-cublas-cu12" }
uv pip install --python $py @pkgs
if ($LASTEXITCODE -ne 0) { throw "依存パッケージのインストールに失敗" }

$piArgs = @(
    "-m", "PyInstaller", "--noconfirm", "--windowed", "--onedir", "--name", "aris-stt",
    "--distpath", "$root\dist\$Variant", "--workpath", "$root\build\work-$Variant", "--specpath", "$root\build",
    "--collect-data", "faster_whisper",          # 無音判定（VAD）のモデル
    "--collect-binaries", "ctranslate2",         # 推論エンジンと cuDNN
    "--hidden-import", "pystray._win32"
)
if ($Variant -eq "gpu") { $piArgs += @("--collect-binaries", "nvidia.cublas") }
$piArgs += "$root\packaging\entry.py"
& $py @piArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller に失敗" }

$out = "$root\dist\$Variant\aris-stt"
Copy-Item "$root\LICENSE", "$root\NOTICE", "$root\README.md" $out
$zip = "$root\dist\aris-stt-$version-windows-$Variant.zip"
Remove-Item $zip -ErrorAction SilentlyContinue
Compress-Archive -Path $out -DestinationPath $zip -CompressionLevel Optimal
"{0}  {1:N0} MB" -f $zip, ((Get-Item $zip).Length / 1MB)
