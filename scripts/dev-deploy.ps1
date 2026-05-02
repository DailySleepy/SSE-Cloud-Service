# scripts/dev-deploy.ps1
# 用于在开发环境下注入本地路径并部署 K8s 配置

# 1. 获取项目根目录 (绝对路径)
$ProjectRoot = (Get-Item -Path $PSScriptRoot).Parent.FullName
Write-Host "Detected Project Root: $ProjectRoot" -ForegroundColor Cyan

# 2. 转换为 Minikube 兼容路径 (例如 F:\path -> /f/path)
# 将盘符大写转小写，反斜杠转正斜杠
$DriveLetter = $ProjectRoot.Substring(0, 1).ToLower()
$RemainingPath = $ProjectRoot.Substring(3).Replace('\', '/')
$MinikubePath = "/$DriveLetter/$RemainingPath"
Write-Host "Minikube Compatible Path: $MinikubePath" -ForegroundColor Green

# 3. 准备补丁文件路径
$PatchFile = Join-Path $ProjectRoot "k8s\overlays\dev\patch-coursebot.yaml"
$BackupFile = $PatchFile + ".bak"

# 4. 动态注入路径并部署
try {
    # 备份原始带占位符的文件
    Copy-Item $PatchFile $BackupFile -Force
    
    # 执行替换
    $Content = Get-Content $PatchFile -Raw
    $NewContent = $Content.Replace('${LOCAL_PROJECT_ROOT}', $MinikubePath)
    Set-Content $PatchFile $NewContent -NoNewline
    
    Write-Host "Injecting path and applying Kustomize..." -ForegroundColor Yellow
    
    # 执行部署
    # 使用 -Cwd 确保在项目根目录执行
    Set-Location $ProjectRoot
    kubectl apply -k k8s/overlays/dev
    
    Write-Host "`nDeployment successful!" -ForegroundColor Green
}
catch {
    Write-Error "Deployment failed: $_"
}
finally {
    # 5. 还原占位符文件，保持代码整洁
    if (Test-Path $BackupFile) {
        Move-Item $BackupFile $PatchFile -Force
        Write-Host "Restored parameterized patch file." -ForegroundColor Gray
    }
}
