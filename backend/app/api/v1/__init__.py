"""
API v1 路由注册
"""
from fastapi import APIRouter

from app.api.v1 import auth, projects, papers, rag


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
