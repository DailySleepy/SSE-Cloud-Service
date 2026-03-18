#!/bin/bash
# demo.sh - 本地调用 CourseBot 的 API 测试脚本

HOST=${1:-"http://localhost"}

echo "--- 1. 检查健康状态 (/healthz) ---"
curl -s "$HOST/healthz"
echo -e "\n\n"

echo "--- 2. 检查就绪状态 (/readyz) ---"
echo "在此测试中，如果未配置 OpenRouter API Key，预计会返回 degraded 和 saas: error"
curl -s "$HOST/readyz"
echo -e "\n\n"

echo "--- 3. 发送正常请求: 测试 Ollama Provider 与本地模型 ---"
echo "正在请求 ollama/qwen2.5:0.5b (第一次请求可能较慢)..."
time curl -s -X POST "$HOST/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ollama/qwen2.5:0.5b",
    "messages": [
      {
        "role": "user",
        "content": "请用一句话解释容器虚拟化的核心概念。"
      }
    ]
  }'
echo -e "\n\n"

echo "--- 4. 发送相同请求: 测试 Redis 缓存机制 ---"
echo "再次请求相同的 prompt，预期瞬间返回并带有 _meta 中 cached: true 的标记..."
time curl -s -X POST "$HOST/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ollama/qwen2.5:0.5b",
    "messages": [
      {
        "role": "user",
        "content": "请用一句话解释容器虚拟化的核心概念。"
      }
    ]
  }'
echo -e "\n\n"

echo "--- 5. 错误处理测试: 非法前缀 ---"
echo "请求 abc/xxx，预期返回 400 Bad Request 和明确错误信息..."
curl -s -X POST "$HOST/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "abc/xxx",
    "messages": [
      {
        "role": "user",
        "content": "hi"
      }
    ]
  }'
echo -e "\n\n"

echo "--- 6. 错误处理测试: 本地未拉取的模型 ---"
echo "请求 ollama/non-existent-model，预期返回 500 并提示未拉取模型..."
curl -s -X POST "$HOST/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ollama/non-existent-model",
    "messages": [
      {
        "role": "user",
        "content": "hi"
      }
    ]
  }'
echo -e "\n\n"

