import time
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

from packages.common.config import settings
from services.llm_adapter.provider import get_provider

# 初始化应用
app = FastAPI(title="CourseBot Gateway", version="0.1.0")

# 初始化对应环境 Provider
llm_provider = get_provider()

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
    # 可以在这里注入对 DB、依赖中间件等连接的检查
    return {"status": "ready", "environment": settings.environment}

@app.post("/v1/chat/completions", summary="OpenAI Standard Chat Completion API")
async def chat_completions(req: ChatCompletionRequest):
    """
    对齐 OpenAI API 标准的非流式聊天接口。
    会代理转发给 LLM Adapter并统一注入 latency_ms 与 token usage。
    """
    try:
        # 转为 list[dict]
        messages = [{"role": m.role, "content": m.content} for m in req.messages]
        
        # 将不需要固定在 model 层声明的可选 kwargs 分别传入
        kwargs = {}
        if req.temperature is not None:
            kwargs["temperature"] = req.temperature
        if req.max_tokens is not None:
            kwargs["max_tokens"] = req.max_tokens

        # 调用 Provider
        response_data = await llm_provider.chat_completion(
            model=req.model,
            messages=messages,
            **kwargs
        )
        return JSONResponse(content=response_data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
