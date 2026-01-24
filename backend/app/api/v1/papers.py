"""
Papers API - 文献管理路由
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
import os
import uuid
from loguru import logger

from app.core.deps import get_db, get_current_user
from app.core.config import settings
from app.models.user import User, Project
from app.models.paper import Paper


router = APIRouter()


# ============ Schemas ============

class PaperResponse(BaseModel):
    """文献响应"""
    id: int
    title: Optional[str]
    authors: Optional[str]
    abstract: Optional[str]
    file_path: str
    status: str
    page_count: int
    project_id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class PaperListResponse(BaseModel):
    """文献列表响应"""
    items: List[PaperResponse]
    total: int
    page: int
    page_size: int


class PaperUploadResponse(BaseModel):
    """文献上传响应"""
    id: int
    filename: str
    status: str
    message: str


# ============ Background Tasks ============

async def process_paper_async(paper_id: int, file_path: str):
    """异步处理文献 (后台任务)"""
    from app.services.pdf_parser import PDFParser
    from app.rag.chunker import SemanticChunker
    from app.rag import rag_engine
    from app.models.database import async_session_maker
    
    logger.info(f"Processing paper {paper_id}: {file_path}")
    
    async with async_session_maker() as db:
        try:
            # 获取Paper
            result = await db.execute(
                select(Paper).where(Paper.id == paper_id)
            )
            paper = result.scalar_one_or_none()
            if not paper:
                logger.error(f"Paper {paper_id} not found")
                return
            
            # 更新状态为处理中
            paper.status = "processing"
            await db.commit()
            
            # 解析PDF
            parser = PDFParser()
            doc = await parser.parse(file_path)
            
            # 更新元数据
            paper.title = doc.title or os.path.basename(file_path)
            paper.authors = ", ".join(doc.authors) if doc.authors else None
            paper.abstract = doc.abstract
            paper.page_count = doc.page_count
            
            # 分块
            chunker = SemanticChunker()
            chunks = chunker.split_text(doc.full_text)
            
            # 索引到向量库
            if chunks:
                chunk_texts = [c.text for c in chunks]
                await rag_engine.index_paper(
                    paper_id=paper_id,
                    chunks=chunk_texts,
                    project_id=paper.project_id
                )
            
            # 更新状态为完成
            paper.status = "completed"
            paper.updated_at = datetime.utcnow()
            await db.commit()
            
            logger.info(f"Paper {paper_id} processed successfully: {len(chunks)} chunks")
            
        except Exception as e:
            logger.error(f"Failed to process paper {paper_id}: {e}")
            paper.status = "failed"
            await db.commit()


# ============ Routes ============

@router.get("", response_model=PaperListResponse)
async def list_papers(
    project_id: Optional[int] = None,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取文献列表
    
    - **project_id**: 按项目筛选
    - **status**: 按状态筛选 (pending, processing, completed, failed)
    - **search**: 按标题搜索
    """
    # 构建查询
    base_query = select(Paper).join(Project).where(
        Project.user_id == current_user.id
    )
    
    if project_id:
        base_query = base_query.where(Paper.project_id == project_id)
    
    if status_filter:
        base_query = base_query.where(Paper.status == status_filter)
    
    if search:
        base_query = base_query.where(Paper.title.ilike(f"%{search}%"))
    
    # 总数
    count_query = select(func.count()).select_from(base_query.subquery())
    total = await db.scalar(count_query)
    
    # 分页
    query = base_query.order_by(Paper.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    
    result = await db.execute(query)
    papers = result.scalars().all()
    
    return PaperListResponse(
        items=[PaperResponse.model_validate(p) for p in papers],
        total=total or 0,
        page=page,
        page_size=page_size
    )


@router.post("/upload", response_model=PaperUploadResponse)
async def upload_paper(
    project_id: int,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    上传文献PDF
    
    - **project_id**: 目标项目ID
    - **file**: PDF文件
    """
    # 验证项目权限
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="项目不存在"
        )
    
    # 验证文件类型
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只支持PDF文件"
        )
    
    # 验证文件大小 (50MB)
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件大小不能超过50MB"
        )
    
    # 保存文件
    upload_dir = os.path.join(settings.UPLOAD_DIR, str(current_user.id))
    os.makedirs(upload_dir, exist_ok=True)
    
    file_id = str(uuid.uuid4())
    file_path = os.path.join(upload_dir, f"{file_id}.pdf")
    
    with open(file_path, "wb") as f:
        f.write(content)
    
    # 创建Paper记录
    paper = Paper(
        title=file.filename,
        file_path=file_path,
        project_id=project_id,
        status="pending"
    )
    
    db.add(paper)
    await db.commit()
    await db.refresh(paper)
    
    # 后台处理
    background_tasks.add_task(process_paper_async, paper.id, file_path)
    
    return PaperUploadResponse(
        id=paper.id,
        filename=file.filename,
        status="pending",
        message="文件已上传，正在后台处理"
    )


@router.get("/{paper_id}", response_model=PaperResponse)
async def get_paper(
    paper_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取文献详情"""
    result = await db.execute(
        select(Paper).join(Project).where(
            Paper.id == paper_id,
            Project.user_id == current_user.id
        )
    )
    paper = result.scalar_one_or_none()
    
    if not paper:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文献不存在"
        )
    
    return PaperResponse.model_validate(paper)


@router.get("/{paper_id}/status")
async def get_paper_status(
    paper_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取文献处理状态"""
    result = await db.execute(
        select(Paper).join(Project).where(
            Paper.id == paper_id,
            Project.user_id == current_user.id
        )
    )
    paper = result.scalar_one_or_none()
    
    if not paper:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文献不存在"
        )
    
    return {
        "id": paper.id,
        "status": paper.status,
        "title": paper.title,
        "updated_at": paper.updated_at
    }


@router.delete("/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_paper(
    paper_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除文献"""
    result = await db.execute(
        select(Paper).join(Project).where(
            Paper.id == paper_id,
            Project.user_id == current_user.id
        )
    )
    paper = result.scalar_one_or_none()
    
    if not paper:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文献不存在"
        )
    
    # 删除文件
    if os.path.exists(paper.file_path):
        os.remove(paper.file_path)
    
    # 删除记录
    await db.delete(paper)
    await db.commit()
