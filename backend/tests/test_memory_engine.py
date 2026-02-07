"""
Memory Engine Unit Tests

测试动态记忆系统的核心功能
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch


class TestMemoryNode:
    """测试MemoryNode数据结构"""
    
    def test_create_memory_node(self):
        """测试创建记忆节点"""
        from app.rag.memory_engine.base import MemoryNode
        
        memory = MemoryNode.create(
            content="测试记忆内容",
            embedding=[0.1] * 1024,
            importance=0.8,
            project_id=1
        )
        
        assert memory.content == "测试记忆内容"
        assert len(memory.embedding) == 1024
        assert memory.importance == 0.8
        assert memory.project_id == 1
        assert memory.memory_type == "dynamic"
        assert memory.access_count == 0
        assert memory.id is not None
        assert memory.timestamp > 0
    
    def test_to_dict(self):
        """测试转换为字典"""
        from app.rag.memory_engine.base import MemoryNode
        
        memory = MemoryNode.create(
            content="字典测试",
            embedding=[0.5] * 1024,
            project_id=2
        )
        
        data = memory.to_dict()
        
        assert isinstance(data, dict)
        assert data["content"] == "字典测试"
        assert data["project_id"] == 2
        assert "id" in data
        assert "timestamp" in data
    
    def test_from_dict(self):
        """测试从字典创建"""
        from app.rag.memory_engine.base import MemoryNode
        
        data = {
            "id": "test-id-123",
            "content": "从字典创建",
            "embedding": [0.2] * 1024,
            "timestamp": 1700000000,
            "importance": 0.6,
            "access_count": 5,
            "memory_type": "dynamic",
            "relations": {},
            "agent_source": "test_agent",
            "project_id": 3
        }
        
        memory = MemoryNode.from_dict(data)
        
        assert memory.id == "test-id-123"
        assert memory.content == "从字典创建"
        assert memory.access_count == 5
        assert memory.agent_source == "test_agent"


class TestDynamicMemoryEngine:
    """测试动态记忆引擎"""
    
    @pytest.fixture
    def mock_milvus(self):
        """模拟Milvus客户端"""
        mock = MagicMock()
        mock.list_collections.return_value = ["agent_memory"]
        mock.insert.return_value = {"insert_count": 1}
        mock.search.return_value = [[
            {
                "entity": {
                    "id": "mem-123",
                    "content": "历史问答内容",
                    "timestamp": 1700000000,
                    "importance": 0.7,
                    "access_count": 1,
                    "memory_type": "dynamic",
                    "agent_source": "qa_agent",
                    "project_id": 1
                },
                "distance": 0.85
            }
        ]]
        return mock
    
    @pytest.mark.asyncio
    async def test_add_memory(self, mock_milvus):
        """测试添加记忆"""
        from app.rag.memory_engine.dynamic_memory import DynamicMemoryEngine
        
        engine = DynamicMemoryEngine()
        engine.milvus = mock_milvus
        engine._initialized = True
        
        # 模拟embedder
        engine.embedder = MagicMock()
        engine.embedder.embed_single = MagicMock(return_value=[0.1] * 1024)
        
        memory = await engine.add_memory(
            content="Q: 什么是RAG?\nA: RAG是检索增强生成技术",
            metadata={"project_id": 1, "agent_source": "qa_agent"}
        )
        
        assert memory.content == "Q: 什么是RAG?\nA: RAG是检索增强生成技术"
        assert memory.project_id == 1
        mock_milvus.insert.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_retrieve_memory(self, mock_milvus):
        """测试检索记忆"""
        from app.rag.memory_engine.dynamic_memory import DynamicMemoryEngine
        
        engine = DynamicMemoryEngine()
        engine.milvus = mock_milvus
        engine._initialized = True
        
        # 模拟embedder
        engine.embedder = MagicMock()
        engine.embedder.embed_single = MagicMock(return_value=[0.1] * 1024)
        
        results = await engine.retrieve(
            query="RAG技术是什么",
            project_id=1,
            top_k=5
        )
        
        assert len(results) == 1
        assert results[0].content == "历史问答内容"
        assert results[0].project_id == 1
        mock_milvus.search.assert_called_once()
    
    def test_compute_importance(self):
        """测试重要性计算"""
        from app.rag.memory_engine.dynamic_memory import DynamicMemoryEngine
        
        engine = DynamicMemoryEngine()
        
        # 短文本
        score1 = engine._compute_importance("短文本")
        assert score1 >= 0.5 and score1 <= 1.0
        
        # 长文本
        long_text = "这是一段很长的文本" * 100
        score2 = engine._compute_importance(long_text)
        assert score2 > score1
        
        # 包含关键词
        important_text = "这是一个重要的发现和核心结论"
        score3 = engine._compute_importance(important_text)
        assert score3 > 0.5


class TestMemoryEmbedder:
    """测试记忆向量化器"""
    
    def test_embed_fallback(self):
        """测试回退向量化(无模型时)"""
        from app.rag.memory_engine.embedder import MemoryEmbedder
        
        embedder = MemoryEmbedder()
        embedder._initialized = True
        embedder.model = None  # 无模型
        
        vectors = embedder.embed(["测试文本1", "测试文本2"])
        
        assert len(vectors) == 2
        assert len(vectors[0]) == 1024
        assert len(vectors[1]) == 1024
    
    def test_embed_single(self):
        """测试单文本向量化"""
        from app.rag.memory_engine.embedder import MemoryEmbedder
        
        embedder = MemoryEmbedder()
        embedder._initialized = True
        embedder.model = None
        
        vector = embedder.embed_single("单个文本")
        
        assert len(vector) == 1024


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
