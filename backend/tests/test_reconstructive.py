"""
Reconstructive Memory Unit Tests

测试重构性记忆系统的Trace-Expand-Reconstruct流程
"""
import pytest
from unittest.mock import MagicMock, AsyncMock
from app.rag.memory_engine.reconstructive import (
    ReconstructiveMemory,
    ReconstructedMemory,
    reconstructive_memory
)
from app.rag.memory_engine.base import MemoryNode
from app.rag.memory_engine.cue_extractor import StructuredCue


class TestReconstructedMemory:
    """测试ReconstructedMemory数据结构"""
    
    def test_default_values(self):
        """测试默认值"""
        result = ReconstructedMemory(content="测试内容")
        
        assert result.content == "测试内容"
        assert result.fragments == []
        assert result.cue is None
        assert result.confidence == 1.0
        assert result.is_reconstructed is False
    
    def test_to_dict(self):
        """测试序列化"""
        cue = StructuredCue(topic="测试主题")
        result = ReconstructedMemory(
            content="重构内容",
            cue=cue,
            confidence=0.8,
            is_reconstructed=True,
            processing_time=150.5
        )
        
        data = result.to_dict()
        assert data["content"] == "重构内容"
        assert data["confidence"] == 0.8
        assert data["is_reconstructed"] is True
        assert data["processing_time_ms"] == 150.5


class TestReconstructiveMemory:
    """测试重构记忆系统"""
    
    @pytest.fixture
    def mock_memory_engine(self):
        """模拟记忆引擎"""
        engine = MagicMock()
        engine.retrieve = AsyncMock(return_value=[
            MemoryNode(
                id="mem-1",
                content="之前讨论了BERT模型的优缺点",
                embedding=[0.1] * 1024,
                timestamp=1700000000,
                importance=0.8,
                project_id=1
            ),
            MemoryNode(
                id="mem-2",
                content="BERT适合理解任务，GPT适合生成任务",
                embedding=[0.2] * 1024,
                timestamp=1700000100,
                importance=0.7,
                project_id=1
            )
        ])
        engine.initialize = AsyncMock()
        return engine
    
    @pytest.fixture
    def reconstructive(self, mock_memory_engine):
        """创建重构记忆实例"""
        rm = ReconstructiveMemory(memory_engine=mock_memory_engine)
        rm._initialized = True
        return rm
    
    @pytest.mark.asyncio
    async def test_reconstruct_without_llm(self, reconstructive):
        """测试无LLM的简单重构"""
        result = await reconstructive.reconstruct(
            query="上次讨论BERT的内容是什么？",
            project_id=1,
            use_llm=False
        )
        
        assert isinstance(result, ReconstructedMemory)
        assert len(result.content) > 0
        assert result.is_reconstructed is False
        assert result.processing_time > 0
        assert len(result.fragments) > 0
    
    @pytest.mark.asyncio
    async def test_reconstruct_empty_result(self, mock_memory_engine):
        """测试无结果时的处理"""
        mock_memory_engine.retrieve = AsyncMock(return_value=[])
        rm = ReconstructiveMemory(memory_engine=mock_memory_engine)
        rm._initialized = True
        
        result = await rm.reconstruct("不存在的内容", project_id=1)
        
        assert result.confidence == 0.0
        assert "未找到" in result.content
    
    @pytest.mark.asyncio
    async def test_trace_phase(self, reconstructive):
        """测试Trace阶段"""
        from app.rag.memory_engine.cue_extractor import StructuredCue
        
        cue = StructuredCue(
            topic="BERT模型",
            entities=["BERT"],
            intent="recall_fact"
        )
        
        results = await reconstructive._trace(cue, project_id=1)
        
        assert len(results) > 0
        assert all(isinstance(m, MemoryNode) for m in results)
    
    @pytest.mark.asyncio
    async def test_expand_phase(self, reconstructive, mock_memory_engine):
        """测试Expand阶段"""
        seeds = [
            MemoryNode(
                id="seed-1",
                content="种子记忆内容",
                embedding=[0.1] * 1024,
                timestamp=1700000000,
                project_id=1
            )
        ]
        
        expanded = await reconstructive._expand(seeds, project_id=1)
        
        # 扩展后应该有更多结果
        assert len(expanded) >= len(seeds)
    
    def test_reconstruct_simple(self, reconstructive):
        """测试简单重构逻辑"""
        fragments = [
            MemoryNode(
                id="f1",
                content="片段1内容",
                embedding=[],
                timestamp=1700000000,
                project_id=1
            ),
            MemoryNode(
                id="f2",
                content="片段2内容",
                embedding=[],
                timestamp=1700000100,
                project_id=1
            )
        ]
        
        content, confidence = reconstructive._reconstruct_simple(fragments)
        
        assert "历史记忆" in content
        assert "片段1内容" in content
        assert "片段2内容" in content
        assert 0 < confidence < 1
    
    def test_build_search_query(self, reconstructive):
        """测试搜索查询构建"""
        cue = StructuredCue(
            topic="Transformer架构",
            entities=["BERT", "GPT"],
            context_hints=["之前讨论"]
        )
        
        query = reconstructive._build_search_query(cue)
        
        assert "Transformer架构" in query
        assert "BERT" in query or "GPT" in query
    
    def test_format_timestamp(self, reconstructive):
        """测试时间戳格式化"""
        ts = 1700000000  # 2023-11-14
        formatted = reconstructive._format_timestamp(ts)
        
        assert "-" in formatted
        assert ":" in formatted
    
    def test_global_instance(self):
        """测试全局实例"""
        assert reconstructive_memory is not None
        assert isinstance(reconstructive_memory, ReconstructiveMemory)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
