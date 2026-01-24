"""
Redis Service - 缓存服务
"""
from typing import Any, Optional
from loguru import logger
import json
from datetime import timedelta


class RedisService:
    """
    Redis缓存服务
    
    用于缓存问答结果、用户会话等
    """
    
    def __init__(self):
        self.client = None
        self._initialized = False
        self._use_fallback = False
        self._fallback_cache: dict = {}
    
    async def initialize(self, url: str = "redis://localhost:6379/0"):
        """初始化Redis连接"""
        if self._initialized:
            return
        
        try:
            import redis.asyncio as redis
            self.client = redis.from_url(url, decode_responses=True)
            # 测试连接
            await self.client.ping()
            self._initialized = True
            logger.info(f"Redis connected: {url}")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, using in-memory fallback")
            self._use_fallback = True
            self._initialized = True
    
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        if self._use_fallback:
            return self._fallback_cache.get(key)
        
        try:
            value = await self.client.get(key)
            if value:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return None
        except Exception as e:
            logger.error(f"Redis get failed: {e}")
            return None
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        expire: Optional[int] = None
    ) -> bool:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            expire: 过期时间（秒）
        """
        if self._use_fallback:
            self._fallback_cache[key] = value
            return True
        
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            await self.client.set(key, value, ex=expire)
            return True
        except Exception as e:
            logger.error(f"Redis set failed: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """删除缓存"""
        if self._use_fallback:
            self._fallback_cache.pop(key, None)
            return True
        
        try:
            await self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis delete failed: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        if self._use_fallback:
            return key in self._fallback_cache
        
        try:
            return await self.client.exists(key)
        except Exception as e:
            logger.error(f"Redis exists failed: {e}")
            return False
    
    # ========== RAG缓存专用方法 ==========
    
    async def cache_answer(
        self,
        question: str,
        project_id: int,
        answer: dict,
        expire: int = 3600  # 1小时
    ):
        """缓存RAG答案"""
        key = f"rag:answer:{project_id}:{hash(question)}"
        await self.set(key, answer, expire)
    
    async def get_cached_answer(
        self,
        question: str,
        project_id: int
    ) -> Optional[dict]:
        """获取缓存的答案"""
        key = f"rag:answer:{project_id}:{hash(question)}"
        return await self.get(key)
    
    async def cache_embeddings(
        self,
        text: str,
        embeddings: list,
        expire: int = 86400  # 24小时
    ):
        """缓存文本向量"""
        key = f"embedding:{hash(text)}"
        await self.set(key, embeddings, expire)
    
    async def get_cached_embeddings(self, text: str) -> Optional[list]:
        """获取缓存的向量"""
        key = f"embedding:{hash(text)}"
        return await self.get(key)
    
    # ========== 会话管理 ==========
    
    async def set_user_session(
        self,
        user_id: int,
        session_data: dict,
        expire: int = 86400
    ):
        """设置用户会话"""
        key = f"session:{user_id}"
        await self.set(key, session_data, expire)
    
    async def get_user_session(self, user_id: int) -> Optional[dict]:
        """获取用户会话"""
        key = f"session:{user_id}"
        return await self.get(key)
    
    @property
    def is_connected(self) -> bool:
        return self._initialized and not self._use_fallback


# 全局实例
redis_service = RedisService()
