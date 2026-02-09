"""
外部学术API集成

提供统一的接口访问多个学术数据源：
- Semantic Scholar
- OpenAlex
- arXiv
- CrossRef
"""
from app.services.external_apis.semantic_scholar import SemanticScholarClient
from app.services.external_apis.openalex import OpenAlexClient
from app.services.external_apis.arxiv_client import ArxivClient
from app.services.external_apis.crossref import CrossRefClient
from app.services.external_apis.aggregator import AcademicSearchAggregator

__all__ = [
    "SemanticScholarClient",
    "OpenAlexClient", 
    "ArxivClient",
    "CrossRefClient",
    "AcademicSearchAggregator",
]
