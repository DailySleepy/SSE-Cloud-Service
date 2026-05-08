from typing import List

def chunk_text(text: str, chunk_size: int = 500, chunk_overlap: int = 120, file_type: str = "general") -> List[str]:
    """
    语义化递归切片算法 (v4.1)：
    - 根据文件类型采用不同的分隔符优先级。
    - PDF 类型下，标点符号优先级高于单换行符。
    
    :param text: 原始文本
    :param chunk_size: 每个块的最大字符数
    :param chunk_overlap: 块之间的重叠字符数
    :param file_type: 文件类型 (pdf, general)
    :return: 文本块列表
    """
    if file_type == "pdf":
        # PDF 策略：段落 > 强标点 > 弱标点 > 换行 > 空格
        # 换行符在 PDF 中通常不代表语义结束，优先级排在标点后面
        separators = [
            "\n\n", "。", ".", "！", "!", "？", "?", "；", ";", "，", ",", "\n", " ", ""
        ]
        high_priority_idx = 8 # 标点及以上视为强语义边界
    else:
        # 默认策略（针对 Markdown/文本）：段落 > 标题 > 换行 > 列表 > 标点 > 空格
        separators = [
            "\n\n", "\n# ", "\n## ", "\n### ", "\n", "\n - ", 
            "。", ".", "；", ";", "，", ",", " ", ""
        ]
        high_priority_idx = 5
    
    def _split_recursive(content: str, separator_idx: int) -> List[str]:
        if len(content) <= chunk_size:
            return [content]
            
        if separator_idx >= len(separators):
            # 暴力兜底
            chunks = []
            for i in range(0, len(content), chunk_size - chunk_overlap):
                chunks.append(content[i : i + chunk_size])
                if i + chunk_size >= len(content):
                    break
            return chunks
        
        separator = separators[separator_idx]
        # 判断当前层级是否需要重叠
        is_low_priority = separator_idx > high_priority_idx
        
        # 将当前内容按当前分隔符切开
        splits = content.split(separator) if separator else list(content)
        
        results = []
        current_chunk = ""
        
        for s in splits:
            # 补回分隔符（除了最后一个片段）
            # 注意：某些分隔符是 \n# 这种，需要精准处理
            potential_segment = (current_chunk + (separator if current_chunk else "") + s)
            
            if len(potential_segment) <= chunk_size:
                current_chunk = potential_segment
            else:
                # 当前累积块已满，推入
                if current_chunk:
                    results.append(current_chunk)
                
                # 情况 A：如果单个 split 单元本身就超过了一个 chunk_size
                if len(s) > chunk_size:
                    results.extend(_split_recursive(s, separator_idx + 1))
                    current_chunk = ""
                # 情况 B：普通合并到上限，重置指针
                else:
                    # 如果是低优先级（句号逗号等情况），新块需要带上上一块末尾重叠
                    if is_low_priority and current_chunk and chunk_overlap > 0:
                        # 简单的字符重叠回溯
                        overlap_prefix = current_chunk[-chunk_overlap:]
                        current_chunk = overlap_prefix + (separator if overlap_prefix else "") + s
                    else:
                        current_chunk = s
        
        if current_chunk:
            results.append(current_chunk)
            
        return results

    # 递归生成
    raw_chunks = _split_recursive(text, 0)
    
    # 清理并去重，过滤空块
    seen = set()
    unique_chunks = []
    for c in raw_chunks:
        cleaned = c.strip()
        if cleaned and cleaned not in seen:
            unique_chunks.append(cleaned)
            seen.add(cleaned)
            
    return unique_chunks
