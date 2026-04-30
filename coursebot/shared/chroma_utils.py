import os
import chromadb
from chromadb.config import Settings

def get_chroma_client() -> chromadb.ClientAPI:
    """
    获取 ChromaDB 客户端。环境变量中未指定时会使用默认的回退地址。
    使用 HttpClient 以适配独立的 Chroma 数据库服务节点。
    """
    host = os.environ.get("CHROMA_HOST", "cb_chroma")
    port = int(os.environ.get("CHROMA_PORT", "8000"))
    
    # 初始化 chromadb http client
    client = chromadb.HttpClient(
        host=host, 
        port=port,
        settings=Settings(allow_reset=True)
    )
    return client

def delete_doc_by_source(collection, source: str) -> int:
    """
    根据 source (文件名) 删除集合中的所有相关切片。
    返回被删除的切片数量。
    """
    # 1. 查找匹配的 ID
    results = collection.get(where={"source": source})
    ids_to_del = results.get("ids", [])
    
    if not ids_to_del:
        return 0
        
    # 2. 执行删除
    collection.delete(ids=ids_to_del)
    return len(ids_to_del)
