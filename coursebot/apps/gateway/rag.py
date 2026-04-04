import os
import httpx
from typing import List, Dict, Any

RETRIEVER_URL = os.environ.get("RETRIEVER_URL", "http://cb_retriever:8000")

async def retrieve_context(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """
    通过调用内部的 retriever 服务，获取查询的相关文本。
    """
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                f"{RETRIEVER_URL}/v1/retrieve",
                json={"query": query, "top_k": top_k},
                timeout=30.0
            )
            if res.status_code == 200:
                data = res.json()
                return data.get("results", [])
        except Exception:
            pass  # 如果调用失败，静默返回空上下文
    return []

def build_rag_prompt(messages: List[Dict[str, str]], retrieved_chunks: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    使用检索到的数据重写最后一条用户 prompt。
    要求模型根据提供的资料回答并引用编号。
    如果检索结果为空，直接原样返回 messages。
    """
    if not retrieved_chunks:
        return messages

    # 找到最后一条 user 消息
    last_user_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i]["role"] == "user":
            last_user_idx = i
            break

    if last_user_idx == -1:
        return messages # 没有user消息，无法修改

    # 构造引用文本
    context_str = "【参考资料】\n"
    for i, chunk in enumerate(retrieved_chunks):
        ref_id = i + 1
        text = chunk.get("text", "")
        source = chunk.get("metadata", {}).get("source", "未知")
        context_str += f"[{ref_id}] 来源：{source}\n{text}\n\n"

    # 修改 prompt
    original_query = messages[last_user_idx]["content"]
    enhanced_prompt = (
        f"{context_str}"
        f"请根据上述【参考资料】回答下面的问题。在回答中，请务必使用形如 [1], [2] 的编号来引用资料来源。如果你认为参考资料无法回答该问题，可以使用你自己的知识并说明。\n\n"
        f"问题：\n{original_query}"
    )

    # 复制并替换
    new_messages = list(messages)
    new_messages[last_user_idx] = {
        "role": "user",
        "content": enhanced_prompt
    }

    return new_messages
