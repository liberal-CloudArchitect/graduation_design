"""
Query Classifier

查询分类器，实现System 1/2分流机制
- System 1 (快思考): 简单事实性问题，使用传统RAG检索
- System 2 (慢思考): 需要回忆/推理的问题，使用重构记忆
"""
from typing import Literal, List, Tuple
from dataclasses import dataclass
from loguru import logger


QueryMode = Literal["system_1", "system_2"]


@dataclass
class ClassificationResult:
    """分类结果"""
    mode: QueryMode
    confidence: float
    matched_keywords: List[str]
    reason: str


class QueryClassifier:
    """
    查询分类器
    
    基于关键词规则区分快思考(System 1)和慢思考(System 2)
    
    使用方式:
        classifier = QueryClassifier()
        result = await classifier.classify("总结我们上次讨论的内容")
        print(result.mode)  # "system_2"
    """
    
    # 触发System 2的关键词
    RECALL_KEYWORDS = [
        "上次", "之前", "记得", "讨论过", "总结", "回顾",
        "earlier", "previously", "remember", "discussed", "summarize"
    ]
    
    REASONING_KEYWORDS = [
        "为什么", "如何", "比较", "区别", "联系", "关系",
        "分析", "推理", "综合", "对比",
        "why", "how", "compare", "difference", "relationship", "analyze"
    ]
    
    TEMPORAL_KEYWORDS = [
        "刚才", "昨天", "上周", "上个月", "今天早些时候",
        "just now", "yesterday", "last week", "last month", "earlier today"
    ]
    
    def __init__(self, system2_threshold: float = 0.3):
        """
        初始化分类器
        
        Args:
            system2_threshold: 触发System 2的置信度阈值
        """
        self.system2_threshold = system2_threshold
        self._all_system2_keywords = (
            self.RECALL_KEYWORDS + 
            self.REASONING_KEYWORDS + 
            self.TEMPORAL_KEYWORDS
        )
    
    async def classify(self, query: str) -> ClassificationResult:
        """
        分类查询
        
        Args:
            query: 用户查询
            
        Returns:
            ClassificationResult 包含分类结果和置信度
        """
        query_lower = query.lower()
        
        # 检测匹配的关键词
        matched = []
        
        for keyword in self._all_system2_keywords:
            if keyword in query_lower or keyword in query:
                matched.append(keyword)
        
        # 计算置信度
        confidence = self._calculate_confidence(query, matched)
        
        # 决策
        if confidence >= self.system2_threshold:
            mode = "system_2"
            reason = f"匹配到回忆/推理关键词: {matched[:3]}"
        else:
            mode = "system_1"
            reason = "普通事实性查询，使用快速检索"
        
        result = ClassificationResult(
            mode=mode,
            confidence=confidence,
            matched_keywords=matched,
            reason=reason
        )
        
        logger.debug(f"Query classified as {mode} (confidence: {confidence:.2f}): {query[:50]}...")
        return result
    
    def _calculate_confidence(self, query: str, matched_keywords: List[str]) -> float:
        """
        计算System 2置信度
        
        Args:
            query: 原始查询
            matched_keywords: 匹配的关键词列表
            
        Returns:
            0-1之间的置信度分数
        """
        if not matched_keywords:
            return 0.0
        
        # 基础分数：匹配关键词数量
        base_score = min(len(matched_keywords) * 0.25, 0.5)
        
        # 加权：不同类型关键词权重不同
        weights = {
            "recall": 0.3,      # 回忆类关键词权重最高
            "temporal": 0.25,   # 时间类次之
            "reasoning": 0.15   # 推理类基础权重
        }
        
        weighted_score = 0.0
        for kw in matched_keywords:
            if kw in self.RECALL_KEYWORDS:
                weighted_score += weights["recall"]
            elif kw in self.TEMPORAL_KEYWORDS:
                weighted_score += weights["temporal"]
            elif kw in self.REASONING_KEYWORDS:
                weighted_score += weights["reasoning"]
        
        # 综合分数（上限1.0）
        final_score = min(base_score + weighted_score, 1.0)
        return round(final_score, 2)
    
    def classify_sync(self, query: str) -> ClassificationResult:
        """
        同步版本的分类方法（用于非异步上下文）
        
        Args:
            query: 用户查询
            
        Returns:
            ClassificationResult
        """
        import asyncio
        return asyncio.get_event_loop().run_until_complete(self.classify(query))


# 全局分类器实例
query_classifier = QueryClassifier()
