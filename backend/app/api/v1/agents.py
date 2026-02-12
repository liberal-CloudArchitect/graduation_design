"""
Agent API - Multi-Agent系统路由

包含 Agent 协调问答、多Agent并行处理、流式Agent问答、写作辅助、分析、搜索、
以及 Skills 管理（列表查询、直接执行）。
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger
import json
import asyncio

from app.core.deps import get_db, get_current_user
from app.models.user import User, Project
from app.models.paper import Conversation, Paper
from app.agents.coordinator import agent_coordinator
from app.agents.base_agent import AgentType
from app.rag import rag_engine


router = APIRouter()


async def _enrich_references_with_titles(
    db: AsyncSession,
    references: List[dict]
) -> List[dict]:
    """批量补全文献标题，避免显示“未知文献”"""
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
        if paper_id and not ref.get("title"):
            ref = {**ref, "title": id_to_title.get(int(paper_id))}
        enriched.append(ref)
    return enriched


def _normalize_agent_markdown(
    content: str,
    references: List[dict],
    agent_type: str
) -> str:
    """
    对非流式 Agent 输出做轻量结构化，提升前端展示一致性。
    """
    text = (content or "").strip()
    if not text:
        return text
    if "## " in text:
        return text

    source_lines = []
    for idx, ref in enumerate(references[:8], 1):
        if not isinstance(ref, dict):
            continue
        title = ref.get("title") or ref.get("paper_title") or ref.get("name") or "未知来源"
        source_lines.append(f"[{idx}] {title}")

    sources = "\n".join(source_lines) if source_lines else "未提供可展示的引用来源。"
    return (
        f"## 回答\n{text}\n\n"
        f"## 处理信息\n- Agent: `{agent_type}`\n- 引用数量: {len(references)}\n\n"
        f"## 引用来源\n{sources}"
    )


# ============ Schemas ============

class AgentRequest(BaseModel):
    """Agent请求"""
    query: str
    project_id: Optional[int] = None
    agent_type: Optional[str] = None  # retriever_agent, analyzer_agent, writer_agent, search_agent
    conversation_id: Optional[int] = None  # 对话ID，用于加载历史上下文
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


class SkillExecuteRequest(BaseModel):
    """Skill 直接执行请求"""
    skill_name: str
    arguments: Dict[str, Any] = {}


# ============ Agent Routes ============

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


@router.post("/stream")
async def agent_stream(
    request: AgentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Agent流式问答 (Server-Sent Events)
    
    通过 Agent Coordinator 自动路由到合适的 Agent，
    以 SSE 流式方式返回处理结果。
    
    SSE 事件类型:
    - routing: 告知前端路由到了哪个 Agent
    - chunk: 逐字输出答案内容
    - references: 引用来源
    - metadata: Agent 元数据（图表数据、skills_used 等）
    - done: 流式结束，包含完整答案
    - error: 错误信息
    """
    # 确保协调器已初始化
    if not agent_coordinator._initialized:
        await agent_coordinator.initialize(rag_engine)
    
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
    
    # 在外部确定路由，以便在 generate() 中使用
    # (generate 是 async generator，不能在其中抛出 HTTPException)
    if request.agent_type:
        try:
            at = AgentType(request.agent_type)
            routed_agent = agent_coordinator.agents.get(at)
        except ValueError:
            routed_agent = None
        if not routed_agent:
            routed_agent, _ = agent_coordinator._route_query(request.query)
        routed_type = routed_agent.agent_type.value
    else:
        routed_agent, confidence = agent_coordinator._route_query(request.query)
        routed_type = routed_agent.agent_type.value
        logger.info(
            f"[agent/stream] Routing to {routed_type} (confidence: {confidence:.2f})"
        )
    
    async def generate():
        """生成 SSE 流式响应"""
        full_answer = ""
        agent_type_used = routed_type
        references_data = []
        metadata_extra = {}
        
        try:
            # 0. 加载对话历史（如果有 conversation_id）
            conversation_history = []
            if request.conversation_id:
                try:
                    hist_result = await db.execute(
                        select(Conversation).where(
                            Conversation.id == request.conversation_id,
                            Conversation.user_id == current_user.id
                        )
                    )
                    hist_conv = hist_result.scalar_one_or_none()
                    if hist_conv and hist_conv.messages:
                        conversation_history = hist_conv.messages
                except Exception as e:
                    logger.warning(f"Failed to load conversation history: {e}")
            
            # 1. 发送路由信息
            agent_labels = {
                "retriever_agent": "文献检索Agent",
                "analyzer_agent": "趋势分析Agent",
                "writer_agent": "写作辅助Agent",
                "search_agent": "学术搜索Agent",
            }
            yield f"data: {json.dumps({'type': 'routing', 'data': {'agent_type': agent_type_used, 'label': agent_labels.get(agent_type_used, agent_type_used)}}, ensure_ascii=False)}\n\n"
            
            # 2. 对于 RetrieverAgent，使用统一的 answer_stream()
            if agent_type_used == "retriever_agent" and rag_engine.llm:
                async for event in rag_engine.answer_stream(
                    question=request.query,
                    project_id=request.project_id,
                    top_k=request.params.get("top_k", 5),
                    use_memory=True,
                    conversation_history=conversation_history,
                    paper_ids=request.params.get("paper_ids"),
                ):
                    event_type = event.get("type")
                    
                    if event_type == "references":
                        references_data = await _enrich_references_with_titles(
                            db, event["data"]
                        )
                        yield f"data: {json.dumps({'type': 'references', 'data': references_data}, ensure_ascii=False)}\n\n"
                    
                    elif event_type == "chunk":
                        full_answer += event["data"]
                        yield f"data: {json.dumps({'type': 'chunk', 'data': event['data']}, ensure_ascii=False)}\n\n"
                    
                    elif event_type == "done":
                        done_data = event["data"]
                        full_answer = done_data.get("answer", full_answer)
                        metadata_extra = {
                            "method": done_data.get("method", "rag_memory_enhanced"),
                            "memory_used": done_data.get("memory_used", False),
                            "memory_count": done_data.get("memory_count", 0),
                        }
            
            else:
                # 3. 非 Retriever Agent（或 LLM 不可用时）：
                #    先执行 Agent 获取完整结果，再逐块流式发送
                try:
                    # 发送处理中状态
                    status_label = agent_labels.get(agent_type_used, agent_type_used)
                    yield f"data: {json.dumps({'type': 'status', 'data': {'stage': 'processing', 'message': f'{status_label}正在处理...'}}, ensure_ascii=False)}\n\n"
                    
                    response = await agent_coordinator.process(
                        query=request.query,
                        project_id=request.project_id,
                        agent_type=agent_type_used,
                        **request.params
                    )
                    
                    agent_type_used = response.agent_type
                    full_content = _normalize_agent_markdown(
                        response.content,
                        response.references or [],
                        response.agent_type,
                    )
                    references_data = response.references
                    metadata_extra = response.metadata
                    
                    # 发送引用
                    if references_data:
                        references_data = await _enrich_references_with_titles(
                            db, references_data
                        )
                        yield f"data: {json.dumps({'type': 'references', 'data': references_data}, ensure_ascii=False)}\n\n"
                    
                    # 发送生成中状态
                    yield f"data: {json.dumps({'type': 'status', 'data': {'stage': 'generating', 'message': '正在生成回复...'}}, ensure_ascii=False)}\n\n"
                    
                    # 逐块发送内容（模拟流式效果）
                    chunk_size = 20  # 每块约20字符
                    for i in range(0, len(full_content), chunk_size):
                        text_chunk = full_content[i:i + chunk_size]
                        full_answer += text_chunk
                        yield f"data: {json.dumps({'type': 'chunk', 'data': text_chunk}, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0.02)
                    
                except Exception as e:
                    logger.error(f"Agent execution failed in stream: {e}")
                    yield f"data: {json.dumps({'type': 'error', 'data': f'Agent处理失败: {str(e)}'}, ensure_ascii=False)}\n\n"
                    return
            
            # 4. 发送元数据
            if metadata_extra:
                yield f"data: {json.dumps({'type': 'metadata', 'data': metadata_extra}, ensure_ascii=False)}\n\n"
            
            # 5. 保存对话到数据库（追加到现有对话或创建新对话）
            conversation_id = None
            try:
                new_msgs = [
                    {"role": "user", "content": request.query},
                    {
                        "role": "assistant",
                        "content": full_answer,
                        "agent_type": agent_type_used,
                        "references": references_data or [],
                        **({"metadata": metadata_extra} if metadata_extra else {}),
                    }
                ]
                
                # 如果有现有对话，追加消息
                if request.conversation_id:
                    try:
                        conv_result = await db.execute(
                            select(Conversation).where(
                                Conversation.id == request.conversation_id,
                                Conversation.user_id == current_user.id
                            )
                        )
                        existing_conv = conv_result.scalar_one_or_none()
                        if existing_conv:
                            existing_msgs = existing_conv.messages or []
                            existing_conv.messages = existing_msgs + new_msgs
                            await db.commit()
                            await db.refresh(existing_conv)
                            conversation_id = existing_conv.id
                    except Exception as e:
                        logger.warning(f"Failed to append to conversation: {e}")
                
                # 否则创建新对话
                if conversation_id is None:
                    conversation = Conversation(
                        user_id=current_user.id,
                        project_id=request.project_id,
                        messages=new_msgs
                    )
                    db.add(conversation)
                    await db.commit()
                    await db.refresh(conversation)
                    conversation_id = conversation.id
            except Exception as e:
                logger.warning(f"Failed to save conversation in stream: {e}")
            
            # 6. 发送完成信号
            yield f"data: {json.dumps({'type': 'done', 'data': {'answer': full_answer, 'agent_type': agent_type_used, 'conversation_id': conversation_id}}, ensure_ascii=False)}\n\n"
        
        except Exception as e:
            logger.error(f"Agent stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)}, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
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


# ============ Knowledge Graph ============

class KGRequest(BaseModel):
    """知识图谱构建请求"""
    project_id: int
    max_entities: int = 30


@router.post("/knowledge-graph")
async def build_project_knowledge_graph(
    request: KGRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    基于项目文献内容构建知识图谱
    
    从项目中的 PDF 文本中提取实体和关系，
    返回 G6 兼容的 nodes/edges 格式。
    """
    if not agent_coordinator._initialized:
        await agent_coordinator.initialize(rag_engine)
    
    # 验证项目权限
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
    
    try:
        from app.models.paper import Paper
        from app.services.mongodb_service import mongodb_service
        
        # 1. 从 PostgreSQL 获取项目下的所有文献
        papers_result = await db.execute(
            select(Paper).where(
                Paper.project_id == request.project_id,
                Paper.status == "completed"
            )
        )
        papers = papers_result.scalars().all()
        
        if not papers:
            return {
                "nodes": [],
                "edges": [],
                "node_count": 0,
                "edge_count": 0,
                "message": "项目中没有已处理完成的文献"
            }
        
        # 2. 从 MongoDB (或内存回退) 获取各文献的文本分块
        paper_ids = [p.id for p in papers]
        text_parts = []
        
        chunks = await mongodb_service.get_project_chunks(
            paper_ids=paper_ids,
            limit_per_paper=10,
            limit=30
        )
        text_parts = [c.get("text", "") for c in chunks if c.get("text")]
        
        # 如果 MongoDB 没数据，尝试从 RAG 引擎的内存缓存获取
        if not text_parts and rag_engine and rag_engine._chunk_cache:
            for paper_id in paper_ids:
                for i in range(20):
                    cache_key = f"{paper_id}_{i}"
                    cached = rag_engine._chunk_cache.get(cache_key)
                    if cached:
                        text_parts.append(cached)
                    else:
                        break
                    if len(text_parts) >= 30:
                        break
        
        # 如果仍无数据，尝试用论文摘要
        if not text_parts:
            for paper in papers:
                if paper.abstract:
                    text_parts.append(paper.abstract)
        
        if not text_parts:
            return {
                "nodes": [],
                "edges": [],
                "node_count": 0,
                "edge_count": 0,
                "message": "项目中未找到文本内容"
            }
        
        # 3. 合并文本（截断到合理长度）
        combined_text = "\n\n".join(text_parts)[:8000]
        logger.info(f"Knowledge graph: collected {len(text_parts)} text parts, total {len(combined_text)} chars")
        
        # 4. 先尝试快速的正则/共现方法，再尝试 LLM
        #    快速方法: 立即返回结果（毫秒级）
        #    LLM方法: 可能需要几分钟
        import asyncio
        from app.skills.analysis.analysis_skills import _build_kg_regex, _build_kg_with_llm
        
        # 先用快速正则方法获得基础结果
        fast_result = _build_kg_regex(combined_text, request.max_entities)
        
        # 如果快速方法结果足够好（有节点和边），直接返回
        # 同时异步尝试 LLM 方法获取更好的结果
        if fast_result.get("node_count", 0) >= 3 and fast_result.get("edge_count", 0) >= 2:
            # 尝试用 LLM 增强，但设置超时
            try:
                llm_result = await asyncio.wait_for(
                    _build_kg_with_llm(combined_text, request.max_entities),
                    timeout=120.0  # 2分钟超时
                )
                if llm_result and llm_result.get("node_count", 0) > fast_result.get("node_count", 0):
                    return {
                        "nodes": llm_result.get("nodes", []),
                        "edges": llm_result.get("edges", []),
                        "node_count": llm_result.get("node_count", 0),
                        "edge_count": llm_result.get("edge_count", 0),
                    }
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"LLM KG enhancement timed out or failed: {e}, using fast result")
            
            return {
                "nodes": fast_result.get("nodes", []),
                "edges": fast_result.get("edges", []),
                "node_count": fast_result.get("node_count", 0),
                "edge_count": fast_result.get("edge_count", 0),
            }
        
        # 快速方法结果不够好，调用完整的 build_knowledge_graph Skill
        kg_result = await agent_coordinator.execute_skill(
            skill_name="build_knowledge_graph",
            text=combined_text,
            max_entities=request.max_entities,
        )
        
        if kg_result.get("success"):
            data = kg_result.get("data", {})
            return {
                "nodes": data.get("nodes", []),
                "edges": data.get("edges", []),
                "node_count": data.get("node_count", 0),
                "edge_count": data.get("edge_count", 0),
            }
        else:
            # LLM 也失败了，返回快速方法的结果（总比空的好）
            if fast_result.get("node_count", 0) > 0:
                return {
                    "nodes": fast_result.get("nodes", []),
                    "edges": fast_result.get("edges", []),
                    "node_count": fast_result.get("node_count", 0),
                    "edge_count": fast_result.get("edge_count", 0),
                }
            return {
                "nodes": [],
                "edges": [],
                "node_count": 0,
                "edge_count": 0,
                "error": kg_result.get("error", "构建失败")
            }
    except Exception as e:
        logger.error(f"Knowledge graph build failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"知识图谱构建失败: {str(e)}"
        )


# ============ Skills Routes ============

@router.get("/skills")
async def list_skills(
    category: Optional[str] = Query(
        None,
        description="按类别筛选: academic, analysis, utility",
    ),
    agent_type: Optional[str] = Query(
        None,
        description="查看指定 Agent 可用的 Skills",
    ),
    current_user: User = Depends(get_current_user),
):
    """
    列出所有可用的 Agent Skills
    
    可按类别（academic/analysis/utility）或指定Agent类型筛选。
    返回每个 Skill 的名称、描述、参数 Schema 和所属类别。
    """
    if not agent_coordinator._initialized:
        await agent_coordinator.initialize(rag_engine)
    
    try:
        if agent_type:
            skills = agent_coordinator.get_agent_skills(agent_type)
        else:
            skills = agent_coordinator.list_available_skills(category=category)
        
        return {
            "skills": skills,
            "total": len(skills),
            "filter": {
                "category": category,
                "agent_type": agent_type,
            },
        }
    except Exception as e:
        logger.error(f"List skills failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取技能列表失败: {str(e)}"
        )


@router.post("/skills/execute")
async def execute_skill(
    request: SkillExecuteRequest,
    current_user: User = Depends(get_current_user),
):
    """
    直接执行指定的 Skill
    
    用于调试或高级用户直接调用原子技能。
    需要提供 skill_name 和对应的 arguments。
    """
    if not agent_coordinator._initialized:
        await agent_coordinator.initialize(rag_engine)
    
    try:
        result = await agent_coordinator.execute_skill(
            skill_name=request.skill_name,
            **request.arguments,
        )
        
        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Skill 执行失败"),
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Execute skill failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Skill 执行失败: {str(e)}"
        )
