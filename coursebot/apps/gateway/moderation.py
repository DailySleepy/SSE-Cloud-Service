import re
from typing import Tuple, List

# PII 正则表达式模式
EMAIL_PATTERN = re.compile(r"\b[\w.-]+@[\w.-]+\.\w+\b")
PHONE_PATTERN = re.compile(r"\b1[3-9]\d{9}\b")
ID_PATTERN = re.compile(r"\b\d{15,18}[\dXx]?\b")

# 关键词黑名单
BLACKLIST_KEYWORDS = ["盗号", "撞库", "绕过鉴权"]

def redact_pii(text: str) -> Tuple[str, List[str]]:
    """
    对文本中的邮箱、手机号、身份证号进行脱敏，替换为对应的占位符。
    返回脱敏后的文本以及检测到的敏感数据类型列表。
    """
    if not text:
        return text, []

    redacted_types = []
    new_text = text

    if EMAIL_PATTERN.search(new_text):
        new_text = EMAIL_PATTERN.sub("[EMAIL]", new_text)
        redacted_types.append("email")

    if PHONE_PATTERN.search(new_text):
        new_text = PHONE_PATTERN.sub("[PHONE]", new_text)
        redacted_types.append("phone")

    if ID_PATTERN.search(new_text):
        new_text = ID_PATTERN.sub("[ID]", new_text)
        redacted_types.append("id")

    return new_text, redacted_types

def check_blacklist(text: str) -> bool:
    """
    检查文本是否包含黑名单词汇（忽略大小写）。
    包含则返回 True，否则返回 False。
    """
    if not text:
        return False
    
    text_lower = text.lower()
    for keyword in BLACKLIST_KEYWORDS:
        if keyword in text_lower:
            return True
    return False
