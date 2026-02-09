"""
API v1 路由注册
"""
from fastapi import APIRouter

from app.api.v1 import auth, projects, papers, rag, external, agents, trends, writing


api_router = APIRouter()

# 注册子路由
api_router.include_router(
    auth.router, 
    prefix="/auth", 
    tags=["认证"]
)

api_router.include_router(
    projects.router, 
    prefix="/projects", 
    tags=["项目管理"]
)

api_router.include_router(
    papers.router, 
    prefix="/papers", 
    tags=["文献管理"]
)

api_router.include_router(
    rag.router, 
    prefix="/rag", 
    tags=["RAG问答"]
)

api_router.include_router(
    external.router,
    prefix="/external",
    tags=["外部学术API"]
)

api_router.include_router(
    agents.router,
    prefix="/agent",
    tags=["Multi-Agent系统"]
)

api_router.include_router(
    trends.router,
    prefix="/trends",
    tags=["趋势分析"]
)

api_router.include_router(
    writing.router,
    prefix="/writing",
    tags=["写作辅助"]
)
