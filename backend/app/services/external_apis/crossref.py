"""
CrossRef API 客户端

提供DOI解析、引用元数据获取。
API文档: https://api.crossref.org/
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from loguru import logger

from app.services.external_apis.base import BaseAPIClient


@dataclass
class CrossRefWork:
    """CrossRef 作品"""
    doi: str
    title: str
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    publisher: Optional[str] = None
    citation_count: int = 0
    reference_count: int = 0
    issn: Optional[str] = None
    url: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "doi": self.doi,
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "journal": self.journal,
            "volume": self.volume,
            "issue": self.issue,
            "pages": self.pages,
            "publisher": self.publisher,
            "citation_count": self.citation_count,
            "reference_count": self.reference_count,
            "url": self.url,
            "source": "crossref"
        }
    
    @classmethod
    def from_api(cls, data: Dict) -> "CrossRefWork":
        # 提取标题
        titles = data.get("title", [])
        title = titles[0] if titles else ""
        
        # 提取作者
        authors = []
        for author in data.get("author", []):
            given = author.get("given", "")
            family = author.get("family", "")
            name = f"{given} {family}".strip()
            if name:
                authors.append(name)
        
        # 提取年份
        year = None
        date_parts = data.get("published-print", data.get("published-online", {}))
        if date_parts and date_parts.get("date-parts"):
            parts = date_parts["date-parts"][0]
            if parts:
                year = parts[0]
        
        # 期刊名
        container = data.get("container-title", [])
        journal = container[0] if container else None
        
        return cls(
            doi=data.get("DOI", ""),
            title=title,
            authors=authors,
            year=year,
            journal=journal,
            volume=data.get("volume"),
            issue=data.get("issue"),
            pages=data.get("page"),
            publisher=data.get("publisher"),
            citation_count=data.get("is-referenced-by-count", 0),
            reference_count=data.get("references-count", 0),
            url=data.get("URL"),
        )


class CrossRefClient(BaseAPIClient):
    """CrossRef API 客户端"""
    
    BASE_URL = "https://api.crossref.org"
    RATE_LIMIT = 10.0
    
    def _default_headers(self) -> Dict[str, str]:
        headers = super()._default_headers()
        headers["User-Agent"] = "LiterAI-Platform/1.0 (mailto:literai@example.com)"
        return headers
    
    async def resolve_doi(self, doi: str) -> Optional[CrossRefWork]:
        """
        解析DOI获取论文元数据
        
        Args:
            doi: DOI标识符
        """
        # 清理DOI
        doi = doi.strip()
        if doi.startswith("https://doi.org/"):
            doi = doi[len("https://doi.org/"):]
        elif doi.startswith("http://dx.doi.org/"):
            doi = doi[len("http://dx.doi.org/"):]
        
        data = await self._request(
            "GET",
            f"{self.BASE_URL}/works/{doi}",
            cache_key=f"cr_doi:{doi}"
        )
        
        if not data or "message" not in data:
            return None
        
        return CrossRefWork.from_api(data["message"])
    
    async def search(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        sort: str = "relevance"
    ) -> List[CrossRefWork]:
        """
        搜索论文
        
        Args:
            query: 搜索关键词
            limit: 返回数量
            offset: 偏移量
            sort: 排序方式 (relevance, published, updated)
        """
        params = {
            "query": query,
            "rows": min(limit, 100),
            "offset": offset,
            "sort": sort,
            "select": "DOI,title,author,published-print,published-online,container-title,volume,issue,page,publisher,is-referenced-by-count,references-count,URL"
        }
        
        data = await self._request(
            "GET",
            f"{self.BASE_URL}/works",
            params=params,
            cache_key=f"cr_search:{query}:{limit}:{offset}"
        )
        
        if not data or "message" not in data:
            return []
        
        items = data["message"].get("items", [])
        return [CrossRefWork.from_api(item) for item in items]
    
    async def get_references(self, doi: str) -> List[Dict]:
        """获取论文的参考文献"""
        data = await self._request(
            "GET",
            f"{self.BASE_URL}/works/{doi}",
            cache_key=f"cr_refs:{doi}"
        )
        
        if not data or "message" not in data:
            return []
        
        references = data["message"].get("reference", [])
        return [
            {
                "doi": ref.get("DOI"),
                "title": ref.get("article-title") or ref.get("volume-title", ""),
                "author": ref.get("author", ""),
                "year": ref.get("year"),
                "journal": ref.get("journal-title", ""),
            }
            for ref in references
        ]


# 全局实例
crossref = CrossRefClient()
