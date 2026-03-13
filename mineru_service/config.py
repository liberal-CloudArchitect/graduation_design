"""
MinerU 解析服务配置
"""
import os


MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "100"))
TASK_TIMEOUT_SEC: int = int(os.getenv("TASK_TIMEOUT_SEC", "600"))
MAX_CONCURRENT: int = int(os.getenv("MAX_CONCURRENT", "1"))
BIND_HOST: str = os.getenv("BIND_HOST", "0.0.0.0")
BIND_PORT: int = int(os.getenv("BIND_PORT", "8010"))
API_KEY: str = os.getenv("API_KEY", "")

MINERU_MODEL_SOURCE: str = os.getenv("MINERU_MODEL_SOURCE", "local")
MINERU_TOOLS_CONFIG_JSON: str = os.getenv("MINERU_TOOLS_CONFIG_JSON", "")
MINERU_BACKEND: str = os.getenv("MINERU_BACKEND", "hybrid-http-client")
MINERU_PARSE_METHOD: str = os.getenv("MINERU_PARSE_METHOD", "auto")
MINERU_LANG: str = os.getenv("MINERU_LANG", "ch")
MINERU_SERVER_URL: str = os.getenv("MINERU_SERVER_URL", "")

GPU_MEMORY_UTILIZATION: float = float(os.getenv("GPU_MEMORY_UTILIZATION", "0.25"))
VLLM_SERVER_PORT: int = int(os.getenv("VLLM_SERVER_PORT", "30000"))
