# start-web-access-profile.ps1 - 启动 web-access 专用的隔离 Chrome 实例
#
# 用途：为 web-access skill 启动唯一可连接的浏览器实例（web-access-profile/）。
#       该实例与你的日常 Chrome 完全隔离（独立 user-data-dir + 独立远程调试端口），
#       只在此窗口内登录 HKU 即可，日常浏览器不可见、不受影响。
#
# 用法：右键"使用 PowerShell 运行"，或：
#   powershell -ExecutionPolicy Bypass -File scripts\start-web-access-profile.ps1
#
# 说明：启动后请保持该窗口常开（web-access 需要它在线）。首次在此窗口登录一次 HKU，
#       之后付费文章抓取即可复用该会话。

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$profileDir = Join-Path $repoRoot 'web-access-profile'

# 确保专用 profile 目录存在
New-Item -ItemType Directory -Path $profileDir -Force | Out-Null

# 定位 chrome.exe
$chrome = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
if (-not (Test-Path $chrome)) {
  $chrome = "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
}
if (-not (Test-Path $chrome)) {
  $chrome = Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe'
}
if (-not (Test-Path $chrome)) {
  Write-Error "未找到 chrome.exe。请安装 Chrome，或手动修改本脚本中的 chrome 路径。"
  exit 1
}

Write-Host "专用 profile 目录: $profileDir"
Write-Host "启动专用 Chrome（远程调试端口 9222）..."

& $chrome `
  "--user-data-dir=$profileDir" `
  "--remote-debugging-port=9222" `
  --no-first-run `
  --no-default-browser-check

Write-Host "已启动。请保持此窗口常开；首次使用请在此窗口登录 HKU。"
