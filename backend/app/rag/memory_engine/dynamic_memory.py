"""
Dynamic Memory Engine

动态记忆引擎实现，负责记忆的存储、检索和更新
"""
from typing import List, Dict, Any, Optional
from loguru import logger
import time

from .base import MemoryNode, BaseMemoryEngine
from .embedder import memory_embedder


class DynamicMemoryEngine(BaseMemoryEngine):
    """
    动态记忆引擎
    
    基于Milvus实现的记忆存储和检索系统
    
    使用方式:
        engine = DynamicMemoryEngine()
        await engine.initialize()
        
        # 添加记忆
        memory = await engine.add_memory("问答内容...", {"project_id": 1})
        
        # 检索记忆
        results = await engine.retrieve("查询问题", project_id=1, top_k=5)
    """
    
    COLLECTION_NAME = "agent_memory"
    
    def __init__(self):
        self.milvus = None
        self.embedder = memory_embedder
        self._initialized = False
    
    async def initialize(self) -> None:
        """初始化动态记忆引擎"""
        if self._initialized:
            return
        
        logger.info("Initializing Dynamic Memory Engine...")
        
        # 初始化向量化器
        await self.embedder.initialize()
        
        # 初始化Milvus连接
        await self._init_milvus()
        
        # 确保Collection存在
        await self._ensure_collection()
        
        self._initialized = True
        logger.info("Dynamic Memory Engine initialized successfully")
    
    async def _init_milvus(self) -> None:
        """初始化Milvus客户端"""
        try:
            from pymilvus import MilvusClient
            from app.core.config import settings
            
            self.milvus = MilvusClient(
                uri=f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}"
            )
            logger.info(f"Connected to Milvus for memory storage")
        except Exception as e:
            logger.warning(f"Milvus connection failed: {e}")
            self.milvus = None
    
    async def _ensure_collection(self) -> None:
        """确保agent_memory Collection存在"""
        if not self.milvus:
            return
        
        try:
            collections = self.milvus.list_collections()
            if self.COLLECTION_NAME in collections:
                logger.info(f"Collection '{self.COLLECTION_NAME}' already exists")
                return
            
            # 创建Collection
            await self._create_collection()
        except Exception as e:
            logger.error(f"Failed to ensure collection: {e}")
    
    async def _create_collection(self) -> None:
        """创建agent_memory Collection"""
        if not self.milvus:
            return
        
        from pymilvus import DataType
        
        # 创建schema
        schema = self.milvus.create_schema(
            auto_id=False,
            enable_dynamic_field=True
        )
        
        # 添加字段
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=64)
        schema.add_field("content", DataType.VARCHAR, max_length=65535)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=1024)
        schema.add_field("timestamp", DataType.INT64)
        schema.add_field("importance", DataType.FLOAT)
        schema.add_field("access_count", DataType.INT64)
        schema.add_field("memory_type", DataType.VARCHAR, max_length=32)
        schema.add_field("agent_source", DataType.VARCHAR, max_length=64)
        schema.add_field("project_id", DataType.INT64)
        
        # 创建索引
        index_params = self.milvus.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="IVF_FLAT",
            metric_type="COSINE",
            params={"nlist": 128}
        )
        
        # 创建collection
        self.milvus.create_collection(
            collection_name=self.COLLECTION_NAME,
            schema=schema,
            index_params=index_params
        )
        
        logger.info(f"Created collection: {self.COLLECTION_NAME}")
    
    async def add_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> MemoryNode:
        """
        添加新记忆
        
        Args:
            content: 记忆内容
            metadata: 元数据 (project_id, agent_source等)
            
        Returns:
            创建的MemoryNode
        """
        metadata = metadata or {}
        
        # 向量化
        embedding = self.embedder.embed_single(content)
        
        # 计算重要性
        importance = self._compute_importance(content)
        
        # 创建记忆节点
        memory = MemoryNode.create(
            content=content,
            embedding=embedding,
            importance=importance,
            memory_type="dynamic",
            agent_source=metadata.get("agent_source", "qa_agent"),
            project_id=metadata.get("project_id", 0)
        )
        
        # 存储到Milvus
        if self.milvus:
            try:
                data = memory.to_dict()
                # relations字段单独处理 (Milvus不支持嵌套JSON作为标量字段)
                data.pop("relations", None)
                
                self.milvus.insert(
                    collection_name=self.COLLECTION_NAME,
                    data=[data]
                )
                logger.debug(f"Memory stored: {memory.id[:8]}...")
            except Exception as e:
                logger.error(f"Failed to store memory: {e}")
        
        return memory
    
    async def retrieve(
        self,
        query: str,
        project_id: Optional[int] = None,
        top_k: int = 5
    ) -> List[MemoryNode]:
        """
        检索相关记忆
        
        Args:
            query: 查询文本
            project_id: 项目ID筛选
            top_k: 返回数量
            
        Returns:
            相关的MemoryNode列表
        """
        if not self.milvus:
            return []
        
        # 向量化查询
        query_embedding = self.embedder.embed_single(query)
        
        # 构建过滤条件
        filter_expr = None
        if project_id is not None:
            filter_expr = f"project_id == {project_id}"
        
        try:
            # 执行向量搜索
            results = self.milvus.search(
                collection_name=self.COLLECTION_NAME,
                data=[query_embedding],
                limit=top_k,
                filter=filter_expr,
                output_fields=[
                    "id", "content", "timestamp", "importance",
                    "access_count", "memory_type", "agent_source", "project_id"
                ]
            )
            
            # 转换为MemoryNode列表
            memories = []
            if results and len(results) > 0:
                for hit in results[0]:
                    entity = hit.get("entity", {})
                    memory = MemoryNode(
                        id=entity.get("id", ""),
                        content=entity.get("content", ""),
                        embedding=[],  # 不返回向量以节省内存
                        timestamp=entity.get("timestamp", 0),
                        importance=entity.get("importance", 1.0),
                        access_count=entity.get("access_count", 0),
                        memory_type=entity.get("memory_type", "dynamic"),
                        relations={},
                        agent_source=entity.get("agent_source", "qa_agent"),
                        project_id=entity.get("project_id", 0)
                    )
                    memories.append(memory)
                    
                    # 异步更新访问计数
                    await self.update_access(memory.id)
            
            logger.debug(f"Retrieved {len(memories)} memories for query")
            return memories
            
        except Exception as e:
            logger.error(f"Memory retrieval failed: {e}")
            return []
    
    async def update_access(self, memory_id: str) -> bool:
        """
        更新记忆访问计数
        
        Args:
            memory_id: 记忆ID
            
        Returns:
            是否更新成功
        """
        if not self.milvus:
            return False
        
        try:
            # Milvus不直接支持原子更新，需要先查询再更新
            # 这里简化处理，实际生产环境可以使用Redis计数器
            # TODO: 使用Redis进行访问计数的原子更新
            return True
        except Exception as e:
            logger.error(f"Failed to update access count: {e}")
            return False
    
    def _compute_importance(self, content: str) -> float:
        """
        计算记忆重要性
        
        简单启发式规则:
        - 内容长度
        - 是否包含关键词
        
        Args:
            content: 记忆内容
            
        Returns:
            重要性分数 (0-1)
        """
        base_score = 0.5
        
        # 长度因子: 较长的内容可能更重要
        length_factor = min(len(content) / 1000, 0.3)
        
        # 关键词因子
        keywords = ["重要", "关键", "核心", "结论", "发现", "important", "key", "conclusion"]
        keyword_factor = 0.2 if any(kw in content.lower() for kw in keywords) else 0
        
        importance = min(base_score + length_factor + keyword_factor, 1.0)
        return round(importance, 2)
    
    async def get_memory_by_id(self, memory_id: str) -> Optional[MemoryNode]:
        """根据ID获取记忆"""
        if not self.milvus:
            return None
        
        try:
            results = self.milvus.query(
                collection_name=self.COLLECTION_NAME,
                filter=f'id == "{memory_id}"',
                output_fields=["id", "content", "timestamp", "importance", 
                              "access_count", "memory_type", "agent_source", "project_id"]
            )
            
            if results:
                entity = results[0]
                return MemoryNode(
                    id=entity.get("id", ""),
                    content=entity.get("content", ""),
                    embedding=[],
                    timestamp=entity.get("timestamp", 0),
                    importance=entity.get("importance", 1.0),
                    access_count=entity.get("access_count", 0),
                    memory_type=entity.get("memory_type", "dynamic"),
                    relations={},
                    agent_source=entity.get("agent_source", "qa_agent"),
                    project_id=entity.get("project_id", 0)
                )
            return None
        except Exception as e:
            logger.error(f"Failed to get memory by ID: {e}")
            return None
    
    async def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        if not self.milvus:
            return False
        
        try:
            self.milvus.delete(
                collection_name=self.COLLECTION_NAME,
                filter=f'id == "{memory_id}"'
            )
            logger.info(f"Deleted memory: {memory_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete memory: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取记忆系统统计信息"""
        if not self.milvus:
            return {"status": "disconnected"}
        
        try:
            stats = self.milvus.get_collection_stats(self.COLLECTION_NAME)
            return {
                "status": "connected",
                "collection": self.COLLECTION_NAME,
                "row_count": stats.get("row_count", 0)
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}


# 全局引擎实例
dynamic_memory_engine = DynamicMemoryEngine()
