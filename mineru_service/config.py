"""
MinerU 解析服务配置
"""
import os


MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "100"))
TASK_TIMEOUT_SEC: int = int(os.getenv("TASK_TIMEOUT_SEC", "600"))
MAX_CONCURRENT: int = int(os.getenv("MAX_CONCURRENT", "1"))
MAX_QUEUE_SIZE: int = int(os.getenv("MAX_QUEUE_SIZE", "16"))
BIND_HOST: str = os.getenv("BIND_HOST", "0.0.0.0")
BIND_PORT: int = int(os.getenv("BIND_PORT", "8010"))
API_KEY: str = os.getenv("API_KEY", "")

ENABLE_CPU_OVERFLOW_FALLBACK: bool = os.getenv(
    "ENABLE_CPU_OVERFLOW_FALLBACK", "true"
).lower() in {"1", "true", "yes", "on"}
GPU_MIN_FREE_MB: int = int(os.getenv("GPU_MIN_FREE_MB", "1024"))
GPU_PRESSURE_CPU_FALLBACK: bool = os.getenv(
    "GPU_PRESSURE_CPU_FALLBACK", "true"
).lower() in {"1", "true", "yes", "on"}
CUDA_OOM_CPU_FALLBACK: bool = os.getenv(
    "CUDA_OOM_CPU_FALLBACK", "true"
).lower() in {"1", "true", "yes", "on"}

MINERU_MODEL_SOURCE: str = os.getenv("MINERU_MODEL_SOURCE", "local")
MINERU_TOOLS_CONFIG_JSON: str = os.getenv("MINERU_TOOLS_CONFIG_JSON", "")
MINERU_BACKEND: str = os.getenv("MINERU_BACKEND", "hybrid-http-client")
MINERU_PARSE_METHOD: str = os.getenv("MINERU_PARSE_METHOD", "auto")
MINERU_LANG: str = os.getenv("MINERU_LANG", "ch")
MINERU_SERVER_URL: str = os.getenv("MINERU_SERVER_URL", "")

# Pipeline model device: "cpu" offloads layout/OCR/formula models to system RAM,
# freeing GPU VRAM exclusively for vLLM.  Recommended "cpu" for <=8 GB GPUs.
PIPELINE_DEVICE: str = os.getenv("PIPELINE_DEVICE", "cpu")

# When hybrid (VLM) parse fails, try pipeline-only before falling back to PyMuPDF.
PIPELINE_FALLBACK_ENABLED: bool = os.getenv(
    "PIPELINE_FALLBACK_ENABLED", "true"
).lower() in {"1", "true", "yes", "on"}

# vLLM: fraction of *total* GPU memory the engine may use (weights + KV cache).
# Too low (e.g. 0.25 on 8GB) can fail startup: model weights ~2.2GiB leave no KV budget.
GPU_MEMORY_UTILIZATION: float = float(os.getenv("GPU_MEMORY_UTILIZATION", "0.40"))
VLLM_SERVER_PORT: int = int(os.getenv("VLLM_SERVER_PORT", "30000"))
