import os
import time
import asyncio
from typing import Dict, Any, List
from services.llm_adapter.provider import OllamaProvider, SaaSProvider
from apps.gateway.security import log_security_event
from packages.common.config import settings

class CircuitBreakerOpenException(Exception):
    pass

class OllamaCircuitBreaker:
    """
    本地 Ollama 服务的单例熔断状态机
    """
    def __init__(self, fail_max: int = 3, reset_timeout: float = 30.0):
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.fail_count = 0
        self.last_state_change = 0.0
        self.is_probing = False
        self._lock = asyncio.Lock()

    async def allow_request(self) -> bool:
        async with self._lock:
            now = time.time()
            if self.state == "OPEN":
                if now - self.last_state_change >= self.reset_timeout:
                    self.state = "HALF_OPEN"
                    self.last_state_change = now
                    self.is_probing = True
                    return True
                else:
                    return False
            elif self.state == "HALF_OPEN":
                if not self.is_probing:
                    self.is_probing = True
                    return True
                else:
                    return False
            return True

    async def record_success(self):
        async with self._lock:
            if self.state in ("HALF_OPEN", "OPEN"):
                self.state = "CLOSED"
            self.fail_count = 0
            self.is_probing = False

    async def record_failure(self):
        async with self._lock:
            self.fail_count += 1
            if self.state == "CLOSED":
                if self.fail_count >= self.fail_max:
                    self.state = "OPEN"
                    self.last_state_change = time.time()
            elif self.state == "HALF_OPEN":
                self.state = "OPEN"
                self.last_state_change = time.time()
            self.is_probing = False

# 全局单例熔断器
ollama_breaker = OllamaCircuitBreaker(fail_max=3, reset_timeout=30.0)

async def run_fallback_chain(model: str, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
    """
    三级降级链路：Ollama (本地) -> SaaS LLM (在线备份) -> Template (静态模板)
    """
    # 1. 第一级：本地 Ollama
    try:
        # 检查熔断状态 (必须在模拟报错前检查，以展现熔断拦截效果)
        if not await ollama_breaker.allow_request():
            raise CircuitBreakerOpenException("Ollama circuit breaker is OPEN")

        # 混沌测试：模拟 Ollama 500 报错
        if os.environ.get("FORCE_OLLAMA_500") == "true":
            raise RuntimeError("FORCE_OLLAMA_500 is set to true")

        # 初始化 Ollama Provider
        ollama_url = os.environ.get("OLLAMA_BASE_URL") or settings.ollama_base_url
        ollama_provider = OllamaProvider(base_url=ollama_url)
        
        # 提取模型名称
        actual_model = model
        if model.startswith("ollama/"):
            actual_model = model[len("ollama/"):]
        elif model.startswith("saas/"):
            # 若强行指定 saas 也可以作为本地请求的参数，或者直接报错。
            # 为了降级弹性，提取后半段即可。
            actual_model = model[len("saas/"):]

        # 超时限制为 10 秒
        response_data = await asyncio.wait_for(
            ollama_provider.chat_completion(model=actual_model, messages=messages, **kwargs),
            timeout=10.0
        )
        
        # 请求成功，记录状态
        await ollama_breaker.record_success()
        
        # 注入非降级元数据
        response_data["metadata"] = {
            "provider": "ollama",
            "degraded": False
        }
        return response_data

    except Exception as e:
        # 记录调用失败
        await ollama_breaker.record_failure()
        
        reason_str = type(e).__name__
        log_security_event("llm_degraded", **{
            "from": "ollama",
            "to": "saas",
            "reason": reason_str
        })
        
        # 进入二级降级
        return await run_saas_fallback(model, messages, reason_str, **kwargs)

async def run_saas_fallback(model: str, messages: List[Dict[str, str]], prev_reason: str, **kwargs) -> Dict[str, Any]:
    """
    第二级：SaaS LLM 备份
    """
    try:
        saas_key = os.environ.get("OPENROUTER_API_KEY") or settings.openrouter_api_key
        if not saas_key:
            raise ValueError("No SaaS API Key configured")
            
        provider_name = os.environ.get("FALLBACK_SAAS_PROVIDER", "openrouter").lower()
        if provider_name == "deepseek":
            fallback_model = "deepseek-chat"
            base_url = "https://api.deepseek.com/v1"
        else:
            fallback_model = "openrouter/free"
            base_url = "https://openrouter.ai/api/v1"
            
        saas_provider = SaaSProvider(api_key=saas_key, base_url=base_url)
        
        # SaaS 请求限制超时为 15 秒
        response_data = await asyncio.wait_for(
            saas_provider.chat_completion(model=fallback_model, messages=messages, **kwargs),
            timeout=15.0
        )
        
        response_data["metadata"] = {
            "provider": "saas",
            "degraded": True
        }
        return response_data
        
    except Exception as e:
        reason_str = type(e).__name__
        log_security_event("llm_degraded", **{
            "from": "saas",
            "to": "template",
            "reason": reason_str
        })
        
        # 进入三级降级: Template
        return run_template_fallback(model)

def run_template_fallback(model: str) -> Dict[str, Any]:
    """
    第三级：本地静态模板，完全零外部网络依赖
    """
    fake_reply = "当前本地模型暂时不可用，系统已进入降级模式。请稍后重试，或换一个更具体的问题。"
    return {
        "id": f"chatcmpl-template-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": fake_reply
            },
            "finish_reason": "stop"
        }],
        "metadata": {
            "provider": "template",
            "degraded": True
        }
    }
