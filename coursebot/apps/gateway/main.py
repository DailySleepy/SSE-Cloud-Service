import os
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
from apps.gateway.rag import retrieve_context, build_rag_prompt, RETRIEVER_URL
from shared.chroma_utils import get_chroma_client

CHROMA_COLLECTION = "coursebot_docs"

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
    use_rag: bool = True
    top_k: int = 3

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
        "saas": "error",
        "retriever": "error",
        "chroma": "error"
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

    # 检查 Retriever 连通性
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(f"{RETRIEVER_URL}/openapi.json", timeout=3.0)
            if res.status_code == 200:
                checks["retriever"] = "ok"
        except Exception:
            checks["retriever"] = "error"

    # 检查 ChromaDB 连通性
    chroma_host = os.environ.get("CHROMA_HOST", "cb_chroma")
    chroma_port = os.environ.get("CHROMA_PORT", "8000")
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(f"http://{chroma_host}:{chroma_port}/api/v2/heartbeat", timeout=3.0)
            if res.status_code == 200:
                checks["chroma"] = "ok"
        except Exception as e:
            import traceback
            print(f"[Ready Check] Chroma failed: {str(e)}")
            traceback.print_exc()
            checks["chroma"] = "error"

    # 判定整体状态：必须核心组件全为 ok 才是 ok，否则为 degraded
    # RAG 组件 (retriever, chroma) 也被视为核心组件 (因为应用默认启用 use_rag)
    is_fully_ok = all(v == "ok" for v in checks.values())
    status = "ok" if is_fully_ok else "degraded"
    
    # 状态码处理逻辑
    # 如果所有核心检查都失败，返回 503
    # 如果部分成功但有核心项失败，也返回 503 代表就绪度存在问题
    http_status = 200 if is_fully_ok else 503
        
    return JSONResponse(status_code=http_status, content={
        "status": status,
        "checks": checks,
        "environment": settings.environment
    })

@app.get("/v1/rag/docs", summary="列出 RAG 知识库中的所有文档")
async def rag_list_docs(show_content: bool = False):
    """
    列出 RAG 知识库中所有不重复的文档来源 (source)，
    并可选择是否展示全部内容。
    """
    try:
        client = get_chroma_client()
        try:
            collection = client.get_collection(name=CHROMA_COLLECTION)
        except Exception:
            return {"documents": [], "total_chunks": 0}

        total = collection.count()
        if total == 0:
            return {"documents": [], "total_chunks": 0}

        # 获取所有条目的 metadata
        all_items = collection.get(include=["metadatas", "documents"])
        metadatas = all_items.get("metadatas", [])
        documents = all_items.get("documents", [])

        # 按 source 分组
        doc_map: dict = {}
        for meta, doc in zip(metadatas, documents):
            src = meta.get("source", "未知")
            if src not in doc_map:
                doc_map[src] = {"source": src, "chunk_count": 0, "chunks": []}
            doc_map[src]["chunk_count"] += 1
            if show_content:
                doc_map[src]["chunks"].append({
                    "chunk_index": meta.get("chunk_index", 0),
                    "text": doc
                })

        result = sorted(doc_map.values(), key=lambda x: x["source"])
        if not show_content:
            for r in result:
                del r["chunks"]

        return {"documents": result, "total_chunks": total}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ChromaDB 查询失败: {str(e)}")


@app.delete("/v1/rag/docs/{source}", summary="按文件名删除 RAG 文档")
async def rag_delete_doc(source: str):
    """
    根据文件名 (source) 删除 RAG 知识库中该文件对应的所有切片。
    """
    try:
        client = get_chroma_client()
        try:
            collection = client.get_collection(name=CHROMA_COLLECTION)
        except Exception:
            raise HTTPException(status_code=404, detail="集合不存在")

        results = collection.get(where={"source": source})
        ids_to_del = results.get("ids", [])
        if not ids_to_del:
            raise HTTPException(status_code=404, detail=f"未找到 source='{source}' 的文档")

        collection.delete(ids=ids_to_del)
        return {"status": "success", "deleted_chunks": len(ids_to_del), "source": source}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")



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
        citations = []

        if req.use_rag:
            # 获取最后一条用户问题
            last_query = next((m["content"] for m in reversed(messages) if m["role"] == "user"), None)
            if last_query:
                # 检索并重写prompt，透传 top_k 参数
                retrieved_chunks = await retrieve_context(last_query, top_k=req.top_k)
                if retrieved_chunks:
                    messages = build_rag_prompt(messages, retrieved_chunks)
                    # 摘取 citations 用于返回附加
                    citations = [
                        {"text": c.get("text"), "source": c.get("metadata", {}).get("source")}
                        for c in retrieved_chunks
                    ]
        
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
        if citations:
            response_data["citations"] = citations

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
