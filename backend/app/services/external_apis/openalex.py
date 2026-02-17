"""
OpenAlex API 客户端

提供开放学术数据访问：论文、作者、机构、概念等。
API文档: https://docs.openalex.org/
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from loguru import logger

from app.services.external_apis.base import BaseAPIClient


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


@dataclass
class OpenAlexWork:
    """OpenAlex 学术作品"""
    work_id: str
    title: str
    abstract: Optional[str] = None
    year: Optional[int] = None
    citation_count: int = 0
    authors: List[Dict[str, str]] = field(default_factory=list)
    doi: Optional[str] = None
    venue: Optional[str] = None
    concepts: List[Dict[str, Any]] = field(default_factory=list)
    is_open_access: bool = False
    pdf_url: Optional[str] = None
    
    @classmethod
    def from_api(cls, data: Dict) -> "OpenAlexWork":
        data = _safe_dict(data)

        # 重建abstract
        abstract = None
        inverted_index = data.get("abstract_inverted_index")
        if isinstance(inverted_index, dict) and inverted_index:
            try:
                # 将倒排索引转为普通文本
                word_positions = []
                for word, positions in inverted_index.items():
                    if not isinstance(word, str):
                        continue
                    for pos in _safe_list(positions):
                        if isinstance(pos, int):
                            word_positions.append((pos, word))
                word_positions.sort()
                abstract = " ".join(w for _, w in word_positions)
            except Exception:
                pass
        
        authors = []
        for authorship in _safe_list(data.get("authorships")):
            authorship = _safe_dict(authorship)
            author = _safe_dict(authorship.get("author"))
            institution = ""
            institutions = _safe_list(authorship.get("institutions"))
            if institutions:
                institution = _safe_dict(institutions[0]).get("display_name", "")
            authors.append({
                "name": author.get("display_name", ""),
                "id": author.get("id", ""),
                "institution": institution
            })
        
        concepts = []
        for c in _safe_list(data.get("concepts")):
            c = _safe_dict(c)
            concepts.append(
                {
                    "name": c.get("display_name", ""),
                    "level": c.get("level", 0),
                    "score": c.get("score", 0),
                }
            )
        
        oa_info = _safe_dict(data.get("open_access"))
        primary_location = _safe_dict(data.get("primary_location"))
        source_info = _safe_dict(primary_location.get("source"))
        
        return cls(
            work_id=data.get("id", ""),
            title=data.get("title", ""),
            abstract=abstract,
            year=data.get("publication_year"),
            citation_count=data.get("cited_by_count", 0),
            authors=authors,
            doi=data.get("doi"),
            venue=source_info.get("display_name"),
            concepts=concepts,
            is_open_access=oa_info.get("is_oa", False),
            pdf_url=oa_info.get("oa_url"),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "work_id": self.work_id,
            "title": self.title,
            "abstract": self.abstract,
            "year": self.year,
            "citation_count": self.citation_count,
            "authors": self.authors,
            "doi": self.doi,
            "venue": self.venue,
            "concepts": self.concepts,
            "is_open_access": self.is_open_access,
            "pdf_url": self.pdf_url,
            "source": "openalex"
        }


class OpenAlexClient(BaseAPIClient):
    """OpenAlex API 客户端"""
    
    BASE_URL = "https://api.openalex.org"
    RATE_LIMIT = 10.0
    
    def _default_headers(self) -> Dict[str, str]:
        headers = super()._default_headers()
        headers["mailto"] = "literai@example.com"  # Polite pool
        return headers
    
    async def search_works(
        self,
        query: str,
        limit: int = 10,
        page: int = 1,
        sort: str = "relevance_score:desc",
        year: Optional[str] = None,
        concepts: Optional[List[str]] = None
    ) -> List[OpenAlexWork]:
        """
        搜索学术作品
        
        Args:
            query: 搜索关键词
            limit: 返回数量
            page: 页码
            sort: 排序方式 (relevance_score:desc, cited_by_count:desc, publication_date:desc)
            year: 年份过滤
            concepts: 概念过滤
        """
        # OpenAlex 要求排序字段带方向后缀，默认降序
        sort_param = sort if ":" in sort else f"{sort}:desc"
        params = {
            "search": query,
            "per_page": min(limit, 200),
            "page": page,
            "sort": sort_param
        }
        
        filters = []
        if year:
            filters.append(f"publication_year:{year}")
        if concepts:
            for concept in concepts:
                filters.append(f"concepts.display_name.search:{concept}")
        if filters:
            params["filter"] = ",".join(filters)
        
        cache_key = f"oa_search:{query}:{limit}:{page}:{year}"
        data = await self._request(
            "GET",
            f"{self.BASE_URL}/works",
            params=params,
            cache_key=cache_key
        )
        
        if not data or "results" not in data:
            return []

        works: List[OpenAlexWork] = []
        for w in _safe_list(data.get("results")):
            if not isinstance(w, dict):
                continue
            try:
                works.append(OpenAlexWork.from_api(w))
            except Exception as e:
                logger.warning(f"OpenAlex work parse skipped: {e}")
        return works
    
    async def get_work(self, work_id: str) -> Optional[OpenAlexWork]:
        """获取作品详情"""
        data = await self._request(
            "GET",
            f"{self.BASE_URL}/works/{work_id}",
            cache_key=f"oa_work:{work_id}"
        )
        
        if not data:
            return None
        
        return OpenAlexWork.from_api(_safe_dict(data))
    
    async def get_trending_concepts(
        self,
        field: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """获取热门研究概念"""
        params = {
            "per_page": limit,
            "sort": "works_count:desc"
        }
        
        if field:
            params["filter"] = f"display_name.search:{field}"
        
        data = await self._request(
            "GET",
            f"{self.BASE_URL}/concepts",
            params=params,
            cache_key=f"oa_concepts:{field}:{limit}"
        )
        
        if not data or "results" not in data:
            return []
        
        return [
            {
                "id": c.get("id", ""),
                "name": c.get("display_name", ""),
                "level": c.get("level", 0),
                "works_count": c.get("works_count", 0),
                "cited_by_count": c.get("cited_by_count", 0),
                "description": c.get("description", ""),
            }
            for c in data["results"]
        ]
    
    async def get_works_by_concept(
        self,
        concept_id: str,
        limit: int = 10,
        sort: str = "cited_by_count:desc"
    ) -> List[OpenAlexWork]:
        """根据概念获取相关作品"""
        params = {
            "filter": f"concepts.id:{concept_id}",
            "per_page": limit,
            "sort": sort
        }
        
        data = await self._request(
            "GET",
            f"{self.BASE_URL}/works",
            params=params,
            cache_key=f"oa_concept_works:{concept_id}:{limit}"
        )
        
        if not data or "results" not in data:
            return []
        
        works: List[OpenAlexWork] = []
        for w in _safe_list(data.get("results")):
            if not isinstance(w, dict):
                continue
            try:
                works.append(OpenAlexWork.from_api(w))
            except Exception as e:
                logger.warning(f"OpenAlex concept work parse skipped: {e}")
        return works
    
    async def get_author(self, author_id: str) -> Optional[Dict]:
        """获取作者信息"""
        data = await self._request(
            "GET",
            f"{self.BASE_URL}/authors/{author_id}",
            cache_key=f"oa_author:{author_id}"
        )
        
        if not data:
            return None
        
        summary_stats = _safe_dict(data.get("summary_stats"))
        return {
            "id": data.get("id", ""),
            "name": data.get("display_name", ""),
            "works_count": data.get("works_count", 0),
            "cited_by_count": data.get("cited_by_count", 0),
            "h_index": summary_stats.get("h_index", 0),
            "affiliations": [
                _safe_dict(inst).get("display_name", "")
                for inst in _safe_list(data.get("affiliations"))
            ],
        }


# 全局实例
openalex = OpenAlexClient()
