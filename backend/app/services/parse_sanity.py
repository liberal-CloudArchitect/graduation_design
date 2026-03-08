"""
解析健全性检查 (Sanity Gate)

仅做两项硬门槛判断，不做需要 ground truth 的质量评分。
不通过时触发降级到 legacy 管线。
"""
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from loguru import logger


@dataclass
class SanityResult:
    """健全性检查结果"""
    passed: bool
    reason: Optional[str] = None


class ParseSanityGate:
    """MinerU 输出的健全性检查 -- 仅做硬门槛, 不做软评分"""

    GARBLE_THRESHOLD = 0.15
    MIN_CHARS_PER_PAGE = 100

    def check(self, markdown_text: str, page_count: int) -> SanityResult:
        """检查 MinerU 输出是否通过健全性门槛。

        仅检查两项:
        1. garble_rate: 非 ASCII/CJK/常见标点 字符占比 > 阈值 → 不通过
        2. text_length: 总文本长度 / 页数 < 最低阈值 → 不通过 (大量内容丢失)
        """
        if not markdown_text or not markdown_text.strip():
            return SanityResult(passed=False, reason="sanity_empty_output")

        garble_rate = self._compute_garble_rate(markdown_text)
        if garble_rate > self.GARBLE_THRESHOLD:
            logger.warning(
                f"Sanity gate: garble_rate={garble_rate:.3f} > {self.GARBLE_THRESHOLD}"
            )
            return SanityResult(passed=False, reason="sanity_garble")

        chars_per_page = len(markdown_text) / max(page_count, 1)
        if chars_per_page < self.MIN_CHARS_PER_PAGE:
            logger.warning(
                f"Sanity gate: chars_per_page={chars_per_page:.0f} < {self.MIN_CHARS_PER_PAGE}"
            )
            return SanityResult(passed=False, reason="sanity_text_short")

        return SanityResult(passed=True)

    def _compute_garble_rate(self, text: str) -> float:
        """计算乱码字符占比。

        合法字符: ASCII 可打印、CJK 统一表意文字、常见中日韩标点、
        拉丁扩展、希腊字母、数学符号、空白字符。
        """
        if not text:
            return 0.0

        total = 0
        garble = 0
        for ch in text:
            total += 1
            if self._is_legitimate_char(ch):
                continue
            garble += 1

        return garble / total if total > 0 else 0.0

    @staticmethod
    def _is_legitimate_char(ch: str) -> bool:
        """判断字符是否为合法（非乱码）字符"""
        if ch.isascii():
            return True

        cat = unicodedata.category(ch)

        # Letters and numbers (covers CJK, Latin extended, Greek, Cyrillic, etc.)
        if cat.startswith(("L", "N")):
            return True

        # Punctuation, symbols, marks
        if cat.startswith(("P", "S", "M", "Z")):
            return True

        return False
