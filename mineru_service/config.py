"""
MinerU 解析服务配置
"""
import os


MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "100"))
TASK_TIMEOUT_SEC: int = int(os.getenv("TASK_TIMEOUT_SEC", "300"))
MAX_CONCURRENT: int = int(os.getenv("MAX_CONCURRENT", "2"))
BIND_HOST: str = os.getenv("BIND_HOST", "0.0.0.0")
BIND_PORT: int = int(os.getenv("BIND_PORT", "8010"))
API_KEY: str = os.getenv("API_KEY", "")

MINERU_MODEL_PATH: str = os.getenv("MINERU_MODEL_PATH", "/models/MinerU2.5-2509-1.2B")
