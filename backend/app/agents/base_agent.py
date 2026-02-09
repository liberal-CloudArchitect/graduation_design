"""
Agent 基类

所有Agent的公共基类，提供统一接口、记忆集成和技能（Skills）支持。
"""
import asyncio
import json
import re
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
    
    Skills 支持:
    - 通过 _skill_categories 声明关心的技能类别
    - 通过 _execute_skill() 安全执行单个技能
    - 通过 _select_and_execute_skills() 让 LLM 自动选择并执行技能
    """
    
    agent_type: AgentType = AgentType.RETRIEVER
    description: str = "Base Agent"
    _skill_categories: List[str] = []  # 子类声明需要的 Skill 类别
    
    def __init__(self):
        self._memory_engine = None
        self._cross_memory = None
        self._llm = None
        self._skill_registry = None
    
    def set_memory_engine(self, memory_engine):
        """设置记忆引擎"""
        self._memory_engine = memory_engine
    
    def set_cross_memory(self, cross_memory):
        """设置跨Agent记忆网络"""
        self._cross_memory = cross_memory
    
    def set_llm(self, llm):
        """设置LLM"""
        self._llm = llm
    
    def set_skill_registry(self, registry):
        """注入技能注册表"""
        self._skill_registry = registry
    
    # ---- Skills 相关方法 ----
    
    def _get_available_skills(self) -> List[Dict[str, Any]]:
        """获取当前 Agent 可用的 Skills 列表"""
        if not self._skill_registry:
            return []
        return self._skill_registry.get_skills_by_categories(self._skill_categories)
    
    def _get_skills_prompt(self) -> str:
        """获取当前 Agent 可用 Skills 的 System Prompt 描述"""
        if not self._skill_registry:
            return ""
        return self._skill_registry.get_skills_prompt(
            categories=self._skill_categories
        )
    
    def _get_openai_tools(self) -> List[Dict]:
        """获取 OpenAI Function Calling 格式的工具描述"""
        if not self._skill_registry:
            return []
        return self._skill_registry.to_openai_functions(
            categories=self._skill_categories
        )
    
    async def _execute_skill(self, skill_name: str, **kwargs) -> Any:
        """
        安全执行单个 Skill
        
        Args:
            skill_name: 技能名称
            **kwargs: 技能参数
            
        Returns:
            SkillResult 对象（包含 success, data, error 字段）
        """
        if not self._skill_registry:
            from app.skills.registry import SkillResult
            return SkillResult(
                success=False,
                error="Skill registry not initialized",
                skill_name=skill_name,
            )
        
        skill = self._skill_registry.get_skill(skill_name)
        if not skill:
            from app.skills.registry import SkillResult
            return SkillResult(
                success=False,
                error=f"Skill '{skill_name}' not found",
                skill_name=skill_name,
            )
        
        logger.info(
            f"[{self.agent_type.value}] Executing skill: {skill_name} "
            f"with args: {list(kwargs.keys())}"
        )
        result = await skill.run(**kwargs)
        
        if result.success:
            logger.info(f"[{self.agent_type.value}] Skill '{skill_name}' succeeded")
        else:
            logger.warning(
                f"[{self.agent_type.value}] Skill '{skill_name}' failed: {result.error}"
            )
        
        return result
    
    async def _execute_skills_parallel(
        self, skill_calls: List[Dict[str, Any]]
    ) -> List[Any]:
        """
        并行执行多个 Skill
        
        Args:
            skill_calls: [{"name": "skill_name", "arguments": {...}}, ...]
            
        Returns:
            SkillResult 列表
        """
        tasks = [
            self._execute_skill(call["name"], **call.get("arguments", {}))
            for call in skill_calls
        ]
        return await asyncio.gather(*tasks, return_exceptions=False)
    
    async def _select_and_execute_skills(
        self, query: str, context: str = ""
    ) -> List[Any]:
        """
        通过 LLM 自动选择并执行合适的 Skills。
        
        流程:
        1. 构建包含可用 Skills 描述的 prompt
        2. 让 LLM 决定是否需要调用 Skill 以及调用哪些
        3. 解析 LLM 输出中的 skill_call 指令
        4. 执行对应的 Skills
        
        Args:
            query: 用户查询
            context: 可选的额外上下文
            
        Returns:
            执行的 SkillResult 列表（可能为空，表示 LLM 决定不调用 Skill）
        """
        if not self._llm or not self._skill_registry:
            return []
        
        available_skills = self._get_available_skills()
        if not available_skills:
            return []
        
        # 构建 Skills 选择 prompt
        skills_desc = self._get_skills_prompt()
        
        selection_prompt = f"""你是一个智能助手，需要判断是否需要调用工具来回答用户的问题。

{skills_desc}

用户问题: {query}
{"附加上下文: " + context if context else ""}

请分析用户的问题，判断是否需要调用上述工具。
- 如果需要调用工具，请输出 JSON 格式的调用指令（可以调用多个工具）。
- 如果不需要调用任何工具，请回复: {{"skill_call": null}}

注意：只在确实需要工具辅助时才调用，简单的问答无需调用工具。"""
        
        try:
            response = await self._llm.ainvoke(selection_prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # 解析 LLM 返回的 skill_call 指令
            skill_calls = self._parse_skill_calls(response_text)
            
            if not skill_calls:
                return []
            
            # 执行所有 Skill 调用
            results = []
            for call in skill_calls:
                result = await self._execute_skill(
                    call["name"], **call.get("arguments", {})
                )
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.warning(
                f"[{self.agent_type.value}] Skill selection/execution failed: {e}"
            )
            return []
    
    def _parse_skill_calls(self, text: str) -> List[Dict[str, Any]]:
        """
        从 LLM 输出中解析 skill_call 指令。
        
        支持格式:
        - {"skill_call": {"name": "xxx", "arguments": {...}}}
        - {"skill_call": [{"name": "xxx", "arguments": {...}}, ...]}
        - {"skill_call": null}  (不调用任何 Skill)
        """
        calls = []
        
        # 尝试从文本中提取 JSON
        json_pattern = r'\{[^{}]*"skill_call"[^{}]*(?:\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}[^{}]*)*\}'
        
        # 更健壮的方式：找到所有可能的 JSON 块
        try:
            # 先尝试直接解析整段文本
            data = json.loads(text.strip())
            if isinstance(data, dict) and "skill_call" in data:
                sc = data["skill_call"]
                if sc is None:
                    return []
                if isinstance(sc, dict):
                    calls.append(sc)
                elif isinstance(sc, list):
                    calls.extend(sc)
                return calls
        except json.JSONDecodeError:
            pass
        
        # 尝试从文本中逐个提取 JSON 块
        brace_depth = 0
        json_start = None
        for i, ch in enumerate(text):
            if ch == '{':
                if brace_depth == 0:
                    json_start = i
                brace_depth += 1
            elif ch == '}':
                brace_depth -= 1
                if brace_depth == 0 and json_start is not None:
                    json_str = text[json_start:i + 1]
                    try:
                        data = json.loads(json_str)
                        if isinstance(data, dict) and "skill_call" in data:
                            sc = data["skill_call"]
                            if sc is None:
                                continue
                            if isinstance(sc, dict):
                                calls.append(sc)
                            elif isinstance(sc, list):
                                calls.extend(sc)
                    except json.JSONDecodeError:
                        pass
                    json_start = None
        
        return calls
    
    # ---- 原有方法 ----
    
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
