"""
Memory Embedder

统一向量化接口，为记忆系统提供文本向量化能力
"""
from typing import List, Optional
from loguru import logger


class MemoryEmbedder:
    """
    记忆向量化器
    
    封装BGE-M3模型，提供统一的向量化接口
    """
    
    def __init__(self, model_path: Optional[str] = None):
        """
        初始化向量化器
        
        Args:
            model_path: 模型路径，None则使用配置默认值
        """
        self.model_path = model_path
        self.model = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """加载向量化模型"""
        if self._initialized:
            return
        
        from app.core.config import settings
        model_path = self.model_path or settings.BGE_MODEL_PATH
        
        try:
            from FlagEmbedding import BGEM3FlagModel
            self.model = BGEM3FlagModel(
                model_path,
                use_fp16=True
            )
            self._initialized = True
            logger.info(f"Memory embedder initialized: {model_path}")
        except Exception as e:
            logger.warning(f"Failed to load BGE-M3: {e}, using fallback")
            self.model = None
            self._initialized = True
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        将文本转换为向量
        
        Args:
            texts: 文本列表
            
        Returns:
            向量列表 (每个向量1024维)
        """
        if not texts:
            return []
        
        if self.model is None:
            # Fallback: 返回随机向量用于测试
            import numpy as np
            return np.random.randn(len(texts), 1024).astype(float).tolist()
        
        result = self.model.encode(texts, return_dense=True)
        return result['dense_vecs'].tolist()
    
    def embed_single(self, text: str) -> List[float]:
        """
        单文本向量化
        
        Args:
            text: 输入文本
            
        Returns:
            1024维向量
        """
        result = self.embed([text])
        return result[0] if result else []


# 全局向量化器实例
memory_embedder = MemoryEmbedder()
