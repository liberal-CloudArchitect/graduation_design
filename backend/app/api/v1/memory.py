"""
Memory System API - 记忆系统可视化与管理

提供记忆系统的查询、管理、重构演示、遗忘预览和跨Agent网络统计。
使后端核心创新（重构性记忆、动态遗忘、跨Agent记忆）对前端可见。
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from loguru import logger

from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter()


# ============ Schemas ============

class ReconstructRequest(BaseModel):
    """重构记忆演示请求"""
    query: str
    project_id: Optional[int] = None
    use_llm: bool = True


# ============ Helper: 延迟初始化 ============

async def _get_memory_engine():
    """延迟获取并初始化 DynamicMemoryEngine"""
    from app.rag.memory_engine.dynamic_memory import dynamic_memory_engine
    if not dynamic_memory_engine._initialized:
        await dynamic_memory_engine.initialize()
    return dynamic_memory_engine


async def _get_forgetting():
    """延迟获取并初始化遗忘机制"""
    from app.rag.memory_engine.forgetting import forgetting_mechanism
    if not forgetting_mechanism._initialized:
        engine = await _get_memory_engine()
        forgetting_mechanism.memory_engine = engine
        await forgetting_mechanism.initialize()
    return forgetting_mechanism


async def _get_cross_memory():
    """延迟获取跨Agent记忆网络"""
    from app.rag.memory_engine.cross_memory import cross_memory_network
    if not cross_memory_network._initialized:
        engine = await _get_memory_engine()
        cross_memory_network.memory_engine = engine
        await cross_memory_network.initialize()
    return cross_memory_network


async def _get_reconstructive():
    """延迟获取重构性记忆"""
    from app.rag.memory_engine.reconstructive import ReconstructiveMemory
    from app.rag import rag_engine
    engine = await _get_memory_engine()
    rm = ReconstructiveMemory(
        memory_engine=engine,
        llm=rag_engine.llm if rag_engine else None
    )
    await rm.initialize()
    return rm


# ============ Routes ============
# NOTE: 固定路径路由必须在 /{memory_id} 之前注册，否则会被路径参数匹配

@router.get("/stats")
async def memory_stats(
    current_user: User = Depends(get_current_user),
):
    """
    获取记忆系统聚合统计
    
    返回记忆总量、按类型/Agent分布、遗忘机制状态、跨Agent网络状态。
    """
    try:
        engine = await _get_memory_engine()
        engine_stats = await engine.get_stats()

        # 遗忘机制配置
        try:
            forgetting = await _get_forgetting()
            forgetting_config = {
                "decay_rate": forgetting.config.decay_rate,
                "protection_period_hours": forgetting.config.protection_period / 3600,
                "min_importance": forgetting.config.min_importance,
                "max_age_days": forgetting.config.max_age / 86400,
            }
        except Exception:
            forgetting_config = {"status": "unavailable"}

        # 跨Agent网络
        try:
            cross = await _get_cross_memory()
            cross_stats = cross.get_network_stats()
        except Exception:
            cross_stats = {"status": "unavailable"}

        return {
            "memory_engine": engine_stats,
            "forgetting": forgetting_config,
            "cross_memory": cross_stats,
        }
    except Exception as e:
        logger.error(f"Memory stats failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取记忆统计失败: {str(e)}"
        )


@router.get("/list")
async def list_memories(
    project_id: Optional[int] = Query(None, description="按项目筛选"),
    memory_type: Optional[str] = Query(None, description="按类型筛选: dynamic/reconstructive/cross_memory"),
    agent_source: Optional[str] = Query(None, description="按来源Agent筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    current_user: User = Depends(get_current_user),
):
    """
    分页列出记忆条目
    """
    try:
        engine = await _get_memory_engine()
        offset = (page - 1) * page_size
        result = await engine.list_memories(
            project_id=project_id,
            memory_type=memory_type,
            agent_source=agent_source,
            offset=offset,
            limit=page_size,
        )
        return {
            "items": result["items"],
            "total": result["total"],
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        logger.error(f"List memories failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取记忆列表失败: {str(e)}"
        )


@router.get("/decay-preview")
async def decay_preview(
    project_id: Optional[int] = Query(None, description="按项目筛选"),
    current_user: User = Depends(get_current_user),
):
    """
    遗忘衰减预览
    
    返回每条记忆的当前重要性 vs 衰减后重要性，
    以及保护状态和是否应被遗忘。
    """
    try:
        engine = await _get_memory_engine()
        forgetting = await _get_forgetting()

        # 获取最近记忆
        memories = await engine.retrieve(
            query="",
            project_id=project_id,
            top_k=50
        )

        previews = forgetting.get_decay_preview(memories)
        
        # 统计
        protected_count = sum(1 for p in previews if p["is_protected"])
        forget_count = sum(1 for p in previews if p["should_forget"])
        decaying_count = len(previews) - protected_count - forget_count

        return {
            "previews": previews,
            "summary": {
                "total": len(previews),
                "protected": protected_count,
                "decaying": decaying_count,
                "to_forget": forget_count,
            },
        }
    except Exception as e:
        logger.error(f"Decay preview failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"衰减预览失败: {str(e)}"
        )


@router.get("/cross-network")
async def cross_network_stats(
    current_user: User = Depends(get_current_user),
):
    """
    跨Agent记忆网络统计
    """
    try:
        cross = await _get_cross_memory()
        stats = cross.get_network_stats()
        agents = cross.get_registered_agents()
        return {
            "stats": stats,
            "registered_agents": agents,
        }
    except Exception as e:
        logger.error(f"Cross network stats failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"跨Agent网络统计失败: {str(e)}"
        )


# ---- 路径参数路由（必须在固定路径之后） ----

@router.get("/{memory_id}")
async def get_memory(
    memory_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    获取单条记忆详情
    """
    try:
        engine = await _get_memory_engine()
        memory = await engine.get_memory_by_id(memory_id)
        if not memory:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="记忆不存在"
            )
        return {
            "id": memory.id,
            "content": memory.content,
            "timestamp": memory.timestamp,
            "importance": memory.importance,
            "access_count": memory.access_count,
            "memory_type": memory.memory_type,
            "agent_source": memory.agent_source,
            "project_id": memory.project_id,
            "relations": memory.relations,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get memory failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取记忆详情失败: {str(e)}"
        )


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    删除指定记忆
    """
    try:
        engine = await _get_memory_engine()
        success = await engine.delete_memory(memory_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="删除失败"
            )
        return {"message": "记忆已删除", "memory_id": memory_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete memory failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除记忆失败: {str(e)}"
        )


@router.post("/reconstruct")
async def reconstruct_memory(
    request: ReconstructRequest,
    current_user: User = Depends(get_current_user),
):
    """
    重构记忆演示（Trace → Expand → Reconstruct）
    
    返回完整的中间过程：
    - cue: 结构化线索
    - trace_seeds: 初始检索到的记忆片段
    - expanded: 时序扩展后的完整片段集
    - reconstruction: 最终重构内容
    - timing: 各阶段耗时
    """
    import time

    try:
        rm = await _get_reconstructive()

        # Step 1: Trace - 提取线索
        t0 = time.time()
        cue = await rm._cue_extractor.extract(request.query)
        t_cue = time.time()

        # Step 2: Trace - 检索种子
        trace_results = await rm._trace(cue, request.project_id)
        t_trace = time.time()

        # Step 3: Expand - 时序扩展
        expanded = await rm._expand(trace_results, request.project_id)
        t_expand = time.time()

        # Step 4: Reconstruct
        if request.use_llm and rm.llm:
            content, confidence = await rm._reconstruct_with_llm(
                request.query, expanded
            )
            is_reconstructed = True
        else:
            content, confidence = rm._reconstruct_simple(expanded)
            is_reconstructed = False
        t_reconstruct = time.time()

        def _memory_to_dict(m):
            return {
                "id": m.id,
                "content": m.content[:300],
                "timestamp": m.timestamp,
                "importance": m.importance,
                "memory_type": m.memory_type,
                "agent_source": m.agent_source,
            }

        return {
            "cue": cue.to_dict() if hasattr(cue, "to_dict") else {"topic": str(cue)},
            "trace_seeds": [_memory_to_dict(m) for m in trace_results],
            "expanded": [_memory_to_dict(m) for m in expanded],
            "reconstruction": {
                "content": content,
                "confidence": confidence,
                "is_reconstructed": is_reconstructed,
                "fragment_count": len(expanded),
            },
            "timing": {
                "cue_extraction_ms": round((t_cue - t0) * 1000, 1),
                "trace_ms": round((t_trace - t_cue) * 1000, 1),
                "expand_ms": round((t_expand - t_trace) * 1000, 1),
                "reconstruct_ms": round((t_reconstruct - t_expand) * 1000, 1),
                "total_ms": round((t_reconstruct - t0) * 1000, 1),
            },
        }
    except Exception as e:
        logger.error(f"Reconstruct memory failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"记忆重构失败: {str(e)}"
        )


@router.post("/cleanup")
async def run_cleanup(
    project_id: Optional[int] = Query(None),
    dry_run: bool = Query(True, description="是否仅模拟（不实际删除）"),
    current_user: User = Depends(get_current_user),
):
    """
    执行记忆清理（遗忘）
    """
    try:
        forgetting = await _get_forgetting()
        deleted_count = await forgetting.cleanup(
            project_id=project_id,
            dry_run=dry_run,
        )
        return {
            "deleted_count": deleted_count,
            "dry_run": dry_run,
            "message": f"{'模拟' if dry_run else '已'}清理 {deleted_count} 条记忆",
        }
    except Exception as e:
        logger.error(f"Memory cleanup failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"记忆清理失败: {str(e)}"
        )
