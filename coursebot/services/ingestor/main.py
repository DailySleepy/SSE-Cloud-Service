import asyncio
import os
import uuid
import json
import httpx
import redis
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from pydantic import BaseModel
import pypdf
import io

from packages.common.config import settings
from shared.chunking import chunk_text
from shared.chroma_utils import get_chroma_client

app = FastAPI(title="CourseBot Ingestor", version="0.1.0")

# 初始化 Redis 客户端并提取 db
redis_client = redis.from_url(settings.redis_url, decode_responses=True)

class IngestRequest(BaseModel):
    source: str
    text: str
    chunk_size: int = 400
    chunk_overlap: int = 50

@app.get("/v1/ingest/status/{task_id}")
async def get_task_status(task_id: str):
    """
    前端轮询此接口获取解析进度
    """
    key = f"ingest_task:{task_id}"
    data = redis_client.get(key)
    if not data:
        raise HTTPException(status_code=404, detail="Task not found")
    return json.loads(data)

@app.delete("/v1/ingest/cancel/{task_id}")
async def cancel_task(task_id: str):
    """
    前端请求取消解析任务
    """
    key = f"ingest_task:{task_id}"
    if not redis_client.exists(key):
        raise HTTPException(status_code=404, detail="Task not found")
    # 设置取消标记
    redis_client.setex(f"ingest_task:{task_id}:cancelled", 3600, "1")
    return {"status": "cancelling"}

@app.post("/v1/ingest/text")
async def ingest_text(req: IngestRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    redis_client.setex(f"ingest_task:{task_id}", 3600, json.dumps({
        "status": "processing",
        "progress": 0,
        "source": req.source,
        "message": "Initializing text injection..."
    }))
    
    background_tasks.add_task(
        run_ingestion_task, 
        task_id, 
        req.text, 
        req.source, 
        req.chunk_size, 
        req.chunk_overlap
    )
    return {"status": "accepted", "task_id": task_id}

@app.post("/v1/ingest/file")
async def ingest_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    chunk_size: int = 400,
    chunk_overlap: int = 50
):
    filename = file.filename
    content = await file.read()
    
    text = ""
    if filename.lower().endswith(".pdf"):
        try:
            reader = pypdf.PdfReader(io.BytesIO(content))
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {str(e)}")
    else:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("utf-8", errors="ignore")

    if not text.strip():
        raise HTTPException(status_code=400, detail="No text extracted from file")

    task_id = str(uuid.uuid4())
    # 设置 1 小时过期时间，防止 Redis 内存泄漏
    redis_client.setex(f"ingest_task:{task_id}", 3600, json.dumps({
        "status": "processing",
        "progress": 0,
        "source": filename,
        "message": "Starting file ingestion..."
    }))

    background_tasks.add_task(
        run_ingestion_task, 
        task_id, 
        text, 
        filename, 
        chunk_size, 
        chunk_overlap
    )
    return {"status": "accepted", "task_id": task_id}

async def run_ingestion_task(task_id: str, text: str, source: str, chunk_size: int, chunk_overlap: int):
    """
    后台任务：执行完整的切分、向量化和落库流程
    """
    key = f"ingest_task:{task_id}"
    
    def update_progress(progress: int, message: str, status: str = "processing"):
        redis_client.setex(key, 3600, json.dumps({
            "status": status,
            "progress": progress,
            "source": source,
            "message": message
        }))

    try:
        # 1. 切分文本
        update_progress(5, "Chunking text...")
        chunks = chunk_text(text, chunk_size, chunk_overlap)
        if not chunks:
            update_progress(0, "Empty chunks after splitting", "failed")
            return

        # 2. 批量向量化
        # batch_size 设置为 4：在 8GB 内存服务器上兼顾速度与内存安全
        # 过大（如16）会导致大文档处理时 Ollama 内存峰值超限 OOM
        batch_size = 4
        embeddings = []
        total_batches = (len(chunks) + batch_size - 1) // batch_size
        
        async with httpx.AsyncClient() as client:
            for i in range(0, len(chunks), batch_size):
                # 每次处理 batch 前检查是否被取消
                if redis_client.get(f"ingest_task:{task_id}:cancelled") == "1":
                    update_progress(progress, "Task cancelled by user", "failed")
                    print(f"[Ingest Cancelled] Task {task_id} cancelled.")
                    return

                batch = chunks[i : i + batch_size]
                current_batch_idx = (i // batch_size) + 1
                
                # 计算进度 (5% - 85% 是 Embedding 阶段)
                progress = 5 + int((current_batch_idx / total_batches) * 80)
                update_progress(progress, f"Embedding chunks ({current_batch_idx}/{total_batches})...")
                
                res = await client.post(
                    f"{settings.ollama_base_url}/api/embed",
                    json={"model": "bge-m3", "input": batch},
                    timeout=300.0
                )
                res.raise_for_status()
                data = res.json()
                embeddings.extend(data.get("embeddings", []))
                
                # 每批次后主动让出协程，允许 GC 回收内存，防止大文档堆积
                await asyncio.sleep(0)

        if len(embeddings) != len(chunks):
            update_progress(85, "Embedding mismatch", "failed")
            return

        # 3. 写入 Chroma
        update_progress(90, "Saving to vector database...")
        chroma_client = get_chroma_client()
        collection = chroma_client.get_or_create_collection(name="coursebot_docs")
        
        ids, docs, metadatas = [], [], []
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            chunk_id = f"{source}_{i}_{uuid.uuid4().hex[:8]}"
            ids.append(chunk_id)
            docs.append(chunk)
            # 记录偏移量
            # 简化 metadatas，避免因 text.find 过慢
            metadatas.append({"source": source, "index": i})

        collection.upsert(
            ids=ids,
            documents=docs,
            embeddings=embeddings,
            metadatas=metadatas
        )

        update_progress(100, "Successfully ingested all chunks!", "completed")
        print(f"[Ingest Finished] Task {task_id} for {source} completed.")

    except Exception as e:
        import traceback
        traceback.print_exc()
        update_progress(0, f"Error: {str(e)}", "failed")
        print(f"[Ingest Failed] Task {task_id} failed: {str(e)}")
