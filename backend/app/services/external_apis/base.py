"""
外部API基类 - 提供限流、重试、缓存等通用功能
"""
import asyncio
import time
from typing import Any, Dict, Optional
from loguru import logger
import httpx


class BaseAPIClient:
    """外部API客户端基类"""
    
    BASE_URL: str = ""
    RATE_LIMIT: float = 1.0  # 每秒最大请求数
    MAX_RETRIES: int = 3
    TIMEOUT: float = 30.0
    
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._last_request_time: float = 0.0
        self._cache: Dict[str, Any] = {}
        self._cache_ttl: Dict[str, float] = {}
        self._cache_duration: float = 300.0  # 缓存5分钟
    
    async def _get_client(self) -> httpx.AsyncClient:
        """获取HTTP客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.TIMEOUT,
                headers=self._default_headers(),
                follow_redirects=True
            )
        return self._client
    
    def _default_headers(self) -> Dict[str, str]:
        """默认请求头"""
        return {
            "User-Agent": "LiterAI-Platform/1.0 (Academic Research Tool)",
            "Accept": "application/json"
        }
    
    async def _rate_limit(self):
        """限流控制"""
        if self.RATE_LIMIT <= 0:
            return
        min_interval = 1.0 / self.RATE_LIMIT
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)
        self._last_request_time = time.time()
    
    def _get_cache(self, key: str) -> Optional[Any]:
        """获取缓存"""
        if key in self._cache:
            if time.time() < self._cache_ttl.get(key, 0):
                return self._cache[key]
            else:
                del self._cache[key]
                del self._cache_ttl[key]
        return None
    
    def _set_cache(self, key: str, value: Any):
        """设置缓存"""
        self._cache[key] = value
        self._cache_ttl[key] = time.time() + self._cache_duration
    
    async def _request(
        self,
        method: str,
        url: str,
        params: Optional[Dict] = None,
        json: Optional[Dict] = None,
        cache_key: Optional[str] = None
    ) -> Optional[Dict]:
        """
        发送HTTP请求，带重试和限流
        """
        # 检查缓存
        if cache_key:
            cached = self._get_cache(cache_key)
            if cached is not None:
                return cached
        
        client = await self._get_client()
        
        for attempt in range(self.MAX_RETRIES):
            await self._rate_limit()
            
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if cache_key:
                        self._set_cache(cache_key, data)
                    return data
                elif response.status_code == 429:
                    # Rate limited
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning(f"Rate limited, waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                elif response.status_code >= 500:
                    logger.warning(f"Server error {response.status_code}, retrying...")
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.error(f"API error: {response.status_code} - {response.text[:200]}")
                    return None
                    
            except httpx.TimeoutException:
                logger.warning(f"Timeout on attempt {attempt + 1}")
                await asyncio.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"Request failed: {e}")
                if attempt == self.MAX_RETRIES - 1:
                    return None
                await asyncio.sleep(2 ** attempt)
        
        return None
    
    async def close(self):
        """关闭客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
