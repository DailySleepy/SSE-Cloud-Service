# scripts/manual-build.ps1
# 用于手动重建镜像并重启 K8s 部署（当修改了依赖或 Dockerfile 时使用）

# 1. 获取项目根目录
$ProjectRoot = (Get-Item -Path $PSScriptRoot).Parent.FullName
Set-Location $ProjectRoot
Write-Host "Project Root: $ProjectRoot" -ForegroundColor Cyan

# 2. 执行开发环境部署（确保 K8s 配置是最新的，包含路径注入）
Write-Host "Step 1: Updating K8s configurations..." -ForegroundColor Yellow
& (Join-Path $ProjectRoot "scripts\dev-deploy.ps1")

# 3. 配置 Docker 环境变量以连接到 Minikube 内部的 Docker Daemon
Write-Host "`nStep 2: Connecting to Minikube Docker daemon..." -ForegroundColor Green
& minikube -p minikube docker-env --shell powershell | Invoke-Expression

# 4. 重建镜像
Write-Host "`nStep 3: Building coursebot image..." -ForegroundColor Blue
docker build -t sse-cloud-service_coursebot:latest ./coursebot

# 5. 重启 Deployment 以加载新镜像
Write-Host "`nStep 4: Restarting deployments to apply new image..." -ForegroundColor Magenta
kubectl rollout restart deployment coursebot
kubectl rollout restart deployment cb-ingestor
kubectl rollout restart deployment cb-retriever

Write-Host "`nManual build and restart completed!" -ForegroundColor Green
