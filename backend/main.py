"""
FastAPI Main Application
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.core.config import settings
from app.models import init_db, close_db
from app.rag import rag_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    
    # 初始化数据库 (可选，失败不阻止启动)
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"Database initialization failed: {e}")
        logger.warning("Application will start without database connection")
    
    # 初始化RAG引擎
    await rag_engine.initialize()
    
    yield
    
    # 关闭时
    try:
        await close_db()
    except Exception:
        pass
    logger.info("Application shutdown")


# 创建FastAPI应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="基于RAG的文献分析大数据平台",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 根路由
@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running"
    }


# 健康检查
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": "connected",
        "rag_engine": "initialized"
    }


# 注册API路由 (待实现)
# from app.api.v1 import auth, papers, rag, analysis
# app.include_router(auth.router, prefix="/api/v1/auth", tags=["认证"])
# app.include_router(papers.router, prefix="/api/v1/papers", tags=["文献"])
# app.include_router(rag.router, prefix="/api/v1/rag", tags=["RAG问答"])
# app.include_router(analysis.router, prefix="/api/v1/analysis", tags=["分析"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
