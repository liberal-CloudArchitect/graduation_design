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
import re
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

REFERENCE_SECTION_PATTERN = re.compile(
    r"^\s*(references?|参考文献|bibliography)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
REFERENCE_ENTRY_PATTERNS = [
    re.compile(r"^\s*\[\d{1,3}\]\s+"),
    re.compile(r"^\s*\d{1,3}\.\s+[A-Z]"),
    re.compile(r"\bet al\.\b", re.IGNORECASE),
    re.compile(r"\bdoi:\s*10\.\d{4,9}/", re.IGNORECASE),
]
LAYOUT_EXCLUDED_REGION_TYPES = {"reference", "header", "footer"}
LAYOUT_PRIORITY_REGION_TYPES = {
    "title", "author", "abstract", "section_header", "paragraph", "list", "caption", "formula"
}


def _is_reference_heavy_text(text: str) -> bool:
    """判断文本块是否更像参考文献区（用于索引前过滤）"""
    if not text:
        return False
    snippet = text[:400]
    if REFERENCE_SECTION_PATTERN.search(snippet):
        return True

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False

    hit = 0
    for ln in lines:
        if any(p.search(ln) for p in REFERENCE_ENTRY_PATTERNS):
            hit += 1

    hit_ratio = hit / max(1, len(lines))
    return hit >= 3 and hit_ratio >= 0.2


def _extract_layout_page_text(page) -> tuple[str, List[str]]:
    """优先使用布局分析结果重建页面文本，降低页眉/参考文献噪声。"""
    raw_text = (getattr(page, "text", "") or "").strip()
    layout = getattr(page, "layout", None)
    if not layout or not isinstance(layout, dict):
        return raw_text, []

    regions = layout.get("regions", []) or []
    if not regions:
        return raw_text, []

    page_region_types: List[str] = []
    selected_texts: List[str] = []
    sorted_regions = sorted(regions, key=lambda r: (r.get("order", 0), r.get("bbox", [0, 0, 0, 0])[1]))

    for region in sorted_regions:
        rtype = str(region.get("type", "")).strip().lower()
        rtext = str(region.get("text", "") or "").strip()
        if not rtext:
            continue
        if rtype:
            page_region_types.append(rtype)

        if rtype in LAYOUT_EXCLUDED_REGION_TYPES:
            continue
        # 对“其他”类型更严格，避免噪声灌入
        if rtype and rtype not in LAYOUT_PRIORITY_REGION_TYPES and len(rtext) < 25:
            continue
        selected_texts.append(rtext)

    layout_text = "\n".join(selected_texts).strip()
    # 过短则回退原始提取文本
    if len(layout_text) < max(80, len(raw_text) // 5):
        return raw_text, page_region_types
    return layout_text, page_region_types


def _is_reference_dominant_page(page_region_types: List[str], page_text: str) -> bool:
    """判断页面是否主要由参考文献构成。"""
    if not page_text:
        return False
    lowered = [str(rt).lower() for rt in page_region_types if rt]
    if not lowered:
        return False

    ref_count = sum(1 for rt in lowered if rt == "reference")
    keep_markers = {"paragraph", "abstract", "section_header", "title"}
    has_keep_region = any(rt in keep_markers for rt in lowered)

    if ref_count > 0 and _is_reference_heavy_text(page_text) and not has_keep_region:
        return True
    return ref_count >= max(2, int(len(lowered) * 0.6)) and not has_keep_region

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


def _is_reliable_paper_title(title: Optional[str]) -> bool:
    """判断解析出的标题是否可用，过滤明显噪声标题。"""
    if not title:
        return False
    t = str(title).strip()
    if len(t) < 12 or len(t) > 260:
        return False
    lower = t.lower()
    noise_tokens = (
        "keywords:",
        "citation:",
        "academic editors",
        "academiceditors",
        "received:",
        "accepted:",
        "doi:",
        "copyright",
    )
    if any(tok in lower for tok in noise_tokens):
        return False
    if t.count(";") >= 2:
        return False
    if "." in t and len(t.split()) > 8:
        return False
    if not (t[0].isupper() or re.match(r"[\u4e00-\u9fff]", t[0])):
        return False
    sentence_like_markers = (
        "in this article",
        "our daily lives",
        "despite",
        "whether",
    )
    if any(marker in lower for marker in sentence_like_markers):
        return False
    if len(t.split()) <= 2:
        return False
    return True


# ============ Background Tasks ============

async def process_paper_async(paper_id: int, file_path: str):
    """异步处理文献 (后台任务)"""
    from app.services.pdf_parser import PDFParser
    from app.rag.chunker import SemanticChunker
    from app.rag import rag_engine
    from app.models.database import async_session_maker
    
    logger.info(f"Processing paper {paper_id}: {file_path}")
    
    async with async_session_maker() as db:
        paper = None
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
            
            # 更新元数据：解析标题质量不足时，保留上传文件名（去扩展名）作为兜底
            parsed_title = (doc.title or "").strip()
            if _is_reliable_paper_title(parsed_title):
                paper.title = parsed_title
            else:
                original_name = (paper.title or os.path.basename(file_path)).strip()
                paper.title = os.path.splitext(original_name)[0][:500]
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
            
            # 分块（按页处理，保留页码）
            chunker = SemanticChunker(
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP,
            )
            chunks = []
            skipped_reference_chunks = 0
            skipped_reference_pages = 0

            for page in (doc.pages or []):
                page_text, page_region_types = _extract_layout_page_text(page)
                if not page_text.strip():
                    continue

                if _is_reference_dominant_page(page_region_types, page_text):
                    skipped_reference_pages += 1
                    continue

                page_chunks = chunker.split_text(
                    page_text,
                    metadata={
                        "page_number": page.page_number,
                        "region_types": sorted(set(rt for rt in page_region_types if rt)),
                    },
                )

                for c in page_chunks:
                    if _is_reference_heavy_text(c.text):
                        skipped_reference_chunks += 1
                        continue
                    chunks.append(
                        {
                            "text": c.text,
                            "page_number": page.page_number,
                            "metadata": c.metadata or {},
                        }
                    )

            # 回退：若按页分块为空，使用全文分块
            if not chunks and doc.full_text:
                for c in chunker.split_text(doc.full_text):
                    if _is_reference_heavy_text(c.text):
                        skipped_reference_chunks += 1
                        continue
                    chunks.append(
                        {
                            "text": c.text,
                            "page_number": None,
                            "metadata": c.metadata or {},
                        }
                    )
            
            # 索引到向量库
            if chunks:
                vector_ids = await rag_engine.index_paper(
                    paper_id=paper_id,
                    chunks=chunks,
                    project_id=paper.project_id
                )
                paper.chunk_count = len(chunks)
                paper.vector_ids = vector_ids
                paper.parse_result = {
                    "chunk_count": len(chunks),
                    "skipped_reference_chunks": skipped_reference_chunks,
                    "skipped_reference_pages": skipped_reference_pages,
                }
            
            # 更新状态为完成
            paper.status = "completed"
            paper.updated_at = datetime.utcnow()
            await db.commit()
            
            logger.info(
                f"Paper {paper_id} processed successfully: {len(chunks)} chunks, "
                f"skipped_reference_chunks={skipped_reference_chunks}"
            )
            
        except Exception as e:
            logger.error(f"Failed to process paper {paper_id}: {e}")
            if paper:
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


@router.post("/{paper_id}/reprocess", response_model=PaperUploadResponse)
async def reprocess_paper(
    paper_id: int,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """重处理文献并重建索引（用于应用新分块/过滤策略）"""
    from app.rag import rag_engine
    from app.services.mongodb_service import mongodb_service

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

    if not paper.file_path or not os.path.exists(paper.file_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文献原始文件不存在，无法重处理"
        )

    # 清理旧索引和分块，避免重复与脏数据
    try:
        await mongodb_service.delete_paper_chunks(paper_id)
    except Exception as e:
        logger.warning(f"Reprocess: delete Mongo chunks failed for paper {paper_id}: {e}")
    try:
        await rag_engine.delete_paper_index(paper_id)
    except Exception as e:
        logger.warning(f"Reprocess: delete retrieval index failed for paper {paper_id}: {e}")

    paper.status = "pending"
    paper.vector_ids = None
    paper.chunk_count = None
    paper.parse_result = {"reprocess_requested_at": datetime.utcnow().isoformat()}
    paper.updated_at = datetime.utcnow()
    await db.commit()

    background_tasks.add_task(process_paper_async, paper.id, paper.file_path)

    return PaperUploadResponse(
        id=paper.id,
        filename=paper.title or f"paper_{paper.id}.pdf",
        status="pending",
        message="文献已进入重处理队列"
    )


@router.delete("/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_paper(
    paper_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除文献"""
    from app.rag import rag_engine
    from app.services.mongodb_service import mongodb_service

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

    # 清理文献分块与检索索引，避免删除后仍被召回
    try:
        await mongodb_service.delete_paper_chunks(paper_id)
    except Exception as e:
        logger.warning(f"Delete Mongo chunks failed for paper {paper_id}: {e}")
    try:
        await rag_engine.delete_paper_index(paper_id)
    except Exception as e:
        logger.warning(f"Delete vector/bm25 index failed for paper {paper_id}: {e}")
    
    # 删除文件
    if paper.file_path and os.path.exists(paper.file_path):
        os.remove(paper.file_path)
    
    # 删除记录
    await db.delete(paper)
    await db.commit()
