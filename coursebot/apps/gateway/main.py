import time
import json
import hashlib
import httpx
import redis.asyncio as redis
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

from packages.common.config import settings
from services.llm_adapter.provider import get_provider

# 初始化应用
app = FastAPI(title="CourseBot Gateway", version="0.1.0")

# 初始化 Redis 客户端
redis_client = redis.from_url(settings.redis_url, decode_responses=True)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = Field(default="openrouter/auto")
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None

@app.get("/healthz", summary="Liveness Probe")
async def healthz():
    """ 
    系统存活探针 
    """
    return {"status": "ok", "timestamp": int(time.time())}

@app.get("/readyz", summary="Readiness Probe")
async def readyz():
    """ 
    系统就绪探针 
    """
    checks = {
        "ollama": "error",
        "saas": "error"
    }

    # 检查 Ollama 连通性
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(f"{settings.ollama_base_url}/", timeout=3.0)
            if res.status_code == 200:
                checks["ollama"] = "ok"
        except Exception:
            pass

    # 检查 SaaS 连通性
    async with httpx.AsyncClient() as client:
        try:
            if settings.openrouter_api_key:
                res = await client.get(
                    "https://openrouter.ai/api/v1/auth/key",
                    headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                    timeout=5.0
                )
                if res.status_code == 200:
                    checks["saas"] = "ok"
        except Exception:
            pass

    status = "ok" if checks["ollama"] == "ok" and checks["saas"] == "ok" else "degraded"
    
    # 状态码处理逻辑
    if list(checks.values()).count("ok") == 0:
        http_status = 503
    elif list(checks.values()).count("error") > 0:
        http_status = 503  # 如果有任何一项失败，直接报 503 代表 degraded
    else:
        http_status = 200
        
    return JSONResponse(status_code=http_status, content={
        "status": status,
        "checks": checks,
        "environment": settings.environment
    })

@app.post("/v1/chat/completions", summary="OpenAI Standard Chat Completion API")
async def chat_completions(req: ChatCompletionRequest):
    """
    对齐 OpenAI API 标准的非流式聊天接口。
    会代理转发给根据 model 前缀判定的具体 Provider。
    """
    # 1. 解析 model 前缀
    if req.model.startswith("ollama/"):
        provider_type = "ollama"
        actual_model = req.model[len("ollama/"):]
    elif req.model.startswith("saas/"):
        provider_type = "saas"
        actual_model = req.model[len("saas/"):]
    else:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "message": f"Invalid model prefix '{req.model}'. Model must start with 'ollama/' or 'saas/'.",
                    "type": "invalid_request_error",
                    "suggestion": "Please explicitly define the backend, e.g. 'ollama/qwen2.5:0.5b' or 'saas/openai/gpt-4o-mini'"
                }
            }
        )

    try:
        messages = [{"role": m.role, "content": m.content} for m in req.messages]
        
        kwargs = {}
        if req.temperature is not None:
            kwargs["temperature"] = req.temperature
        if req.max_tokens is not None:
            kwargs["max_tokens"] = req.max_tokens

        # 2. Redis 缓存获取
        prompt_str = json.dumps(messages, ensure_ascii=False)
        cache_key = hashlib.sha256(f"{actual_model}_{prompt_str}".encode("utf-8")).hexdigest()
        
        try:
            cached_response = await redis_client.get(cache_key)
            if cached_response:
                data = json.loads(cached_response)
                # 使用缓存时附加一个 meta 标识以供客户端查验
                data["_meta"] = {"cached": True}
                return JSONResponse(content=data)
        except Exception:
            pass # 缓存异常则忽略，直接走实时

        # 3. 缓存未穿透，调用底层 Provider
        llm_provider = get_provider(provider_type)
        response_data = await llm_provider.chat_completion(
            model=actual_model,
            messages=messages,
            **kwargs
        )
        response_data["_meta"] = {"cached": False}

        # 4. 写入缓存 (TTL 10min)
        try:
            await redis_client.setex(cache_key, 600, json.dumps(response_data, ensure_ascii=False))
        except Exception:
            pass

        return JSONResponse(content=response_data)

    except Exception as e:
        # 详细错误处理设计
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": f"Provider Exception: {str(e)}",
                    "provider": provider_type,
                    "model": actual_model,
                    "suggestion": "Check if your selected backend service is healthy. For Ollama, verify if it is started and if model is pulled. For SaaS, verify if the OpenRouter API Key is valid."
                }
            }
        )
