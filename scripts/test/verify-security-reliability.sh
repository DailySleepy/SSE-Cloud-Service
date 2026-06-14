#!/bin/bash
# scripts/test/verify-security-reliability.sh
# CourseBot 安全网关与可靠性测试套件 (Linux Bash 版)

set -e

# 定义终端输出颜色
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # 无颜色

write_header() {
    echo -e "\n${CYAN}==========================================${NC}"
    echo -e "${CYAN}>>> $1${NC}"
    echo -e "${CYAN}==========================================${NC}"
}

write_success() {
    echo -e "${GREEN}[SUCCESS] $1${NC}"
}

write_failure() {
    echo -e "${RED}[FAILURE] $1${NC}"
}

GATEWAY_URL="http://localhost:8080/v1/chat/completions"
API_KEY="cb-gateway-api-key-12345"

# ==========================================
# 第一部分：可靠性降级链路成功
# ==========================================
# 【当前在干什么】：将配置项 FORCE_OLLAMA_500 设为 true，并重启服务。随后发送测试请求并还原配置。
# 【目的是什么】：验证在高可用架构中，当本地 primary LLM (Ollama) 服务不可用或崩溃时，
#             系统能自动且平滑地实施降级，转入 SaaS 备份服务或返回 template 静态模板，而不会使网关直接瘫痪。
# ==========================================
write_header "第一部分：可靠性降级链路成功"

echo "正在模拟 Ollama 故障 (通过设置 FORCE_OLLAMA_500 = true 以强制让本地 LLM 返回 500 报错)..."
kubectl patch configmap cb-config --type merge -p '
data:
  FORCE_OLLAMA_500: "true"
'
kubectl rollout restart deployment/coursebot
echo "等待 coursebot 重启就绪..."
kubectl rollout status deployment/coursebot --timeout=60s
echo "等待 5 秒以让 Nginx 的内部 DNS 解析缓存刷新..."
sleep 5

echo "发送测试请求到网关以验证降级机制..."
BODY='{"model": "ollama/qwen2.5:0.5b", "messages": [{"role": "user", "content": "Please introduce yourself"}]}'

RESPONSE=$(curl -s -i -X POST "$GATEWAY_URL" -H "Content-Type: application/json" -H "X-API-Key: $API_KEY" -d "$BODY")
echo -e "返回 JSON 结果:\n$RESPONSE"

if [[ "$RESPONSE" == *"degraded"* && "$RESPONSE" == *"true"* ]] || [[ "$RESPONSE" == *"provider"* && "$RESPONSE" == *"saas"* ]] || [[ "$RESPONSE" == *"provider"* && "$RESPONSE" == *"template"* ]]; then
    write_success "降级链路测试成功：已成功降级，并返回 degraded=true / provider 备份标识！"
else
    write_failure "降级链路测试未检测到 degraded=true 标记。"
fi

echo -e "\n正在恢复 Ollama 的正常工作状态 (设置 FORCE_OLLAMA_500 = false)..."
kubectl patch configmap cb-config --type merge -p '
data:
  FORCE_OLLAMA_500: "false"
'
kubectl rollout restart deployment/coursebot
echo "等待 coursebot 重启就绪..."
kubectl rollout status deployment/coursebot --timeout=60s
echo "等待 5 秒以让 Nginx DNS 缓存刷新..."
sleep 5


# ==========================================
# 第二部分：滚动升级与回滚
# ==========================================
# 【当前在干什么】：调用 kubectl rollout history 打印出应用与网关的历史部署版本列表。
# 【目的是什么】：验证在 Kubernetes 环境中服务具备完善的滚动升级与版本回溯追溯机制，
#             确保当部署存在安全漏洞或程序缺陷时能够随时实现版本回滚。
# ==========================================
write_header "第二部分：滚动升级与回滚"

echo -e "${YELLOW}当前 Deployment/coursebot 的版本历史记录:${NC}"
kubectl rollout history deployment/coursebot

echo -e "\n${YELLOW}当前 Deployment/nginx-gateway 的版本历史记录:${NC}"
kubectl rollout history deployment/nginx-gateway

write_success "版本滚动历史已成功展示。"


# ==========================================
# 第三部分：API 鉴权与限流
# ==========================================
# 【当前在干什么】：
#   1. 临时修改配置将 RATE_LIMIT_PER_MINUTE 限制调低为 5，并重启服务；
#   2. 发送不带 API Key、带错误 API Key 的请求，拦截并提取对应的 401 审计日志；
#   3. 发送 8 次无害的 invalid-model 请求触发限流，验证 429 拦截，并提取对应的限流审计日志；
#   4. 最终将限流限制还原回 30。
# 【目的是什么】：验证网关的入口安全防护能力。确认当请求缺失或携带非法 X-API-Key 时能够被 401 强行拦截并产生安全审计日志；
#             同时验证在高频并发（如 DDoS）或非授权刷量场景下，网关能通过 Redis 计数器对 API Key 维度实施精确的限流控制，返回 429。
# ==========================================
write_header "第三部分：API 鉴权与限流"

echo "临时将限流频次调低为每分钟 5 次..."
kubectl patch configmap cb-config --type merge -p '
data:
  RATE_LIMIT_PER_MINUTE: "5"
'
kubectl rollout restart deployment/coursebot
echo "等待 coursebot 重启就绪..."
kubectl rollout status deployment/coursebot --timeout=60s
echo "等待 5 秒以让 Nginx DNS 缓存刷新..."
sleep 5

echo "重置 Redis 限流计数器..."
kubectl exec statefulset/cb-redis -- redis-cli flushall > /dev/null

# --- 1. 未带 API Key 的测试 ---
echo "1. 测试未带 API Key 访问..."
NO_KEY_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$GATEWAY_URL" \
    -H "Content-Type: application/json" \
    -d "$BODY")

if [ "$NO_KEY_STATUS" -eq 401 ]; then
    write_success "未带 API Key 拦截成功：返回了 401！"
else
    write_failure "未带 API Key 拦截失败：返回了 $NO_KEY_STATUS！"
fi

# 提取未带 API Key 的日志
echo -e "提取未携带 API Key 拦截的安全审计日志..."
sleep 2
NEWEST_POD=$(kubectl get pods -l app=coursebot --field-selector=status.phase=Running --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}')
LOGS=$(kubectl logs "$NEWEST_POD" --tail=30)
NO_KEY_LOG_FOUND=false
while IFS= read -r line; do
    if [[ "$line" == *"event=request_rejected"* && "$line" == *"reason=invalid_api_key"* && "$line" == *"api_key_suffix=none"* ]]; then
        echo -e "${YELLOW}发现 API Key 缺失拦截日志: $line${NC}"
        NO_KEY_LOG_FOUND=true
    fi
done <<< "$LOGS"
if [ "$NO_KEY_LOG_FOUND" = true ]; then
    write_success "API Key 缺失拦截安全日志验证成功！"
else
    write_failure "未能在日志中找到 API Key 缺失的安全审计事件。"
fi

# --- 2. 携带错误 API Key 的测试 ---
echo -e "\n2. 测试带错误 API Key 访问..."
WRONG_KEY_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$GATEWAY_URL" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: wrong-key-abc" \
    -d "$BODY")

if [ "$WRONG_KEY_STATUS" -eq 401 ]; then
    write_success "错误 API Key 拦截成功：返回了 401！"
else
    write_failure "错误 API Key 拦截失败：返回了 $WRONG_KEY_STATUS！"
fi

# 提取错误 API Key 的日志
echo -e "提取携带错误 API Key 拦截的安全审计日志..."
sleep 2
LOGS=$(kubectl logs "$NEWEST_POD" --tail=30)
WRONG_KEY_LOG_FOUND=false
while IFS= read -r line; do
    if [[ "$line" == *"event=request_rejected"* && "$line" == *"reason=invalid_api_key"* && "$line" == *"api_key_suffix=-key-abc"* ]]; then
        echo -e "${YELLOW}发现错误 API Key 拦截日志: $line${NC}"
        WRONG_KEY_LOG_FOUND=true
    fi
done <<< "$LOGS"
if [ "$WRONG_KEY_LOG_FOUND" = true ]; then
    write_success "错误 API Key 拦截安全日志验证成功！"
else
    write_failure "未能在日志中找到错误 API Key 拦截的安全审计事件。"
fi

# --- 3. 限流防护测试 ---
echo -e "\n3. 测试频次限流 (使用无害 invalid-model 连续发送 8 次请求)..."
LIMIT_EXCEEDED=false
STATUS_429_COUNT=0
FAST_BODY='{"model": "invalid-model", "messages": [{"role": "user", "content": "ping"}]}'

for i in {1..8}; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$GATEWAY_URL" \
        -H "Content-Type: application/json" \
        -H "X-API-Key: $API_KEY" \
        -d "$FAST_BODY")
    if [ "$STATUS" -eq 429 ]; then
        LIMIT_EXCEEDED=true
        ((STATUS_429_COUNT++))
    fi
done

if [ "$LIMIT_EXCEEDED" = true ]; then
    write_success "限流拦截成功：触发了 429 Too Many Requests (拦截了 $STATUS_429_COUNT 次)！"
else
    write_failure "限流拦截失败：发送了 8 次请求均未触发 429！"
fi

# 提取限流拦截的日志
echo -e "提取限流拦截的安全审计日志..."
sleep 2
LOGS=$(kubectl logs "$NEWEST_POD" --tail=30)
RATE_LIMIT_LOG_FOUND=false
while IFS= read -r line; do
    if [[ "$line" == *"event=rate_limited"* && "$line" == *"api_key_suffix=ey-12345"* ]]; then
        echo -e "${YELLOW}发现限流拦截日志: $line${NC}"
        RATE_LIMIT_LOG_FOUND=true
    fi
done <<< "$LOGS"
if [ "$RATE_LIMIT_LOG_FOUND" = true ]; then
    write_success "限流拦截安全日志验证成功！"
else
    write_failure "未能在日志中找到限流拦截的安全审计事件。"
fi

echo -e "\n恢复限流频次为每分钟 30 次..."
kubectl patch configmap cb-config --type merge -p '
data:
  RATE_LIMIT_PER_MINUTE: "30"
'
kubectl rollout restart deployment/coursebot
echo "等待 coursebot 重启就绪..."
kubectl rollout status deployment/coursebot --timeout=60s
echo "等待 5 秒以让 Nginx DNS 缓存刷新..."
sleep 5


# ==========================================
# 第四部分：内容审查与安全日志
# ==========================================
# 【当前在干什么】：
#   1. 向网关提交包含手机号、邮箱、身份证号的 PII 测试请求，验证返回内容已被占位符替换，并检查 PII 审计日志；
#   2. 向网关提交包含黑名单词汇（“盗号”）的请求，验证请求已被直接拒绝（400 状态），并检查 request_rejected 审计日志。
# 【目的是什么】：验证网关的内容安全审查机制。确保系统不会向大模型泄露用户的敏感 PII 数据（即在输入端就进行脱敏替换）；
#             同时验证对于违法、违规的敏感黑名单关键词，网关能直接拒绝该请求，防范恶意 prompt 注入，并输出可审计的安全日志。
# ==========================================
write_header "第四部分：内容审查与安全日志"

echo "重置 Redis 限流计数器..."
kubectl exec statefulset/cb-redis -- redis-cli flushall > /dev/null

# --- 1. PII 敏感信息脱敏测试 ---
echo "1. 测试 PII 敏感信息脱敏..."
PII_PROMPT="Output this exact line: phone: 13912345678, email: test@example.com, ID: 110101199003072345"
echo -e "${YELLOW}[INPUT PROMPT] $PII_PROMPT${NC}"

PII_BODY="{\"model\": \"ollama/qwen2.5:0.5b\", \"messages\": [{\"role\": \"user\", \"content\": \"$PII_PROMPT\"}]}"

PII_RESPONSE=$(curl -s -X POST "$GATEWAY_URL" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d "$PII_BODY")

echo -e "模型返回内容 (应包含脱敏占位符 [PHONE], [EMAIL], [ID]):\n$PII_RESPONSE"

if [[ "$PII_RESPONSE" =~ \[[[:space:]]*PHONE[[:space:]]*\] && "$PII_RESPONSE" =~ \[[[:space:]]*EMAIL[[:space:]]*\] && "$PII_RESPONSE" =~ \[[[:space:]]*ID[[:space:]]*\] ]]; then
    write_success "PII 响应脱敏回显检测成功！"
else
    write_failure "PII 响应脱敏回显检测失败：未包含期望的脱敏占位符。"
fi

echo -e "提取 PII 安全审计日志..."
sleep 2
NEWEST_POD=$(kubectl get pods -l app=coursebot --field-selector=status.phase=Running --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}')
LOGS=$(kubectl logs "$NEWEST_POD" --tail=30)
PII_LOG_FOUND=false
while IFS= read -r line; do
    if [[ "$line" == *"event=pii_redacted"* ]]; then
        echo -e "${YELLOW}发现 PII 脱敏日志: $line${NC}"
        PII_LOG_FOUND=true
    fi
done <<< "$LOGS"

if [ "$PII_LOG_FOUND" = true ]; then
    write_success "PII 安全审计日志检测成功！"
else
    write_failure "未发现 PII 安全审计日志。"
fi


# --- 2. 黑名单关键词拦截测试 ---
echo -e "\n2. 测试黑名单关键词拦截..."
BLACKLIST_PROMPT="盗号"
echo -e "${YELLOW}[INPUT PROMPT] $BLACKLIST_PROMPT${NC}"

BLACKLIST_BODY='{"model": "ollama/qwen2.5:0.5b", "messages": [{"role": "user", "content": "\u76d7\u53f7"}]}'

BLACKLIST_RES=$(curl -s -i -X POST "$GATEWAY_URL" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d "$BLACKLIST_BODY")

if [[ "$BLACKLIST_RES" == *"400 Bad Request"* || "$BLACKLIST_RES" == *"HTTP/1.1 400"* ]] && [[ "$BLACKLIST_RES" == *"request rejected"* ]]; then
    write_success "黑名单拦截成功：返回了 400 Bad Request 并且包含 'request rejected' 消息！"
else
    write_failure "黑名单拦截失败！"
fi

echo -e "提取黑名单安全审计日志..."
sleep 2
NEWEST_POD=$(kubectl get pods -l app=coursebot --field-selector=status.phase=Running --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}')
LOGS=$(kubectl logs "$NEWEST_POD" --tail=30)
REJECTED_LOG_FOUND=false
while IFS= read -r line; do
    if [[ "$line" == *"event=request_rejected"* && "$line" == *"reason=blocked_keyword"* ]]; then
        echo -e "${YELLOW}发现黑名单拦截日志: $line${NC}"
        REJECTED_LOG_FOUND=true
    fi
done <<< "$LOGS"

if [ "$REJECTED_LOG_FOUND" = true ]; then
    write_success "黑名单安全审计日志检测成功！"
else
    write_failure "未发现黑名单安全审计日志。"
fi

write_header "测试套件全部执行完毕"
