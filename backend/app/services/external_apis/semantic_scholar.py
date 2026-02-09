"""
Semantic Scholar API 客户端

提供论文搜索、引用网络、作者信息等功能。
API文档: https://api.semanticscholar.org/
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from loguru import logger

from app.services.external_apis.base import BaseAPIClient


@dataclass
class S2Paper:
    """Semantic Scholar 论文"""
    paper_id: str
    title: str
    abstract: Optional[str] = None
    year: Optional[int] = None
    citation_count: int = 0
    reference_count: int = 0
    authors: List[Dict[str, str]] = field(default_factory=list)
    venue: Optional[str] = None
    url: Optional[str] = None
    doi: Optional[str] = None
    fields_of_study: List[str] = field(default_factory=list)
    tldr: Optional[str] = None
    is_open_access: bool = False
    
    @classmethod
    def from_api(cls, data: Dict) -> "S2Paper":
        return cls(
            paper_id=data.get("paperId", ""),
            title=data.get("title", ""),
            abstract=data.get("abstract"),
            year=data.get("year"),
            citation_count=data.get("citationCount", 0),
            reference_count=data.get("referenceCount", 0),
            authors=[
                {"name": a.get("name", ""), "authorId": a.get("authorId", "")}
                for a in data.get("authors", [])
            ],
            venue=data.get("venue"),
            url=data.get("url"),
            doi=data.get("externalIds", {}).get("DOI") if data.get("externalIds") else None,
            fields_of_study=data.get("fieldsOfStudy") or [],
            tldr=data.get("tldr", {}).get("text") if data.get("tldr") else None,
            is_open_access=data.get("isOpenAccess", False),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "abstract": self.abstract,
            "year": self.year,
            "citation_count": self.citation_count,
            "reference_count": self.reference_count,
            "authors": self.authors,
            "venue": self.venue,
            "url": self.url,
            "doi": self.doi,
            "fields_of_study": self.fields_of_study,
            "tldr": self.tldr,
            "is_open_access": self.is_open_access,
            "source": "semantic_scholar"
        }


class SemanticScholarClient(BaseAPIClient):
    """Semantic Scholar API 客户端"""
    
    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    RATE_LIMIT = 10.0  # 10 requests/s (free tier)
    
    # 常用字段
    PAPER_FIELDS = "paperId,title,abstract,year,citationCount,referenceCount,authors,venue,url,externalIds,fieldsOfStudy,tldr,isOpenAccess"
    CITATION_FIELDS = "paperId,title,abstract,year,citationCount,authors,venue,url"
    
    async def search_papers(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        year: Optional[str] = None,
        fields_of_study: Optional[List[str]] = None
    ) -> List[S2Paper]:
        """
        搜索论文
        
        Args:
            query: 搜索关键词
            limit: 返回数量
            offset: 偏移量
            year: 年份过滤 (e.g., "2020-2024")
            fields_of_study: 领域过滤
        """
        params = {
            "query": query,
            "limit": min(limit, 100),
            "offset": offset,
            "fields": self.PAPER_FIELDS
        }
        
        if year:
            params["year"] = year
        if fields_of_study:
            params["fieldsOfStudy"] = ",".join(fields_of_study)
        
        cache_key = f"s2_search:{query}:{limit}:{offset}:{year}"
        data = await self._request(
            "GET",
            f"{self.BASE_URL}/paper/search",
            params=params,
            cache_key=cache_key
        )
        
        if not data or "data" not in data:
            return []
        
        return [S2Paper.from_api(p) for p in data["data"]]
    
    async def get_paper(self, paper_id: str) -> Optional[S2Paper]:
        """
        获取论文详情
        
        Args:
            paper_id: Semantic Scholar paper ID, DOI, ArXiv ID etc.
        """
        data = await self._request(
            "GET",
            f"{self.BASE_URL}/paper/{paper_id}",
            params={"fields": self.PAPER_FIELDS},
            cache_key=f"s2_paper:{paper_id}"
        )
        
        if not data:
            return None
        
        return S2Paper.from_api(data)
    
    async def get_citations(
        self, paper_id: str, limit: int = 50, offset: int = 0
    ) -> List[S2Paper]:
        """获取引用该论文的论文列表"""
        data = await self._request(
            "GET",
            f"{self.BASE_URL}/paper/{paper_id}/citations",
            params={
                "fields": self.CITATION_FIELDS,
                "limit": min(limit, 1000),
                "offset": offset
            },
            cache_key=f"s2_citations:{paper_id}:{limit}:{offset}"
        )
        
        if not data or "data" not in data:
            return []
        
        return [
            S2Paper.from_api(item["citingPaper"])
            for item in data["data"]
            if item.get("citingPaper")
        ]
    
    async def get_references(
        self, paper_id: str, limit: int = 50, offset: int = 0
    ) -> List[S2Paper]:
        """获取该论文引用的论文列表"""
        data = await self._request(
            "GET",
            f"{self.BASE_URL}/paper/{paper_id}/references",
            params={
                "fields": self.CITATION_FIELDS,
                "limit": min(limit, 1000),
                "offset": offset
            },
            cache_key=f"s2_references:{paper_id}:{limit}:{offset}"
        )
        
        if not data or "data" not in data:
            return []
        
        return [
            S2Paper.from_api(item["citedPaper"])
            for item in data["data"]
            if item.get("citedPaper")
        ]
    
    async def get_recommendations(
        self, paper_id: str, limit: int = 10
    ) -> List[S2Paper]:
        """获取相关论文推荐"""
        data = await self._request(
            "GET",
            f"https://api.semanticscholar.org/recommendations/v1/papers/forpaper/{paper_id}",
            params={"fields": self.PAPER_FIELDS, "limit": limit},
            cache_key=f"s2_recommend:{paper_id}:{limit}"
        )
        
        if not data or "recommendedPapers" not in data:
            return []
        
        return [S2Paper.from_api(p) for p in data["recommendedPapers"]]
    
    async def search_author(self, query: str, limit: int = 5) -> List[Dict]:
        """搜索作者"""
        data = await self._request(
            "GET",
            f"{self.BASE_URL}/author/search",
            params={
                "query": query,
                "limit": limit,
                "fields": "name,affiliations,paperCount,citationCount,hIndex"
            },
            cache_key=f"s2_author:{query}:{limit}"
        )
        
        if not data or "data" not in data:
            return []
        
        return data["data"]


# 全局实例
semantic_scholar = SemanticScholarClient()
