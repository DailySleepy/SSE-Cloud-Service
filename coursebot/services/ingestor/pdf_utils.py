import pdfplumber
import io
import re

def extract_and_clean_pdf(content: bytes) -> str:
    """
    使用 pdfplumber 提取文本，并进行清洗：
    1. 提取表格并转换为文本
    2. 识别并截断参考文献 (References/参考文献)
    """
    all_text = []
    
    # 参考文献截断关键词 (不区分大小写)
    ref_keywords = [
        r"^references\s*$", 
        r"^bibliography\s*$", 
        r"^参考文献\s*$",
        r"^\d+\.\s+references\s*$"
    ]
    
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            # --- 1. 提取表格 ---
            tables = page.extract_tables()
            table_texts = []
            for table in tables:
                # 将表格转换为简易的文本格式
                rows = []
                for row in table:
                    if row:
                        rows.append(" | ".join([str(cell or "").strip() for cell in row]))
                if rows:
                    table_texts.append("\n[Table Data]:\n" + "\n".join(rows) + "\n")
            
            # --- 2. 提取文本 ---
            page_text = page.extract_text() or ""
            
            # 组合当前页内容
            combined_page = page_text
            if table_texts:
                combined_page += "\n" + "\n".join(table_texts)
            
            all_text.append(combined_page)
            
    full_content = "\n".join(all_text)
    
    # --- 3. 参考文献截断逻辑 ---
    # 将内容按行切分，寻找匹配项
    lines = full_content.split("\n")
    cleaned_lines = []
    found_refs = False
    
    for line in lines:
        stripped_line = line.strip().lower()
        # 检查是否匹配任何参考文献关键词
        for kw in ref_keywords:
            if re.match(kw, stripped_line):
                found_refs = True
                break
        
        if found_refs:
            # 发现参考文献，停止添加后续行
            break
        cleaned_lines.append(line)
        
    return "\n".join(cleaned_lines)
