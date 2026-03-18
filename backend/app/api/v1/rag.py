"""
RAG API - RAG问答路由
"""
from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
import json
from loguru import logger

from app.core.deps import get_db, get_current_user
from app.models.user import User, Project
from app.models.paper import Conversation, Paper
from app.rag import rag_engine


router = APIRouter()


# ============ Schemas ============

class QuestionRequest(BaseModel):
    """问题请求"""
    question: str
    project_id: Optional[int] = None
    paper_ids: Optional[List[int]] = None
    top_k: int = 5


class ReferenceItem(BaseModel):
    """引用项"""
    paper_id: int
    paper_title: Optional[str] = None
    chunk_index: int
    page_number: Optional[int] = None
    text: str
    score: float
    display_score: Optional[float] = None
    raw_score: Optional[float] = None
    citation_context: Optional[str] = None
    citation_number: Optional[int] = None
    citation_spans: Optional[List[Dict]] = None
    # Phase 2: hierarchical chunking fields
    parent_id: Optional[str] = None
    section_path: Optional[str] = None
    section_anchor: Optional[str] = None
    sibling_chunk_indices: Optional[List[int]] = None


class AnswerResponse(BaseModel):
    """答案响应"""
    answer: str
    references: List[ReferenceItem]
    conversation_id: Optional[int] = None
    method: str = "rag"


class SearchResponse(BaseModel):
    """检索响应"""
    references: List[ReferenceItem]
    method: str = "retrieval"


class ConversationMessage(BaseModel):
    """对话消息"""
    role: str  # user / assistant
    content: str
    references: Optional[List[ReferenceItem]] = None
    metadata: Optional[Dict] = None
    agent_type: Optional[str] = None
    reasoning_content: Optional[str] = None
    created_at: datetime


class ConversationResponse(BaseModel):
    """对话响应"""
    id: int
    project_id: Optional[int]
    messages: List[ConversationMessage]
    created_at: datetime


async def _enrich_references_with_titles(
    db: AsyncSession,
    references: List[dict]
) -> List[dict]:
    """批量补全文献标题，避免前端展示“未知文献”"""
    if not references:
        return []

    paper_ids = {
        int(ref.get("paper_id"))
        for ref in references
        if isinstance(ref, dict) and ref.get("paper_id")
    }
    if not paper_ids:
        return references

    result = await db.execute(
        select(Paper.id, Paper.title).where(Paper.id.in_(paper_ids))
    )
    id_to_title = {pid: title for pid, title in result.all()}

    enriched = []
    for ref in references:
        if not isinstance(ref, dict):
            enriched.append(ref)
            continue
        paper_id = ref.get("paper_id")
        if paper_id:
            title = ref.get("paper_title") or ref.get("title") or id_to_title.get(int(paper_id))
            ref = {**ref, "title": title, "paper_title": title}
        enriched.append(ref)
    return enriched


def _ref_dict_to_item(ref: dict) -> ReferenceItem:
    """Convert a reference dict to a ReferenceItem, handling Phase 2 fields."""
    return ReferenceItem(
        paper_id=ref.get("paper_id", 0),
        paper_title=ref.get("paper_title") or ref.get("title"),
        chunk_index=ref.get("chunk_index", 0),
        page_number=ref.get("page_number"),
        text=ref.get("text", ""),
        score=ref.get("score", 0),
        display_score=ref.get("display_score"),
        raw_score=ref.get("raw_score"),
        citation_context=ref.get("citation_context"),
        citation_number=ref.get("citation_number"),
        citation_spans=ref.get("citation_spans"),
        parent_id=ref.get("parent_id"),
        section_path=ref.get("section_path"),
        section_anchor=ref.get("section_anchor"),
        sibling_chunk_indices=ref.get("sibling_chunk_indices"),
    )


async def _validate_requested_paper_ids(
    db: AsyncSession,
    user_id: int,
    paper_ids: Optional[List[int]],
    project_id: Optional[int] = None,
) -> Optional[List[int]]:
    """校验 paper_ids 是否都属于当前用户（且可选属于指定项目）"""
    if not paper_ids:
        return None

    unique_ids = list(dict.fromkeys(int(pid) for pid in paper_ids if pid))
    if not unique_ids:
        return None

    query = (
        select(Paper.id)
        .join(Project, Paper.project_id == Project.id)
        .where(Paper.id.in_(unique_ids), Project.user_id == user_id)
    )
    if project_id is not None:
        query = query.where(Paper.project_id == project_id)

    result = await db.execute(query)
    accessible_ids = {int(row[0]) for row in result.all()}

    if len(accessible_ids) != len(unique_ids):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="包含无权限访问的文献ID"
        )
    return unique_ids


# ============ Routes ============

@router.post("/ask", response_model=AnswerResponse)
async def ask_question(
    request: QuestionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    RAG问答
    
    - **question**: 用户问题
    - **project_id**: 项目ID (限定检索范围)
    - **paper_ids**: 指定文献ID列表
    - **top_k**: 检索文档数量
    """
    # 验证项目权限
    if request.project_id:
        result = await db.execute(
            select(Project).where(
                Project.id == request.project_id,
                Project.user_id == current_user.id
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="项目不存在"
            )
    
    validated_paper_ids = await _validate_requested_paper_ids(
        db=db,
        user_id=current_user.id,
        paper_ids=request.paper_ids,
        project_id=request.project_id,
    )

    # 调用RAG引擎
    try:
        result = await rag_engine.answer(
            question=request.question,
            project_id=request.project_id,
            top_k=request.top_k,
            paper_ids=validated_paper_ids,
        )
    except Exception as e:
        logger.error(f"RAG error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"RAG问答失败: {str(e)}"
        )
    
    # 补全引用标题，提升可读性
    enriched_refs = await _enrich_references_with_titles(
        db, result.get("references", [])
    )

    # 保存对话（包含引用，支持历史回放）
    conversation = Conversation(
        user_id=current_user.id,
        project_id=request.project_id,
        messages=[
            {"role": "user", "content": request.question},
            {
                "role": "assistant",
                "content": result["answer"],
                "references": enriched_refs,
                "metadata": {
                    "method": result.get("method", "rag"),
                    "memory_used": result.get("memory_used", False),
                    "memory_count": result.get("memory_count", 0),
                },
                "agent_type": "retriever_agent",
            }
        ]
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    
    references = [_ref_dict_to_item(ref) for ref in enriched_refs]
    
    return AnswerResponse(
        answer=result["answer"],
        references=references,
        conversation_id=conversation.id,
        method=result.get("method", "rag")
    )


@router.post("/search", response_model=SearchResponse)
async def search_documents(
    request: QuestionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    纯检索接口

    仅返回引用结果，不触发 LLM 生成，也不写入对话历史。
    """
    if request.project_id:
        result = await db.execute(
            select(Project).where(
                Project.id == request.project_id,
                Project.user_id == current_user.id
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="项目不存在"
            )

    validated_paper_ids = await _validate_requested_paper_ids(
        db=db,
        user_id=current_user.id,
        paper_ids=request.paper_ids,
        project_id=request.project_id,
    )

    try:
        raw_refs = await rag_engine.search_enriched(
            query=request.question,
            project_id=request.project_id,
            top_k=request.top_k,
            paper_ids=validated_paper_ids,
        )
    except Exception as e:
        logger.error(f"RAG search error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"RAG检索失败: {str(e)}"
        )

    enriched_refs = await _enrich_references_with_titles(db, raw_refs)
    references = [_ref_dict_to_item(ref) for ref in enriched_refs]
    return SearchResponse(references=references, method="retrieval")


@router.post("/stream")
async def stream_answer(
    request: QuestionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    流式RAG问答 (Server-Sent Events)
    
    返回流式响应，实时输出答案
    """
    # 验证项目权限
    if request.project_id:
        result = await db.execute(
            select(Project).where(
                Project.id == request.project_id,
                Project.user_id == current_user.id
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="项目不存在"
            )
    
    validated_paper_ids = await _validate_requested_paper_ids(
        db=db,
        user_id=current_user.id,
        paper_ids=request.paper_ids,
        project_id=request.project_id,
    )

    async def generate():
        """使用统一的 answer_stream() 生成流式响应"""
        try:
            async for event in rag_engine.answer_stream(
                question=request.question,
                project_id=request.project_id,
                top_k=request.top_k,
                use_memory=True,
                paper_ids=validated_paper_ids,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )


@router.get("/conversations", response_model=List[ConversationResponse])
async def list_conversations(
    project_id: Optional[int] = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取对话历史列表"""
    query = select(Conversation).where(
        Conversation.user_id == current_user.id
    )
    
    if project_id:
        query = query.where(Conversation.project_id == project_id)
    
    query = query.order_by(Conversation.created_at.desc()).limit(limit)
    
    result = await db.execute(query)
    conversations = result.scalars().all()
    
    return [
        ConversationResponse(
            id=conv.id,
            project_id=conv.project_id,
            messages=[
                ConversationMessage(
                    role=msg["role"],
                    content=msg["content"],
                    references=[
                        _ref_dict_to_item(ref)
                        for ref in (msg.get("references") or [])
                        if isinstance(ref, dict)
                    ] or None,
                    metadata=msg.get("metadata"),
                    agent_type=msg.get("agent_type"),
                    reasoning_content=msg.get("reasoning_content"),
                    created_at=conv.created_at
                )
                for msg in (conv.messages or [])
            ],
            created_at=conv.created_at
        )
        for conv in conversations
    ]


@router.get("/conversations/count")
async def get_conversation_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取当前用户的对话总数"""
    result = await db.execute(
        select(func.count(Conversation.id)).where(
            Conversation.user_id == current_user.id
        )
    )
    count = result.scalar() or 0
    return {"count": count}


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取对话详情"""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id
        )
    )
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对话不存在"
        )
    
    return ConversationResponse(
        id=conversation.id,
        project_id=conversation.project_id,
        messages=[
            ConversationMessage(
                role=msg["role"],
                content=msg["content"],
                references=[
                    _ref_dict_to_item(ref)
                    for ref in (msg.get("references") or [])
                    if isinstance(ref, dict)
                ] or None,
                metadata=msg.get("metadata"),
                agent_type=msg.get("agent_type"),
                reasoning_content=msg.get("reasoning_content"),
                created_at=conversation.created_at
            )
            for msg in (conversation.messages or [])
        ],
        created_at=conversation.created_at
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除对话"""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id
        )
    )
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对话不存在"
        )
    
    await db.delete(conversation)
    await db.commit()
