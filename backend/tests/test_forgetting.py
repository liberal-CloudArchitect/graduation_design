"""
Forgetting Mechanism Unit Tests

测试记忆遗忘机制
"""
import pytest
import time
from app.rag.memory_engine.forgetting import (
    ForgettingMechanism,
    DecayConfig,
    forgetting_mechanism
)
from app.rag.memory_engine.base import MemoryNode


class TestDecayConfig:
    """测试衰减配置"""
    
    def test_default_values(self):
        """测试默认配置"""
        config = DecayConfig()
        
        assert config.decay_rate == 0.1
        assert config.protection_period == 24 * 3600
        assert config.min_importance == 0.05
    
    def test_custom_values(self):
        """测试自定义配置"""
        config = DecayConfig(
            decay_rate=0.2,
            protection_period=3600,
            min_importance=0.1
        )
        
        assert config.decay_rate == 0.2
        assert config.protection_period == 3600


class TestForgettingMechanism:
    """测试遗忘机制"""
    
    @pytest.fixture
    def forgetting(self):
        """创建遗忘机制实例"""
        fm = ForgettingMechanism()
        fm._initialized = True
        return fm
    
    def test_calculate_decay_protected(self, forgetting):
        """测试保护期内不衰减"""
        current_time = int(time.time())
        
        memory = MemoryNode(
            id="new-mem",
            content="新记忆",
            embedding=[],
            timestamp=current_time - 3600,  # 1小时前
            importance=0.8,
            project_id=1
        )
        
        # 在保护期内，重要性不变
        decayed = forgetting.calculate_decay(memory)
        assert decayed == memory.importance
    
    def test_calculate_decay_old_memory(self, forgetting):
        """测试老记忆衰减"""
        current_time = int(time.time())
        
        memory = MemoryNode(
            id="old-mem",
            content="老记忆",
            embedding=[],
            timestamp=current_time - 7 * 24 * 3600,  # 7天前
            importance=0.5,
            access_count=0,
            project_id=1
        )
        
        decayed = forgetting.calculate_decay(memory)
        # 老记忆应该衰减
        assert decayed < memory.importance
    
    def test_access_boost(self, forgetting):
        """测试访问增强"""
        current_time = int(time.time())
        
        # 相同年龄，不同访问次数
        mem_low_access = MemoryNode(
            id="low-access",
            content="低访问",
            embedding=[],
            timestamp=current_time - 3 * 24 * 3600,
            importance=0.5,
            access_count=0,
            project_id=1
        )
        
        mem_high_access = MemoryNode(
            id="high-access",
            content="高访问",
            embedding=[],
            timestamp=current_time - 3 * 24 * 3600,
            importance=0.5,
            access_count=10,
            project_id=1
        )
        
        decay_low = forgetting.calculate_decay(mem_low_access)
        decay_high = forgetting.calculate_decay(mem_high_access)
        
        # 高访问应该有更高的保留重要性
        assert decay_high > decay_low
    
    def test_is_protected(self, forgetting):
        """测试保护期检查"""
        current_time = int(time.time())
        
        new_memory = MemoryNode(
            id="new",
            content="新",
            embedding=[],
            timestamp=current_time - 3600,  # 1小时前
            project_id=1
        )
        
        old_memory = MemoryNode(
            id="old",
            content="老",
            embedding=[],
            timestamp=current_time - 3 * 24 * 3600,  # 3天前
            project_id=1
        )
        
        assert forgetting.is_protected(new_memory) is True
        assert forgetting.is_protected(old_memory) is False
    
    def test_should_forget(self, forgetting):
        """测试遗忘判断"""
        current_time = int(time.time())
        
        # 老记忆，低重要性，无访问
        to_forget = MemoryNode(
            id="forget-me",
            content="应该遗忘",
            embedding=[],
            timestamp=current_time - 30 * 24 * 3600,  # 30天前
            importance=0.1,
            access_count=0,
            project_id=1
        )
        
        # 老记忆，高访问
        keep = MemoryNode(
            id="keep-me",
            content="应该保留",
            embedding=[],
            timestamp=current_time - 30 * 24 * 3600,
            importance=0.5,
            access_count=20,
            project_id=1
        )
        
        assert forgetting.should_forget(to_forget) is True
        assert forgetting.should_forget(keep) is False
    
    def test_get_decay_preview(self, forgetting):
        """测试衰减预览"""
        current_time = int(time.time())
        
        memories = [
            MemoryNode(
                id=f"mem-{i}",
                content=f"内容{i}",
                embedding=[],
                timestamp=current_time - i * 24 * 3600,
                importance=0.5,
                access_count=i,
                project_id=1
            )
            for i in range(3)
        ]
        
        previews = forgetting.get_decay_preview(memories)
        
        assert len(previews) == 3
        assert all("memory_id" in p for p in previews)
        assert all("decayed_importance" in p for p in previews)
    
    def test_update_config(self, forgetting):
        """测试配置更新"""
        original = forgetting.config.decay_rate
        
        forgetting.update_config(decay_rate=0.2)
        
        assert forgetting.config.decay_rate == 0.2
        assert forgetting.config.decay_rate != original
    
    def test_global_instance(self):
        """测试全局实例"""
        assert forgetting_mechanism is not None
        assert isinstance(forgetting_mechanism, ForgettingMechanism)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
