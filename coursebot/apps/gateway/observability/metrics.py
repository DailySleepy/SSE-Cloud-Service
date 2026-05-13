import time
from prometheus_client import Gauge, Counter, Histogram

# 核心指标 1：当前活跃的 LLM 请求并发数
gateway_llm_active_requests = Gauge(
    "gateway_llm_active_requests",
    "Number of active LLM requests being processed by the gateway"
)

# 核心指标 2：LLM 请求总数（带有状态和模型标签）
gateway_llm_requests_total = Counter(
    "gateway_llm_requests_total",
    "Total number of LLM requests processed by the gateway",
    labelnames=["status", "model"]
)

# 核心指标 3：LLM 请求处理耗时
# 定义一些针对 LLM 响应时间的典型 bucket（例如 0.5s 到 120s）
gateway_llm_request_latency_seconds = Histogram(
    "gateway_llm_request_latency_seconds",
    "Latency of LLM requests processed by the gateway in seconds",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0]
)
