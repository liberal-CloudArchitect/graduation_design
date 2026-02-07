"""
Cross Memory Network

跨Agent记忆共享网络
支持不同Agent之间的知识共享和协作记忆
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from loguru import logger
import time

from .base import MemoryNode, BaseMemoryEngine
from .dynamic_memory import DynamicMemoryEngine, dynamic_memory_engine


@dataclass
class SharedMemory:
    """
    共享记忆
    
    Attributes:
        memory: 原始记忆节点
        source_agent: 来源Agent
        target_agents: 目标Agent列表
        share_time: 共享时间戳
        access_level: 访问级别 (public/restricted/private)
    """
    memory: MemoryNode
    source_agent: str
    target_agents: List[str] = field(default_factory=list)
    share_time: int = field(default_factory=lambda: int(time.time()))
    access_level: str = "public"
    
    def to_dict(self) -> dict:
        return {
            "memory_id": self.memory.id,
            "content": self.memory.content,
            "source_agent": self.source_agent,
            "target_agents": self.target_agents,
            "share_time": self.share_time,
            "access_level": self.access_level
        }


class CrossMemoryNetwork:
    """
    跨Agent记忆网络
    
    功能：
    1. 注册Agent到网络
    2. 共享记忆给其他Agent
    3. 检索其他Agent的共享记忆
    4. 管理记忆访问权限
    
    使用方式:
        network = CrossMemoryNetwork()
        network.register_agent("qa_agent")
        network.register_agent("analysis_agent")
        
        await network.share_memory(
            memory=some_memory,
            source_agent="qa_agent",
            target_agents=["analysis_agent"]
        )
        
        memories = await network.retrieve_shared(
            query="问题分析",
            agent_id="analysis_agent"
        )
    """
    
    # 默认Agent类型
    DEFAULT_AGENTS = ["qa_agent", "analysis_agent", "summary_agent"]
    
    def __init__(self, memory_engine: Optional[BaseMemoryEngine] = None):
        """
        初始化跨记忆网络
        
        Args:
            memory_engine: 记忆存储引擎
        """
        self.memory_engine = memory_engine or dynamic_memory_engine
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._shared_memories: List[SharedMemory] = []
        self._initialized = False
    
    async def initialize(self) -> None:
        """初始化网络"""
        if self._initialized:
            return
        
        if hasattr(self.memory_engine, 'initialize'):
            await self.memory_engine.initialize()
        
        # 注册默认Agent
        for agent_id in self.DEFAULT_AGENTS:
            self.register_agent(agent_id)
        
        self._initialized = True
        logger.info("CrossMemoryNetwork initialized with default agents")
    
    def register_agent(
        self,
        agent_id: str,
        capabilities: Optional[List[str]] = None
    ) -> bool:
        """
        注册Agent到网络
        
        Args:
            agent_id: Agent唯一标识
            capabilities: Agent能力标签列表
            
        Returns:
            是否注册成功
        """
        if agent_id in self._agents:
            logger.warning(f"Agent {agent_id} already registered")
            return False
        
        self._agents[agent_id] = {
            "id": agent_id,
            "capabilities": capabilities or [],
            "registered_at": int(time.time()),
            "shared_count": 0,
            "received_count": 0
        }
        
        logger.info(f"Agent {agent_id} registered to CrossMemoryNetwork")
        return True
    
    def unregister_agent(self, agent_id: str) -> bool:
        """注销Agent"""
        if agent_id not in self._agents:
            return False
        
        del self._agents[agent_id]
        logger.info(f"Agent {agent_id} unregistered")
        return True
    
    def get_registered_agents(self) -> List[str]:
        """获取所有已注册的Agent"""
        return list(self._agents.keys())
    
    async def share_memory(
        self,
        memory: MemoryNode,
        source_agent: str,
        target_agents: Optional[List[str]] = None,
        access_level: str = "public"
    ) -> SharedMemory:
        """
        共享记忆给其他Agent
        
        Args:
            memory: 要共享的记忆
            source_agent: 来源Agent
            target_agents: 目标Agent列表（None表示对所有Agent公开）
            access_level: 访问级别
            
        Returns:
            SharedMemory 共享记录
        """
        if source_agent not in self._agents:
            self.register_agent(source_agent)
        
        # 确定目标Agent
        if target_agents is None:
            # 公开给所有其他Agent
            targets = [a for a in self._agents.keys() if a != source_agent]
        else:
            targets = target_agents
        
        # 创建共享记录
        shared = SharedMemory(
            memory=memory,
            source_agent=source_agent,
            target_agents=targets,
            access_level=access_level
        )
        
        self._shared_memories.append(shared)
        
        # 更新Agent统计
        self._agents[source_agent]["shared_count"] += 1
        for target in targets:
            if target in self._agents:
                self._agents[target]["received_count"] += 1
        
        # 将共享记忆存入存储引擎（添加跨Agent标记）
        memory_with_relations = MemoryNode(
            id=memory.id,
            content=memory.content,
            embedding=memory.embedding,
            timestamp=memory.timestamp,
            importance=memory.importance,
            access_count=memory.access_count,
            memory_type="cross_memory",
            relations={
                "source_agent": source_agent,
                "target_agents": targets,
                "access_level": access_level
            },
            agent_source=source_agent,
            project_id=memory.project_id
        )
        
        logger.info(
            f"Memory {memory.id} shared from {source_agent} to {len(targets)} agents"
        )
        
        return shared
    
    async def retrieve_shared(
        self,
        query: str,
        agent_id: str,
        project_id: Optional[int] = None,
        top_k: int = 5,
        include_own: bool = False
    ) -> List[MemoryNode]:
        """
        检索Agent可访问的共享记忆
        
        Args:
            query: 查询内容
            agent_id: 请求Agent的ID
            project_id: 项目ID
            top_k: 返回数量
            include_own: 是否包含自己共享的记忆
            
        Returns:
            可访问的记忆列表
        """
        # 过滤可访问的共享记忆
        accessible_memories = []
        
        for shared in self._shared_memories:
            # 检查访问权限
            if not self._can_access(shared, agent_id, include_own):
                continue
            
            # 检查项目ID
            if project_id and shared.memory.project_id != project_id:
                continue
            
            accessible_memories.append(shared.memory)
        
        if not accessible_memories:
            # 没有共享记忆，使用普通检索
            return await self.memory_engine.retrieve(
                query=query,
                project_id=project_id,
                top_k=top_k
            )
        
        # 简化：直接返回所有可访问记忆（实际应用中应做相似度排序）
        logger.debug(f"Found {len(accessible_memories)} accessible shared memories")
        return accessible_memories[:top_k]
    
    def _can_access(
        self,
        shared: SharedMemory,
        agent_id: str,
        include_own: bool
    ) -> bool:
        """
        检查Agent是否有权访问共享记忆
        
        Args:
            shared: 共享记忆
            agent_id: 请求Agent
            include_own: 是否包含自己的记忆
            
        Returns:
            是否有权限
        """
        # 自己共享的记忆
        if shared.source_agent == agent_id:
            return include_own
        
        # 公开记忆
        if shared.access_level == "public":
            return True
        
        # 受限记忆 - 检查是否在目标列表中
        if shared.access_level == "restricted":
            return agent_id in shared.target_agents
        
        # 私有记忆
        return False
    
    def get_network_stats(self) -> Dict[str, Any]:
        """获取网络统计信息"""
        return {
            "total_agents": len(self._agents),
            "total_shared_memories": len(self._shared_memories),
            "agents": {
                agent_id: {
                    "shared": info["shared_count"],
                    "received": info["received_count"]
                }
                for agent_id, info in self._agents.items()
            }
        }


# 全局实例
cross_memory_network = CrossMemoryNetwork()
