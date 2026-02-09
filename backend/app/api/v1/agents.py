"""
Agent API - Multi-Agent系统路由
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
import json
import asyncio

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.agents.coordinator import agent_coordinator
from app.rag import rag_engine


router = APIRouter()


# ============ Schemas ============

class AgentRequest(BaseModel):
    """Agent请求"""
    query: str
    project_id: Optional[int] = None
    agent_type: Optional[str] = None  # retriever_agent, analyzer_agent, writer_agent, search_agent
    params: dict = {}


class AgentMultiRequest(BaseModel):
    """多Agent请求"""
    query: str
    project_id: Optional[int] = None
    agent_types: Optional[List[str]] = None
    params: dict = {}


class WritingRequest(BaseModel):
    """写作请求"""
    query: str
    project_id: Optional[int] = None
    task_type: str = "auto"  # outline, review, polish, citation, general
    context: str = ""  # 润色时的原文


class AnalysisRequest(BaseModel):
    """分析请求"""
    query: str
    project_id: Optional[int] = None
    analysis_type: str = "auto"  # keywords, timeline, hotspot, burst, comparison


# ============ Routes ============

@router.post("/ask")
async def agent_ask(
    request: AgentRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Agent协调问答
    
    自动路由到合适的Agent处理用户请求。
    可通过agent_type字段指定Agent。
    """
    # 确保协调器已初始化
    if not agent_coordinator._initialized:
        await agent_coordinator.initialize(rag_engine)
    
    try:
        response = await agent_coordinator.process(
            query=request.query,
            project_id=request.project_id,
            agent_type=request.agent_type,
            **request.params
        )
        return response.to_dict()
    except Exception as e:
        logger.error(f"Agent ask failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent处理失败: {str(e)}"
        )


@router.post("/multi")
async def agent_multi(
    request: AgentMultiRequest,
    current_user: User = Depends(get_current_user)
):
    """
    多Agent并行处理
    
    同时调用多个Agent，返回各Agent的结果。
    """
    if not agent_coordinator._initialized:
        await agent_coordinator.initialize(rag_engine)
    
    try:
        responses = await agent_coordinator.process_multi(
            query=request.query,
            project_id=request.project_id,
            agent_types=request.agent_types,
            **request.params
        )
        return {
            agent_type: resp.to_dict()
            for agent_type, resp in responses.items()
        }
    except Exception as e:
        logger.error(f"Agent multi failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"多Agent处理失败: {str(e)}"
        )


@router.post("/write")
async def agent_write(
    request: WritingRequest,
    current_user: User = Depends(get_current_user)
):
    """
    写作辅助Agent
    
    支持大纲生成、文献综述、段落润色、引用建议。
    """
    if not agent_coordinator._initialized:
        await agent_coordinator.initialize(rag_engine)
    
    try:
        response = await agent_coordinator.process(
            query=request.query,
            project_id=request.project_id,
            agent_type="writer_agent",
            task_type=request.task_type,
            context=request.context
        )
        return response.to_dict()
    except Exception as e:
        logger.error(f"Writer agent failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"写作辅助失败: {str(e)}"
        )


@router.post("/analyze")
async def agent_analyze(
    request: AnalysisRequest,
    current_user: User = Depends(get_current_user)
):
    """
    分析Agent
    
    支持关键词频率、趋势分析、热点识别、突现词检测。
    """
    if not agent_coordinator._initialized:
        await agent_coordinator.initialize(rag_engine)
    
    try:
        response = await agent_coordinator.process(
            query=request.query,
            project_id=request.project_id,
            agent_type="analyzer_agent",
            analysis_type=request.analysis_type
        )
        return response.to_dict()
    except Exception as e:
        logger.error(f"Analyzer agent failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"分析失败: {str(e)}"
        )


@router.post("/search")
async def agent_search(
    request: AgentRequest,
    current_user: User = Depends(get_current_user)
):
    """
    搜索Agent
    
    调用外部学术API搜索论文。
    """
    if not agent_coordinator._initialized:
        await agent_coordinator.initialize(rag_engine)
    
    try:
        response = await agent_coordinator.process(
            query=request.query,
            project_id=request.project_id,
            agent_type="search_agent",
            **request.params
        )
        return response.to_dict()
    except Exception as e:
        logger.error(f"Search agent failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"搜索失败: {str(e)}"
        )
