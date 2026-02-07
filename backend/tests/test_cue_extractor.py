"""
Cue Extractor Unit Tests

测试结构化线索提取器
"""
import pytest
from app.rag.memory_engine.cue_extractor import (
    CueExtractor,
    StructuredCue,
    cue_extractor
)


class TestStructuredCue:
    """测试StructuredCue数据结构"""
    
    def test_default_values(self):
        """测试默认值"""
        cue = StructuredCue()
        assert cue.topic == ""
        assert cue.intent == "recall_fact"
        assert cue.time_frame == "all_time"
        assert cue.entities == []
        assert cue.context_hints == []
    
    def test_to_dict(self):
        """测试序列化"""
        cue = StructuredCue(
            topic="Transformer",
            intent="compare",
            entities=["BERT", "GPT"]
        )
        data = cue.to_dict()
        
        assert data["topic"] == "Transformer"
        assert data["intent"] == "compare"
        assert "BERT" in data["entities"]
    
    def test_from_dict(self):
        """测试反序列化"""
        data = {
            "topic": "RAG技术",
            "intent": "summarize",
            "time_frame": "last_month",
            "entities": ["LangChain"],
            "context_hints": ["之前"]
        }
        cue = StructuredCue.from_dict(data)
        
        assert cue.topic == "RAG技术"
        assert cue.intent == "summarize"
        assert cue.time_frame == "last_month"


class TestCueExtractor:
    """测试线索提取器"""
    
    @pytest.fixture
    def extractor(self):
        return CueExtractor()
    
    @pytest.mark.asyncio
    async def test_extract_time_frame_today(self, extractor):
        """测试今天时间范围提取"""
        queries = [
            "刚才我们说了什么？",
            "今天讨论的内容",
            "just now we discussed"
        ]
        
        for query in queries:
            cue = await extractor.extract(query)
            assert cue.time_frame == "today", f"Query '{query}' should have time_frame 'today'"
    
    @pytest.mark.asyncio
    async def test_extract_time_frame_last_month(self, extractor):
        """测试上周/上月时间范围提取"""
        queries = [
            "上周我们讨论的主题",
            "上个月提到的论文",
            "last week's discussion"
        ]
        
        for query in queries:
            cue = await extractor.extract(query)
            assert cue.time_frame == "last_month"
    
    @pytest.mark.asyncio
    async def test_extract_intent_summarize(self, extractor):
        """测试总结意图提取"""
        queries = [
            "总结一下我们的对话",
            "概括上次的讨论",
            "summarize the conversation"
        ]
        
        for query in queries:
            cue = await extractor.extract(query)
            assert cue.intent == "summarize"
    
    @pytest.mark.asyncio
    async def test_extract_intent_compare(self, extractor):
        """测试比较意图提取"""
        queries = [
            "比较BERT和GPT的区别",
            "对比这两种方法",
            "compare the differences"
        ]
        
        for query in queries:
            cue = await extractor.extract(query)
            assert cue.intent == "compare"
    
    @pytest.mark.asyncio
    async def test_extract_entities_tech_terms(self, extractor):
        """测试技术术语实体提取"""
        query = "BERT和Transformer的关系是什么？"
        cue = await extractor.extract(query)
        
        assert "BERT" in cue.entities or "TRANSFORMER" in cue.entities
    
    @pytest.mark.asyncio
    async def test_extract_entities_proper_nouns(self, extractor):
        """测试专有名词提取"""
        query = "OpenAI发布的GPT-4有什么特点？"
        cue = await extractor.extract(query)
        
        assert len(cue.entities) > 0
    
    @pytest.mark.asyncio
    async def test_extract_context_hints(self, extractor):
        """测试上下文提示提取"""
        query = "之前讨论过的RAG技术要点"
        cue = await extractor.extract(query)
        
        assert len(cue.context_hints) > 0
        assert "之前" in cue.context_hints or "讨论过" in cue.context_hints
    
    @pytest.mark.asyncio
    async def test_extract_topic(self, extractor):
        """测试主题提取"""
        query = "请帮我总结一下上次关于向量数据库的讨论"
        cue = await extractor.extract(query)
        
        assert len(cue.topic) > 0
        assert len(cue.topic) <= 53  # 50 + "..."
    
    def test_sync_extraction(self, extractor):
        """测试同步提取"""
        cue = extractor.extract_sync("测试查询")
        assert isinstance(cue, StructuredCue)
    
    def test_global_instance(self):
        """测试全局实例"""
        assert cue_extractor is not None
        assert isinstance(cue_extractor, CueExtractor)
    
    @pytest.mark.asyncio
    async def test_complex_query(self, extractor):
        """测试复杂查询"""
        query = "上次我们比较BERT和GPT时，你认为哪个更适合NLP任务？"
        cue = await extractor.extract(query)
        
        # 应该提取到时间、意图、实体
        assert cue.time_frame != "all_time" or len(cue.context_hints) > 0
        assert len(cue.entities) >= 1  # 至少提取到BERT或GPT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
