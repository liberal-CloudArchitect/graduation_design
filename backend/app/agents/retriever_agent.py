"""
Retriever Agent - 检索Agent

负责文献检索和RAG问答，是最核心的Agent。
集成 Skills: parse_pdf_with_docling（高精度PDF解析）
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
    4. [Skill] 高精度PDF文档解析（parse_pdf_with_docling）
    """
    
    agent_type = AgentType.RETRIEVER
    description = "文献检索与RAG问答Agent"
    _skill_categories = ["academic"]  # 可使用学术类 Skills
    
    # 触发关键词
    TRIGGER_KEYWORDS = [
        "查找", "搜索", "检索", "查询", "找",
        "什么是", "是什么", "定义", "解释",
        "文献", "论文", "文章", "研究",
        "search", "find", "what is", "define", "paper",
        "根据文献", "基于论文", "参考"
    ]
    
    # 触发 PDF 解析 Skill 的关键词
    PDF_PARSE_KEYWORDS = [
        "解析", "parse", "提取内容", "读取pdf", "pdf内容",
        "文档解析", "全文", "结构化"
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
        file_path: str = "",
        **kwargs
    ) -> AgentResponse:
        """
        执行检索问答
        
        增强流程：
        1. 如果提供了 file_path 或查询涉及 PDF 解析，先调用 parse_pdf_with_docling Skill
        2. 将 Skill 结果作为额外上下文注入 RAG 问答
        3. 返回融合后的回答
        """
        skills_used = []
        extra_context = ""
        
        try:
            # ---- Skill 集成：PDF 解析 ----
            if file_path or self._should_parse_pdf(query):
                pdf_path = file_path or kwargs.get("pdf_path", "")
                if pdf_path:
                    logger.info(f"[RetrieverAgent] Invoking parse_pdf_with_docling for: {pdf_path}")
                    skill_result = await self._execute_skill(
                        "parse_pdf_with_docling", file_path=pdf_path
                    )
                    if skill_result.success:
                        # 将解析的 Markdown 作为额外上下文
                        markdown = skill_result.data.get("markdown", "") if isinstance(skill_result.data, dict) else str(skill_result.data)
                        if markdown:
                            extra_context = f"\n\n[PDF解析内容]:\n{markdown[:3000]}"
                            skills_used.append("parse_pdf_with_docling")
                    else:
                        logger.warning(
                            f"[RetrieverAgent] PDF parse skill failed: {skill_result.error}"
                        )
            
            # ---- 也支持 LLM 自动选择 Skill ----
            if not skills_used and self._skill_registry:
                auto_results = await self._select_and_execute_skills(query)
                for r in auto_results:
                    if r.success:
                        skills_used.append(r.skill_name)
                        if isinstance(r.data, dict) and "markdown" in r.data:
                            extra_context += f"\n\n[{r.skill_name}结果]:\n{r.data['markdown'][:2000]}"
            
            # ---- RAG 检索问答 ----
            if not self.rag_engine:
                if extra_context:
                    # 即使 RAG 引擎未就绪，如果有 Skill 结果也可以返回
                    return AgentResponse(
                        agent_type=self.agent_type.value,
                        content=f"RAG引擎未初始化，但通过Skills获取了以下信息：{extra_context[:2000]}",
                        metadata={"skills_used": skills_used},
                        confidence=0.5,
                    )
                return AgentResponse(
                    agent_type=self.agent_type.value,
                    content="RAG引擎未初始化",
                    confidence=0.0,
                )
            
            # 修复查询污染：保持原始 query 用于检索，
            # extra_context 作为独立参数在 Prompt 中注入，不影响向量检索
            result = await self.rag_engine.answer(
                question=query,  # 使用原始查询，不拼接额外内容
                project_id=project_id,
                top_k=top_k,
                use_memory=use_memory,
                extra_context=extra_context,  # 通过独立参数注入
            )
            
            # 保存交互到记忆
            await self._save_to_memory(
                content=f"Q: {query}\nA: {result['answer']}",
                metadata={"project_id": project_id or 0},
            )
            
            return AgentResponse(
                agent_type=self.agent_type.value,
                content=result["answer"],
                references=result.get("references", []),
                metadata={
                    "method": result.get("method", "rag"),
                    "memory_used": result.get("memory_used", False),
                    "memory_count": result.get("memory_count", 0),
                    "skills_used": skills_used,
                },
                confidence=0.85,
            )
            
        except Exception as e:
            logger.error(f"RetrieverAgent error: {e}")
            return AgentResponse(
                agent_type=self.agent_type.value,
                content=f"检索失败: {str(e)}",
                metadata={"skills_used": skills_used},
                confidence=0.0,
            )
    
    def _should_parse_pdf(self, query: str) -> bool:
        """判断查询是否涉及 PDF 解析"""
        query_lower = query.lower()
        return any(kw in query_lower for kw in self.PDF_PARSE_KEYWORDS)
