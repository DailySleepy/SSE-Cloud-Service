#!/bin/bash
# demo.sh - 本地调用 CourseBot 的 API 测试脚本

HOST=${1:-"http://localhost"}

echo "--- 检查健康状态 ---"
curl -s "$HOST/healthz"
echo -e "\n"

echo "--- 检查就绪状态 ---"
curl -s "$HOST/readyz"
echo -e "\n"

echo "--- 发送对话请求 (POST /v1/chat/completions) ---"
curl -s -X POST "$HOST/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openrouter/auto",
    "messages": [
      {
        "role": "user",
        "content": "Hello! What is your name and what can you do? (Keep it short under 10 words)"
      }
    ]
  }' | jq || echo "如没有 jq，请查看上方原始输出"
echo -e "\n"
