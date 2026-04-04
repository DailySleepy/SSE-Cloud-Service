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
