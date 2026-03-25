# --------------------------------------------------------------------------
# MinerU PDF Parse Service — vLLM-accelerated
#
# Base: vllm/vllm-openai (includes CUDA 12.x, PyTorch, vLLM).
# RTX 5090 / Blackwell should prefer a CUDA 12.8+ image.
# If you need the older 4060 profile, build with:
#   --build-arg VLLM_BASE_IMAGE=vllm/vllm-openai:v0.10.1.1
#
# Two-process architecture inside the container:
#   1. mineru-openai-server — vLLM-based VLM inference (controls GPU memory)
#   2. app.py (uvicorn)     — FastAPI wrapper using hybrid-http-client backend
#
# Models are downloaded during build so the image is self-contained.
#
# Requires host driver supporting CUDA >= 12.8 (Driver >= 570).
# Preferred for RTX 5090 / Blackwell. Legacy 4060 users can pin an older image.
# --------------------------------------------------------------------------
ARG VLLM_BASE_IMAGE=vllm/vllm-openai:v0.11.2
FROM ${VLLM_BASE_IMAGE}

# System deps: PDF/image libs, CJK fonts
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        fonts-noto-core \
        fonts-noto-cjk \
        fontconfig \
        libgl1 \
        curl && \
    fc-cache -fv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# MinerU (reuses the PyTorch/CUDA already in vLLM image)
RUN python3 -m pip install --no-cache-dir -U 'mineru[core]>=2.7.0' --break-system-packages && \
    python3 -m pip cache purge

# Download ALL models (pipeline + VLM) during build.
# Pipeline models: layout/OCR/formula/table (~2-3GB)
# VLM model: ~2.5GB
# Switch to -s modelscope if HuggingFace is inaccessible.
RUN /bin/bash -c "mineru-models-download -s huggingface -m all"

WORKDIR /app

COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt --break-system-packages

COPY . .
RUN chmod +x /app/entrypoint.sh /app/start_service.sh /app/start_linux.sh

EXPOSE 8010

ENV MINERU_MODEL_SOURCE=local

ENTRYPOINT ["/app/entrypoint.sh"]
