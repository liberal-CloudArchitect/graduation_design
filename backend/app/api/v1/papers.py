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
    title: Optional[str] = None
    authors: Optional[str] = None
    abstract: Optional[str] = None
    file_path: Optional[str] = None
    status: str
    page_count: Optional[int] = None
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


# ============ Helper Functions ============

def _extract_keywords_from_abstract(abstract: str, top_n: int = 10) -> List[str]:
    """从摘要中使用TF-IDF提取关键词（当PDF中未找到显式关键词时的回退方案）"""
    import re
    from collections import Counter
    
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "for", "and", "but", "or",
        "not", "no", "nor", "so", "yet", "to", "of", "in", "on", "at", "by",
        "from", "with", "as", "into", "about", "between", "through", "during",
        "before", "after", "above", "below", "this", "that", "these", "those",
        "it", "its", "they", "them", "their", "we", "our", "you", "your",
        "which", "who", "whom", "what", "where", "when", "how", "why",
        "also", "more", "most", "very", "such", "than", "then", "each",
        "other", "some", "any", "all", "both", "few", "many", "much",
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
        "都", "一", "这", "中", "大", "为", "上", "个", "到", "说",
        "们", "也", "会", "着", "要", "而", "去", "之", "过", "与",
        "使用", "通过", "进行", "可以", "已经", "其中", "以及", "由于",
    }
    
    # 提取英文词组和中文短语
    words = re.findall(r'[a-zA-Z]{3,}|[\u4e00-\u9fff]{2,6}', abstract.lower())
    filtered = [w for w in words if w not in stop_words]
    counter = Counter(filtered)
    return [word for word, _ in counter.most_common(top_n)]


def _extract_publication_date(metadata: dict, full_text: str):
    """尝试从PDF元数据或文本中提取发表日期"""
    import re
    from datetime import date
    
    # 优先使用元数据中的日期
    if metadata.get("date"):
        try:
            return date.fromisoformat(str(metadata["date"])[:10])
        except (ValueError, TypeError):
            pass
    
    # 从文本中提取年份（常见的学术论文日期格式）
    text_head = full_text[:3000] if full_text else ""
    
    # 匹配常见日期格式: "Published: 2024-01-15", "Received 15 January 2024" 等
    date_patterns = [
        r'(?:published|accepted|received|submitted)[:\s]+(\d{4})[.-/](\d{1,2})[.-/](\d{1,2})',
        r'(?:published|accepted|received|submitted)[:\s]+\d{1,2}\s+\w+\s+(\d{4})',
        r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',
        r'(\d{4})\s*(?:年)',
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, text_head, re.IGNORECASE)
        if match:
            groups = match.groups()
            try:
                if len(groups) == 3:
                    return date(int(groups[0]), int(groups[1]), int(groups[2]))
                elif len(groups) == 1:
                    year = int(groups[0])
                    if 1990 <= year <= 2030:
                        return date(year, 1, 1)
            except (ValueError, TypeError):
                continue
    
    return None


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
            
            # 保存关键词（PDF解析提取的 + 从摘要TF-IDF提取的）
            extracted_keywords = doc.keywords or []
            if not extracted_keywords and doc.abstract:
                # 从摘要中提取关键词作为回退
                extracted_keywords = _extract_keywords_from_abstract(doc.abstract)
            if extracted_keywords:
                paper.keywords = extracted_keywords
            
            # 尝试从元数据中提取发表日期
            pub_date = _extract_publication_date(doc.metadata, doc.full_text)
            if pub_date:
                paper.publication_date = pub_date
            
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
        user_id=current_user.id,
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
