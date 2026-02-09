"""
External API - 外部学术API路由
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from loguru import logger

from app.core.deps import get_current_user
from app.models.user import User
from app.services.external_apis.aggregator import search_aggregator
from app.services.external_apis.semantic_scholar import semantic_scholar
from app.services.external_apis.openalex import openalex
from app.services.external_apis.crossref import crossref


router = APIRouter()


# ============ Schemas ============

class ExternalPaperResponse(BaseModel):
    """外部论文响应"""
    title: str
    authors: list
    abstract: Optional[str] = None
    year: Optional[int] = None
    citation_count: int = 0
    doi: Optional[str] = None
    venue: Optional[str] = None
    source: str = ""
    url: Optional[str] = None
    is_open_access: bool = False


class CitationNetworkResponse(BaseModel):
    """引用网络响应"""
    nodes: list
    edges: list
    center_paper_id: str


class ConceptResponse(BaseModel):
    """研究概念响应"""
    id: str
    name: str
    level: int = 0
    works_count: int = 0
    cited_by_count: int = 0
    description: str = ""


# ============ Routes ============

@router.get("/search")
async def search_papers(
    query: str = Query(..., min_length=1, description="搜索关键词"),
    limit: int = Query(10, ge=1, le=50),
    sources: Optional[str] = Query(None, description="搜索源，逗号分隔 (semantic_scholar,openalex,arxiv,crossref)"),
    year: Optional[str] = Query(None, description="年份过滤 (e.g., 2020-2024)"),
    current_user: User = Depends(get_current_user)
):
    """
    跨源论文搜索
    
    聚合Semantic Scholar、OpenAlex、arXiv、CrossRef的搜索结果。
    """
    source_list = sources.split(",") if sources else None
    
    try:
        results = await search_aggregator.search(
            query=query,
            limit=limit,
            sources=source_list,
            year=year
        )
        return {"results": results, "total": len(results), "query": query}
    except Exception as e:
        logger.error(f"External search failed: {e}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


@router.get("/paper/{paper_id}")
async def get_paper_detail(
    paper_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取论文详情 (Semantic Scholar)
    """
    paper = await semantic_scholar.get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="论文未找到")
    return paper.to_dict()


@router.get("/citations/{paper_id}")
async def get_citation_network(
    paper_id: str,
    depth: int = Query(1, ge=1, le=2),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user)
):
    """
    获取论文引用网络
    
    返回节点和边的网络数据，可用于知识图谱可视化。
    """
    try:
        network = await search_aggregator.get_citation_network(
            paper_id=paper_id,
            depth=depth,
            limit=limit
        )
        return network
    except Exception as e:
        logger.error(f"Citation network failed: {e}")
        raise HTTPException(status_code=500, detail=f"获取引用网络失败: {str(e)}")


@router.get("/recommendations/{paper_id}")
async def get_recommendations(
    paper_id: str,
    limit: int = Query(10, ge=1, le=30),
    current_user: User = Depends(get_current_user)
):
    """获取相关论文推荐"""
    try:
        papers = await semantic_scholar.get_recommendations(paper_id, limit=limit)
        return {"results": [p.to_dict() for p in papers]}
    except Exception as e:
        logger.error(f"Recommendations failed: {e}")
        raise HTTPException(status_code=500, detail=f"获取推荐失败: {str(e)}")


@router.get("/doi/{doi:path}")
async def resolve_doi(
    doi: str,
    current_user: User = Depends(get_current_user)
):
    """
    通过DOI获取论文元数据 (CrossRef)
    """
    work = await crossref.resolve_doi(doi)
    if not work:
        raise HTTPException(status_code=404, detail="DOI未找到")
    return work.to_dict()


@router.get("/concepts")
async def get_trending_concepts(
    field: Optional[str] = Query(None, description="研究领域"),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user)
):
    """获取热门研究概念 (OpenAlex)"""
    try:
        concepts = await openalex.get_trending_concepts(field=field, limit=limit)
        return {"results": concepts}
    except Exception as e:
        logger.error(f"Concepts failed: {e}")
        raise HTTPException(status_code=500, detail=f"获取概念失败: {str(e)}")


@router.get("/author/search")
async def search_author(
    query: str = Query(..., min_length=1),
    limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_user)
):
    """搜索作者 (Semantic Scholar)"""
    try:
        authors = await semantic_scholar.search_author(query, limit=limit)
        return {"results": authors}
    except Exception as e:
        logger.error(f"Author search failed: {e}")
        raise HTTPException(status_code=500, detail=f"作者搜索失败: {str(e)}")
