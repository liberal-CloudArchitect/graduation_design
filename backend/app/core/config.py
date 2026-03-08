"""
Configuration Management
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """应用配置"""
    
    # 基础配置
    APP_NAME: str = "文献分析大数据平台"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # 数据库配置 - PostgreSQL
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "graduation_project"
    
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    @property
    def DATABASE_URL_SYNC(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    # MongoDB配置
    MONGODB_URI: str = "mongodb://localhost:27017/"
    MONGODB_DB: str = "graduation_project"
    
    # Redis配置
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Milvus配置
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    
    # Elasticsearch配置
    ES_HOST: str = "localhost"
    ES_PORT: int = 9200
    
    # JWT配置
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24小时
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # 统一 LLM 配置（OpenAI 兼容接口）
    # 默认切换为 DeepSeek 官方推理模型
    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: str = "https://api.deepseek.com"
    LLM_MODEL: str = "deepseek-reasoner"

    # 兼容旧变量（OpenRouter），保留以避免现有部署直接失效
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "tngtech/deepseek-r1t2-chimera:free"

    @property
    def EFFECTIVE_LLM_API_KEY(self) -> Optional[str]:
        return self.LLM_API_KEY or self.OPENROUTER_API_KEY

    @property
    def EFFECTIVE_LLM_BASE_URL(self) -> str:
        # 若显式配置了 LLM_API_KEY，优先使用 LLM_*；
        # 否则回退到 OPENROUTER_*，兼容旧部署。
        if self.LLM_API_KEY:
            return self.LLM_BASE_URL
        if self.OPENROUTER_API_KEY:
            return self.OPENROUTER_BASE_URL
        return self.LLM_BASE_URL

    @property
    def EFFECTIVE_LLM_MODEL(self) -> str:
        if self.LLM_API_KEY:
            return self.LLM_MODEL
        if self.OPENROUTER_API_KEY:
            return self.OPENROUTER_MODEL
        return self.LLM_MODEL
    
    # 文件存储
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB
    
    # RAG配置
    BGE_MODEL_PATH: str = "BAAI/bge-m3"
    CHUNK_SIZE: int = 1024       # 从 512 提升到 1024，适配学术论文段落
    CHUNK_OVERLAP: int = 128     # 从 50 提升到 128，减少上下文断裂
    RETRIEVAL_TOP_K: int = 5
    
    # Phase 1: MinerU 解析 (仅对复杂 PDF 生效, 简单 PDF 继续走现有管线)
    MINERU_ENABLED: bool = False
    MINERU_API_URL: str = "http://localhost:8010"
    PDF_PARSE_TIMEOUT: int = 120
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()
