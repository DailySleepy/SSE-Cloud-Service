import os
import uuid
import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
import pypdf
import io

from packages.common.config import settings
from shared.chunking import chunk_text
from shared.chroma_utils import get_chroma_client

app = FastAPI(title="CourseBot Ingestor", version="0.1.0")

class IngestRequest(BaseModel):
    source: str
    text: str
    chunk_size: int = 300
    chunk_overlap: int = 50

@app.post("/v1/ingest/text")
async def ingest_text(req: IngestRequest):
    return await process_ingestion(req.text, req.source, req.chunk_size, req.chunk_overlap)

@app.post("/v1/ingest/file")
async def ingest_file(
    file: UploadFile = File(...),
    chunk_size: int = 300,
    chunk_overlap: int = 50
):
    filename = file.filename
    content = await file.read()
    
    text = ""
    if filename.endswith(".pdf"):
        try:
            reader = pypdf.PdfReader(io.BytesIO(content))
            for page in reader.pages:
                text += page.extract_text() + "\n"
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {str(e)}")
    else:
        # Assume text for other types like .txt, .md
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Only UTF-8 encoded text files are supported")

    if not text.strip():
        raise HTTPException(status_code=400, detail="No text extracted from file")

    return await process_ingestion(text, filename, chunk_size, chunk_overlap)

async def process_ingestion(text: str, source: str, chunk_size: int, chunk_overlap: int):
    # 1. 切分文本
    chunks = chunk_text(text, chunk_size, chunk_overlap)
    if not chunks:
        raise HTTPException(status_code=400, detail="Empty text or invalid chunks")

    # 2. 获取 Embeddings
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                f"{settings.ollama_base_url}/api/embed",
                json={
                    "model": "bge-m3",
                    "input": chunks
                },
                timeout=60.0
            )
            # Ollama /api/embed 可能返回 embeddings 或者针对不存在模型报 404
            if res.status_code == 404:
                 raise HTTPException(status_code=500, detail="Embedding model not found. Check if bge-m3 is pulled.")
            res.raise_for_status()
            data = res.json()
            embeddings = data.get("embeddings", [])
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ollama Error: {str(e)}")

    if len(embeddings) != len(chunks):
         raise HTTPException(status_code=500, detail="Embedding count mismatch")

    # 3. 保存入 Chroma
    chroma_client = get_chroma_client()
    try:
        collection = chroma_client.get_or_create_collection(name="coursebot_docs")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chroma connection failed: {str(e)}")
        
    ids = []
    metadatas = []
    docs = []
    embeds = []

    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        chunk_id = f"{req.source}_{i}_{uuid.uuid4().hex[:8]}"
        ids.append(chunk_id)
        docs.append(chunk)
        embeds.append(emb)
        # ChromaDB meta 不支持 dict / list
        start_idx = text.find(chunk)
        metadatas.append({
            "source": source,
            "chunk_index": i,
            "start": start_idx if start_idx != -1 else 0,
            "end": (start_idx + len(chunk)) if start_idx != -1 else 0
        })

    try:
        collection.upsert(
            ids=ids,
            documents=docs,
            embeddings=embeds,
            metadatas=metadatas
        )
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Chroma upsert failed: {str(e)}")

    return {"status": "success", "chunks_ingested": len(chunks), "source": source}
