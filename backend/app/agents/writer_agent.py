"""
Writer Agent - 写作辅助Agent

负责论文大纲生成、文献综述、段落润色等写作任务。
"""
from typing import Optional, List, Dict, Any
from loguru import logger

from app.agents.base_agent import BaseAgent, AgentType, AgentResponse


class WriterAgent(BaseAgent):
    """
    写作辅助Agent
    
    核心功能：
    1. 论文大纲生成
    2. 文献综述生成
    3. 段落润色
    4. 引用建议
    """
    
    agent_type = AgentType.WRITER
    description = "学术写作辅助Agent"
    
    TRIGGER_KEYWORDS = [
        "写", "撰写", "生成", "大纲", "综述",
        "润色", "修改", "改写", "摘要", "总结",
        "引用", "文献综述", "论文",
        "write", "draft", "outline", "review",
        "polish", "rewrite", "summarize", "abstract"
    ]
    
    def __init__(self, rag_engine=None):
        super().__init__()
        self.rag_engine = rag_engine
    
    def set_rag_engine(self, rag_engine):
        self.rag_engine = rag_engine
    
    def can_handle(self, query: str) -> float:
        query_lower = query.lower()
        score = 0.1
        
        for keyword in self.TRIGGER_KEYWORDS:
            if keyword in query_lower:
                score += 0.2
        
        return min(score, 1.0)
    
    async def execute(
        self,
        query: str,
        project_id: Optional[int] = None,
        task_type: str = "auto",
        context: str = "",
        **kwargs
    ) -> AgentResponse:
        """执行写作任务"""
        try:
            if task_type == "auto":
                task_type = self._detect_task_type(query)
            
            if task_type == "outline":
                result = await self._generate_outline(query, project_id, **kwargs)
            elif task_type == "review":
                result = await self._generate_review(query, project_id, **kwargs)
            elif task_type == "polish":
                result = await self._polish_text(query, context, **kwargs)
            elif task_type == "citation":
                result = await self._suggest_citations(query, project_id, **kwargs)
            else:
                result = await self._general_writing(query, project_id, **kwargs)
            
            await self._save_to_memory(
                content=f"写作任务({task_type}): {query[:100]}",
                metadata={"project_id": project_id or 0, "task_type": task_type}
            )
            
            return AgentResponse(
                agent_type=self.agent_type.value,
                content=result["content"],
                references=result.get("references", []),
                metadata={"task_type": task_type},
                confidence=0.85
            )
            
        except Exception as e:
            logger.error(f"WriterAgent error: {e}")
            return AgentResponse(
                agent_type=self.agent_type.value,
                content=f"写作辅助失败: {str(e)}",
                confidence=0.0
            )
    
    def _detect_task_type(self, query: str) -> str:
        query_lower = query.lower()
        if any(kw in query_lower for kw in ["大纲", "outline", "框架", "structure"]):
            return "outline"
        if any(kw in query_lower for kw in ["综述", "review", "总结", "summarize"]):
            return "review"
        if any(kw in query_lower for kw in ["润色", "polish", "改写", "rewrite"]):
            return "polish"
        if any(kw in query_lower for kw in ["引用", "citation", "参考"]):
            return "citation"
        return "general"
    
    async def _generate_outline(self, query: str, project_id: Optional[int], **kwargs) -> Dict:
        """生成论文大纲"""
        # 检索相关文献作为参考
        refs = []
        if self.rag_engine:
            search_results = await self.rag_engine.search(query, project_id, top_k=5)
            refs = await self.rag_engine._fetch_documents(search_results)
        
        ref_context = "\n".join(
            f"[{i+1}] {r.get('text', '')[:200]}"
            for i, r in enumerate(refs)
        )
        
        if self._llm:
            prompt = f"""请为以下研究主题生成一份详细的论文大纲。

研究主题：{query}

相关文献参考：
{ref_context if ref_context else '无可用参考文献'}

请生成包含以下部分的大纲：
1. 标题建议
2. 摘要要点
3. 引言（研究背景、问题、目的）
4. 相关工作/文献综述
5. 方法论
6. 实验/结果
7. 讨论
8. 结论

每个部分请给出2-3个要点。使用Markdown格式输出。"""
            
            response = await self._llm.ainvoke(prompt)
            return {"content": response.content, "references": refs}
        
        return {"content": "LLM未初始化，无法生成大纲", "references": []}
    
    async def _generate_review(self, query: str, project_id: Optional[int], **kwargs) -> Dict:
        """生成文献综述"""
        refs = []
        if self.rag_engine:
            search_results = await self.rag_engine.search(query, project_id, top_k=10)
            refs = await self.rag_engine._fetch_documents(search_results)
        
        ref_context = "\n\n".join(
            f"文献[{i+1}]: {r.get('text', '')[:500]}"
            for i, r in enumerate(refs)
        )
        
        if self._llm:
            prompt = f"""请基于以下文献资料，撰写一篇学术文献综述段落。

研究主题：{query}

参考文献：
{ref_context if ref_context else '无可用参考文献'}

要求：
1. 使用学术写作风格
2. 使用[1][2]格式引用文献
3. 逻辑清晰，层次分明
4. 包含研究背景、现有方法、不足之处和发展方向
5. 字数约500-800字"""
            
            response = await self._llm.ainvoke(prompt)
            return {"content": response.content, "references": refs}
        
        return {"content": "LLM未初始化，无法生成综述", "references": []}
    
    async def _polish_text(self, query: str, context: str, **kwargs) -> Dict:
        """润色学术文本"""
        text_to_polish = context if context else query
        
        if self._llm:
            prompt = f"""请对以下学术文本进行润色和改进：

原文：
{text_to_polish}

要求：
1. 保持原意不变
2. 使用更专业的学术用语
3. 改善句式结构和逻辑连贯性
4. 修正语法和拼写错误
5. 输出润色后的完整文本，并在最后简要说明主要改动"""
            
            response = await self._llm.ainvoke(prompt)
            return {"content": response.content}
        
        return {"content": "LLM未初始化，无法润色文本"}
    
    async def _suggest_citations(self, query: str, project_id: Optional[int], **kwargs) -> Dict:
        """建议引用"""
        if self.rag_engine:
            search_results = await self.rag_engine.search(query, project_id, top_k=10)
            refs = await self.rag_engine._fetch_documents(search_results)
            
            citation_list = "\n".join(
                f"- {r.get('title', 'Unknown')} ({r.get('year', 'N/A')}): {r.get('text', '')[:100]}..."
                for r in refs
            )
            
            content = f"基于您的研究主题「{query}」，建议引用以下文献：\n\n{citation_list}"
            return {"content": content, "references": refs}
        
        return {"content": "RAG引擎未就绪，无法提供引用建议"}
    
    async def _general_writing(self, query: str, project_id: Optional[int], **kwargs) -> Dict:
        """通用写作辅助"""
        refs = []
        if self.rag_engine:
            search_results = await self.rag_engine.search(query, project_id, top_k=5)
            refs = await self.rag_engine._fetch_documents(search_results)
        
        if self._llm:
            ref_context = "\n".join(
                f"[{i+1}] {r.get('text', '')[:200]}" for i, r in enumerate(refs)
            )
            
            prompt = f"""请根据以下请求进行学术写作辅助：

用户请求：{query}

参考资料：
{ref_context if ref_context else '无'}

请用学术风格完成写作任务。"""
            
            response = await self._llm.ainvoke(prompt)
            return {"content": response.content, "references": refs}
        
        return {"content": "LLM未初始化"}
