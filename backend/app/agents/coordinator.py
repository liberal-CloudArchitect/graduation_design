"""
Agent Coordinator - Agent协调器

负责任务路由、多Agent协作、结果整合和 Skills 管理。
"""
import asyncio
import uuid
from typing import Optional, List, Dict, Any
from loguru import logger

from app.agents.base_agent import (
    BaseAgent, AgentType, AgentTask, AgentResponse, TaskStatus
)
from app.agents.retriever_agent import RetrieverAgent
from app.agents.analyzer_agent import AnalyzerAgent
from app.agents.writer_agent import WriterAgent
from app.agents.search_agent import SearchAgent


class AgentCoordinator:
    """
    Agent协调器
    
    核心职责：
    1. 查询意图识别 → 路由到合适的Agent
    2. 多Agent协作编排
    3. 结果整合与输出
    4. 记忆管理
    5. Skills 注册表注入与管理
    """
    
    def __init__(self):
        # Agent 注册表
        self.agents: Dict[AgentType, BaseAgent] = {}
        self._rag_engine = None
        self._memory_engine = None
        self._cross_memory = None
        self._llm = None
        self._skill_registry = None
        self._initialized = False
    
    async def initialize(self, rag_engine=None):
        """初始化协调器和所有Agent"""
        if self._initialized:
            return
        
        self._rag_engine = rag_engine
        
        if rag_engine:
            self._memory_engine = rag_engine.memory_engine
            self._llm = rag_engine.llm
        
        # 初始化 Skills 注册表（导入模块触发所有 Skill 注册）
        try:
            from app.skills import skill_registry
            self._skill_registry = skill_registry
            skill_count = len(skill_registry.skills)
            logger.info(f"Skills registry loaded: {skill_count} skills available")
        except Exception as e:
            logger.warning(f"Skills registry init failed: {e}")
            self._skill_registry = None
        
        # 初始化跨Agent记忆网络
        try:
            from app.rag.memory_engine.cross_memory import CrossMemoryNetwork
            self._cross_memory = CrossMemoryNetwork()
            if self._memory_engine:
                await self._cross_memory.initialize(self._memory_engine)
            
            # 注册Agent到记忆网络
            for agent_type in AgentType:
                await self._cross_memory.register_agent(agent_type.value)
        except Exception as e:
            logger.warning(f"Cross memory init failed: {e}")
        
        # 注册Agent
        self._register_agents()
        
        self._initialized = True
        logger.info(
            f"AgentCoordinator initialized with {len(self.agents)} agents, "
            f"skills_registry={'loaded' if self._skill_registry else 'unavailable'}"
        )
    
    def _register_agents(self):
        """注册所有Agent，并注入 Skills 注册表"""
        # Retriever Agent
        retriever = RetrieverAgent(rag_engine=self._rag_engine)
        retriever.set_memory_engine(self._memory_engine)
        retriever.set_cross_memory(self._cross_memory)
        retriever.set_llm(self._llm)
        if self._skill_registry:
            retriever.set_skill_registry(self._skill_registry)
        self.agents[AgentType.RETRIEVER] = retriever
        
        # Analyzer Agent
        analyzer = AnalyzerAgent()
        analyzer.set_memory_engine(self._memory_engine)
        analyzer.set_cross_memory(self._cross_memory)
        analyzer.set_llm(self._llm)
        if self._skill_registry:
            analyzer.set_skill_registry(self._skill_registry)
        self.agents[AgentType.ANALYZER] = analyzer
        
        # Writer Agent
        writer = WriterAgent(rag_engine=self._rag_engine)
        writer.set_memory_engine(self._memory_engine)
        writer.set_cross_memory(self._cross_memory)
        writer.set_llm(self._llm)
        if self._skill_registry:
            writer.set_skill_registry(self._skill_registry)
        self.agents[AgentType.WRITER] = writer
        
        # Search Agent
        search = SearchAgent()
        search.set_memory_engine(self._memory_engine)
        search.set_cross_memory(self._cross_memory)
        search.set_llm(self._llm)
        if self._skill_registry:
            search.set_skill_registry(self._skill_registry)
        self.agents[AgentType.SEARCH] = search
    
    async def process(
        self,
        query: str,
        project_id: Optional[int] = None,
        agent_type: Optional[str] = None,
        **kwargs
    ) -> AgentResponse:
        """
        处理用户请求
        
        Args:
            query: 用户查询
            project_id: 项目ID
            agent_type: 指定Agent类型 (可选，不指定则自动路由)
            **kwargs: 额外参数
            
        Returns:
            AgentResponse
        """
        if not self._initialized:
            await self.initialize(self._rag_engine)
        
        # 如果指定了Agent类型
        if agent_type:
            try:
                at = AgentType(agent_type)
                agent = self.agents.get(at)
                if agent:
                    return await agent.execute(query, project_id, **kwargs)
            except ValueError:
                logger.warning(f"Unknown agent type: {agent_type}")
        
        # 自动路由
        best_agent, confidence = self._route_query(query)
        
        logger.info(f"Routing query to {best_agent.agent_type.value} (confidence: {confidence:.2f})")
        
        # 执行
        response = await best_agent.execute(query, project_id, **kwargs)
        
        return response
    
    async def process_multi(
        self,
        query: str,
        project_id: Optional[int] = None,
        agent_types: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, AgentResponse]:
        """
        多Agent并行处理
        
        同时调用多个Agent，整合结果。
        """
        if not self._initialized:
            await self.initialize(self._rag_engine)
        
        # 确定要调用的Agent
        agents_to_call = []
        if agent_types:
            for at_str in agent_types:
                try:
                    at = AgentType(at_str)
                    if at in self.agents:
                        agents_to_call.append(self.agents[at])
                except ValueError:
                    pass
        else:
            # 选择所有有意愿处理的Agent
            for agent in self.agents.values():
                score = agent.can_handle(query)
                if score > 0.3:
                    agents_to_call.append(agent)
        
        if not agents_to_call:
            agents_to_call = [self.agents[AgentType.RETRIEVER]]
        
        # 并行执行
        tasks = [
            agent.execute(query, project_id, **kwargs)
            for agent in agents_to_call
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 整合结果
        responses = {}
        for agent, result in zip(agents_to_call, results):
            if isinstance(result, Exception):
                logger.error(f"{agent.agent_type.value} failed: {result}")
                responses[agent.agent_type.value] = AgentResponse(
                    agent_type=agent.agent_type.value,
                    content=f"处理失败: {str(result)}",
                    confidence=0.0
                )
            else:
                responses[agent.agent_type.value] = result
        
        return responses
    
    def _route_query(self, query: str) -> tuple:
        """
        路由查询到最合适的Agent
        
        Returns:
            (best_agent, confidence)
        """
        scores = {}
        for agent_type, agent in self.agents.items():
            score = agent.can_handle(query)
            scores[agent_type] = score
        
        # 选择最高分的Agent
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]
        
        # 如果所有分数都很低，默认用检索Agent
        if best_score < 0.3:
            return self.agents[AgentType.RETRIEVER], 0.3
        
        return self.agents[best_type], best_score
    
    def set_trend_service(self, trend_service):
        """为Analyzer Agent设置趋势服务"""
        analyzer = self.agents.get(AgentType.ANALYZER)
        if analyzer:
            analyzer.set_trend_service(trend_service)
    
    # ---- Skills 管理方法 ----
    
    def list_available_skills(
        self, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        列出所有可用的 Skills
        
        Args:
            category: 按类别筛选 (academic, analysis, utility)
            
        Returns:
            技能描述列表
        """
        if not self._skill_registry:
            return []
        return self._skill_registry.list_skills(category=category)
    
    async def execute_skill(
        self, skill_name: str, **kwargs
    ) -> Dict[str, Any]:
        """
        直接执行指定的 Skill（用于 API 层直接调用）
        
        Args:
            skill_name: 技能名称
            **kwargs: 技能参数
            
        Returns:
            执行结果字典
        """
        if not self._skill_registry:
            return {"success": False, "error": "Skills registry not initialized"}
        
        skill = self._skill_registry.get_skill(skill_name)
        if not skill:
            return {"success": False, "error": f"Skill '{skill_name}' not found"}
        
        result = await skill.run(**kwargs)
        return {
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "skill_name": result.skill_name,
        }
    
    def get_agent_skills(self, agent_type: str) -> List[Dict[str, Any]]:
        """获取指定 Agent 可用的 Skills 列表"""
        try:
            at = AgentType(agent_type)
            agent = self.agents.get(at)
            if agent:
                return agent._get_available_skills()
        except (ValueError, AttributeError):
            pass
        return []


# 全局协调器实例
agent_coordinator = AgentCoordinator()
