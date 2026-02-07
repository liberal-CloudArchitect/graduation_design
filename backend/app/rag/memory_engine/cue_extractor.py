"""
Cue Extractor

结构化线索提取器，从模糊查询中提取结构化检索线索
用于增强记忆检索的精准度
"""
from typing import List, Optional
from dataclasses import dataclass, field
from loguru import logger
import json
import re


@dataclass
class StructuredCue:
    """
    结构化线索
    
    Attributes:
        topic: 核心讨论主题
        intent: 查询意图类型
        time_frame: 时间范围
        entities: 关键实体列表
        context_hints: 上下文提示词
    """
    topic: str = ""
    intent: str = "recall_fact"  # recall_fact/recall_opinion/summarize/compare
    time_frame: str = "all_time"  # today/this_week/last_month/all_time
    entities: List[str] = field(default_factory=list)
    context_hints: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "intent": self.intent,
            "time_frame": self.time_frame,
            "entities": self.entities,
            "context_hints": self.context_hints
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "StructuredCue":
        return cls(
            topic=data.get("topic", ""),
            intent=data.get("intent", "recall_fact"),
            time_frame=data.get("time_frame", "all_time"),
            entities=data.get("entities", []),
            context_hints=data.get("context_hints", [])
        )


# LLM Prompt模板
CUE_EXTRACTION_PROMPT = """你是一个记忆检索助手。分析用户的查询，提取结构化的检索线索。

用户查询: {user_query}

请输出 JSON 格式的结构化线索（不要包含其他文字）:
{{
    "topic": "核心讨论主题（简短描述）",
    "intent": "查询意图类型，只能是以下之一: recall_fact / recall_opinion / summarize / compare",
    "time_frame": "时间范围，只能是以下之一: today / this_week / last_month / all_time",
    "entities": ["关键实体1", "关键实体2"],
    "context_hints": ["上下文提示词1", "上下文提示词2"]
}}

注意：
1. topic 应该简明扼要，不超过20个字
2. entities 提取查询中的关键名词（模型名、技术名、人名等）
3. context_hints 提取暗示上下文的词语（"上次"、"之前讨论"等）
"""


class CueExtractor:
    """
    线索提取器
    
    从用户查询中提取结构化线索，支持两种模式：
    1. 规则提取（快速，无需LLM）
    2. LLM提取（精准，需要LLM调用）
    
    使用方式:
        extractor = CueExtractor()
        cue = await extractor.extract("上次我们讨论的Transformer变体是什么？")
        print(cue.topic)  # "Transformer变体"
    """
    
    # 时间范围关键词映射
    TIME_KEYWORDS = {
        "today": ["今天", "刚才", "just now", "today", "earlier today"],
        "this_week": ["这周", "本周", "这几天", "this week"],
        "last_month": ["上周", "上个月", "前几天", "last week", "last month"],
    }
    
    # 意图关键词映射
    INTENT_KEYWORDS = {
        "recall_opinion": ["觉得", "认为", "看法", "观点", "opinion", "think"],
        "summarize": ["总结", "概括", "归纳", "summarize", "summary"],
        "compare": ["比较", "对比", "区别", "不同", "compare", "difference"],
    }
    
    def __init__(self, llm=None):
        """
        初始化线索提取器
        
        Args:
            llm: LLM实例，None则使用规则提取
        """
        self.llm = llm
    
    async def extract(self, query: str, use_llm: bool = False) -> StructuredCue:
        """
        提取结构化线索
        
        Args:
            query: 用户查询
            use_llm: 是否使用LLM提取（更精准但更慢）
            
        Returns:
            StructuredCue 结构化线索
        """
        if use_llm and self.llm:
            return await self._extract_with_llm(query)
        else:
            return self._extract_with_rules(query)
    
    def _extract_with_rules(self, query: str) -> StructuredCue:
        """
        基于规则的快速提取
        
        Args:
            query: 用户查询
            
        Returns:
            StructuredCue
        """
        query_lower = query.lower()
        
        # 提取时间范围
        time_frame = "all_time"
        for tf, keywords in self.TIME_KEYWORDS.items():
            if any(kw in query_lower or kw in query for kw in keywords):
                time_frame = tf
                break
        
        # 提取意图
        intent = "recall_fact"  # 默认
        for intent_type, keywords in self.INTENT_KEYWORDS.items():
            if any(kw in query_lower or kw in query for kw in keywords):
                intent = intent_type
                break
        
        # 提取实体（简单的名词提取）
        entities = self._extract_entities(query)
        
        # 提取上下文提示
        context_hints = self._extract_context_hints(query)
        
        # 提取主题（去除时间词和意图词后的核心内容）
        topic = self._extract_topic(query)
        
        cue = StructuredCue(
            topic=topic,
            intent=intent,
            time_frame=time_frame,
            entities=entities,
            context_hints=context_hints
        )
        
        logger.debug(f"Extracted cue: {cue.to_dict()}")
        return cue
    
    async def _extract_with_llm(self, query: str) -> StructuredCue:
        """
        使用LLM进行精准提取
        
        Args:
            query: 用户查询
            
        Returns:
            StructuredCue
        """
        if not self.llm:
            return self._extract_with_rules(query)
        
        try:
            prompt = CUE_EXTRACTION_PROMPT.format(user_query=query)
            response = await self.llm.ainvoke(prompt)
            
            # 解析JSON响应
            content = response.content if hasattr(response, 'content') else str(response)
            
            # 尝试提取JSON
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                data = json.loads(json_match.group())
                return StructuredCue.from_dict(data)
            
        except Exception as e:
            logger.warning(f"LLM extraction failed: {e}, falling back to rules")
        
        return self._extract_with_rules(query)
    
    def _extract_entities(self, query: str) -> List[str]:
        """
        提取关键实体
        
        简单实现：提取引号内容、英文专有名词、技术术语
        """
        entities = []
        
        # 提取引号内容
        quoted = re.findall(r'[「」""\'\'](.*?)[「」""\'\']', query)
        entities.extend(quoted)
        
        # 提取英文单词（包括连字符形式如GPT-4）
        # 不使用\b边界，因为在中文环境下不可靠
        english_words = re.findall(r'([A-Za-z][A-Za-z0-9-]*[A-Za-z0-9]|[A-Za-z])', query)
        for word in english_words:
            # 只保留长度>=2或全大写的单词
            if len(word) >= 2:
                entities.append(word)
        
        # 去重并保持顺序
        seen = set()
        unique_entities = []
        for e in entities:
            e_upper = e.upper()
            if e_upper not in seen:
                seen.add(e_upper)
                unique_entities.append(e)
        
        return unique_entities
    
    def _extract_context_hints(self, query: str) -> List[str]:
        """
        提取上下文提示词
        """
        hints = []
        hint_patterns = [
            "上次", "之前", "刚才", "昨天", "前几天",
            "讨论过", "提到过", "说过", "问过",
            "earlier", "previously", "last time", "before"
        ]
        
        for pattern in hint_patterns:
            if pattern in query.lower() or pattern in query:
                hints.append(pattern)
        
        return hints
    
    def _extract_topic(self, query: str) -> str:
        """
        提取核心主题
        
        去除时间词、意图词后的核心内容
        """
        # 移除常见的问句结构
        topic = query
        remove_patterns = [
            r'^(请问|请|麻烦|帮我|能不能|可以)',
            r'(是什么|是啥|怎么样|如何|吗|呢|？|\?|。|\.)+$',
            r'(上次|之前|刚才|昨天|今天|这周|上周)',
            r'(总结|概括|回顾|分析|比较)',
        ]
        
        for pattern in remove_patterns:
            topic = re.sub(pattern, '', topic)
        
        topic = topic.strip()
        
        # 截断过长的主题
        if len(topic) > 50:
            topic = topic[:50] + "..."
        
        return topic if topic else query[:30]
    
    def extract_sync(self, query: str) -> StructuredCue:
        """同步版本"""
        return self._extract_with_rules(query)


# 全局提取器实例
cue_extractor = CueExtractor()
