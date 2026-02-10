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
from app.models.paper import Conversation
from app.agents.coordinator import agent_coordinator
from app.agents.base_agent import AgentType
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
            # 1. 发送路由信息
            agent_labels = {
                "retriever_agent": "文献检索Agent",
                "analyzer_agent": "趋势分析Agent",
                "writer_agent": "写作辅助Agent",
                "search_agent": "学术搜索Agent",
            }
            yield f"data: {json.dumps({'type': 'routing', 'data': {'agent_type': agent_type_used, 'label': agent_labels.get(agent_type_used, agent_type_used)}}, ensure_ascii=False)}\n\n"
            
            # 2. 对于 RetrieverAgent，使用流式 LLM 输出
            if agent_type_used == "retriever_agent" and rag_engine.llm:
                # 2a. 先检索文档
                search_results = await rag_engine.search(
                    request.query,
                    request.project_id,
                    request.params.get("top_k", 5)
                )
                
                # 发送引用
                if search_results:
                    docs = await rag_engine._fetch_documents(search_results)
                    references_data = docs
                    yield f"data: {json.dumps({'type': 'references', 'data': docs}, ensure_ascii=False)}\n\n"
                else:
                    docs = []
                
                # 2b. 获取记忆上下文（如果可用）
                memory_results = []
                if rag_engine.memory_engine:
                    try:
                        memory_results = await rag_engine.memory_engine.retrieve(
                            request.query, request.project_id, top_k=3
                        )
                    except Exception as e:
                        logger.warning(f"Memory retrieval failed in stream: {e}")
                
                # 2c. 构建上下文
                context = rag_engine._build_context_with_memory(docs, memory_results)
                
                # 2d. 流式生成答案
                prompt = f"""根据以下参考资料回答用户问题。

参考资料:
{context}

用户问题: {request.query}

要求:
1. 仅基于提供的参考资料回答
2. 如有引用，使用[1][2]格式标注
3. 如果资料中没有相关信息，请明确说明
4. 如有历史对话记忆相关内容，可适当参考
"""
                async for chunk in rag_engine.llm.astream(prompt):
                    if hasattr(chunk, 'content') and chunk.content:
                        full_answer += chunk.content
                        yield f"data: {json.dumps({'type': 'chunk', 'data': chunk.content}, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0.01)
                
                metadata_extra = {
                    "method": "rag_memory_enhanced",
                    "memory_used": len(memory_results) > 0,
                    "memory_count": len(memory_results),
                }
                
                # 保存到记忆
                if rag_engine.memory_engine:
                    try:
                        await rag_engine.memory_engine.add_memory(
                            content=f"Q: {request.query}\nA: {full_answer}",
                            metadata={"project_id": request.project_id or 0, "agent_source": "retriever_agent"}
                        )
                    except Exception as e:
                        logger.warning(f"Failed to save memory in stream: {e}")
            
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
                    full_content = response.content
                    references_data = response.references
                    metadata_extra = response.metadata
                    
                    # 发送引用
                    if references_data:
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
            
            # 5. 保存对话到数据库（含元数据用于前端重渲染图表等）
            try:
                assistant_msg = {
                    "role": "assistant",
                    "content": full_answer,
                    "agent_type": agent_type_used,
                }
                if metadata_extra:
                    assistant_msg["metadata"] = metadata_extra
                
                conversation = Conversation(
                    user_id=current_user.id,
                    project_id=request.project_id,
                    messages=[
                        {"role": "user", "content": request.query},
                        assistant_msg
                    ]
                )
                db.add(conversation)
                await db.commit()
                await db.refresh(conversation)
                conversation_id = conversation.id
            except Exception as e:
                logger.warning(f"Failed to save conversation in stream: {e}")
                conversation_id = None
            
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
        # 1. 从 MongoDB 获取项目文献的文本摘要
        text_parts = []
        if rag_engine and hasattr(rag_engine, '_mongodb'):
            try:
                from app.services.mongodb_service import mongodb_service
                chunks = await mongodb_service.get_project_chunks(
                    request.project_id, limit=20
                )
                text_parts = [c.get("content", "") for c in chunks if c.get("content")]
            except Exception as e:
                logger.warning(f"Failed to fetch chunks from MongoDB: {e}")
        
        # 如果没有从 MongoDB 取到，尝试从 Milvus 搜索
        if not text_parts and rag_engine:
            try:
                results = await rag_engine.search("research methodology findings", request.project_id, top_k=10)
                docs = await rag_engine._fetch_documents(results)
                text_parts = [d.get("text", "") for d in docs if d.get("text")]
            except Exception:
                pass
        
        if not text_parts:
            return {
                "nodes": [],
                "edges": [],
                "node_count": 0,
                "edge_count": 0,
                "message": "项目中未找到文本内容"
            }
        
        # 2. 合并文本（截断到合理长度）
        combined_text = "\n\n".join(text_parts)[:6000]
        
        # 3. 调用 build_knowledge_graph Skill
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
