"""
arXiv API 客户端

提供预印本论文搜索和元数据获取。
API文档: https://info.arxiv.org/help/api/
"""
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from loguru import logger

from app.services.external_apis.base import BaseAPIClient


@dataclass
class ArxivPaper:
    """arXiv 论文"""
    arxiv_id: str
    title: str
    abstract: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    published: Optional[str] = None
    updated: Optional[str] = None
    pdf_url: Optional[str] = None
    doi: Optional[str] = None
    comment: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors,
            "categories": self.categories,
            "published": self.published,
            "updated": self.updated,
            "pdf_url": self.pdf_url,
            "doi": self.doi,
            "comment": self.comment,
            "source": "arxiv"
        }


class ArxivClient(BaseAPIClient):
    """arXiv API 客户端"""
    
    BASE_URL = "http://export.arxiv.org/api/query"
    RATE_LIMIT = 1.0  # arXiv限制较严格
    TIMEOUT = 60.0  # arXiv可能较慢
    
    # XML 命名空间
    NS = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
        "opensearch": "http://a9.com/-/spec/opensearch/1.1/"
    }
    
    async def search(
        self,
        query: str,
        limit: int = 10,
        start: int = 0,
        sort_by: str = "relevance",
        sort_order: str = "descending",
        categories: Optional[List[str]] = None
    ) -> List[ArxivPaper]:
        """
        搜索arXiv论文
        
        Args:
            query: 搜索关键词
            limit: 返回数量
            start: 起始位置
            sort_by: 排序方式 (relevance, lastUpdatedDate, submittedDate)
            sort_order: 排序顺序 (ascending, descending)
            categories: 类别过滤
        """
        # 构建搜索查询
        search_query = f"all:{query}"
        if categories:
            cat_query = " OR ".join(f"cat:{c}" for c in categories)
            search_query = f"({search_query}) AND ({cat_query})"
        
        params = {
            "search_query": search_query,
            "start": start,
            "max_results": min(limit, 100),
            "sortBy": sort_by,
            "sortOrder": sort_order
        }
        
        client = await self._get_client()
        await self._rate_limit()
        
        try:
            response = await client.get(self.BASE_URL, params=params)
            if response.status_code != 200:
                logger.error(f"arXiv API error: {response.status_code}")
                return []
            
            return self._parse_response(response.text)
            
        except Exception as e:
            logger.error(f"arXiv search failed: {e}")
            return []
    
    def _parse_response(self, xml_text: str) -> List[ArxivPaper]:
        """解析arXiv XML响应"""
        papers = []
        
        try:
            root = ET.fromstring(xml_text)
            
            for entry in root.findall("atom:entry", self.NS):
                # 提取arXiv ID
                entry_id = entry.findtext("atom:id", "", self.NS)
                arxiv_id = entry_id.split("/abs/")[-1] if "/abs/" in entry_id else entry_id
                
                # 提取标题
                title = entry.findtext("atom:title", "", self.NS).strip()
                title = " ".join(title.split())  # 清理空白
                
                # 提取摘要
                abstract = entry.findtext("atom:summary", "", self.NS).strip()
                abstract = " ".join(abstract.split())
                
                # 提取作者
                authors = []
                for author in entry.findall("atom:author", self.NS):
                    name = author.findtext("atom:name", "", self.NS)
                    if name:
                        authors.append(name)
                
                # 提取分类
                categories = []
                for cat in entry.findall("atom:category", self.NS):
                    term = cat.get("term", "")
                    if term:
                        categories.append(term)
                
                # PDF链接
                pdf_url = None
                for link in entry.findall("atom:link", self.NS):
                    if link.get("title") == "pdf":
                        pdf_url = link.get("href")
                        break
                
                # 日期
                published = entry.findtext("atom:published", "", self.NS)
                updated = entry.findtext("atom:updated", "", self.NS)
                
                # DOI
                doi = entry.findtext("arxiv:doi", None, self.NS)
                
                # 评论
                comment = entry.findtext("arxiv:comment", None, self.NS)
                
                papers.append(ArxivPaper(
                    arxiv_id=arxiv_id,
                    title=title,
                    abstract=abstract,
                    authors=authors,
                    categories=categories,
                    published=published[:10] if published else None,
                    updated=updated[:10] if updated else None,
                    pdf_url=pdf_url,
                    doi=doi,
                    comment=comment
                ))
        
        except ET.ParseError as e:
            logger.error(f"Failed to parse arXiv XML: {e}")
        
        return papers
    
    async def get_paper(self, arxiv_id: str) -> Optional[ArxivPaper]:
        """根据arXiv ID获取论文"""
        papers = await self.search(f"id:{arxiv_id}", limit=1)
        return papers[0] if papers else None


# 全局实例
arxiv_client = ArxivClient()
