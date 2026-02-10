"""
FastAPI Main Application
"""
import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.core.config import settings
from app.models import init_db, close_db
from app.rag import rag_engine
from app.services.mongodb_service import mongodb_service
from app.services.redis_service import redis_service
from app.agents.coordinator import agent_coordinator


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
    
    # 初始化MongoDB (可选)
    try:
        await mongodb_service.initialize(
            uri=settings.MONGODB_URI,
            db_name=settings.MONGODB_DB
        )
    except Exception as e:
        logger.warning(f"MongoDB initialization failed: {e}")
    
    # 初始化Redis (可选)
    try:
        await redis_service.initialize(url=settings.REDIS_URL)
    except Exception as e:
        logger.warning(f"Redis initialization failed: {e}")
    
    # 初始化RAG引擎
    await rag_engine.initialize()
    
    # 初始化Agent协调器
    try:
        await agent_coordinator.initialize(rag_engine)
        logger.info("Agent coordinator initialized")
    except Exception as e:
        logger.warning(f"Agent coordinator initialization failed: {e}")
    
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
    redoc_url=None
)


# 自定义ReDoc路由
from fastapi.responses import HTMLResponse

@app.get("/redoc", include_in_schema=False)
async def custom_redoc():
    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
    <title>文献分析大数据平台 - ReDoc</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
    <style>
        body { margin: 0; padding: 0; }
    </style>
</head>
<body>
    <redoc spec-url='/openapi.json'></redoc>
    <script src="https://unpkg.com/redoc@latest/bundles/redoc.standalone.js"></script>
</body>
</html>
""")

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
        "mongodb": "connected" if mongodb_service.is_connected else "fallback",
        "redis": "connected" if redis_service.is_connected else "fallback",
        "rag_engine": "initialized" if rag_engine._initialized else "not_ready",
        "agent_system": "initialized" if agent_coordinator._initialized else "not_ready",
        "agents_count": len(agent_coordinator.agents) if agent_coordinator._initialized else 0
    }


# 注册API路由
from app.api.v1 import api_router
app.include_router(api_router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )

