"""
学术搜索聚合器

将多个外部API的搜索结果聚合、去重、排序。
"""
import asyncio
from typing import List, Dict, Any, Optional
from loguru import logger

from app.services.external_apis.semantic_scholar import SemanticScholarClient, semantic_scholar
from app.services.external_apis.openalex import OpenAlexClient, openalex
from app.services.external_apis.arxiv_client import ArxivClient, arxiv_client
from app.services.external_apis.crossref import CrossRefClient, crossref


class AcademicSearchAggregator:
    """学术搜索聚合器"""
    
    def __init__(
        self,
        s2_client: Optional[SemanticScholarClient] = None,
        oa_client: Optional[OpenAlexClient] = None,
        arxiv: Optional[ArxivClient] = None,
        cr_client: Optional[CrossRefClient] = None
    ):
        self.s2 = s2_client or semantic_scholar
        self.oa = oa_client or openalex
        self.arxiv = arxiv or arxiv_client
        self.cr = cr_client or crossref
    
    async def search(
        self,
        query: str,
        limit: int = 10,
        sources: Optional[List[str]] = None,
        year: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        跨源聚合搜索
        
        Args:
            query: 搜索关键词
            limit: 每个源的最大返回数
            sources: 指定搜索源 (semantic_scholar, openalex, arxiv, crossref)
            year: 年份过滤
            
        Returns:
            聚合后的论文列表
        """
        if sources is None:
            sources = ["semantic_scholar", "openalex", "arxiv"]
        
        # 并行搜索
        tasks = []
        
        if "semantic_scholar" in sources:
            tasks.append(self._search_s2(query, limit, year))
        if "openalex" in sources:
            tasks.append(self._search_oa(query, limit, year))
        if "arxiv" in sources:
            tasks.append(self._search_arxiv(query, limit))
        if "crossref" in sources:
            tasks.append(self._search_cr(query, limit))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 合并结果
        all_papers = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Search source failed: {result}")
                continue
            all_papers.extend(result)
        
        # 去重 (基于DOI或标题)
        deduplicated = self._deduplicate(all_papers)
        
        # 排序 (引用数 > 年份)
        deduplicated.sort(
            key=lambda p: (p.get("citation_count", 0), p.get("year", 0)),
            reverse=True
        )
        
        return deduplicated[:limit * 2]  # 返回合理数量
    
    async def _search_s2(self, query: str, limit: int, year: Optional[str]) -> List[Dict]:
        """Semantic Scholar 搜索"""
        try:
            papers = await self.s2.search_papers(query, limit=limit, year=year)
            return [p.to_dict() for p in papers]
        except Exception as e:
            logger.warning(f"Semantic Scholar search failed: {e}")
            return []
    
    async def _search_oa(self, query: str, limit: int, year: Optional[str]) -> List[Dict]:
        """OpenAlex 搜索"""
        try:
            works = await self.oa.search_works(query, limit=limit, year=year)
            return [w.to_dict() for w in works]
        except Exception as e:
            logger.warning(f"OpenAlex search failed: {e}")
            return []
    
    async def _search_arxiv(self, query: str, limit: int) -> List[Dict]:
        """arXiv 搜索"""
        try:
            papers = await self.arxiv.search(query, limit=limit)
            return [p.to_dict() for p in papers]
        except Exception as e:
            logger.warning(f"arXiv search failed: {e}")
            return []
    
    async def _search_cr(self, query: str, limit: int) -> List[Dict]:
        """CrossRef 搜索"""
        try:
            works = await self.cr.search(query, limit=limit)
            return [w.to_dict() for w in works]
        except Exception as e:
            logger.warning(f"CrossRef search failed: {e}")
            return []
    
    def _deduplicate(self, papers: List[Dict]) -> List[Dict]:
        """基于DOI和标题去重"""
        seen_dois = set()
        seen_titles = set()
        unique = []
        
        for paper in papers:
            doi = paper.get("doi")
            title = (paper.get("title") or "").lower().strip()
            
            if doi and doi in seen_dois:
                continue
            if title and title in seen_titles:
                continue
            
            if doi:
                seen_dois.add(doi)
            if title:
                seen_titles.add(title)
            
            unique.append(paper)
        
        return unique
    
    async def get_citation_network(
        self,
        paper_id: str,
        depth: int = 1,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        获取论文引用网络
        
        Args:
            paper_id: Semantic Scholar paper ID
            depth: 网络深度 (1或2)
            limit: 每层的最大节点数
            
        Returns:
            节点和边的网络数据
        """
        nodes = []
        edges = []
        visited = set()
        
        async def fetch_level(pid: str, current_depth: int):
            if pid in visited or current_depth > depth:
                return
            visited.add(pid)
            
            # 获取论文信息
            paper = await self.s2.get_paper(pid)
            if not paper:
                return
            
            nodes.append({
                "id": paper.paper_id,
                "title": paper.title,
                "year": paper.year,
                "citation_count": paper.citation_count,
                "type": "center" if current_depth == 0 else "cited"
            })
            
            # 获取引用
            citations = await self.s2.get_citations(pid, limit=limit)
            for cited_paper in citations:
                if cited_paper.paper_id not in visited:
                    nodes.append({
                        "id": cited_paper.paper_id,
                        "title": cited_paper.title,
                        "year": cited_paper.year,
                        "citation_count": cited_paper.citation_count,
                        "type": "citing"
                    })
                    edges.append({
                        "source": cited_paper.paper_id,
                        "target": pid,
                        "type": "cites"
                    })
                    
                    if current_depth + 1 <= depth:
                        await fetch_level(cited_paper.paper_id, current_depth + 1)
            
            # 获取参考文献
            references = await self.s2.get_references(pid, limit=limit)
            for ref_paper in references:
                if ref_paper.paper_id not in visited:
                    nodes.append({
                        "id": ref_paper.paper_id,
                        "title": ref_paper.title,
                        "year": ref_paper.year,
                        "citation_count": ref_paper.citation_count,
                        "type": "referenced"
                    })
                    edges.append({
                        "source": pid,
                        "target": ref_paper.paper_id,
                        "type": "references"
                    })
        
        await fetch_level(paper_id, 0)
        
        return {
            "nodes": nodes,
            "edges": edges,
            "center_paper_id": paper_id
        }


# 全局实例
search_aggregator = AcademicSearchAggregator()
