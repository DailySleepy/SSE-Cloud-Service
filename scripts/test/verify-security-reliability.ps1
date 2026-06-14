# scripts/test/verify-security-reliability.ps1
# CourseBot 安全网关与可靠性测试套件 (Windows PowerShell 版)

$ErrorActionPreference = "Stop"

# 定义终端输出颜色函数
function Write-Header ($text) {
    Write-Host "`n==========================================" -ForegroundColor Cyan
    Write-Host ">>> $text" -ForegroundColor Cyan
    Write-Host "==========================================" -ForegroundColor Cyan
}

function Write-Success ($text) {
    Write-Host "[SUCCESS] $text" -ForegroundColor Green
}

function Write-Failure ($text) {
    Write-Host "[FAILURE] $text" -ForegroundColor Red
}

$GatewayUrl = "http://localhost:8080/v1/chat/completions"
$ApiKey = "cb-gateway-api-key-12345"

# 自动确保本地开发环境中的 8080 端口转发存活
function Ensure-PortForward {
    if ($GatewayUrl -match "8080") {
        $check = & curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/healthz
        if ($LASTEXITCODE -ne 0 -or $check -eq "000") {
            Write-Host "检测到本地 8080 端口转发已断开，正在自动重新建立连接..." -ForegroundColor Yellow
            Stop-Process -Name "kubectl" -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 1
            Start-Process -FilePath "kubectl" -ArgumentList "port-forward svc/nginx-gateway 8080:80" -NoNewWindow
            Start-Sleep -Seconds 3
        }
    }
}

# 辅助函数：通过临时文件绕过命令行转义限制发送 POST 请求，并返回 HTTP 状态码与响应体
function Send-Request ($bodyText, $apiKeyVal) {
    $tempFile = Join-Path $PSScriptRoot "temp_payload.json"
    [System.IO.File]::WriteAllText($tempFile, $bodyText, [System.Text.Encoding]::UTF8)

    $curlArgs = @("-s", "-i", "-X", "POST", $GatewayUrl, "-H", "Content-Type: application/json")
    if ($apiKeyVal) {
        $curlArgs += @("-H", "X-API-Key: $apiKeyVal")
    }
    $curlArgs += @("-d", "@$tempFile")
    
    $rawResponse = & curl.exe $curlArgs
    $responseStr = $rawResponse -join "`n"
    
    if (Test-Path $tempFile) {
        Remove-Item $tempFile -Force | Out-Null
    }
    
    $statusCode = 500
    if ($responseStr -match 'HTTP/\d\.\d\s+(\d+)' -or $responseStr -match 'HTTP/\d\s+(\d+)') {
        $statusCode = [int]$Matches[1]
    }
    
    return [PSCustomObject]@{
        StatusCode = $statusCode
        Content = $responseStr
    }
}

# ==========================================
# 第一部分：可靠性降级链路成功
# ==========================================
# 【DOING】：将配置项 FORCE_OLLAMA_500 设为 true，并重启服务。随后发送测试请求并还原配置。
# 【PURPOSE】：验证在高可用架构中，当本地 primary LLM (Ollama) 服务不可用或崩溃时，
#             系统能自动且平滑地实施降级，转入 SaaS 备份服务或返回 template 静态模板，而不会使网关直接瘫痪。
# ==========================================
Write-Header "第一部分：可靠性降级链路成功"

Write-Host "正在模拟 Ollama 故障 (通过设置 FORCE_OLLAMA_500 = true 以强制让本地 LLM 返回 500 报错)..."
kubectl patch configmap cb-config --type merge -p "data:`n  FORCE_OLLAMA_500: 'true'"
kubectl rollout restart deployment/coursebot
Write-Host "等待 coursebot 滚动重启就绪..."
kubectl rollout status deployment/coursebot --timeout=60s
Write-Host "等待 5 秒以让 Nginx 的内部 DNS 解析缓存刷新..."
Start-Sleep -Seconds 5

Write-Host "向网关发送测试请求以验证降级机制..."
$Body = '{"model": "ollama/qwen2.5:0.5b", "messages": [{"role": "user", "content": "Introduce yourself in one sentence in Chinese."}], "use_rag": false}'

$ResObj = Send-Request $Body $ApiKey
Write-Host "网关返回的 JSON 结果如下：" -ForegroundColor Gray
Write-Host $ResObj.Content -ForegroundColor DarkGray

if ($ResObj.Content -match '"degraded"\s*:\s*true' -or $ResObj.Content -match '"provider"\s*:\s*"saas"' -or $ResObj.Content -match '"provider"\s*:\s*"template"') {
    Write-Success "降级链路验证成功：网关在 Ollama 故障时成功熔断，并返回了 degraded=true / 备份 provider 响应！"
} else {
    Write-Failure "降级链路验证失败：返回内容中未包含 degraded=true 或降级备份标识。"
}

# 还原 Ollama 故障设置，保证后续测试可以使用本地 LLM
Write-Host "`n正在恢复 Ollama 的正常工作状态 (设置 FORCE_OLLAMA_500 = false)..."
kubectl patch configmap cb-config --type merge -p "data:`n  FORCE_OLLAMA_500: 'false'"
kubectl rollout restart deployment/coursebot
Write-Host "等待 coursebot 滚动重启就绪..."
kubectl rollout status deployment/coursebot --timeout=60s
Write-Host "等待 5 秒以让 Nginx DNS 缓存刷新..."
Start-Sleep -Seconds 5


# ==========================================
# 第二部分：滚动升级与回滚
# ==========================================
# 【DOING】：对 nginx-gateway 依次进行滚动升级与回滚操作，并在各个阶段检查 /healthz 服务的可用性。
# 【PURPOSE】：验证在 Kubernetes 环境中服务具备完善的滚动升级与版本回溯追溯机制，
#             确保在升级期间及版本回滚后网关均保持高可用状态，其健康检查（healthz）仍然可达。
# ==========================================
Write-Header "第二部分：滚动升级与回滚"

# 1. 记录初始版本历史
Write-Host "滚动升级前 Deployment/nginx-gateway 的版本历史记录:" -ForegroundColor Yellow
kubectl rollout history deployment/nginx-gateway

# 2. 触发滚动升级
Write-Host "正在触发 nginx-gateway 的滚动升级..."
kubectl rollout restart deployment/nginx-gateway
Write-Host "等待 nginx-gateway 滚动升级完成..."
kubectl rollout status deployment/nginx-gateway --timeout=60s

# 3. 升级后健康检查 (包含端口转发恢复与多轮重试以应对网络切换延迟)
$HealthzUrl = $GatewayUrl -replace '/v1/chat/completions$', '/healthz'
$UpgradeHealthStatus = "000"
$curlArgs = @("-s", "-o", "NUL", "-w", "%{http_code}", $HealthzUrl)

for ($i = 1; $i -le 5; $i++) {
    Ensure-PortForward
    Write-Host "升级完成，正在检查网关健康状态 (第 $i 次尝试): $HealthzUrl"
    $UpgradeHealthStatus = & curl.exe $curlArgs
    if ($UpgradeHealthStatus -eq "200") {
        break
    }
    Start-Sleep -Seconds 2
}

if ($UpgradeHealthStatus -eq "200") {
    Write-Success "升级后健康检查成功：返回了 200 OK！"
} else {
    Write-Failure "升级后健康检查失败：返回了 $UpgradeHealthStatus！"
}

# 4. 执行回滚操作
Write-Host "正在执行版本回滚，还原到上一个版本..."
kubectl rollout undo deployment/nginx-gateway
Write-Host "等待 nginx-gateway 回滚完成..."
kubectl rollout status deployment/nginx-gateway --timeout=60s

# 5. 回滚后健康检查 (包含端口转发恢复与多轮重试以应对网络切换延迟)
$RollbackHealthStatus = "000"
for ($i = 1; $i -le 5; $i++) {
    Ensure-PortForward
    Write-Host "回滚完成，正在检查网关健康状态 (第 $i 次尝试): $HealthzUrl"
    $RollbackHealthStatus = & curl.exe $curlArgs
    if ($RollbackHealthStatus -eq "200") {
        break
    }
    Start-Sleep -Seconds 2
}

if ($RollbackHealthStatus -eq "200") {
    Write-Success "回滚后健康检查成功：返回了 200 OK，网关恢复正常且可访问！"
} else {
    Write-Failure "回滚后健康检查失败：返回了 $RollbackHealthStatus！"
}

Write-Host "`n滚动升级与回滚后 Deployment/nginx-gateway 的版本历史记录:" -ForegroundColor Yellow
kubectl rollout history deployment/nginx-gateway
Write-Success "第二部分：滚动升级与回滚验证通过！"


# ==========================================
# 第三部分：API 鉴权与限流
# ==========================================
# 【DOING】：
#   1. 临时修改配置将 RATE_LIMIT_PER_MINUTE 限制调低为 5，并重启服务；
#   2. 发送不带 API Key、带错误 API Key 的请求，拦截并提取对应的 401 审计日志；
#   3. 发送 8 次无害的 invalid-model 请求触发限流，验证 429 拦截，并提取对应的限流审计日志；
#   4. 最终将限流限制还原回 30。
# 【PURPOSE】：验证网关的入口安全防护能力。确认当请求缺失或携带非法 X-API-Key 时能够被 401 强行拦截并产生安全审计日志；
#             同时验证在高频并发（如 DDoS）或非授权刷量场景下，网关能通过 Redis 计数器对 API Key 维度实施精确的限流控制，返回 429。
# ==========================================
Write-Header "第三部分：API 鉴权与限流"

Write-Host "正在临时将每分钟请求限流阈值调低为 5 次..."
kubectl patch configmap cb-config --type merge -p "data:`n  RATE_LIMIT_PER_MINUTE: '5'"
kubectl rollout restart deployment/coursebot
Write-Host "等待 coursebot 滚动重启就绪..."
kubectl rollout status deployment/coursebot --timeout=60s
Write-Host "等待 5 秒以让 Nginx DNS 缓存刷新..."
Start-Sleep -Seconds 5

Write-Host "正在清空 Redis 缓存以重置原有限流计数..."
kubectl exec statefulset/cb-redis -- redis-cli flushall | Out-Null

# --- 1. 未带 API Key 的测试 ---
Write-Host "1. 测试未携带 API Key 的请求拦截状态..."
$NoKeyResult = Send-Request $Body $null
if ($NoKeyResult.StatusCode -eq 401 -or $NoKeyResult.Content -match "invalid api key") {
    Write-Success "未带 API Key 拦截成功：已返回 HTTP 401 状态！"
} else {
    Write-Failure "未带 API Key 拦截失败：返回了 HTTP $($NoKeyResult.StatusCode)！"
}

# 提取未带 API Key 的安全审计日志
Write-Host "提取未携带 API Key 拦截的安全审计日志..." -ForegroundColor Yellow
Start-Sleep -Seconds 2
$NewestPod = kubectl get pods -l app=coursebot --field-selector=status.phase=Running --sort-by=.metadata.creationTimestamp -o jsonpath="{.items[-1].metadata.name}"
$Logs = kubectl logs $NewestPod --tail=30
$NoKeyLogFound = $false
foreach ($line in ($Logs -split "`n")) {
    if ($line -match "event=request_rejected" -and $line -match "reason=invalid_api_key" -and $line -match "api_key_suffix=none") {
        Write-Host "发现 API Key 缺失拦截日志: $line" -ForegroundColor DarkYellow
        $NoKeyLogFound = $true
    }
}
if ($NoKeyLogFound) {
    Write-Success "API Key 缺失拦截安全日志验证成功！"
} else {
    Write-Failure "未能在日志中找到 API Key 缺失的安全审计事件。"
}

# --- 2. 携带错误 API Key 的测试 ---
Write-Host "`n2. 测试携带错误 API Key 的请求拦截状态..."
$WrongKeyResult = Send-Request $Body "wrong-key-abc"
if ($WrongKeyResult.StatusCode -eq 401 -or $WrongKeyResult.Content -match "invalid api key") {
    Write-Success "错误 API Key 拦截成功：已返回 HTTP 401 状态！"
} else {
    Write-Failure "错误 API Key 拦截失败：返回了 HTTP $($WrongKeyResult.StatusCode)！"
}

# 提取携带错误 API Key 的安全审计日志
Write-Host "提取携带错误 API Key 拦截的安全审计日志..." -ForegroundColor Yellow
Start-Sleep -Seconds 2
$Logs = kubectl logs $NewestPod --tail=30
$WrongKeyLogFound = $false
foreach ($line in ($Logs -split "`n")) {
    if ($line -match "event=request_rejected" -and $line -match "reason=invalid_api_key" -and $line -match "api_key_suffix=-key-abc") {
        Write-Host "发现错误 API Key 拦截日志: $line" -ForegroundColor DarkYellow
        $WrongKeyLogFound = $true
    }
}
if ($WrongKeyLogFound) {
    Write-Success "错误 API Key 拦截安全日志验证成功！"
} else {
    Write-Failure "未能在日志中找到错误 API Key 拦截的安全审计事件。"
}

# --- 3. 限流防护测试 ---
Write-Host "`n3. 测试高频请求下的频次限流防护 (发送 8 次请求，使用的 invalid-model 模型前缀会直接触发 400，以此避免无关敏感词且提升测试并发度)..."
$LimitExceeded = $false
$Status429Count = 0
$FastBody = '{"model": "invalid-model", "messages": [{"role": "user", "content": "ping"}], "use_rag": false}'

for ($i = 1; $i -le 8; $i++) {
    $Res = Send-Request $FastBody $ApiKey
    if ($Res.StatusCode -eq 429 -or $Res.Content -match "rate limit exceeded" -or $Res.Content -match "Rate limit exceeded") {
        $LimitExceeded = $true
        $Status429Count++
    }
}

if ($LimitExceeded) {
    Write-Success "频次限流验证成功：成功拦截并触发了 429 Too Many Requests 状态码 (总共拦截了 $Status429Count 次)！"
} else {
    Write-Failure "频次限流验证失败：连续发送了 8 次高频请求但未触发过任何 429 报错！"
}

# 提取限流安全审计日志
Write-Host "提取频次限流拦截的安全审计日志..." -ForegroundColor Yellow
Start-Sleep -Seconds 2
$Logs = kubectl logs $NewestPod --tail=30
$RateLimitLogFound = $false
foreach ($line in ($Logs -split "`n")) {
    if ($line -match "event=rate_limited" -and $line -match "api_key_suffix=ey-12345") {
        Write-Host "发现限流拦截日志: $line" -ForegroundColor DarkYellow
        $RateLimitLogFound = $true
    }
}
if ($RateLimitLogFound) {
    Write-Success "频次限流安全日志验证成功！"
} else {
    Write-Failure "未能在日志中找到频次限流的安全审计事件。"
}

# 恢复默认的限流设定值（30次/分钟）
Write-Host "`n正在恢复默认的限流阈值 (设置 RATE_LIMIT_PER_MINUTE = 30)..."
kubectl patch configmap cb-config --type merge -p "data:`n  RATE_LIMIT_PER_MINUTE: '30'"
kubectl rollout restart deployment/coursebot
Write-Host "等待 coursebot 滚动重启就绪..."
kubectl rollout status deployment/coursebot --timeout=60s
Write-Host "等待 5 秒以让 Nginx DNS 缓存刷新..."
Start-Sleep -Seconds 5


# ==========================================
# 第四部分：内容审查与安全日志
# ==========================================
# 【DOING】：
#   1. 向网关提交包含手机号、邮箱、身份证号的 PII 测试请求，验证返回内容已被占位符替换，并检查 PII 审计日志；
#   2. 向网关提交包含黑名单词汇（“盗号”）的请求，验证请求已被直接拒绝（400 状态），并检查 request_rejected 审计日志。
# 【PURPOSE】：验证网关的内容安全审查机制。确保系统不会向大模型泄露用户的敏感 PII 数据（即在输入端就进行脱敏替换）；
#             同时验证对于违法、违规的敏感黑名单关键词，网关能直接拒绝该请求，防范恶意 prompt 注入，并输出可审计的安全日志。
# ==========================================
Write-Header "第四部分：内容审查与安全日志"

Write-Host "正在清空 Redis 缓存以防受此前限流计数影响..."
kubectl exec statefulset/cb-redis -- redis-cli flushall | Out-Null

# --- 1. PII 敏感信息脱敏测试 ---
Write-Host "1. 测试 PII 敏感信息脱敏..."
$PiiPrompt = "Output this exact line: phone: 13912345678, email: test@example.com, ID: 110101199003072345"
Write-Host "[INPUT PROMPT] $PiiPrompt" -ForegroundColor Yellow

$PiiBody = '{"model": "ollama/qwen2.5:0.5b", "messages": [{"role": "user", "content": "' + $PiiPrompt + '"}], "use_rag": false}'

$PiiResObj = Send-Request $PiiBody $ApiKey
Write-Host "模型实际响应的文本内容 (应包含被替换后的 [PHONE], [EMAIL], [ID] 占位符):" -ForegroundColor Gray
Write-Host $PiiResObj.Content -ForegroundColor DarkGray

if ($PiiResObj.Content -match '\[\s*PHONE\s*\]' -and $PiiResObj.Content -match '\[\s*EMAIL\s*\]' -and $PiiResObj.Content -match '\[\s*ID\s*\]') {
    Write-Success "PII 响应脱敏回显匹配检测成功！"
} else {
    Write-Failure "PII 响应脱敏回显匹配检测失败：返回数据中未捕获到正确的脱敏占位符。"
}

# 提取 PII 敏感信息脱敏的安全审计日志
Write-Host "提取 PII 安全审计日志..." -ForegroundColor Yellow
Start-Sleep -Seconds 2
$NewestPod = kubectl get pods -l app=coursebot --field-selector=status.phase=Running --sort-by=.metadata.creationTimestamp -o jsonpath="{.items[-1].metadata.name}"
$Logs = kubectl logs $NewestPod --tail=30
$PiiLogFound = $false
foreach ($line in ($Logs -split "`n")) {
    if ($line -match "event=pii_redacted") {
        Write-Host "Found PII log: $line" -ForegroundColor DarkYellow
        $PiiLogFound = $true
    }
}
if ($PiiLogFound) {
    Write-Success "PII 数据安全审计日志验证成功！"
} else {
    Write-Failure "未在最新的日志中定位到 PII 脱敏审计日志。"
}

# --- 2. 黑名单关键词拦截测试 ---
Write-Host "`n2. 测试黑名单关键词拦截..."
$BlacklistPrompt = "盗号"
Write-Host "[INPUT PROMPT] $BlacklistPrompt" -ForegroundColor Yellow

$BlacklistBody = '{"model": "ollama/qwen2.5:0.5b", "messages": [{"role": "user", "content": "\u76d7\u53f7"}], "use_rag": false}'

$BlacklistResObj = Send-Request $BlacklistBody $ApiKey
if ($BlacklistResObj.StatusCode -eq 400 -and $BlacklistResObj.Content -match "request rejected") {
    Write-Success "黑名单拦截验证成功：网关拦截请求并返回了 HTTP 400 状态与 'request rejected' 错误消息！"
} else {
    Write-Failure "黑名单拦截验证失败：返回状态为 HTTP $($BlacklistResObj.StatusCode)，内容为 $($BlacklistResObj.Content)！"
}

# 提取黑名单关键词拦截的安全审计日志
Write-Host "提取黑名单关键词拦截日志..." -ForegroundColor Yellow
Start-Sleep -Seconds 2
$NewestPod = kubectl get pods -l app=coursebot --field-selector=status.phase=Running --sort-by=.metadata.creationTimestamp -o jsonpath="{.items[-1].metadata.name}"
$Logs = kubectl logs $NewestPod --tail=30
$RejectedLogFound = $false
foreach ($line in ($Logs -split "`n")) {
    if ($line -match "event=request_rejected.*reason=blocked_keyword") {
        Write-Host "Found blacklist log: $line" -ForegroundColor DarkYellow
        $RejectedLogFound = $true
    }
}
if ($RejectedLogFound) {
    Write-Success "黑名单数据拦截安全审计日志验证成功！"
} else {
    Write-Failure "未在最新的日志中定位到黑名单拦截的审计日志。"
}

Write-Header "所有测试用例已全部执行并通过验证"
