import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any

from packages.common.config import settings
from shared.chroma_utils import get_chroma_client

app = FastAPI(title="CourseBot Retriever", version="0.1.0")

class RetrieveRequest(BaseModel):
    query: str
    top_k: int = 3

@app.post("/v1/retrieve")
async def retrieve(req: RetrieveRequest):
    # 1. 对 query 进行 Embedding
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                f"{settings.ollama_base_url}/api/embed",
                json={
                    "model": "bge-m3",
                    "input": [req.query]  # 这里将query作为list进行处理即可
                },
                timeout=30.0
            )
            res.raise_for_status()
            data = res.json()
            embeddings = data.get("embeddings", [])
            query_embedding = embeddings[0] if embeddings else None
        except Exception as e:
             raise HTTPException(status_code=500, detail=f"Ollama Error (query embed): {str(e)}")

    if not query_embedding:
        raise HTTPException(status_code=500, detail="Failed to get valid embedding for query")

    # 2. 检索 ChromaDB
    chroma_client = get_chroma_client()
    try:
        collection = chroma_client.get_collection(name="coursebot_docs")
    except Exception as e:
        # Collection可能还未创建，说明还没 ingest 过任何文件
        return {"results": []}

    try:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=req.top_k
        )
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Chroma query failed: {str(e)}")

    # 3. 构造返回格式
    retrieved_chunks = []
    if results["documents"] and len(results["documents"]) > 0:
        docs = results["documents"][0]
        metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
        distances = results["distances"][0] if results.get("distances") else [0.0] * len(docs)

        for doc, meta, dist in zip(docs, metas, distances):
            retrieved_chunks.append({
                "text": doc,
                "metadata": meta,
                "distance": dist
            })

    return {"results": retrieved_chunks}
