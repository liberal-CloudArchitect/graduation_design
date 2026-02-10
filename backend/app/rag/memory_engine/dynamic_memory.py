"""
Dynamic Memory Engine

动态记忆引擎实现，负责记忆的存储、检索和更新
"""
from typing import List, Dict, Any, Optional
from loguru import logger
import time

from .base import MemoryNode, BaseMemoryEngine
from .embedder import memory_embedder


def _sanitize(value):
    """将 Milvus 返回的 numpy 类型转换为 Python 原生类型，避免 JSON 序列化失败"""
    if value is None:
        return value
    type_name = type(value).__module__
    if type_name == "numpy":
        # numpy scalar -> Python scalar
        return value.item()
    return value


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
        """创建agent_memory Collection (pymilvus 2.3.x ORM API)"""
        if not self.milvus:
            return
        
        from pymilvus import (
            FieldSchema, CollectionSchema, DataType,
            Collection, connections, utility
        )
        from app.core.config import settings
        
        # 确保 ORM 连接存在
        alias = "default"
        if not connections.has_connection(alias):
            connections.connect(
                alias=alias,
                host=settings.MILVUS_HOST,
                port=settings.MILVUS_PORT
            )
        
        # 定义字段
        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=64),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=1024),
            FieldSchema(name="timestamp", dtype=DataType.INT64),
            FieldSchema(name="importance", dtype=DataType.FLOAT),
            FieldSchema(name="access_count", dtype=DataType.INT64),
            FieldSchema(name="memory_type", dtype=DataType.VARCHAR, max_length=32),
            FieldSchema(name="agent_source", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="project_id", dtype=DataType.INT64),
        ]
        
        schema = CollectionSchema(
            fields=fields,
            description="Agent memory storage",
            enable_dynamic_field=True
        )
        
        # 创建 Collection
        collection = Collection(
            name=self.COLLECTION_NAME,
            schema=schema,
            using=alias
        )
        
        # 创建向量索引
        index_params = {
            "index_type": "IVF_FLAT",
            "metric_type": "COSINE",
            "params": {"nlist": 128}
        }
        collection.create_index(field_name="embedding", index_params=index_params)
        collection.load()
        
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
                        id=str(entity.get("id", "")),
                        content=str(entity.get("content", "")),
                        embedding=[],  # 不返回向量以节省内存
                        timestamp=int(_sanitize(entity.get("timestamp", 0))),
                        importance=float(_sanitize(entity.get("importance", 1.0))),
                        access_count=int(_sanitize(entity.get("access_count", 0))),
                        memory_type=str(entity.get("memory_type", "dynamic")),
                        relations={},
                        agent_source=str(entity.get("agent_source", "qa_agent")),
                        project_id=int(_sanitize(entity.get("project_id", 0)))
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
                    id=str(entity.get("id", "")),
                    content=str(entity.get("content", "")),
                    embedding=[],
                    timestamp=int(_sanitize(entity.get("timestamp", 0))),
                    importance=float(_sanitize(entity.get("importance", 1.0))),
                    access_count=int(_sanitize(entity.get("access_count", 0))),
                    memory_type=str(entity.get("memory_type", "dynamic")),
                    relations={},
                    agent_source=str(entity.get("agent_source", "qa_agent")),
                    project_id=int(_sanitize(entity.get("project_id", 0)))
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
    
    async def list_memories(
        self,
        project_id: Optional[int] = None,
        memory_type: Optional[str] = None,
        agent_source: Optional[str] = None,
        offset: int = 0,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        分页列出记忆条目（基于标量过滤，非向量搜索）
        
        Args:
            project_id: 按项目筛选
            memory_type: 按类型筛选 (dynamic/reconstructive/cross_memory)
            agent_source: 按来源Agent筛选
            offset: 分页偏移
            limit: 每页数量
            
        Returns:
            {"items": [...], "total": int}
        """
        if not self.milvus:
            return {"items": [], "total": 0}
        
        try:
            # 构建过滤条件
            filters = []
            if project_id is not None:
                filters.append(f"project_id == {project_id}")
            if memory_type:
                filters.append(f'memory_type == "{memory_type}"')
            if agent_source:
                filters.append(f'agent_source == "{agent_source}"')
            
            filter_expr = " && ".join(filters) if filters else ""
            
            # 查询总量（用较大limit估算）
            count_results = self.milvus.query(
                collection_name=self.COLLECTION_NAME,
                filter=filter_expr if filter_expr else None,
                output_fields=["id"],
                limit=10000
            )
            total = len(count_results) if count_results else 0
            
            # 查询分页数据
            results = self.milvus.query(
                collection_name=self.COLLECTION_NAME,
                filter=filter_expr if filter_expr else None,
                output_fields=[
                    "id", "content", "timestamp", "importance",
                    "access_count", "memory_type", "agent_source", "project_id"
                ],
                limit=limit + offset
            )
            
            # 手动分页（Milvus query 不支持 offset）
            paged = results[offset:offset + limit] if results else []
            
            items = []
            for entity in paged:
                items.append({
                    "id": str(entity.get("id", "")),
                    "content": str(entity.get("content", "")),
                    "timestamp": int(_sanitize(entity.get("timestamp", 0))),
                    "importance": float(_sanitize(entity.get("importance", 1.0))),
                    "access_count": int(_sanitize(entity.get("access_count", 0))),
                    "memory_type": str(entity.get("memory_type", "dynamic")),
                    "agent_source": str(entity.get("agent_source", "qa_agent")),
                    "project_id": int(_sanitize(entity.get("project_id", 0))),
                })
            
            return {"items": items, "total": total}
            
        except Exception as e:
            logger.error(f"Failed to list memories: {e}")
            return {"items": [], "total": 0}
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取记忆系统统计信息"""
        if not self.milvus:
            return {"status": "disconnected"}
        
        try:
            type_breakdown = {}
            agent_breakdown = {}
            row_count = 0
            
            try:
                # 使用 query 代替 get_collection_stats（pymilvus 2.3.5 兼容）
                all_items = self.milvus.query(
                    collection_name=self.COLLECTION_NAME,
                    filter="",
                    output_fields=["memory_type", "agent_source"],
                    limit=10000
                )
                row_count = len(all_items or [])
                for item in (all_items or []):
                    mt = str(item.get("memory_type", "unknown"))
                    ag = str(item.get("agent_source", "unknown"))
                    type_breakdown[mt] = type_breakdown.get(mt, 0) + 1
                    agent_breakdown[ag] = agent_breakdown.get(ag, 0) + 1
            except Exception:
                pass
            
            return {
                "status": "connected",
                "collection": self.COLLECTION_NAME,
                "row_count": row_count,
                "type_breakdown": type_breakdown,
                "agent_breakdown": agent_breakdown,
            }
        except Exception as e:
            logger.error(f"Get stats failed: {e}")
            return {"status": "error", "message": str(e)}


# 全局引擎实例
dynamic_memory_engine = DynamicMemoryEngine()
