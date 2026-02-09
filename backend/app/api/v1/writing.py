"""
Writing API - 写作辅助路由
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from loguru import logger

from app.core.deps import get_current_user
from app.models.user import User
from app.services.writing_assistant import writing_assistant
from app.rag import rag_engine


router = APIRouter()


# ============ Schemas ============

class OutlineRequest(BaseModel):
    """大纲生成请求"""
    topic: str
    project_id: Optional[int] = None
    style: str = "standard"  # standard, conference, journal
    sections: Optional[List[str]] = None


class ReviewRequest(BaseModel):
    """文献综述请求"""
    topic: str
    project_id: Optional[int] = None
    max_words: int = 800
    focus_areas: Optional[List[str]] = None


class PolishRequest(BaseModel):
    """段落润色请求"""
    text: str
    style: str = "academic"  # academic, formal, concise
    language: str = "auto"


class CitationRequest(BaseModel):
    """引用建议请求"""
    text: str
    project_id: Optional[int] = None
    limit: int = 10


# ============ Initialization ============

def _ensure_initialized():
    """确保写作助手已初始化"""
    if writing_assistant._llm is None and rag_engine.llm:
        writing_assistant.set_llm(rag_engine.llm)
    if writing_assistant._rag_engine is None and rag_engine._initialized:
        writing_assistant.set_rag_engine(rag_engine)


# ============ Routes ============

@router.post("/outline")
async def generate_outline(
    request: OutlineRequest,
    current_user: User = Depends(get_current_user)
):
    """
    生成论文大纲
    
    根据研究主题和参考文献生成结构化大纲。
    """
    _ensure_initialized()
    
    try:
        result = await writing_assistant.generate_outline(
            topic=request.topic,
            project_id=request.project_id,
            style=request.style,
            sections=request.sections
        )
        return result
    except Exception as e:
        logger.error(f"Outline generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"大纲生成失败: {str(e)}")


@router.post("/review")
async def generate_review(
    request: ReviewRequest,
    current_user: User = Depends(get_current_user)
):
    """
    生成文献综述
    
    基于项目中的文献生成学术文献综述。
    """
    _ensure_initialized()
    
    try:
        result = await writing_assistant.generate_review(
            topic=request.topic,
            project_id=request.project_id,
            max_words=request.max_words,
            focus_areas=request.focus_areas
        )
        return result
    except Exception as e:
        logger.error(f"Review generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"综述生成失败: {str(e)}")


@router.post("/polish")
async def polish_text(
    request: PolishRequest,
    current_user: User = Depends(get_current_user)
):
    """
    段落润色
    
    对学术文本进行语言和结构优化。
    """
    _ensure_initialized()
    
    try:
        result = await writing_assistant.polish_text(
            text=request.text,
            style=request.style,
            language=request.language
        )
        return result
    except Exception as e:
        logger.error(f"Polish failed: {e}")
        raise HTTPException(status_code=500, detail=f"润色失败: {str(e)}")


@router.post("/suggest-citations")
async def suggest_citations(
    request: CitationRequest,
    current_user: User = Depends(get_current_user)
):
    """
    引用建议
    
    根据文本内容推荐合适的引用文献。
    """
    _ensure_initialized()
    
    try:
        result = await writing_assistant.suggest_citations(
            text=request.text,
            project_id=request.project_id,
            limit=request.limit
        )
        return result
    except Exception as e:
        logger.error(f"Citation suggestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"引用建议失败: {str(e)}")
