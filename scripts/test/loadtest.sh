#!/bin/bash
# scripts/test/loadtest.sh
# Linux/Bash 并发压测脚本 - 已加入动态标签绕过缓存

TARGET_URL="http://localhost:8000/v1/chat/completions"
CONCURRENCY=5
REQUESTS_PER_PROCESS=10
MODEL_NAME="ollama/qwen2.5:0.5b"

echo -e "\033[0;36m开始执行并发测试, URL: $TARGET_URL\033[0m"
echo -e "\033[0;36m并发数: $CONCURRENCY, 每进程请求数: $REQUESTS_PER_PROCESS\033[0m"

# 测试执行函数
send_requests() {
    local url=$1
    local model=$2
    local requests=$3
    
    for ((i=1; i<=requests; i++)); do
        # --- 关键修改：动态生成唯一内容 ---
        # %3N 在某些 macOS 版本下可能不支持，但在标准 Linux 下工作正常
        timestamp=$(date +"%H:%M:%S.%3N")
        random_num=$((RANDOM % 9000 + 1000))
        unique_content="hi - [$timestamp]-[$random_num]"
        
        # 构造 JSON Payload
        payload=$(cat <<EOF
{
  "model": "$model",
  "messages": [
    {"role": "user", "content": "$unique_content"}
  ],
  "use_rag": false
}
EOF
)

        # 发送请求并检查响应
        response=$(curl -s -w "\n%{http_code}" -X POST -H "Content-Type: application/json" -d "$payload" "$url")
        http_code=$(echo "$response" | tail -n1)
        
        if [ "$http_code" -ne 200 ]; then
            echo -e "\033[0;31m请求失败! HTTP Code: $http_code\033[0m"
            echo "$response" | head -n -1
        fi
        
        # 稍微加一点延迟
        sleep 0.2
    done
}

# 启动并发进程
for ((i=0; i<CONCURRENCY; i++)); do
    send_requests "$TARGET_URL" "$MODEL_NAME" "$REQUESTS_PER_PROCESS" &
done

echo -e "\033[0;33m后台任务已启动，正在压测中（预计持续 10~20 秒），请去 Grafana 观察数据...\033[0m"

# 等待所有后台任务完成
wait

echo -e "\033[0;32m压测执行完毕！\033[0m"
