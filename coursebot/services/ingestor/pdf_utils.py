import fitz  # PyMuPDF
import re
import io

def extract_and_clean_pdf(content: bytes) -> str:
    """
    使用 PyMuPDF 进行高性能 PDF 提取：
    1. 自动识别单/双栏布局
    2. 提取表格并转换为 Markdown 风格文本
    3. 智能段落重组与断词修复
    4. 参考文献截断
    """
    doc = fitz.open(stream=content, filetype="pdf")
    all_pages_text = []

    for page in doc:
        # --- 1. 提取表格并获取其范围 (避免与文本重复提取) ---
        tables = page.find_tables()
        table_list = []
        table_rects = []
        
        for table in tables:
            table_rects.append(table.bbox) # 记录表格坐标矩形
            df = table.extract()
            if df:
                rows = []
                for row in df:
                    rows.append(" | ".join([str(cell or "").replace("\n", " ").strip() for cell in row]))
                if rows:
                    table_list.append("\n[Table Data]:\n" + "\n".join(rows) + "\n")

        # --- 2. 提取并排版文本块 ---
        # get_text("blocks") 返回: (x0, y0, x1, y1, "text", block_no, block_type)
        blocks = page.get_text("blocks")
        page_width = page.rect.width
        
        # 判定布局类型：检测是否有大量块分布在左右两侧
        is_double = _is_double_column(blocks, page_width)
        
        processed_blocks = []
        if is_double:
            # 双栏逻辑：分桶后分别按 Y 轴排序
            gutter = page_width / 2
            left_col, right_col, spans = [], [], []
            
            for b in blocks:
                if _is_inside_tables(b[:4], table_rects): continue # 跳过表格内的文字块
                
                x0, y0, x1, y1, text, b_no, b_type = b
                if b_type != 0: continue # 只处理文本
                
                # 判定：跨越中缝且宽度超过页面 45% 视为通栏
                if x0 < gutter - 20 and x1 > gutter + 20 and (x1 - x0) > page_width * 0.45:
                    spans.append(b)
                elif (x0 + x1) / 2 < gutter:
                    left_col.append(b)
                else:
                    right_col.append(b)
            
            # 排序并组装：通栏块作为分隔符，清空左右缓存
            # 注意：这里简化为 [所有通栏] -> [所有左栏] -> [所有右栏]
            # 若需处理更复杂的交替布局，可引入更精细的 Y 轴 flush 逻辑
            left_col.sort(key=lambda x: x[1])
            right_col.sort(key=lambda x: x[1])
            spans.sort(key=lambda x: x[1])
            
            page_text = "\n".join([b[4] for b in spans]) + "\n"
            page_text += "\n".join([b[4] for b in left_col]) + "\n"
            page_text += "\n".join([b[4] for b in right_col])
        else:
            # 单栏逻辑：直接按 Y 轴从上到下
            sorted_blocks = sorted(blocks, key=lambda x: x[1])
            texts = []
            for b in sorted_blocks:
                if b[6] == 0 and not _is_inside_tables(b[:4], table_rects):
                    texts.append(b[4])
            page_text = "\n".join(texts)

        # 拼接当前页的文本和表格
        combined_page = page_text + "\n" + "\n".join(table_list)
        all_pages_text.append(combined_page)

    doc.close()
    
    full_content = "\n".join(all_pages_text)
    
    # --- 3. 后处理：清洗、去断词、截断参考文献 ---
    cleaned_content = _post_process_text(full_content)
    final_result = _truncate_references(cleaned_content)
    
    return final_result

def _is_double_column(blocks, page_width) -> bool:
    """启发式判断页面是否为双栏布局"""
    left_count = 0
    right_count = 0
    gutter = page_width / 2
    for b in blocks:
        if b[6] != 0: continue # skip non-text
        x0, x1 = b[0], b[2]
        if x1 <= gutter: left_count += 1
        elif x0 >= gutter: right_count += 1
    # 如果左右两边都有一定数量的独立块，判定为双栏
    return left_count > 3 and right_count > 3

def _is_inside_tables(rect, table_rects) -> bool:
    """检查文本块是否落在已提取的表格范围内，避免重复"""
    for t_rect in table_rects:
        # 如果文本块的中点在表格内，则认为属于表格
        mid_x = (rect[0] + rect[2]) / 2
        mid_y = (rect[1] + rect[3]) / 2
        if t_rect[0] <= mid_x <= t_rect[2] and t_rect[1] <= mid_y <= t_rect[3]:
            return True
    return False

def _post_process_text(text: str) -> str:
    """清洗文本块之间的硬换行，修复断词"""
    # 1. 修复被换行切断的单词: deci-\nsions -> decisions
    text = re.sub(r"(\w+)-\s*\n\s*(\w+)", r"\1\2", text)
    
    lines = text.split("\n")
    cleaned_lines = []
    buffer = ""

    for line in lines:
        s = line.strip()
        if not s:
            if buffer: cleaned_lines.append(buffer)
            buffer = ""
            continue
        
        # 表格行不合并
        if "|" in s or s.startswith("[Table Data]"):
            if buffer: cleaned_lines.append(buffer)
            cleaned_lines.append(s)
            buffer = ""
            continue
        
        if buffer:
            # 如果 buffer 结尾不是句末标点，尝试合并下一行
            if re.search(r'[^.!?;:。！？；：]$', buffer):
                buffer += " " + s
            else:
                cleaned_lines.append(buffer)
                buffer = s
        else:
            buffer = s
            
    if buffer: cleaned_lines.append(buffer)
    
    result = "\n".join(cleaned_lines)
    return re.sub(r" +", " ", result)

def _truncate_references(text: str) -> str:
    """截断参考文献"""
    ref_keywords = [r"^references\s*$", r"^bibliography\s*$", r"^参考文献\s*$", r"^\d+\.\s+references\s*$"]
    lines = text.split("\n")
    final_lines = []
    for line in lines:
        s_lower = line.strip().lower()
        if any(re.match(kw, s_lower) for kw in ref_keywords):
            break
        final_lines.append(line)
    return "\n".join(final_lines)