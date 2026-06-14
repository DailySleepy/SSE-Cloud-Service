import os
import time
import hmac
import logging
from typing import Optional
from fastapi import Header, HTTPException
import redis.asyncio as redis
from packages.common.config import settings

# 实例化独立的 Redis 客户端，避免循环引用
redis_client = redis.from_url(settings.redis_url, decode_responses=True)

# 初始化系统 Logger
logger = logging.getLogger("coursebot.security")

def log_security_event(event: str, **kwargs):
    """
    输出结构化 Key-Value 格式的安全日志到标准输出
    """
    # 过滤敏感信息（以防 kwargs 中带入敏感参数）
    filtered_kwargs = {}
    for k, v in kwargs.items():
        if k in ("api_key", "token", "password", "secret", "prompt", "response"):
            continue
        filtered_kwargs[k] = v
        
    kv_pairs = [f"event={event}"] + [f"{k}={v}" for k, v in filtered_kwargs.items()]
    log_str = " ".join(kv_pairs)
    
    # 打印到标准输出以供 K8s 日志收集，同时使用 logger 输出
    print(log_str, flush=True)
    logger.info(log_str)

def get_api_key_suffix(api_key: Optional[str]) -> str:
    """
    获取 API Key 的后 8 位后缀，若长度不足则返回全部。若为 None 返回 "none"。
    """
    if not api_key:
        return "none"
    return api_key[-8:] if len(api_key) >= 8 else api_key

async def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> str:
    """
    API 鉴权拦截器。采用恒定时间比较防御时序攻击。
    若 API-Key 缺失或错误，返回 HTTP 401 Unauthorized。
    """
    expected_key = os.environ.get("COURSEBOT_API_KEY", "")
    suffix = get_api_key_suffix(x_api_key)

    if not x_api_key:
        log_security_event("request_rejected", reason="invalid_api_key", api_key_suffix="none")
        raise HTTPException(status_code=401, detail="invalid api key")

    if not hmac.compare_digest(x_api_key, expected_key):
        log_security_event("request_rejected", reason="invalid_api_key", api_key_suffix=suffix)
        raise HTTPException(status_code=401, detail="invalid api key")

    return x_api_key

async def check_rate_limit(api_key: str):
    """
    使用 Redis 计数器实现按 API Key 维度的限流。
    """
    limit = int(os.environ.get("RATE_LIMIT_PER_MINUTE", 30))
    suffix = get_api_key_suffix(api_key)
    
    # 分钟级时间戳，格式：YYYYMMDDHHMM
    minute_timestamp = time.strftime("%Y%m%d%H%M", time.localtime())
    redis_key = f"rate_limit:{suffix}:{minute_timestamp}"
    
    try:
        current_count = await redis_client.incr(redis_key)
        # 若是当前窗口首次请求，设置过期时间
        if current_count == 1:
            await redis_client.expire(redis_key, 70)
            
        if current_count > limit:
            log_security_event("rate_limited", api_key_suffix=suffix, limit=limit, window="minute")
            raise HTTPException(status_code=429, detail="rate limit exceeded")
    except HTTPException:
        raise
    except Exception as e:
        # 缓存或连接异常时，选择放行，但不影响核心调用逻辑 (KISS + Fail-open)
        logger.warning(f"Redis rate limiter exception: {str(e)}")
        pass
