"""
Agent 基类

所有Agent的公共基类，提供统一接口和记忆集成。
"""
from typing import Any, Dict, Optional, List
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger
import time


class AgentType(str, Enum):
    """Agent类型"""
    RETRIEVER = "retriever_agent"
    ANALYZER = "analyzer_agent"
    WRITER = "writer_agent"
    SEARCH = "search_agent"


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentTask:
    """Agent任务"""
    task_id: str
    query: str
    agent_type: AgentType
    params: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


@dataclass
class AgentResponse:
    """Agent响应"""
    agent_type: str
    content: str
    references: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_type": self.agent_type,
            "content": self.content,
            "references": self.references,
            "metadata": self.metadata,
            "confidence": self.confidence
        }


class BaseAgent(ABC):
    """
    Agent基类
    
    所有Agent必须实现:
    - execute(): 执行任务
    - can_handle(): 判断是否能处理该查询
    """
    
    agent_type: AgentType = AgentType.RETRIEVER
    description: str = "Base Agent"
    
    def __init__(self):
        self._memory_engine = None
        self._cross_memory = None
        self._llm = None
    
    def set_memory_engine(self, memory_engine):
        """设置记忆引擎"""
        self._memory_engine = memory_engine
    
    def set_cross_memory(self, cross_memory):
        """设置跨Agent记忆网络"""
        self._cross_memory = cross_memory
    
    def set_llm(self, llm):
        """设置LLM"""
        self._llm = llm
    
    @abstractmethod
    async def execute(
        self, 
        query: str, 
        project_id: Optional[int] = None,
        **kwargs
    ) -> AgentResponse:
        """
        执行Agent任务
        
        Args:
            query: 用户查询
            project_id: 项目ID
            **kwargs: 额外参数
            
        Returns:
            AgentResponse
        """
        ...
    
    @abstractmethod
    def can_handle(self, query: str) -> float:
        """
        判断该Agent是否能处理查询
        
        Returns:
            0.0-1.0的置信度分数
        """
        ...
    
    async def _save_to_memory(self, content: str, metadata: Dict = None):
        """保存交互记录到记忆"""
        if self._memory_engine:
            try:
                meta = metadata or {}
                meta["agent_source"] = self.agent_type.value
                await self._memory_engine.add_memory(
                    content=content,
                    metadata=meta
                )
            except Exception as e:
                logger.warning(f"Failed to save memory: {e}")
    
    async def _share_memory(self, content: str, target_agents: List[str] = None):
        """共享记忆给其他Agent"""
        if self._cross_memory:
            try:
                from app.rag.memory_engine.base import MemoryNode
                node = MemoryNode(
                    content=content,
                    metadata={"agent_source": self.agent_type.value}
                )
                await self._cross_memory.share_memory(
                    memory=node,
                    source_agent=self.agent_type.value,
                    target_agents=target_agents or []
                )
            except Exception as e:
                logger.warning(f"Failed to share memory: {e}")
    
    async def _get_shared_memories(self, limit: int = 5) -> List[Any]:
        """获取其他Agent共享的记忆"""
        if self._cross_memory:
            try:
                return await self._cross_memory.get_agent_memories(
                    agent_id=self.agent_type.value,
                    limit=limit
                )
            except Exception as e:
                logger.warning(f"Failed to get shared memories: {e}")
        return []
