"""
Trends API - 趋势分析路由
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.services.trend_analyzer import trend_analyzer


router = APIRouter()


@router.get("/keywords")
async def get_keyword_frequency(
    project_id: Optional[int] = Query(None, description="项目ID"),
    limit: int = Query(50, ge=1, le=200),
    source: str = Query("metadata", description="来源: metadata(关键词字段) 或 text(全文提取)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取关键词频率统计
    
    - source=metadata: 从论文关键词字段统计
    - source=text: 从论文摘要全文提取 (TF-IDF)
    """
    try:
        if source == "text":
            data = await trend_analyzer.get_text_keyword_frequency(
                db, project_id, limit
            )
        else:
            data = await trend_analyzer.get_keyword_frequency(
                db, project_id, limit
            )
        return {"keywords": data, "total": len(data)}
    except Exception as e:
        logger.error(f"Keyword frequency failed: {e}")
        raise HTTPException(status_code=500, detail=f"关键词统计失败: {str(e)}")


@router.get("/hotspots")
async def get_hotspots(
    project_id: Optional[int] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取研究热点"""
    try:
        data = await trend_analyzer.get_hotspots(db, project_id, limit)
        return {"hotspots": data, "total": len(data)}
    except Exception as e:
        logger.error(f"Hotspots failed: {e}")
        raise HTTPException(status_code=500, detail=f"热点识别失败: {str(e)}")


@router.get("/timeline")
async def get_timeline(
    project_id: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None, description="可选：特定关键词的时间趋势"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取时间趋势分析"""
    try:
        data = await trend_analyzer.get_timeline(db, project_id, keyword)
        return {"timeline": data, "total": len(data)}
    except Exception as e:
        logger.error(f"Timeline failed: {e}")
        raise HTTPException(status_code=500, detail=f"时间趋势分析失败: {str(e)}")


@router.get("/bursts")
async def get_burst_terms(
    project_id: Optional[int] = Query(None),
    min_frequency: int = Query(2, ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """检测突现词"""
    try:
        data = await trend_analyzer.get_burst_terms(db, project_id, min_frequency)
        return {"bursts": data, "total": len(data)}
    except Exception as e:
        logger.error(f"Burst detection failed: {e}")
        raise HTTPException(status_code=500, detail=f"突现词检测失败: {str(e)}")


@router.get("/distribution")
async def get_field_distribution(
    project_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取领域分布"""
    try:
        data = await trend_analyzer.get_field_distribution(db, project_id)
        return {"distribution": data, "total": len(data)}
    except Exception as e:
        logger.error(f"Distribution failed: {e}")
        raise HTTPException(status_code=500, detail=f"领域分布分析失败: {str(e)}")
