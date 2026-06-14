# scripts/dev/dev-deploy.ps1
# 用于在开发环境下构建本地镜像并部署 K8s 配置

if ($PSScriptRoot) {
    $ProjectRoot = (Get-Item -Path $PSScriptRoot).Parent.Parent.FullName
} else {
    $ProjectRoot = (Get-Location).Path
}
Write-Host "Project Root: $ProjectRoot" -ForegroundColor Cyan

try {
    # 2. 在 Minikube 内部构建 Docker 镜像
    Write-Host "Building Docker image inside Minikube..." -ForegroundColor Yellow
    Set-Location $ProjectRoot
    minikube image build -t sse-cloud-service_coursebot:latest --build-opt=pull=false ./coursebot

    # 3. 部署 Kustomize 配置到 K8s
    Write-Host "`nApplying Kustomize to Kubernetes..." -ForegroundColor Yellow
    kubectl apply -k k8s/overlays/dev

    # 4. 重启 Deployment 以确保加载最新构建的本地镜像
    Write-Host "`nRestarting deployments to load the new image..." -ForegroundColor Magenta
    kubectl rollout restart deployment/coursebot deployment/cb-ingestor deployment/cb-retriever

    Write-Host "`nDeployment successful!" -ForegroundColor Green
} catch {
    Write-Error "Deployment failed: $_"
}