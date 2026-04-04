import os
import sys
import argparse
import httpx
import logging
import json

# 路径修复逻辑：将 coursebot 目录加入 sys.path 以支持 shared/packages 导入
# 当前脚本在 coursebot/scripts/，其父目录是 coursebot/
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

try:
    from shared.chroma_utils import get_chroma_client
except ImportError:
    # 兼容在项目最外层运行的情况
    sys.path.append(os.path.join(os.getcwd(), "coursebot"))
    from shared.chroma_utils import get_chroma_client

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# 环境适配：如果是本地运行且没有设置环境变量，默认指向 localhost
# 同时设置 NO_PROXY 避免被系统代理拦截到 502 (Windows 常见问题)
if "CHROMA_HOST" not in os.environ:
    os.environ["CHROMA_HOST"] = "localhost"
if "NO_PROXY" not in os.environ:
    os.environ["NO_PROXY"] = "localhost,127.0.0.1"

DEFAULT_COLLECTION = "coursebot_docs"
BASE_URL = "http://localhost"

def cmd_ingest(args):
    """上传文件并向量化"""
    file_path = args.file
    if not os.path.exists(file_path):
        logger.error(f"文件未找到: {file_path}")
        return

    source_name = os.path.basename(file_path)
    logger.info(f"正在读取文件: {file_path}")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text_content = f.read()
    except Exception as e:
        logger.error(f"读取文件失败: {e}")
        return

    if not text_content.strip():
        logger.error("文件内容为空")
        return

    logger.info(f"正在上传到 Ingestor 服务 (Source: {source_name})...")
    try:
        # 使用 trust_env=False 绕过可能的系统代理 (502 问题修复)
        with httpx.Client(trust_env=False) as client:
            res = client.post(
                f"{BASE_URL}/v1/ingest/text",
                json={
                    "source": source_name,
                    "text": text_content,
                    "chunk_size": args.chunk_size,
                    "chunk_overlap": args.overlap
                },
                timeout=120.0
            )
            res.raise_for_status()
            data = res.json()
            logger.info(f"✅ 上传成功! 响应: {data}")
    except httpx.HTTPError as e:
        logger.error(f"❌ HTTP 请求失败: {e}")
        if hasattr(e, 'response') and e.response:
            logger.error(f"返回内容: {e.response.text}")
    except Exception as e:
        logger.error(f"发生未知错误: {e}")

def cmd_list(args):
    """列出所有集合"""
    client = get_chroma_client()
    collections = client.list_collections()
    logger.info(f"当前共有 {len(collections)} 个集合:")
    for col in collections:
        print(f" - {col.name}")

def cmd_count(args):
    """统计集合中的记录数"""
    client = get_chroma_client()
    try:
        collection = client.get_collection(name=args.collection)
        count = collection.count()
        logger.info(f"集合 '{args.collection}' 中共有 {count} 条记录。")
    except Exception as e:
        logger.error(f"查询失败: {e}")

def cmd_peek(args):
    """查看前几条记录"""
    client = get_chroma_client()
    try:
        collection = client.get_collection(name=args.collection)
        results = collection.peek(limit=args.limit)
        
        count = len(results['ids'])
        logger.info(f"展示集合 '{args.collection}' 的前 {count} 条数据:")
        
        for i in range(count):
            print(f"\n--- [ID: {results['ids'][i]}] ---")
            print(f"Metadata: {json.dumps(results['metadatas'][i], ensure_ascii=False)}")
            content = results['documents'][i]
            if not getattr(args, 'full', False) and len(content) > 100:
                content = content[:100] + "..."
            print(f"Content: {content}")
            
    except Exception as e:
        logger.error(f"Peek 失败: {e}")

def cmd_del_file(args):
    """删除指定文件的所有向量"""
    client = get_chroma_client()
    try:
        collection = client.get_collection(name=args.collection)
        # 获取匹配 source 的所有 ID
        results = collection.get(where={"source": args.source})
        ids_to_del = results['ids']
        
        if not ids_to_del:
            logger.warning(f"未找到 Source 为 '{args.source}' 的记录。")
            return
            
        collection.delete(ids=ids_to_del)
        logger.info(f"✅ 已成功删除 Source 为 '{args.source}' 的 {len(ids_to_del)} 条记录。")
    except Exception as e:
        logger.error(f"删除失败: {e}")

def cmd_reset(args):
    """彻底重置集合"""
    client = get_chroma_client()
    confirm = input(f"⚠️ 确定要彻底删除并重置集合 '{args.collection}' 吗？此操作不可恢复！(y/N): ")
    if confirm.lower() != 'y':
        print("操作已取消。")
        return
        
    try:
        client.delete_collection(name=args.collection)
        client.create_collection(name=args.collection)
        logger.info(f"✅ 集合 '{args.collection}' 已重置完毕。")
    except Exception as e:
        logger.error(f"重置失败: {e}")

def main():
    parser = argparse.ArgumentParser(description="CourseBot RAG 内容管理工具")
    subparsers = parser.add_subparsers(dest="command", help="子命令任务")

    # Ingest
    p_ingest = subparsers.add_parser("ingest", help="上传并切分文件入库")
    p_ingest.add_argument("file", help="本地文件路径")
    p_ingest.add_argument("--chunk-size", type=int, default=300, help="切分长度 (默认 300)")
    p_ingest.add_argument("--overlap", type=int, default=50, help="重叠长度 (默认 50)")

    # List
    p_list = subparsers.add_parser("list", help="列出所有集合")

    # Count
    p_count = subparsers.add_parser("count", help="统计集合内的文档条数")
    p_count.add_argument("--collection", default=DEFAULT_COLLECTION, help=f"目标集合 (默认: {DEFAULT_COLLECTION})")

    # Peek
    p_peek = subparsers.add_parser("peek", help="查看集合内的前几条数据")
    p_peek.add_argument("--collection", default=DEFAULT_COLLECTION, help=f"目标集合")
    p_peek.add_argument("--full", action="store_true", help="显示完整内容")
    p_peek.add_argument("--limit", type=int, default=5, help="显示的条数 (默认 5)")

    # Del File
    p_del = subparsers.add_parser("del-file", help="按文件名 (source) 删除记录")
    p_del.add_argument("source", help="要删除的文件名 (元数据中的 source 字段)")
    p_del.add_argument("--collection", default=DEFAULT_COLLECTION, help=f"目标集合")

    # Reset
    p_reset = subparsers.add_parser("reset", help="彻底清空并重置集合")
    p_reset.add_argument("--collection", default=DEFAULT_COLLECTION, help=f"目标集合")

    args = parser.parse_args()
    
    if args.command == "ingest":
        cmd_ingest(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "count":
        cmd_count(args)
    elif args.command == "peek":
        cmd_peek(args)
    elif args.command == "del-file":
        cmd_del_file(args)
    elif args.command == "reset":
        cmd_reset(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
