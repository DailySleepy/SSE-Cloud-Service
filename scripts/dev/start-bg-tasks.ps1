<#
.SYNOPSIS
    启动开发环境所需的后台任务 (使用 PowerShell Background Jobs)
#>

# 获取项目根目录
$ProjectRoot = (Get-Item -Path $PSScriptRoot).Parent.Parent.FullName
Write-Host "项目根目录: $ProjectRoot" -ForegroundColor Cyan

# 预清理可能存在的旧作业 (可选)
# Get-Job | Remove-Job -Force

# 1. 后端挂载 minikube mount
$DriveLetter = $ProjectRoot.Substring(0, 1).ToLower()
$RestPath = $ProjectRoot.Substring(2).Replace('\', '/')
$MinikubePath = "/$DriveLetter$RestPath/coursebot"
$LocalPath = "$ProjectRoot\coursebot"

Write-Host "启动作业 [MinikubeMount]: $LocalPath -> $MinikubePath" -ForegroundColor Yellow
Start-Job -Name "MinikubeMount" -ScriptBlock {
    param($local, $remote)
    minikube mount "${local}:${remote}"
} -ArgumentList $LocalPath, $MinikubePath

# 2. 端口转发
Write-Host "启动作业 [PortForward]: kubectl port-forward svc/nginx-gateway 8080:80" -ForegroundColor Yellow
Start-Job -Name "PortForward" -ScriptBlock {
    kubectl port-forward svc/nginx-gateway 8080:80
}

# 3. 启动前端开发
Write-Host "启动作业 [FrontendDev]: npm run dev" -ForegroundColor Yellow
$FrontendDir = Join-Path $ProjectRoot "frontend"
Start-Job -Name "FrontendDev" -ScriptBlock {
    param($dir)
    Set-Location $dir
    # 这里的 npm 不需要加 .cmd 因为是在新的 powershell 会话中执行
    npm run dev
} -ArgumentList $FrontendDir

Write-Host "`n所有后台作业已启动！" -ForegroundColor Green
Write-Host "管理命令参考：" -ForegroundColor Gray
Write-Host "  查看列表: Get-Job"
Write-Host "  查看日志: Receive-Job -Name FrontendDev -Keep"
Write-Host "  停止作业: Stop-Job -Name *"
Write-Host "  清理作业: Remove-Job -Name *"
