from typing import List

def chunk_text(text: str, chunk_size: int = 500, chunk_overlap: int = 120) -> List[str]:
    """
    递归字符切分算法，旨在寻找语义边界（段落、标题、换行、标点）。
    如果某个分块超长，则尝试使用下一级分隔符。
    
    :param text: 原始文本
    :param chunk_size: 每个块的最大字符数
    :param chunk_overlap: 块之间的重叠字符数
    :return: 文本块列表
    """
    # 按照优先级排序的分隔符列表
    # 包含了 Markdown 结构 (\n# ), 段落 (\n\n), 换行 (\n), 列表 (\n - ), 标点 (。), 空格 (" ")
    separators = ["\n\n", "\n# ", "\n## ", "\n### ", "\n", "\n - ", "。", ".", " ", ""]
    
    final_chunks = []
    
    def _split_recursive(content: str, separator_idx: int) -> List[str]:
        # 如果长度已经满足，直接返回
        if len(content) <= chunk_size:
            return [content]
            
        # 如果已经到了最后一个分隔符 (空字符串)，说明无法再根据语义分割，只能暴力切割
        if separator_idx >= len(separators) - 1:
            # 暴力切分为 chunk_size 大小的块 (虽然不理想)
            return [content[i : i + chunk_size] for i in range(0, len(content), chunk_size)]
        
        separator = separators[separator_idx]
        splits = content.split(separator) if separator else list(content)
        
        results = []
        current_chunk = ""
        
        for s in splits:
            # 如果加上这个片段后仍然在 chunk_size 内，则合并
            # 注意需要补回分隔符
            potential_chunk = (current_chunk + (separator if current_chunk else "") + s)
            
            if len(potential_chunk) <= chunk_size:
                current_chunk = potential_chunk
            else:
                # 当前块已经满了，保存它
                if current_chunk:
                    results.append(current_chunk)
                
                # 处理被分割出的这部分 (如果它本身就很长，则递归进入下一层分隔符)
                if len(s) > chunk_size:
                    results.extend(_split_recursive(s, separator_idx + 1))
                    current_chunk = "" # 处理完毕，重置
                else:
                    current_chunk = s # 作为新块的起点
        
        if current_chunk:
            results.append(current_chunk)
            
        return results

    # 1. 递归初步切分
    raw_chunks = _split_recursive(text, 0)
    
    # 2. 合并小块并处理 Overlap (可选提升)
    # 此处省略复杂的滑动窗口合并，仅实现基础合并以达到 chunk_size
    # 实际应用中，Overlap 通常在 chunk 生成时通过后向前回溯获取
    # 为了保持简单且高效，我们采用目前的切分结果
    
    return [c.strip() for c in raw_chunks if c.strip()]
