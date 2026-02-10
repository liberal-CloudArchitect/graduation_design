"""
MongoDB Service - 文档存储服务
"""
from typing import List, Dict, Any, Optional
from loguru import logger
from datetime import datetime


class MongoDBService:
    """
    MongoDB文档存储服务
    
    用于存储文献分块内容和元数据
    """
    
    def __init__(self):
        self.client = None
        self.db = None
        self._initialized = False
        self._use_fallback = False
        self._fallback_store: Dict[str, List[Dict]] = {}
    
    async def initialize(self, uri: str = "mongodb://localhost:27017/", db_name: str = "graduation_project"):
        """初始化MongoDB连接"""
        if self._initialized:
            return
        
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            self.client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
            # 测试连接
            await self.client.admin.command('ping')
            self.db = self.client[db_name]
            self._initialized = True
            logger.info(f"MongoDB connected: {uri}")
        except Exception as e:
            logger.warning(f"MongoDB connection failed: {e}, using in-memory fallback")
            self._use_fallback = True
            self._initialized = True
    
    async def insert_chunks(self, paper_id: int, chunks: List[Dict[str, Any]]) -> List[str]:
        """
        插入文献分块
        
        Args:
            paper_id: 文献ID
            chunks: 分块列表，每个包含 {text, index, page_number, metadata}
        """
        if self._use_fallback:
            return self._fallback_insert(paper_id, chunks)
        
        try:
            collection = self.db.paper_chunks
            docs = []
            for chunk in chunks:
                docs.append({
                    "paper_id": paper_id,
                    "chunk_index": chunk.get("index", 0),
                    "text": chunk.get("text", ""),
                    "page_number": chunk.get("page_number"),
                    "metadata": chunk.get("metadata", {}),
                    "created_at": datetime.utcnow()
                })
            
            result = await collection.insert_many(docs)
            return [str(id) for id in result.inserted_ids]
        except Exception as e:
            logger.error(f"MongoDB insert failed: {e}")
            return self._fallback_insert(paper_id, chunks)
    
    def _fallback_insert(self, paper_id: int, chunks: List[Dict]) -> List[str]:
        """内存回退存储"""
        key = f"paper_{paper_id}"
        if key not in self._fallback_store:
            self._fallback_store[key] = []
        
        ids = []
        for i, chunk in enumerate(chunks):
            doc_id = f"{paper_id}_{i}"
            self._fallback_store[key].append({
                "_id": doc_id,
                "paper_id": paper_id,
                "chunk_index": chunk.get("index", i),
                "text": chunk.get("text", ""),
                "page_number": chunk.get("page_number"),
            })
            ids.append(doc_id)
        
        return ids
    
    async def get_chunks(self, paper_id: int) -> List[Dict[str, Any]]:
        """获取文献分块"""
        if self._use_fallback:
            key = f"paper_{paper_id}"
            return self._fallback_store.get(key, [])
        
        try:
            collection = self.db.paper_chunks
            cursor = collection.find({"paper_id": paper_id}).sort("chunk_index", 1)
            chunks = await cursor.to_list(length=1000)
            return chunks
        except Exception as e:
            logger.error(f"MongoDB query failed: {e}")
            return []
    
    async def get_chunk_by_index(self, paper_id: int, chunk_index: int) -> Optional[Dict]:
        """获取指定分块"""
        if self._use_fallback:
            key = f"paper_{paper_id}"
            chunks = self._fallback_store.get(key, [])
            for chunk in chunks:
                if chunk.get("chunk_index") == chunk_index:
                    return chunk
            return None
        
        try:
            collection = self.db.paper_chunks
            chunk = await collection.find_one({
                "paper_id": paper_id,
                "chunk_index": chunk_index
            })
            return chunk
        except Exception as e:
            logger.error(f"MongoDB query failed: {e}")
            return None
    
    async def get_project_chunks(
        self, paper_ids: List[int], limit_per_paper: int = 10, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        获取项目下多篇文献的分块内容
        
        Args:
            paper_ids: 文献ID列表
            limit_per_paper: 每篇文献最多取多少分块
            limit: 总共最多返回多少分块
            
        Returns:
            分块列表
        """
        all_chunks = []
        for paper_id in paper_ids:
            if len(all_chunks) >= limit:
                break
            chunks = await self.get_chunks(paper_id)
            for chunk in chunks[:limit_per_paper]:
                if len(all_chunks) >= limit:
                    break
                all_chunks.append(chunk)
        return all_chunks
    
    async def delete_paper_chunks(self, paper_id: int) -> int:
        """删除文献所有分块"""
        if self._use_fallback:
            key = f"paper_{paper_id}"
            count = len(self._fallback_store.get(key, []))
            self._fallback_store.pop(key, None)
            return count
        
        try:
            collection = self.db.paper_chunks
            result = await collection.delete_many({"paper_id": paper_id})
            return result.deleted_count
        except Exception as e:
            logger.error(f"MongoDB delete failed: {e}")
            return 0
    
    async def store_parse_result(self, paper_id: int, result: Dict[str, Any]):
        """存储解析结果"""
        if self._use_fallback:
            self._fallback_store[f"parse_{paper_id}"] = [result]
            return
        
        try:
            collection = self.db.parse_results
            await collection.update_one(
                {"paper_id": paper_id},
                {"$set": {
                    "paper_id": paper_id,
                    "result": result,
                    "updated_at": datetime.utcnow()
                }},
                upsert=True
            )
        except Exception as e:
            logger.error(f"MongoDB store failed: {e}")
    
    @property
    def is_connected(self) -> bool:
        return self._initialized and not self._use_fallback


# 全局实例
mongodb_service = MongoDBService()
