# build.ps1 —— 构建 photo-mole-game 技能一键安装器（单文件 windowed exe）
# 用法：
#   powershell -ExecutionPolicy Bypass -File .\build.ps1
#   powershell -ExecutionPolicy Bypass -File .\build.ps1 -Payload "D:\path\to\photo-mole-game"
param(
    [string]$Payload = "",
    [string]$Python = "python",
    [switch]$CleanEnv
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# 1) 定位载荷（技能本体），优先使用备份目录中的 v1.2.0 完整副本
if ([string]::IsNullOrWhiteSpace($Payload)) {
    $candidates = @(
        (Join-Path $PSScriptRoot "..\skill"),
        (Join-Path $PSScriptRoot "..\backup\photo-mole-game_v1.2.0"),
        (Join-Path $PSScriptRoot "..\photo-mole-game"),
        (Join-Path $env:USERPROFILE ".workbuddy\skills\photo-mole-game")
    )
    foreach ($c in $candidates) {
        if (Test-Path (Join-Path $c "SKILL.md")) { $Payload = (Resolve-Path $c).Path; break }
    }
}
if (-not $Payload -or -not (Test-Path (Join-Path $Payload "SKILL.md"))) {
    throw "未找到技能载荷目录，请用 -Payload 指定包含 SKILL.md 的 photo-mole-game 目录。"
}
$Payload = (Resolve-Path $Payload).Path

# 2) 载荷体检：文件数 / 总字节（排除 __pycache__、*.pyc、.DS_Store）
$files = Get-ChildItem -Path $Payload -Recurse -File |
    Where-Object { $_.Name -ne ".DS_Store" -and $_.Extension -ne ".pyc" -and $_.DirectoryName -notmatch "\\__pycache__" }
$count = ($files | Measure-Object).Count
$bytes = ($files | Measure-Object -Property Length -Sum).Sum
Write-Host "[payload] $Payload"
Write-Host "[payload] 文件数=$count  总字节=$bytes"

# 3) 环境检查
& $Python -c "import sys;print('[python]',sys.version.split()[0])"
& $Python -c "import PyInstaller;print('[pyinstaller]',PyInstaller.__version__)"
& $Python -c "import tkinter;print('[tk]',tkinter.TkVersion)"

# 4) PyInstaller 单文件构建
$pyArgs = @(
    "--onefile",
    "--windowed",
    "--name", "photo-mole-game-installer",
    "--add-data", "$Payload;skill_payload/photo-mole-game",
    "--distpath", "dist",
    "--workpath", "build",
    "--specpath", ".",
    "--clean",
    "-y",
    "photo_mole_installer.py"
)
if ($CleanEnv) { $pyArgs = @("--noconfirm") + $pyArgs }

Write-Host "[build] pyinstaller $($pyArgs -join ' ')"
& $Python -m PyInstaller @pyArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败，退出码 $LASTEXITCODE" }

$exe = Join-Path $PSScriptRoot "dist\photo-mole-game-installer.exe"
if (-not (Test-Path $exe)) { throw "构建结束但未找到产物：$exe" }

$size = (Get-Item $exe).Length
$sha = (Get-FileHash -Path $exe -Algorithm SHA256).Hash
Write-Host ""
Write-Host "[done] 产物：$exe"
Write-Host "[done] 体积：$size 字节 ($([math]::Round($size/1MB,2)) MB)"
Write-Host "[done] SHA256：$sha"

