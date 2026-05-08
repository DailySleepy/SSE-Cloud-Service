# scripts/dev-deploy.ps1
# 用于在开发环境下注入本地路径并部署 K8s 配置

# 1. 获取项目根目录 (绝对路径)
$ProjectRoot = (Get-Item -Path $PSScriptRoot).Parent.FullName
Write-Host "Detected Project Root: $ProjectRoot" -ForegroundColor Cyan

# 2. 转换为 Minikube 兼容路径 (例如 F:\path -> /f/path)
$DriveLetter = $ProjectRoot.Substring(0, 1).ToLower()
$RemainingPath = $ProjectRoot.Substring(3).Replace('\', '/')
$MinikubePath = "/$DriveLetter/$RemainingPath"
Write-Host "Minikube Compatible Path: $MinikubePath" -ForegroundColor Green

# 3. 准备所有需要路径注入的补丁文件
$PatchFiles = @(
    (Join-Path $ProjectRoot "k8s\overlays\dev\patch-coursebot.yaml"),
    (Join-Path $ProjectRoot "k8s\overlays\dev\patch-ingestor.yaml"),
    (Join-Path $ProjectRoot "k8s\overlays\dev\patch-retriever.yaml")
)
$NoBomUtf8 = New-Object System.Text.UTF8Encoding $false

# 4. 动态注入路径并部署
try {
    foreach ($PatchFile in $PatchFiles) {
        $BackupFile = $PatchFile + ".bak"
        Copy-Item $PatchFile $BackupFile -Force
        $Content = [System.IO.File]::ReadAllText($PatchFile)
        $NewContent = $Content.Replace('${LOCAL_PROJECT_ROOT}', $MinikubePath)
        [System.IO.File]::WriteAllText($PatchFile, $NewContent, $NoBomUtf8)
    }

    Write-Host "Injecting path and applying Kustomize..." -ForegroundColor Yellow
    Set-Location $ProjectRoot
    kubectl apply -k k8s/overlays/dev

    Write-Host "`nDeployment successful!" -ForegroundColor Green
} catch {
    Write-Error "Deployment failed: $_"
} finally {
    foreach ($PatchFile in $PatchFiles) {
        $BackupFile = $PatchFile + ".bak"
        if (Test-Path $BackupFile) {
            Move-Item $BackupFile $PatchFile -Force
        }
    }
    Write-Host "Restored parameterized patch files." -ForegroundColor Gray
}