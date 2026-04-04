import httpx
import time
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost"

def test_rag_flow():
    # 1. 模拟上传文档 (Ingestor)
    logger.info(">>> 1. Ingesting Text...")
    sample_text = """
    FastAPI 是一个用于构建 API 的现代、快速（高性能）的 web 框架，使用 Python 3.8+ 并基于标准的 Python 类型提示。
    Pydantic 是 FastAPI 使用的数据验证库。
    Ollama 提供了一种在本地运行大语言模型（LLM）的便捷方法。
    """
    
    try:
        with httpx.Client(trust_env=False) as client:
            res = client.post(
                f"{BASE_URL}/v1/ingest/text",
                json={
                    "source": "api_framework_doc",
                    "text": sample_text,
                    "chunk_size": 50,
                    "chunk_overlap": 10
                },
                timeout=60.0
            )
            res.raise_for_status()
        logger.info(f"Ingest Result: {res.json()}")
    except Exception as e:
        logger.error(f"Ingest Failed: {str(e)}")
        return

    # 等待 Chroma 索引生效
    time.sleep(2)

    # 2. 模拟检索 (Retriever)
    logger.info("\n>>> 2. Retrieving Context...")
    query = "FastAPI 依赖什么库来进行数据验证？"
    try:
        with httpx.Client(trust_env=False) as client:
            res = client.post(
                f"{BASE_URL}/v1/retrieve",
                json={
                    "query": query,
                    "top_k": 2
                },
                timeout=30.0
            )
            res.raise_for_status()
        logger.info("Retrieve Result:")
        print(json.dumps(res.json(), indent=2, ensure_ascii=False))
    except Exception as e:
        logger.error(f"Retrieve Failed: {str(e)}")
        return

    # 3. 最终聊天测试带引用回答 (Gateway /v1/chat/completions)
    logger.info("\n>>> 3. Testing Gateway Chat Completions with RAG...")
    try:
        with httpx.Client(trust_env=False) as client:
            res = client.post(
                f"{BASE_URL}/v1/chat/completions",
                json={
                    "model": "ollama/qwen2.5:0.5b", # 使用一个可能在本地测试部署的模型
                    "messages": [
                        {"role": "user", "content": query}
                    ],
                    "use_rag": True,
                    "temperature": 0.3
                },
                timeout=60.0
            )
            res.raise_for_status()
        data = res.json()
        logger.info("Chat Response:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        if "citations" in data:
            logger.info(f"Found Citations: {len(data['citations'])} item(s)")
    except Exception as e:
        logger.error(f"Chat failed: {str(e)}")

if __name__ == "__main__":
    test_rag_flow()
