# Windows 安装包验收：静默安装 → 检查内置核心 → 启动/停止 → 静默卸载。
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [string]$InstallDir = (Join-Path $env:RUNNER_TEMP "QuickSwitchTest")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Step([string]$Text) { Write-Host "`n== $Text" }
function Assert-Path([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path)) { throw "缺少 $Label：$Path" }
    Write-Host "  OK  $Label：$Path"
}

$Installer = (Resolve-Path -LiteralPath $Installer).Path
if (Test-Path -LiteralPath $InstallDir) {
    Remove-Item -LiteralPath $InstallDir -Recurse -Force
}

$oldConfig = $env:QUICKSWITCH_CONFIG
$oldLog = $env:QUICKSWITCH_LOG
$env:QUICKSWITCH_CONFIG = Join-Path $env:RUNNER_TEMP "quickswitch-installer-test-config.json"
$env:QUICKSWITCH_LOG = Join-Path $env:RUNNER_TEMP "quickswitch-installer-test.log"
Remove-Item -LiteralPath $env:QUICKSWITCH_CONFIG -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $env:QUICKSWITCH_LOG -Force -ErrorAction SilentlyContinue

try {
    Write-Step "静默安装"
    $install = Start-Process -FilePath $Installer -ArgumentList @("/S", "/D=$InstallDir") -Wait -PassThru
    if ($install.ExitCode -ne 0) { throw "安装失败，退出码 $($install.ExitCode)" }
    Start-Sleep -Seconds 2

    $exe = Join-Path $InstallDir "QuickSwitch.exe"
    $deskflow = Join-Path $InstallDir "deskflow\deskflow-core.exe"
    $deskflowLicense = Join-Path $InstallDir "deskflow\LICENSE"
    $notice = Join-Path $InstallDir "THIRD_PARTY_NOTICES.md"
    Assert-Path $exe "QuickSwitch.exe"
    Assert-Path $deskflow "内置 Deskflow"
    Assert-Path $deskflowLicense "Deskflow LICENSE"
    Assert-Path $notice "第三方许可说明"

    $deskflowSize = (Get-Item -LiteralPath $deskflow).Length
    if ($deskflowSize -lt 1MB) { throw "内置 Deskflow 文件过小：$deskflowSize bytes" }
    Write-Host "  OK  Deskflow 文件大小：$deskflowSize bytes"

    Write-Step "检查内置路径"
    $statusErr = Join-Path $env:RUNNER_TEMP "quickswitch-deskflow-status.err"
    $statusText = & $exe --deskflow-status 2>$statusErr | Out-String
    if ($LASTEXITCODE -ne 0) { throw "--deskflow-status 失败：$statusText $(Get-Content -Raw $statusErr -ErrorAction SilentlyContinue)" }
    $status = $statusText | ConvertFrom-Json
    if (-not $status.installed) { throw "没有检测到内置 Deskflow：$statusText" }
    if (-not $status.bundled) { throw "Deskflow 未被识别为内置版本：$statusText" }
    $expected = (Resolve-Path -LiteralPath $deskflow).Path
    $actual = (Resolve-Path -LiteralPath $status.path).Path
    if ($actual -ne $expected) { throw "Deskflow 路径不匹配：$actual != $expected" }
    Write-Host "  OK  $actual"

    Write-Step "启动内置 Deskflow"
    $startErr = Join-Path $env:RUNNER_TEMP "quickswitch-start-deskflow.err"
    $startText = & $exe --start-deskflow 2>$startErr | Out-String
    if ($LASTEXITCODE -ne 0) { throw "--start-deskflow 失败：$startText $(Get-Content -Raw $startErr -ErrorAction SilentlyContinue)" }
    $deadline = (Get-Date).AddSeconds(8)
    $process = $null
    while ((Get-Date) -lt $deadline) {
        $process = Get-Process -Name "deskflow-core" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($process) { break }
        Start-Sleep -Milliseconds 250
    }
    if (-not $process) { throw "deskflow-core 启动后没有检测到进程：$startText" }
    Write-Host "  OK  PID $($process.Id)"

    Write-Step "停止内置核心"
    $stopErr = Join-Path $env:RUNNER_TEMP "quickswitch-stop-deskflow.err"
    $stopText = & $exe --stop-deskflow 2>$stopErr | Out-String
    if ($LASTEXITCODE -ne 0) { throw "--stop-deskflow 失败：$stopText $(Get-Content -Raw $stopErr -ErrorAction SilentlyContinue)" }
    if (Get-Process -Name "deskflow-core" -ErrorAction SilentlyContinue) {
        throw "停止后 deskflow-core 仍然存在：$stopText"
    }
    Write-Host "  OK  已停止"

    Write-Step "静默卸载"
    $uninstaller = Join-Path $InstallDir "Uninstall.exe"
    Assert-Path $uninstaller "Uninstall.exe"
    $uninstall = Start-Process -FilePath $uninstaller -ArgumentList "/S" -Wait -PassThru
    if ($uninstall.ExitCode -ne 0) { throw "卸载失败，退出码 $($uninstall.ExitCode)" }
    Start-Sleep -Seconds 2
    if (Test-Path -LiteralPath $exe) { throw "卸载后 QuickSwitch.exe 仍然存在" }
    if (Test-Path -LiteralPath (Join-Path $InstallDir "deskflow")) { throw "卸载后 Deskflow 目录仍然存在" }
    Write-Host "  OK  已清理程序目录"

    Write-Step "Windows 安装包验收通过"
} finally {
    Get-Process -Name "deskflow-core" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    if ($null -eq $oldConfig) { Remove-Item Env:QUICKSWITCH_CONFIG -ErrorAction SilentlyContinue }
    else { $env:QUICKSWITCH_CONFIG = $oldConfig }
    if ($null -eq $oldLog) { Remove-Item Env:QUICKSWITCH_LOG -ErrorAction SilentlyContinue }
    else { $env:QUICKSWITCH_LOG = $oldLog }
}
