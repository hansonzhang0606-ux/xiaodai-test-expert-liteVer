# ============================================================
# install.ps1 — 效贷效融测试专家【Lite版】一键安装脚本
# 适用：Windows / WorkBuddy
# 用法：
#   1) 完全退出 WorkBuddy（托盘区右键图标 -> 退出）
#   2) 下载本仓库并解压，进入仓库根目录
#   3) 右键本文件 -> "使用 PowerShell 运行"（或在该目录打开 PowerShell 执行 .\install.ps1）
# 说明：
#   本脚本不依赖 WorkBuddy 的「添加团队市场」自动注册（该流程在部分客户端版本不稳定），
#   而是直接将专家包复制到 my-experts 并写入市场清单，确保【我的专家】稳定显示。
# ============================================================
$ErrorActionPreference = "Stop"

# 1) 仓库根 = 脚本所在目录
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition

# 2) 定位专家包源（兼容两种仓库布局）
$srcCandidates = @(
    (Join-Path $repoRoot "xiaodai-testing-expert-lite"),
    (Join-Path $repoRoot "plugins\xiaodai-testing-expert-lite")
)
$src = $null
foreach ($c in $srcCandidates) { if (Test-Path $c) { $src = $c; break } }
if (-not $src) {
    Write-Host "[失败] 未在仓库中找到专家包目录（期望 xiaodai-testing-expert-lite 或 plugins\xiaodai-testing-expert-lite）。请确认本脚本位于仓库根目录运行。" -ForegroundColor Red
    exit 1
}

# 3) 目标目录
$home = $env:USERPROFILE
$myExperts = Join-Path $home ".workbuddy\plugins\marketplaces\my-experts"
$target = Join-Path $myExperts "plugins\xiaodai-testing-expert-lite"

# 4) 复制专家包（幂等：先清旧的再复制）
if (Test-Path $target) {
    Remove-Item $target -Recurse -Force
    Write-Host "[清理] 已移除旧版 lite 专家包目录"
}
Copy-Item $src $target -Recurse -Force
Write-Host "[OK] 专家包已安装至 $target"

# 5) 注册到 my-experts 市场清单（幂等）
$mf = Join-Path $myExperts ".codebuddy-plugin\marketplace.json"
if (-not (Test-Path $mf)) {
    $json = [PSCustomObject]@{
        name        = "my-experts"
        description = "my-experts marketplace (auto-generated)"
        plugins     = @()
    }
    Write-Host "[新建] my-experts 市场清单缺失，已创建最小结构"
} else {
    $json = Get-Content $mf -Raw | ConvertFrom-Json
}

$has = $false
if ($json.plugins) {
    foreach ($p in $json.plugins) { if ($p.name -eq "xiaodai-testing-expert-lite") { $has = $true; break } }
}
if (-not $has) {
    $lite = [PSCustomObject]@{
        name        = "xiaodai-testing-expert-lite"
        source      = "./plugins/xiaodai-testing-expert-lite"
        description = "A lightweight testing expert for Xiaodai, Xiaorong, and Microloan business lines with seven on-demand stages and mandatory time-savings tracking."
    }
    if (-not $json.plugins) { $json.plugins = @() }
    $json.plugins += $lite
    Write-Host "[OK] 已在市场清单注册 lite 条目"
} else {
    Write-Host "[跳过] 市场清单已含 lite 条目"
}
[System.IO.File]::WriteAllText($mf, ($json | ConvertTo-Json -Depth 10), [System.Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "★ 安装完成。请完全退出 WorkBuddy（托盘右键退出）再重新打开，进入【我的专家】即可看到「效贷效融测试专家【Lite版】」。" -ForegroundColor Green
