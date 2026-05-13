# scripts/test/loadtest.ps1
# PowerShell 并发压测脚本 - 已加入动态标签绕过缓存

$TargetUrl = "http://localhost:8000/v1/chat/completions"
$Concurrency = 5
$RequestsPerProcess = 10
$ModelName = "ollama/qwen2.5:0.5b" # 将模型名称提取出来方便传递

Write-Host "开始执行并发测试, URL: $TargetUrl" -ForegroundColor Cyan
Write-Host "并发数: $Concurrency, 每进程请求数: $RequestsPerProcess" -ForegroundColor Cyan

# 定义要在后台执行的脚本块
$ScriptBlock = {
    param($Url, $Model, $Requests)
    for ($i = 1; $i -le $Requests; $i++) {
        try {
            # --- 关键修改：动态生成唯一内容 ---
            $timestamp = Get-Date -Format "HH:mm:ss.fff"
            $randomNum = Get-Random -Minimum 1000 -Maximum 9999
            $uniqueContent = "hi - [$timestamp]-[$randomNum]"

            # 动态构造对象并转换为 JSON
            $DynamicPayload = @{
                model = $Model
                messages = @(
                    @{ role = "user"; content = $uniqueContent }
                )
                use_rag = $false
            } | ConvertTo-Json -Depth 10
            # -------------------------------

            $response = Invoke-RestMethod -Uri $Url -Method Post -Body $DynamicPayload -ContentType "application/json" -ErrorAction Stop
            
            # 可选：在控制台打印进度（注意多线程竞争下输出可能较乱）
            # Write-Host "发送内容: $uniqueContent" 

            Start-Sleep -Milliseconds 200
        } catch {
            Write-Host "请求失败: $_" -ForegroundColor Red
        }
    }
}

$Runspaces = @()
for ($i = 0; $i -lt $Concurrency; $i++) {
    # 传递参数：URL、模型名称、每进程请求数
    $Runspaces += Start-ThreadJob -ScriptBlock $ScriptBlock -ArgumentList $TargetUrl, $ModelName, $RequestsPerProcess
}

Write-Host "后台任务已启动，正在发送动态请求以绕过缓存..." -ForegroundColor Yellow

# 等待所有后台任务完成
Receive-Job -Job $Runspaces -Wait | Out-Null
Remove-Job -Job $Runspaces

Write-Host "压测执行完毕！" -ForegroundColor Green