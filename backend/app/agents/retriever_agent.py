"""
Retriever Agent - 检索Agent

负责文献检索和RAG问答，是最核心的Agent。
"""
from typing import Optional, List, Dict, Any
from loguru import logger

from app.agents.base_agent import BaseAgent, AgentType, AgentResponse


class RetrieverAgent(BaseAgent):
    """
    检索Agent
    
    核心功能：
    1. 基于RAG的文献问答
    2. 向量检索 + 关键词检索
    3. 记忆增强的上下文构建
    """
    
    agent_type = AgentType.RETRIEVER
    description = "文献检索与RAG问答Agent"
    
    # 触发关键词
    TRIGGER_KEYWORDS = [
        "查找", "搜索", "检索", "查询", "找",
        "什么是", "是什么", "定义", "解释",
        "文献", "论文", "文章", "研究",
        "search", "find", "what is", "define", "paper",
        "根据文献", "基于论文", "参考"
    ]
    
    def __init__(self, rag_engine=None):
        super().__init__()
        self.rag_engine = rag_engine
    
    def set_rag_engine(self, rag_engine):
        """设置RAG引擎"""
        self.rag_engine = rag_engine
    
    def can_handle(self, query: str) -> float:
        """判断是否为检索类查询"""
        query_lower = query.lower()
        
        score = 0.3  # 基础分数（检索是默认行为）
        
        for keyword in self.TRIGGER_KEYWORDS:
            if keyword in query_lower:
                score += 0.15
        
        # 问句通常需要检索
        if query.endswith("?") or query.endswith("？"):
            score += 0.1
        
        return min(score, 1.0)
    
    async def execute(
        self,
        query: str,
        project_id: Optional[int] = None,
        top_k: int = 5,
        use_memory: bool = True,
        **kwargs
    ) -> AgentResponse:
        """执行检索问答"""
        if not self.rag_engine:
            return AgentResponse(
                agent_type=self.agent_type.value,
                content="RAG引擎未初始化",
                confidence=0.0
            )
        
        try:
            # 调用RAG引擎
            result = await self.rag_engine.answer(
                question=query,
                project_id=project_id,
                top_k=top_k,
                use_memory=use_memory
            )
            
            # 保存交互到记忆
            await self._save_to_memory(
                content=f"Q: {query}\nA: {result['answer']}",
                metadata={"project_id": project_id or 0}
            )
            
            return AgentResponse(
                agent_type=self.agent_type.value,
                content=result["answer"],
                references=result.get("references", []),
                metadata={
                    "method": result.get("method", "rag"),
                    "memory_used": result.get("memory_used", False),
                    "memory_count": result.get("memory_count", 0)
                },
                confidence=0.85
            )
            
        except Exception as e:
            logger.error(f"RetrieverAgent error: {e}")
            return AgentResponse(
                agent_type=self.agent_type.value,
                content=f"检索失败: {str(e)}",
                confidence=0.0
            )
