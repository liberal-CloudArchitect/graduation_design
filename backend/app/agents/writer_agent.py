"""
Writer Agent - 写作辅助Agent

负责论文大纲生成、文献综述、段落润色等写作任务。
集成 Skills:
- get_paper_bibtex（PDF提取BibTeX引用）
- parse_bibtex_entries（解析BibTeX数据）
- format_references（参考文献格式化）
- summarize_with_model（文本摘要）
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
    5. [Skill] PDF BibTeX 提取（get_paper_bibtex）
    6. [Skill] BibTeX 文件解析（parse_bibtex_entries）
    7. [Skill] 参考文献格式化（format_references）
    8. [Skill] 文本摘要（summarize_with_model）
    """
    
    agent_type = AgentType.WRITER
    description = "学术写作辅助Agent"
    _skill_categories = ["academic", "utility"]  # 可使用学术类 + 通用类 Skills
    
    TRIGGER_KEYWORDS = [
        "写", "撰写", "生成", "大纲", "综述",
        "润色", "修改", "改写", "摘要", "总结",
        "引用", "文献综述", "论文",
        "write", "draft", "outline", "review",
        "polish", "rewrite", "summarize", "abstract"
    ]
    
    # Skill 触发关键词
    BIBTEX_KEYWORDS = ["bibtex", "引用信息", "doi", "bib", "文献格式"]
    FORMAT_KEYWORDS = ["格式化", "参考文献格式", "引用格式", "apa", "mla", "chicago", "国标"]
    SUMMARY_KEYWORDS = ["摘要", "总结", "概括", "summarize", "abstract", "summary"]
    
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
        
        # Skill 关键词也增加匹配度
        for kw in self.BIBTEX_KEYWORDS + self.FORMAT_KEYWORDS:
            if kw in query_lower:
                score += 0.15
        
        return min(score, 1.0)
    
    async def execute(
        self,
        query: str,
        project_id: Optional[int] = None,
        task_type: str = "auto",
        context: str = "",
        file_path: str = "",
        citation_style: str = "apa",
        **kwargs
    ) -> AgentResponse:
        """
        执行写作任务
        
        增强流程：
        1. 检测是否需要调用 Skill（BibTeX提取、文献格式化、摘要生成）
        2. 执行 Skill 获取辅助数据
        3. 结合 RAG 检索和 LLM 完成写作任务
        """
        skills_used = []
        skill_context = ""
        
        try:
            if task_type == "auto":
                task_type = self._detect_task_type(query)
            
            query_lower = query.lower()
            
            # ---- Skill: BibTeX 提取 ----
            if file_path and any(kw in query_lower for kw in self.BIBTEX_KEYWORDS):
                logger.info(f"[WriterAgent] Extracting BibTeX from: {file_path}")
                bib_result = await self._execute_skill(
                    "get_paper_bibtex", file_path=file_path
                )
                if bib_result.success:
                    bibtex = bib_result.data.get("bibtex", "") if isinstance(bib_result.data, dict) else str(bib_result.data)
                    if bibtex:
                        skill_context += f"\n\n[BibTeX引用信息]:\n{bibtex}"
                    skills_used.append("get_paper_bibtex")
            
            # ---- Skill: BibTeX 解析 ----
            bibtex_content = kwargs.get("bibtex_content", "")
            bibtex_file = kwargs.get("bibtex_file", "")
            if bibtex_content or bibtex_file:
                logger.info("[WriterAgent] Parsing BibTeX data")
                parse_result = await self._execute_skill(
                    "parse_bibtex_entries",
                    bibtex_content=bibtex_content,
                    file_path=bibtex_file,
                )
                if parse_result.success:
                    entries = parse_result.data.get("entries", [])
                    if entries:
                        skill_context += f"\n\n[解析的文献条目({len(entries)}篇)]:\n"
                        for e in entries[:10]:
                            skill_context += (
                                f"- {e.get('title', 'N/A')} "
                                f"({e.get('author', 'Unknown')}, {e.get('year', 'N/A')})\n"
                            )
                    skills_used.append("parse_bibtex_entries")
            
            # ---- Skill: 参考文献格式化 ----
            references_data = kwargs.get("references_data", [])
            if references_data or any(kw in query_lower for kw in self.FORMAT_KEYWORDS):
                if references_data:
                    logger.info(f"[WriterAgent] Formatting {len(references_data)} references")
                    fmt_result = await self._execute_skill(
                        "format_references",
                        references=references_data,
                        style=citation_style,
                    )
                    if fmt_result.success:
                        skill_context += (
                            f"\n\n[格式化参考文献({citation_style}格式)]:\n"
                            f"{fmt_result.data.get('formatted_text', '')}"
                        )
                        skills_used.append("format_references")
            
            # ---- Skill: 文本摘要 ----
            if task_type == "summary" or any(
                kw in query_lower for kw in self.SUMMARY_KEYWORDS
            ):
                text_to_summarize = context or kwargs.get("text", "")
                if text_to_summarize and len(text_to_summarize) > 200:
                    logger.info("[WriterAgent] Generating summary via summarize_with_model")
                    sum_result = await self._execute_skill(
                        "summarize_with_model",
                        text=text_to_summarize,
                        language="auto",
                        focus=kwargs.get("focus", ""),
                    )
                    if sum_result.success:
                        skill_context += (
                            f"\n\n[自动摘要]:\n{sum_result.data.get('summary', '')}"
                        )
                        skills_used.append("summarize_with_model")
            
            # ---- 执行写作任务 ----
            if task_type == "outline":
                result = await self._generate_outline(
                    query, project_id, skill_context=skill_context, **kwargs
                )
            elif task_type == "review":
                result = await self._generate_review(
                    query, project_id, skill_context=skill_context, **kwargs
                )
            elif task_type == "polish":
                result = await self._polish_text(query, context, **kwargs)
            elif task_type == "citation":
                result = await self._suggest_citations(
                    query, project_id, skill_context=skill_context,
                    citation_style=citation_style, **kwargs
                )
            else:
                result = await self._general_writing(
                    query, project_id, skill_context=skill_context, **kwargs
                )
            
            await self._save_to_memory(
                content=f"写作任务({task_type}): {query[:100]}",
                metadata={
                    "project_id": project_id or 0,
                    "task_type": task_type,
                    "skills_used": skills_used,
                },
            )
            
            return AgentResponse(
                agent_type=self.agent_type.value,
                content=result["content"],
                references=result.get("references", []),
                metadata={
                    "task_type": task_type,
                    "skills_used": skills_used,
                },
                confidence=0.85,
            )
            
        except Exception as e:
            logger.error(f"WriterAgent error: {e}")
            return AgentResponse(
                agent_type=self.agent_type.value,
                content=f"写作辅助失败: {str(e)}",
                metadata={"skills_used": skills_used},
                confidence=0.0,
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
        if any(kw in query_lower for kw in self.SUMMARY_KEYWORDS):
            return "summary"
        return "general"
    
    async def _generate_outline(
        self, query: str, project_id: Optional[int],
        skill_context: str = "", **kwargs
    ) -> Dict:
        """生成论文大纲"""
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
{skill_context}

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
    
    async def _generate_review(
        self, query: str, project_id: Optional[int],
        skill_context: str = "", **kwargs
    ) -> Dict:
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
{skill_context}

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
    
    async def _suggest_citations(
        self, query: str, project_id: Optional[int],
        skill_context: str = "", citation_style: str = "apa", **kwargs
    ) -> Dict:
        """建议引用 — 增强版：结合 Skill 格式化输出"""
        refs = []
        if self.rag_engine:
            search_results = await self.rag_engine.search(query, project_id, top_k=10)
            refs = await self.rag_engine._fetch_documents(search_results)
        
        # 如果有文献数据且 format_references Skill 可用，格式化引用
        if refs and self._skill_registry:
            ref_data = []
            for r in refs:
                ref_data.append({
                    "title": r.get("title", "Unknown"),
                    "author": r.get("authors", r.get("author", "Unknown")),
                    "year": r.get("year", "N/A"),
                    "journal": r.get("journal", r.get("venue", "")),
                    "doi": r.get("doi", ""),
                })
            
            fmt_result = await self._execute_skill(
                "format_references",
                references=ref_data,
                style=citation_style,
            )
            
            if fmt_result.success:
                formatted = fmt_result.data.get("formatted_text", "")
                content = (
                    f"基于您的研究主题「{query}」，建议引用以下文献"
                    f"（{citation_style.upper()} 格式）：\n\n{formatted}"
                )
                return {"content": content, "references": refs}
        
        # 降级：简单列表
        citation_list = "\n".join(
            f"- {r.get('title', 'Unknown')} ({r.get('year', 'N/A')}): "
            f"{r.get('text', '')[:100]}..."
            for r in refs
        )
        
        content = f"基于您的研究主题「{query}」，建议引用以下文献：\n\n{citation_list}"
        if skill_context:
            content += f"\n\n{skill_context}"
        return {"content": content, "references": refs}
    
    async def _general_writing(
        self, query: str, project_id: Optional[int],
        skill_context: str = "", **kwargs
    ) -> Dict:
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
{skill_context}

请用学术风格完成写作任务。"""
            
            response = await self._llm.ainvoke(prompt)
            return {"content": response.content, "references": refs}
        
        return {"content": "LLM未初始化"}
