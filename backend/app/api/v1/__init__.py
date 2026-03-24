"""API v1 route registry.

Build the router lazily so importing a specific submodule like
``app.api.v1.rag`` does not eagerly load every route module and its runtime
dependencies.
"""

from typing import Any, Optional

from fastapi import APIRouter


_api_router: Optional[APIRouter] = None


def _build_api_router() -> APIRouter:
    from . import agents, auth, external, memory, papers, projects, rag, trends, writing

    router = APIRouter()

    router.include_router(auth.router, prefix="/auth", tags=["认证"])
    router.include_router(projects.router, prefix="/projects", tags=["项目管理"])
    router.include_router(papers.router, prefix="/papers", tags=["文献管理"])
    router.include_router(rag.router, prefix="/rag", tags=["RAG问答"])
    router.include_router(external.router, prefix="/external", tags=["外部学术API"])
    router.include_router(agents.router, prefix="/agent", tags=["Multi-Agent系统"])
    router.include_router(trends.router, prefix="/trends", tags=["趋势分析"])
    router.include_router(writing.router, prefix="/writing", tags=["写作辅助"])
    router.include_router(memory.router, prefix="/memory", tags=["记忆系统"])

    return router


def __getattr__(name: str) -> Any:
    global _api_router

    if name == "api_router":
        if _api_router is None:
            _api_router = _build_api_router()
        return _api_router
    raise AttributeError(f"module 'app.api.v1' has no attribute {name!r}")
