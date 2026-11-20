<#
  install.ps1 — 把 photo-mole-game 技能装到 WorkBuddy 的 skills 目录

  用法：
    powershell -ExecutionPolicy Bypass -File .\install.ps1
    .\install.ps1 -Target "D:\my\skills" -Force
    .\install.ps1 -DryRun

  行为：
    1. 定位目标目录（默认 %USERPROFILE%\.workbuddy\skills）
    2. 校验本包完整性（SKILL.md 存在、frontmatter 里有 name 与 version）
    3. 目标已存在旧版 → 备份为 photo-mole-game.bak-<时间戳>
    4. 复制整包，剔除 __pycache__ / .git 等无用目录
    5. 打印版本与验证结果
#>
param(
    [string]$Target = "",
    [switch]$Force,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$SkillName = "photo-mole-game"

function Info($m) { Write-Host "  $m" }
function Ok($m) { Write-Host "  [OK] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  [!!] $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "  [错误] $m" -ForegroundColor Red; exit 1 }

$src = Split-Path -Parent $MyInvocation.MyCommand.Path
Info "源目录: $src"

# ---------- 1. 校验源包 ----------
$skillMd = Join-Path $src "SKILL.md"
if (-not (Test-Path $skillMd)) { Fail "找不到 SKILL.md，这个包不完整（请在解压后的 photo-mole-game 目录里运行）" }

$head = Get-Content $skillMd -TotalCount 30 -Encoding UTF8
$verLine = $head | Where-Object { $_ -match '^version:\s*' } | Select-Object -First 1
$nameLine = $head | Where-Object { $_ -match '^name:\s*' } | Select-Object -First 1
if (-not $verLine) { Fail "SKILL.md 缺少 version 字段" }
if (-not $nameLine) { Fail "SKILL.md 缺少 name 字段" }
$ver = ($verLine -split ':', 2)[1].Trim()
$name = ($nameLine -split ':', 2)[1].Trim()
if ($name -ne $SkillName) { Warn "SKILL.md 里 name=$name，与目录名 $SkillName 不一致（一般无碍，但建议统一）" }
Ok "包版本 $ver / 名称 $name"

$scripts = @("gate.py", "gen_expressions.py", "make_sheet.py", "cutout.py", "gen_prize.py", "build_game.py", "verify_game.py")
foreach ($s in $scripts) {
    if (-not (Test-Path (Join-Path $src "scripts\$s"))) { Fail "缺少脚本 scripts\$s" }
}
if (-not (Test-Path (Join-Path $src "assets\game_template.html"))) { Fail "缺少模板 assets\game_template.html" }
Ok "脚本与模板齐全（$($scripts.Count) 个脚本）"

# ---------- 2. 目标目录 ----------
if (-not $Target) { $Target = Join-Path $env:USERPROFILE ".workbuddy\skills" }
$dest = Join-Path $Target $SkillName
Info "目标目录: $dest"

if ($DryRun) {
    Warn "DryRun 模式：仅演示，不会改动任何文件"
    if (Test-Path $dest) { Info "会先备份现有 $dest" } else { Info "会新建 $dest" }
    Info "会把 $src 复制到 $dest（排除 __pycache__ / .git / .DS_Store）"
    exit 0
}

if (-not (Test-Path $Target)) {
    New-Item -ItemType Directory -Path $Target -Force | Out-Null
    Info "已创建 $Target"
}

# ---------- 3. 备份旧版 ----------
if (Test-Path $dest) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $bak = "$dest.bak-$stamp"
    Copy-Item -Path $dest -Destination $bak -Recurse -Force
    Ok "已备份旧版 -> $bak"
    if (-not $Force) {
        Write-Host "  即将覆盖 $dest（按 Ctrl+C 可中止，5 秒后继续）..." -ForegroundColor Yellow
        Start-Sleep -Seconds 5
    }
    Remove-Item -Path $dest -Recurse -Force
}

# ---------- 4. 复制 ----------
Copy-Item -Path $src -Destination $dest -Recurse -Force
Get-ChildItem -Path $dest -Recurse -Directory |
    Where-Object { $_.Name -in @("__pycache__", ".git", ".idea", ".vscode") } |
    ForEach-Object { Remove-Item -Path $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
Get-ChildItem -Path $dest -Recurse -File -Include "*.pyc", ".DS_Store" -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item -Path $_.FullName -Force -ErrorAction SilentlyContinue }

$files = Get-ChildItem -Path $dest -Recurse -File
$bytes = ($files | Measure-Object -Property Length -Sum).Sum
Ok "已复制 $($files.Count) 个文件 / $([math]::Round($bytes/1KB,1)) KB"

# ---------- 5. 收尾检查 ----------
if (Test-Path (Join-Path $dest "SKILL.md")) { Ok "SKILL.md 就位" } else { Fail "复制后找不到 SKILL.md" }
$missing = $scripts | Where-Object { -not (Test-Path (Join-Path $dest "scripts\$_")) }
if ($missing) { Fail "复制后缺少脚本: $($missing -join ', ')" }

Write-Host ""
Write-Host "  安装完成：$SkillName $ver" -ForegroundColor Green
Write-Host "  技能目录：$dest"
Write-Host "  下一步：重启 WorkBuddy（或技能面板点刷新），列表里应出现「照片打地鼠游戏生成器」"
Write-Host "  依赖：pip install pillow numpy opencv-python"
Write-Host ""
