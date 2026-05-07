import time
import httpx
from abc import ABC, abstractmethod
from typing import Any, Dict, List
from packages.common.config import settings

class Provider(ABC):
    """
    统一的模型提供者接口
    """
    @abstractmethod
    async def chat_completion(self, model: str, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        pass

class FakeProvider(Provider):
    """
    本地开发或无环境时的伪造数据提供者
    """
    async def chat_completion(self, model: str, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        start_time = time.time()
        # 简单模拟耗时
        time.sleep(0.1)
        latency_ms = int((time.time() - start_time) * 1000)

        fake_reply = "【FakeReply】我是一个本地模拟的 AI 助手，未连接外部服务。"
        
        return {
            "id": "chatcmpl-fake-id",
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
            "usage": {
                "prompt_tokens": len(str(messages)),
                "completion_tokens": len(fake_reply),
                "total_tokens": len(str(messages)) + len(fake_reply),
                "latency_ms": latency_ms
            }
        }

class SaaSProvider(Provider):
    """
    接入真实 SaaS API (如 OpenRouter) 的调用提供者
    """
    def __init__(self, api_key: str, base_url: str = "https://openrouter.ai/api/v1"):
        self.api_key = api_key
        self.base_url = base_url

    async def chat_completion(self, model: str, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        start_time = time.time()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "http://localhost",
            "X-Title": "CourseBot"
        }
        
        payload = {
            "model": model,
            "messages": messages,
            **kwargs
        }

        # 策略：先直连（绕过代理），失败后走 HTTPS_PROXY 环境变量
        # 代理关闭 → 直连成功；代理开启且直连受阻 → 自动切换走代理
        last_exc: Exception = Exception("No attempt made")
        for trust_env in (False, True):
            try:
                async with httpx.AsyncClient(trust_env=trust_env) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=30.0
                    )
                    response.raise_for_status()
                    data = response.json()
                    break
            except Exception as e:
                last_exc = e
                continue
        else:
            raise last_exc
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        # 确保使用信息在顶层被注入 latency_ms
        if "usage" not in data:
             data["usage"] = {
                 "prompt_tokens": 0,
                 "completion_tokens": 0,
                 "total_tokens": 0
             }
        data["usage"]["latency_ms"] = latency_ms

        return data

class OllamaProvider(Provider):
    """
    接入本地 Ollama 的调用提供者
    """
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url

    async def chat_completion(self, model: str, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        start_time = time.time()
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            **kwargs
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=600.0  # 10min: 覆盖极端情况下慢速机器的首次推理
                )
                response.raise_for_status()
                data = response.json()
            except httpx.ConnectError:
                raise Exception(f"Failed to connect to Ollama at {self.base_url}. Is the container running?")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise Exception(f"Model '{model}' not found in Ollama. Have you pulled it?")
                raise Exception(f"Ollama API Error: {e.response.status_code} - {e.response.text}")
            except Exception as e:
                raise Exception(f"Ollama Request Error: {str(e)}")
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        # 统一格式化为 OpenAI 格式
        return {
            "id": f"chatcmpl-ollama-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": data.get("message", {"role": "assistant", "content": ""}),
                "finish_reason": data.get("done_reason", "stop")
            }],
            "usage": {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
                "latency_ms": latency_ms
            }
        }

# 工厂函数返回对应实现
def get_provider(provider_type: str = "saas") -> Provider:
    if provider_type == "ollama":
        return OllamaProvider(base_url=settings.ollama_base_url)
    
    # saas provider 优先使用配置，如果在本地或没有配 API KEY，走 Fake
    if not settings.openrouter_api_key or settings.environment == "development_offline":
        return FakeProvider()
    return SaaSProvider(api_key=settings.openrouter_api_key)
