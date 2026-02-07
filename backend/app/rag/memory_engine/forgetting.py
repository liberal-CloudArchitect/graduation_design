"""
Forgetting Mechanism

记忆遗忘机制
实现基于时间衰减、访问频率的记忆遗忘策略
"""
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass
from loguru import logger
import time
import math

from .base import MemoryNode, BaseMemoryEngine
from .dynamic_memory import DynamicMemoryEngine, dynamic_memory_engine


@dataclass
class DecayConfig:
    """
    衰减配置
    
    Attributes:
        decay_rate: 衰减率 (0-1, 越高衰减越快)
        protection_period: 保护期（秒），新记忆在此期间不衰减
        min_importance: 最低重要性阈值，低于此值将被标记为可删除
        access_boost: 每次访问的重要性提升
        max_age: 最大保留时长（秒），超过将强制衰减
    """
    decay_rate: float = 0.1
    protection_period: int = 24 * 3600  # 24小时保护期
    min_importance: float = 0.05
    access_boost: float = 0.1
    max_age: int = 30 * 24 * 3600  # 30天最大保留


class ForgettingMechanism:
    """
    记忆遗忘机制
    
    核心功能：
    1. 时间衰减 - 随时间降低记忆重要性
    2. 访问增强 - 被访问的记忆增加重要性
    3. 保护期 - 新记忆在保护期内不衰减
    4. 清理 - 删除低于阈值的记忆
    
    使用方式:
        forgetting = ForgettingMechanism()
        await forgetting.initialize()
        
        # 计算单个记忆的衰减后重要性
        new_importance = forgetting.calculate_decay(memory)
        
        # 批量处理遗忘
        to_delete = await forgetting.process_forgetting(project_id=1)
        
        # 清理
        deleted_count = await forgetting.cleanup(project_id=1)
    """
    
    def __init__(
        self,
        memory_engine: Optional[BaseMemoryEngine] = None,
        config: Optional[DecayConfig] = None
    ):
        """
        初始化遗忘机制
        
        Args:
            memory_engine: 记忆存储引擎
            config: 衰减配置
        """
        self.memory_engine = memory_engine or dynamic_memory_engine
        self.config = config or DecayConfig()
        self._initialized = False
    
    async def initialize(self) -> None:
        """初始化遗忘机制"""
        if self._initialized:
            return
        
        if hasattr(self.memory_engine, 'initialize'):
            await self.memory_engine.initialize()
        
        self._initialized = True
        logger.info("ForgettingMechanism initialized")
    
    def calculate_decay(self, memory: MemoryNode) -> float:
        """
        计算记忆衰减后的重要性
        
        使用艾宾浩斯遗忘曲线的变体：
        R = I * e^(-λt/τ) + A * access_boost
        
        其中：
        - R: 衰减后的重要性
        - I: 初始重要性
        - λ: 衰减率
        - t: 时间（秒）
        - τ: 时间常数
        - A: 访问次数
        
        Args:
            memory: 记忆节点
            
        Returns:
            衰减后的重要性 (0-1)
        """
        current_time = int(time.time())
        age = current_time - memory.timestamp
        
        # 保护期内不衰减
        if age < self.config.protection_period:
            return memory.importance
        
        # 计算有效年龄（减去保护期）
        effective_age = age - self.config.protection_period
        
        # 时间常数：随访问次数增加而增加（更难衰减）
        time_constant = 86400 * (1 + memory.access_count * 0.5)  # 基础1天
        
        # 艾宾浩斯衰减
        decay_factor = math.exp(-self.config.decay_rate * effective_age / time_constant)
        
        # 访问增强
        access_bonus = min(memory.access_count * self.config.access_boost, 0.5)
        
        # 最终重要性
        new_importance = memory.importance * decay_factor + access_bonus
        
        # 限制在 [0, 1] 范围
        return max(0.0, min(1.0, new_importance))
    
    def is_protected(self, memory: MemoryNode) -> bool:
        """
        检查记忆是否在保护期内
        
        Args:
            memory: 记忆节点
            
        Returns:
            是否受保护
        """
        current_time = int(time.time())
        age = current_time - memory.timestamp
        return age < self.config.protection_period
    
    def should_forget(self, memory: MemoryNode) -> bool:
        """
        判断记忆是否应该被遗忘
        
        Args:
            memory: 记忆节点
            
        Returns:
            是否应该遗忘
        """
        # 保护期内不遗忘
        if self.is_protected(memory):
            return False
        
        # 计算衰减后的重要性
        decayed_importance = self.calculate_decay(memory)
        
        # 低于阈值则应该遗忘
        return decayed_importance < self.config.min_importance
    
    async def process_forgetting(
        self,
        memories: Optional[List[MemoryNode]] = None,
        project_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        处理遗忘流程
        
        Args:
            memories: 待处理的记忆列表（None则从引擎获取）
            project_id: 项目ID
            
        Returns:
            处理结果统计
        """
        # 如果没有提供记忆，从引擎获取
        if memories is None:
            # 获取所有记忆（实际应用中应分页处理）
            memories = await self.memory_engine.retrieve(
                query="",  # 空查询获取最近记忆
                project_id=project_id,
                top_k=100
            )
        
        to_forget = []
        to_decay = []
        protected = []
        
        for memory in memories:
            if self.is_protected(memory):
                protected.append(memory.id)
            elif self.should_forget(memory):
                to_forget.append(memory)
            else:
                # 更新衰减后的重要性
                new_importance = self.calculate_decay(memory)
                if new_importance != memory.importance:
                    to_decay.append({
                        "memory_id": memory.id,
                        "old_importance": memory.importance,
                        "new_importance": new_importance
                    })
        
        result = {
            "total_processed": len(memories),
            "protected_count": len(protected),
            "to_forget_count": len(to_forget),
            "to_decay_count": len(to_decay),
            "to_forget_ids": [m.id for m in to_forget],
            "decay_updates": to_decay
        }
        
        logger.info(
            f"Forgetting processed: {len(memories)} total, "
            f"{len(to_forget)} to forget, {len(to_decay)} to decay, "
            f"{len(protected)} protected"
        )
        
        return result
    
    async def cleanup(
        self,
        project_id: Optional[int] = None,
        dry_run: bool = False
    ) -> int:
        """
        执行记忆清理
        
        Args:
            project_id: 项目ID
            dry_run: 是否仅模拟（不实际删除）
            
        Returns:
            删除的记忆数量
        """
        result = await self.process_forgetting(project_id=project_id)
        
        to_forget_ids = result["to_forget_ids"]
        
        if dry_run:
            logger.info(f"Dry run: would delete {len(to_forget_ids)} memories")
            return len(to_forget_ids)
        
        # 实际删除
        deleted_count = 0
        if hasattr(self.memory_engine, 'delete'):
            for memory_id in to_forget_ids:
                try:
                    await self.memory_engine.delete(memory_id)
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete memory {memory_id}: {e}")
        
        logger.info(f"Cleanup completed: {deleted_count} memories deleted")
        return deleted_count
    
    def get_decay_preview(
        self,
        memories: List[MemoryNode]
    ) -> List[Dict[str, Any]]:
        """
        预览衰减效果
        
        Args:
            memories: 记忆列表
            
        Returns:
            每个记忆的衰减预览
        """
        previews = []
        
        for memory in memories:
            current_importance = memory.importance
            decayed_importance = self.calculate_decay(memory)
            
            previews.append({
                "memory_id": memory.id,
                "content_preview": memory.content[:50],
                "age_days": (int(time.time()) - memory.timestamp) / 86400,
                "access_count": memory.access_count,
                "current_importance": round(current_importance, 3),
                "decayed_importance": round(decayed_importance, 3),
                "is_protected": self.is_protected(memory),
                "should_forget": self.should_forget(memory)
            })
        
        return previews
    
    def update_config(self, **kwargs) -> None:
        """
        更新衰减配置
        
        Args:
            **kwargs: 配置参数
        """
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                logger.info(f"Config updated: {key} = {value}")


# 全局实例
forgetting_mechanism = ForgettingMechanism()
