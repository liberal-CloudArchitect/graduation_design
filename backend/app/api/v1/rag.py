"""
RAG API - RAG问答路由
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import json
import asyncio
from loguru import logger

from app.core.deps import get_db, get_current_user
from app.models.user import User, Project
from app.models.paper import Conversation
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
    paper_title: Optional[str]
    chunk_index: int
    page_number: Optional[int]
    text: str
    score: float


class AnswerResponse(BaseModel):
    """答案响应"""
    answer: str
    references: List[ReferenceItem]
    conversation_id: Optional[int] = None
    method: str = "rag"


class ConversationMessage(BaseModel):
    """对话消息"""
    role: str  # user / assistant
    content: str
    created_at: datetime


class ConversationResponse(BaseModel):
    """对话响应"""
    id: int
    project_id: Optional[int]
    messages: List[ConversationMessage]
    created_at: datetime


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
    
    # 调用RAG引擎
    try:
        result = await rag_engine.answer(
            question=request.question,
            project_id=request.project_id,
            top_k=request.top_k
        )
    except Exception as e:
        logger.error(f"RAG error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"RAG问答失败: {str(e)}"
        )
    
    # 保存对话
    conversation = Conversation(
        user_id=current_user.id,
        project_id=request.project_id,
        messages=[
            {"role": "user", "content": request.question},
            {"role": "assistant", "content": result["answer"]}
        ]
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    
    # 构建引用
    references = []
    for ref in result.get("references", []):
        references.append(ReferenceItem(
            paper_id=ref.get("paper_id", 0),
            paper_title=ref.get("title"),
            chunk_index=ref.get("chunk_index", 0),
            page_number=ref.get("page_number"),
            text=ref.get("text", ""),
            score=ref.get("score", 0)
        ))
    
    return AnswerResponse(
        answer=result["answer"],
        references=references,
        conversation_id=conversation.id,
        method=result.get("method", "rag")
    )


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
    
    async def generate():
        """生成流式响应"""
        try:
            # 1. 先检索文档
            search_results = await rag_engine.search(
                request.question, 
                request.project_id, 
                request.top_k
            )
            
            # 发送检索结果
            yield f"data: {json.dumps({'type': 'references', 'data': search_results})}\n\n"
            
            # 2. 获取文档内容
            docs = await rag_engine._fetch_documents(search_results)
            context = rag_engine._build_context(docs)
            
            # 3. 流式生成答案
            if rag_engine.llm:
                prompt = f"""根据以下参考文献回答用户问题。

参考文献:
{context}

用户问题: {request.question}

要求:
1. 仅基于提供的参考文献回答
2. 如有引用，使用[1][2]格式标注
3. 如果文献中没有相关信息，请明确说明
"""
                full_answer = ""
                async for chunk in rag_engine.llm.astream(prompt):
                    if hasattr(chunk, 'content') and chunk.content:
                        full_answer += chunk.content
                        yield f"data: {json.dumps({'type': 'chunk', 'data': chunk.content})}\n\n"
                        await asyncio.sleep(0.01)  # 小延迟确保流畅
                
                # 发送完成信号
                yield f"data: {json.dumps({'type': 'done', 'data': {'answer': full_answer}})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'data': 'LLM未初始化'})}\n\n"
                
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
                    created_at=conv.created_at
                )
                for msg in (conv.messages or [])
            ],
            created_at=conv.created_at
        )
        for conv in conversations
    ]


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
