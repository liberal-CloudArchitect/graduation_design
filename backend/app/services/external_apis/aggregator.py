"""
学术搜索聚合器

将多个外部API的搜索结果聚合、去重、排序。
"""
import asyncio
import math
import re
from typing import List, Dict, Any, Optional
from loguru import logger

from app.services.external_apis.semantic_scholar import SemanticScholarClient, semantic_scholar
from app.services.external_apis.openalex import OpenAlexClient, openalex
from app.services.external_apis.arxiv_client import ArxivClient, arxiv_client
from app.services.external_apis.crossref import CrossRefClient, crossref


class AcademicSearchAggregator:
    """学术搜索聚合器"""
    TOKEN_PATTERN = re.compile(r"[a-z0-9]{2,}|[\u4e00-\u9fff]{2,}", re.IGNORECASE)
    EN_STOPWORDS = {
        "the", "and", "for", "with", "from", "into", "that", "this", "those",
        "these", "what", "which", "when", "where", "how", "why", "about",
        "over", "under", "between", "using", "based", "than", "into", "their",
        "your", "our", "are", "is", "was", "were", "been", "being",
    }
    CN_STOPWORDS = {
        "什么", "哪些", "如何", "以及", "关于", "相关", "研究", "方法",
        "进行", "一个", "可以", "主要", "论文", "文献", "分析", "对比",
        "比较", "综合", "总结", "归纳", "给出", "请问", "方面",
    }
    AI_CONTEXT_TERMS = {
        "rag", "llm", "agentic", "retrieval", "generation", "prompt",
        "大模型", "检索增强", "生成式", "智能体", "学术", "文献",
    }
    BIOMED_RAG_NOISE_TERMS = {
        "rag-1", "rag-2", "vdj", "v(d)j", "lymphocyte", "immunoglobulin",
        "mtorc1", "t cell", "b cell", "recombination", "gene", "mice",
    }
    
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
        normalized_query = self._rewrite_query(query)
        if sources is None:
            sources = ["semantic_scholar", "openalex", "arxiv"]

        # 并行搜索
        tasks = []

        if "semantic_scholar" in sources:
            tasks.append(self._search_s2(normalized_query, limit, year))
        if "openalex" in sources:
            tasks.append(self._search_oa(normalized_query, limit, year))
        if "arxiv" in sources:
            tasks.append(self._search_arxiv(normalized_query, limit))
        if "crossref" in sources:
            tasks.append(self._search_cr(normalized_query, limit))
        
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

        ranked = self._rank_and_filter(query, deduplicated)
        if ranked:
            return ranked[:limit * 2]  # 返回合理数量

        # 回退：保留原有排序策略，避免全过滤导致无结果
        deduplicated.sort(
            key=lambda p: (p.get("citation_count", 0), p.get("year", 0)),
            reverse=True,
        )
        return deduplicated[:limit * 2]
    
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

    def _rewrite_query(self, query: str) -> str:
        """对学术搜索查询做轻量改写，提升召回与语义聚焦。"""
        q = (query or "").strip()
        if not q:
            return q
        lower = q.lower()

        expansions: List[str] = []
        if re.search(r"\brag\b", lower):
            expansions.append("retrieval augmented generation")
            expansions.append("large language model")
        if "agentic" in lower and "rag" in lower:
            expansions.append("autonomous agents planning tool use")
        if "综述" in q or "survey" in lower:
            expansions.append("survey review")

        if expansions:
            q = f"{q} {' '.join(expansions)}"
        return q

    def _tokenize(self, text: str) -> set:
        if not text:
            return set()
        tokens = set()
        for raw in self.TOKEN_PATTERN.findall(text.lower()):
            tok = raw.strip()
            if len(tok) <= 1:
                continue
            if tok in self.EN_STOPWORDS or tok in self.CN_STOPWORDS:
                continue
            tokens.add(tok)
        return tokens

    def _is_ai_query_context(self, query: str, query_tokens: set) -> bool:
        lower = (query or "").lower()
        return any(term in lower for term in self.AI_CONTEXT_TERMS) or bool(
            query_tokens & self.AI_CONTEXT_TERMS
        )

    def _is_biomed_rag_noise(self, paper: Dict[str, Any], ai_context: bool) -> bool:
        if not ai_context:
            return False
        title = str(paper.get("title", "") or "").lower()
        abstract = str(
            paper.get("abstract", "") or paper.get("summary", "") or paper.get("tldr", "") or ""
        ).lower()
        combined = f"{title} {abstract}"
        noise_hits = sum(1 for term in self.BIOMED_RAG_NOISE_TERMS if term in combined)
        return noise_hits >= 2

    def _paper_relevance_score(self, query_tokens: set, paper: Dict[str, Any]) -> float:
        title = str(paper.get("title", "") or "")
        abstract = str(
            paper.get("abstract", "") or paper.get("summary", "") or paper.get("tldr", "") or ""
        )
        title_tokens = self._tokenize(title)
        abs_tokens = self._tokenize(abstract)

        if query_tokens:
            title_overlap = len(query_tokens & title_tokens) / len(query_tokens)
            abs_overlap = len(query_tokens & abs_tokens) / len(query_tokens)
        else:
            title_overlap = 0.0
            abs_overlap = 0.0

        combined_text = f"{title} {abstract}".lower()
        phrase_boost = 0.0
        if "retrieval augmented generation" in combined_text:
            phrase_boost += 0.08
        if "agentic rag" in combined_text or "agentic retrieval augmented generation" in combined_text:
            phrase_boost += 0.08

        citations = max(0, int(paper.get("citation_count", 0) or 0))
        citation_boost = min(math.log1p(citations) / 20.0, 0.15)
        year = int(paper.get("year", 0) or 0)
        recency_boost = 0.05 if year >= 2021 else 0.0
        abstract_boost = 0.03 if abstract else 0.0

        score = (
            title_overlap * 0.55
            + abs_overlap * 0.28
            + phrase_boost
            + citation_boost
            + recency_boost
            + abstract_boost
        )
        return max(0.0, min(1.0, score))

    def _rank_and_filter(self, query: str, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        query_tokens = self._tokenize(query)
        ai_context = self._is_ai_query_context(query, query_tokens)
        scored: List[Dict[str, Any]] = []

        for p in papers:
            if not isinstance(p, dict):
                continue
            if self._is_biomed_rag_noise(p, ai_context):
                continue

            rel = self._paper_relevance_score(query_tokens, p)
            min_relevance = 0.06 if query_tokens else 0.0
            if rel < min_relevance:
                continue

            enriched = dict(p)
            enriched["external_relevance_score"] = round(rel, 6)
            scored.append(enriched)

        scored.sort(
            key=lambda p: (
                float(p.get("external_relevance_score", 0.0)),
                int(p.get("citation_count", 0) or 0),
                int(p.get("year", 0) or 0),
            ),
            reverse=True,
        )
        return scored
    
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
