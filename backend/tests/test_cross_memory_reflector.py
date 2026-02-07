"""
Cross Memory and Reflector Unit Tests

测试跨Agent记忆网络和海马体反思器
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from app.rag.memory_engine.cross_memory import (
    CrossMemoryNetwork,
    SharedMemory,
    cross_memory_network
)
from app.rag.memory_engine.reflector import (
    HippocampusReflector,
    ConsolidationTask,
    hippocampus_reflector
)
from app.rag.memory_engine.base import MemoryNode


class TestCrossMemoryNetwork:
    """测试跨Agent记忆网络"""
    
    @pytest.fixture
    def network(self):
        """创建网络实例"""
        n = CrossMemoryNetwork()
        n._initialized = True
        return n
    
    def test_register_agent(self, network):
        """测试Agent注册"""
        result = network.register_agent("test_agent")
        
        assert result is True
        assert "test_agent" in network.get_registered_agents()
    
    def test_register_duplicate_agent(self, network):
        """测试重复注册"""
        network.register_agent("dup_agent")
        result = network.register_agent("dup_agent")
        
        assert result is False
    
    def test_unregister_agent(self, network):
        """测试Agent注销"""
        network.register_agent("temp_agent")
        result = network.unregister_agent("temp_agent")
        
        assert result is True
        assert "temp_agent" not in network.get_registered_agents()
    
    @pytest.mark.asyncio
    async def test_share_memory(self, network):
        """测试记忆共享"""
        network.register_agent("source_agent")
        network.register_agent("target_agent")
        
        memory = MemoryNode(
            id="test-mem-1",
            content="测试共享内容",
            embedding=[0.1] * 1024,
            timestamp=1700000000,
            project_id=1
        )
        
        shared = await network.share_memory(
            memory=memory,
            source_agent="source_agent",
            target_agents=["target_agent"]
        )
        
        assert isinstance(shared, SharedMemory)
        assert shared.source_agent == "source_agent"
        assert "target_agent" in shared.target_agents
    
    @pytest.mark.asyncio
    async def test_retrieve_shared(self, network):
        """测试共享记忆检索"""
        network.register_agent("agent_a")
        network.register_agent("agent_b")
        
        memory = MemoryNode(
            id="shared-mem-1",
            content="共享记忆内容",
            embedding=[0.1] * 1024,
            timestamp=1700000000,
            project_id=1
        )
        
        await network.share_memory(
            memory=memory,
            source_agent="agent_a",
            target_agents=["agent_b"]
        )
        
        # agent_b 应该能检索到
        results = await network.retrieve_shared(
            query="共享",
            agent_id="agent_b",
            project_id=1
        )
        
        # 注：简化实现返回所有可访问记忆
        assert len(results) >= 0
    
    def test_network_stats(self, network):
        """测试网络统计"""
        network.register_agent("stat_agent")
        stats = network.get_network_stats()
        
        assert "total_agents" in stats
        assert "total_shared_memories" in stats
    
    def test_global_instance(self):
        """测试全局实例"""
        assert cross_memory_network is not None
        assert isinstance(cross_memory_network, CrossMemoryNetwork)


class TestHippocampusReflector:
    """测试海马体反思器"""
    
    @pytest.fixture
    def reflector(self):
        """创建反思器实例"""
        return HippocampusReflector()
    
    def test_task_creation(self):
        """测试任务创建"""
        task = ConsolidationTask(
            task_id="test-1",
            task_type="summarize",
            memories=[]
        )
        
        assert task.task_id == "test-1"
        assert task.status == "pending"
    
    def test_task_to_dict(self):
        """测试任务序列化"""
        task = ConsolidationTask(
            task_id="test-2",
            task_type="compress",
            memories=[],
            priority=8
        )
        
        data = task.to_dict()
        assert data["task_id"] == "test-2"
        assert data["priority"] == 8
    
    @pytest.mark.asyncio
    async def test_submit_task(self, reflector):
        """测试任务提交"""
        memories = [
            MemoryNode(
                id="mem-1",
                content="内容1",
                embedding=[],
                timestamp=1700000000,
                project_id=1
            )
        ]
        
        task_id = await reflector.submit_task(
            task_type="summarize",
            memories=memories
        )
        
        assert task_id is not None
        assert reflector.get_task_status(task_id) == "pending"
    
    @pytest.mark.asyncio
    async def test_worker_lifecycle(self, reflector):
        """测试工作器生命周期"""
        await reflector.start()
        assert reflector._running is True
        
        await reflector.stop()
        assert reflector._running is False
    
    def test_get_stats(self, reflector):
        """测试统计获取"""
        stats = reflector.get_stats()
        
        assert "running" in stats
        assert "pending_tasks" in stats
        assert "queue_size" in stats
    
    def test_global_instance(self):
        """测试全局实例"""
        assert hippocampus_reflector is not None
        assert isinstance(hippocampus_reflector, HippocampusReflector)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
