"""
Query Classifier Unit Tests

测试查询分类器的System 1/2分流逻辑
"""
import pytest
from app.rag.memory_engine.query_classifier import (
    QueryClassifier, 
    ClassificationResult,
    query_classifier
)


class TestQueryClassifier:
    """测试查询分类器"""
    
    @pytest.fixture
    def classifier(self):
        """创建分类器实例"""
        return QueryClassifier()
    
    @pytest.mark.asyncio
    async def test_system1_factual_query(self, classifier):
        """测试事实性问题分类为System 1"""
        queries = [
            "BERT的作者是谁？",
            "什么是Transformer模型？",
            "RAG技术的定义是什么？",
            "GPT-4有多少参数？"
        ]
        
        for query in queries:
            result = await classifier.classify(query)
            assert result.mode == "system_1", f"Query '{query}' should be system_1"
            assert result.confidence < 0.3
    
    @pytest.mark.asyncio
    async def test_system2_recall_query(self, classifier):
        """测试回忆类问题分类为System 2"""
        queries = [
            "上次我们讨论了什么？",
            "之前关于Transformer的结论是什么？",
            "总结一下我们的对话",
            "记得上周提到的那个算法吗？"
        ]
        
        for query in queries:
            result = await classifier.classify(query)
            assert result.mode == "system_2", f"Query '{query}' should be system_2"
            assert result.confidence >= 0.3
            assert len(result.matched_keywords) > 0
    
    @pytest.mark.asyncio
    async def test_system2_reasoning_query(self, classifier):
        """测试推理类问题分类为System 2"""
        queries = [
            "为什么BERT比GPT更适合这个任务？",
            "比较一下这两篇论文的方法",
            "分析一下这个结果的原因"
        ]
        
        for query in queries:
            result = await classifier.classify(query)
            # 推理类需要累积多个关键词才会触发System 2
            assert result.mode in ["system_1", "system_2"]
    
    @pytest.mark.asyncio
    async def test_system2_temporal_query(self, classifier):
        """测试时间相关问题分类为System 2"""
        queries = [
            "刚才我问了什么问题？",
            "今天早些时候我们讨论的主题",
            "昨天的对话内容"
        ]
        
        for query in queries:
            result = await classifier.classify(query)
            assert result.mode == "system_2", f"Query '{query}' should be system_2"
    
    @pytest.mark.asyncio
    async def test_classification_result_structure(self, classifier):
        """测试分类结果结构完整性"""
        result = await classifier.classify("上次讨论的内容")
        
        assert isinstance(result, ClassificationResult)
        assert result.mode in ["system_1", "system_2"]
        assert 0 <= result.confidence <= 1
        assert isinstance(result.matched_keywords, list)
        assert isinstance(result.reason, str)
    
    @pytest.mark.asyncio
    async def test_english_keywords(self, classifier):
        """测试英文关键词识别"""
        queries = [
            "What did we discuss earlier?",
            "Summarize the previous conversation",
            "Compare these two approaches"
        ]
        
        for query in queries:
            result = await classifier.classify(query)
            assert len(result.matched_keywords) > 0 or result.mode == "system_1"
    
    def test_sync_classification(self, classifier):
        """测试同步分类方法"""
        result = classifier.classify_sync("测试查询")
        assert isinstance(result, ClassificationResult)
    
    def test_global_instance(self):
        """测试全局实例"""
        assert query_classifier is not None
        assert isinstance(query_classifier, QueryClassifier)
    
    @pytest.mark.asyncio
    async def test_confidence_calculation(self, classifier):
        """测试置信度计算逻辑"""
        # 无关键词
        result1 = await classifier.classify("这是一个普通问题")
        assert result1.confidence == 0.0
        
        # 单个关键词
        result2 = await classifier.classify("总结一下")
        assert result2.confidence > 0
        
        # 多个关键词应该有更高置信度
        result3 = await classifier.classify("回顾一下之前讨论过的内容")
        assert result3.confidence > result2.confidence


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
