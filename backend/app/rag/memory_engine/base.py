"""
Memory Engine Base Classes

定义记忆系统的基础数据结构和抽象接口
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid


@dataclass
class MemoryNode:
    """
    记忆节点数据结构
    
    Attributes:
        id: 唯一标识符
        content: 记忆内容
        embedding: 向量表示 (1024维)
        timestamp: 创建时间戳 (Unix timestamp)
        importance: 重要性分数 (0-1)
        access_count: 访问次数
        memory_type: 记忆类型 (dynamic/reconstructive/cross)
        relations: 与其他记忆的关系 (JSON格式)
        agent_source: 来源Agent标识
        project_id: 所属项目ID
    """
    id: str
    content: str
    embedding: List[float]
    timestamp: int
    importance: float = 1.0
    access_count: int = 0
    memory_type: str = "dynamic"
    relations: Dict[str, Any] = field(default_factory=dict)
    agent_source: str = "qa_agent"
    project_id: int = 0
    
    @classmethod
    def create(
        cls,
        content: str,
        embedding: List[float],
        importance: float = 1.0,
        memory_type: str = "dynamic",
        agent_source: str = "qa_agent",
        project_id: int = 0,
        relations: Optional[Dict] = None
    ) -> "MemoryNode":
        """工厂方法：创建新的记忆节点"""
        return cls(
            id=str(uuid.uuid4()),
            content=content,
            embedding=embedding,
            timestamp=int(datetime.now().timestamp()),
            importance=importance,
            access_count=0,
            memory_type=memory_type,
            relations=relations or {},
            agent_source=agent_source,
            project_id=project_id
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式 (用于Milvus插入)"""
        return {
            "id": self.id,
            "content": self.content,
            "embedding": self.embedding,
            "timestamp": self.timestamp,
            "importance": self.importance,
            "access_count": self.access_count,
            "memory_type": self.memory_type,
            "relations": self.relations,
            "agent_source": self.agent_source,
            "project_id": self.project_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryNode":
        """从字典创建记忆节点"""
        return cls(
            id=data["id"],
            content=data["content"],
            embedding=data.get("embedding", []),
            timestamp=data.get("timestamp", 0),
            importance=data.get("importance", 1.0),
            access_count=data.get("access_count", 0),
            memory_type=data.get("memory_type", "dynamic"),
            relations=data.get("relations", {}),
            agent_source=data.get("agent_source", "qa_agent"),
            project_id=data.get("project_id", 0)
        )


class BaseMemoryEngine(ABC):
    """
    记忆引擎抽象基类
    
    定义记忆系统的核心接口
    """
    
    @abstractmethod
    async def initialize(self) -> None:
        """初始化记忆引擎"""
        pass
    
    @abstractmethod
    async def add_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> MemoryNode:
        """
        添加新记忆
        
        Args:
            content: 记忆内容
            metadata: 元数据 (project_id, agent_source等)
            
        Returns:
            创建的MemoryNode
        """
        pass
    
    @abstractmethod
    async def retrieve(
        self,
        query: str,
        project_id: Optional[int] = None,
        top_k: int = 5
    ) -> List[MemoryNode]:
        """
        检索相关记忆
        
        Args:
            query: 查询文本
            project_id: 项目ID筛选
            top_k: 返回数量
            
        Returns:
            相关的MemoryNode列表
        """
        pass
    
    @abstractmethod
    async def update_access(self, memory_id: str) -> bool:
        """
        更新记忆访问计数
        
        Args:
            memory_id: 记忆ID
            
        Returns:
            是否更新成功
        """
        pass
    
    async def delete_memory(self, memory_id: str) -> bool:
        """
        删除记忆 (可选实现)
        
        Args:
            memory_id: 记忆ID
            
        Returns:
            是否删除成功
        """
        return False
    
    async def get_memory_by_id(self, memory_id: str) -> Optional[MemoryNode]:
        """
        根据ID获取记忆 (可选实现)
        
        Args:
            memory_id: 记忆ID
            
        Returns:
            MemoryNode或None
        """
        return None
