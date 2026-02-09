"""
Search Agent - 外部搜索Agent

负责调用外部学术API（Semantic Scholar、OpenAlex、arXiv、CrossRef）。
集成 Skills:
- search_and_scrape_papers（在线论文搜索与抓取，作为外部API的补充来源）
"""
from typing import Optional, List, Dict, Any
from loguru import logger

from app.agents.base_agent import BaseAgent, AgentType, AgentResponse
from app.services.external_apis.aggregator import search_aggregator


class SearchAgent(BaseAgent):
    """
    外部搜索Agent
    
    核心功能：
    1. 跨源学术论文搜索
    2. 引用网络获取
    3. 论文推荐
    4. DOI解析
    5. [Skill] 在线论文搜索与抓取（search_and_scrape_papers，补充来源）
    """
    
    agent_type = AgentType.SEARCH
    description = "外部学术API搜索Agent"
    _skill_categories = ["academic"]  # 可使用学术类 Skills
    
    TRIGGER_KEYWORDS = [
        "最新", "最近", "前沿", "外部", "在线",
        "Semantic Scholar", "arXiv", "OpenAlex",
        "引用网络", "相关论文", "推荐",
        "search online", "latest", "recent", "state-of-the-art",
        "arxiv上", "谷歌学术", "学术搜索",
        "有哪些论文", "有哪些研究"
    ]
    
    # Skill 触发关键词
    SCRAPE_KEYWORDS = [
        "抓取", "爬取", "下载论文", "scrape", "crawl",
        "pubmed", "全文获取"
    ]
    
    def __init__(self, aggregator=None):
        super().__init__()
        self.aggregator = aggregator or search_aggregator
    
    def can_handle(self, query: str) -> float:
        query_lower = query.lower()
        score = 0.1
        
        for keyword in self.TRIGGER_KEYWORDS:
            if keyword.lower() in query_lower:
                score += 0.2
        
        # Skill 关键词也增加匹配度
        for kw in self.SCRAPE_KEYWORDS:
            if kw in query_lower:
                score += 0.15
        
        return min(score, 1.0)
    
    async def execute(
        self,
        query: str,
        project_id: Optional[int] = None,
        search_type: str = "auto",
        sources: Optional[List[str]] = None,
        limit: int = 10,
        use_scraper: bool = False,
        **kwargs
    ) -> AgentResponse:
        """
        执行外部搜索
        
        增强流程：
        1. 使用现有 aggregator 搜索多个学术 API
        2. 如果用户需要额外来源或 aggregator 结果不足，
           调用 scrape_papers Skill 补充来源
        3. 合并去重后返回结果
        """
        skills_used = []
        
        try:
            if search_type == "auto":
                search_type = self._detect_search_type(query)
            
            query_lower = query.lower()
            
            if search_type == "paper_search":
                result = await self._search_papers(query, sources, limit)
                
                # ---- Skill: 补充论文抓取 ----
                should_scrape = (
                    use_scraper
                    or any(kw in query_lower for kw in self.SCRAPE_KEYWORDS)
                    or len(result.get("papers", [])) < 3  # 结果不足时自动补充
                )
                
                if should_scrape and self._skill_registry:
                    logger.info("[SearchAgent] Supplementing with scrape_papers skill")
                    scrape_sources = ["arxiv"]
                    if "pubmed" in query_lower:
                        scrape_sources.append("pubmed")
                    
                    scrape_result = await self._execute_skill(
                        "search_and_scrape_papers",
                        query=query,
                        limit=min(limit, 5),
                    )
                    
                    if scrape_result.success:
                        scraped_papers = scrape_result.data.get("papers", [])
                        if scraped_papers:
                            # 合并并去重（基于标题）
                            existing_titles = {
                                p.get("title", "").lower()
                                for p in result.get("papers", [])
                            }
                            new_papers = []
                            for sp in scraped_papers:
                                if sp.get("title", "").lower() not in existing_titles:
                                    new_papers.append(sp)
                                    existing_titles.add(sp.get("title", "").lower())
                            
                            result["papers"].extend(new_papers)
                            result["total"] = len(result["papers"])
                            
                            if new_papers:
                                result["summary"] += (
                                    f"\n\n通过 Skill 补充抓取到 "
                                    f"{len(new_papers)} 篇额外论文"
                                )
                            skills_used.append("search_and_scrape_papers")
                
            elif search_type == "citation_network":
                paper_id = kwargs.get("paper_id", "")
                result = await self._get_citation_network(paper_id)
            elif search_type == "recommendation":
                paper_id = kwargs.get("paper_id", "")
                result = await self._get_recommendations(paper_id, limit)
            else:
                result = await self._search_papers(query, sources, limit)
            
            # 保存搜索记忆
            await self._save_to_memory(
                content=f"外部搜索: {query}\n找到{len(result.get('papers', []))}篇论文",
                metadata={
                    "project_id": project_id or 0,
                    "search_type": search_type,
                    "skills_used": skills_used,
                },
            )
            
            # 共享搜索结果给其他Agent
            await self._share_memory(
                content=f"搜索结果({query}): {result.get('summary', '')}",
                target_agents=["retriever_agent", "analyzer_agent"],
            )
            
            return AgentResponse(
                agent_type=self.agent_type.value,
                content=result["summary"],
                references=result.get("papers", []),
                metadata={
                    "search_type": search_type,
                    "total": result.get("total", 0),
                    "skills_used": skills_used,
                },
                confidence=0.8,
            )
            
        except Exception as e:
            logger.error(f"SearchAgent error: {e}")
            return AgentResponse(
                agent_type=self.agent_type.value,
                content=f"搜索失败: {str(e)}",
                metadata={"skills_used": skills_used},
                confidence=0.0,
            )
    
    def _detect_search_type(self, query: str) -> str:
        query_lower = query.lower()
        if any(kw in query_lower for kw in ["引用", "citation", "cited"]):
            return "citation_network"
        if any(kw in query_lower for kw in ["推荐", "相关", "recommend", "similar"]):
            return "recommendation"
        return "paper_search"
    
    async def _search_papers(
        self, query: str, sources: Optional[List[str]], limit: int
    ) -> Dict[str, Any]:
        """搜索论文"""
        papers = await self.aggregator.search(
            query=query, limit=limit, sources=sources
        )
        
        # 构建摘要
        if papers:
            paper_list = "\n".join(
                f"- {p.get('title', 'Unknown')} ({p.get('year', 'N/A')}, "
                f"引用: {p.get('citation_count', 0)}) [{p.get('source', '')}]"
                for p in papers[:5]
            )
            summary = f"找到{len(papers)}篇相关论文，其中前5篇：\n\n{paper_list}"
        else:
            summary = "未找到相关论文"
        
        return {"summary": summary, "papers": papers, "total": len(papers)}
    
    async def _get_citation_network(self, paper_id: str) -> Dict[str, Any]:
        """获取引用网络"""
        if not paper_id:
            return {"summary": "请提供论文ID", "papers": [], "total": 0}
        
        network = await self.aggregator.get_citation_network(paper_id)
        node_count = len(network.get("nodes", []))
        edge_count = len(network.get("edges", []))
        
        return {
            "summary": f"引用网络: {node_count}个节点, {edge_count}条边",
            "papers": network.get("nodes", []),
            "network": network,
            "total": node_count,
        }
    
    async def _get_recommendations(self, paper_id: str, limit: int) -> Dict[str, Any]:
        """获取推荐"""
        if not paper_id:
            return {"summary": "请提供论文ID获取推荐", "papers": [], "total": 0}
        
        from app.services.external_apis.semantic_scholar import semantic_scholar
        papers = await semantic_scholar.get_recommendations(paper_id, limit=limit)
        paper_dicts = [p.to_dict() for p in papers]
        
        return {
            "summary": f"推荐了{len(paper_dicts)}篇相关论文",
            "papers": paper_dicts,
            "total": len(paper_dicts),
        }
