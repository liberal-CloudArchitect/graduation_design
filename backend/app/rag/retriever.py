"""
Retriever - 混合检索器
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from loguru import logger
import asyncio


@dataclass
class RetrievalResult:
    """检索结果"""
    text: str
    score: float
    paper_id: int
    chunk_index: int
    page_number: Optional[int] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class VectorRetriever:
    """向量检索器 (Milvus)"""
    
    def __init__(self, collection_name: str = "paper_vectors"):
        self.collection_name = collection_name
        self.client = None
        self._initialized = False
    
    async def initialize(self, host: str = "localhost", port: int = 19530):
        """初始化Milvus连接"""
        if self._initialized:
            return
        
        try:
            from pymilvus import MilvusClient
            self.client = MilvusClient(uri=f"http://{host}:{port}")
            
            # 检查集合是否存在
            collections = self.client.list_collections()
            if self.collection_name not in collections:
                await self._create_collection()
            
            self._initialized = True
            logger.info(f"Vector retriever initialized: {self.collection_name}")
        except Exception as e:
            logger.warning(f"Milvus connection failed: {e}")
            self.client = None
    
    async def _create_collection(self):
        """创建向量集合"""
        if not self.client:
            return
        
        from pymilvus import DataType
        
        # 创建schema
        schema = self.client.create_schema(
            auto_id=True,
            enable_dynamic_field=True
        )
        
        schema.add_field("id", DataType.INT64, is_primary=True)
        schema.add_field("paper_id", DataType.INT64)
        schema.add_field("chunk_index", DataType.INT32)
        schema.add_field("page_number", DataType.INT32)
        schema.add_field("text", DataType.VARCHAR, max_length=65535)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=1024)
        
        # 创建索引
        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type="IVF_FLAT",
            metric_type="COSINE",
            params={"nlist": 128}
        )
        
        # 创建集合
        self.client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params
        )
        
        logger.info(f"Created collection: {self.collection_name}")
    
    async def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filter_expr: Optional[str] = None
    ) -> List[RetrievalResult]:
        """向量搜索"""
        if not self.client:
            return []
        
        try:
            results = self.client.search(
                collection_name=self.collection_name,
                data=[query_vector],
                limit=top_k,
                filter=filter_expr,
                output_fields=["paper_id", "chunk_index", "page_number", "text", "parent_id", "section_path"]
            )
            
            retrieval_results = []
            if results and len(results) > 0:
                for hit in results[0]:
                    entity = hit.get("entity", {})
                    result = RetrievalResult(
                        text=entity.get("text", ""),
                        score=hit.get("distance", 0),
                        paper_id=entity.get("paper_id", 0),
                        chunk_index=entity.get("chunk_index", 0),
                        page_number=entity.get("page_number"),
                        metadata={
                            "parent_id": entity.get("parent_id"),
                            "section_path": entity.get("section_path"),
                        },
                    )
                    retrieval_results.append(result)
            
            return retrieval_results
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    async def insert(
        self,
        paper_id: int,
        chunks: List[Dict[str, Any]],
        vectors: List[List[float]]
    ) -> List[int]:
        """插入向量"""
        if not self.client:
            return []
        
        try:
            data = []
            for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
                data.append({
                    "paper_id": paper_id,
                    "chunk_index": i,
                    "page_number": chunk.get("page_number", 0),
                    "text": chunk.get("text", "")[:65000],  # 限制长度
                    "vector": vector
                })
            
            result = self.client.insert(
                collection_name=self.collection_name,
                data=data
            )
            
            return result.get("ids", [])
        except Exception as e:
            logger.error(f"Vector insert failed: {e}")
            return []


class BM25Retriever:
    """BM25检索器 (Elasticsearch)"""
    
    def __init__(self, index_name: str = "paper_chunks"):
        self.index_name = index_name
        self.client = None
        self._initialized = False
        self._supports_project_filter = True
    
    async def initialize(self, host: str = "localhost", port: int = 9200):
        """初始化Elasticsearch连接"""
        if self._initialized:
            return
        
        try:
            from elasticsearch import AsyncElasticsearch
            self.client = AsyncElasticsearch(
                hosts=[f"http://{host}:{port}"],
                request_timeout=30
            )
            
            # 检查索引是否存在
            exists = await self.client.indices.exists(index=self.index_name)
            if not exists:
                await self._create_index()
                self._supports_project_filter = True
            else:
                self._supports_project_filter = await self._has_project_field()
            
            self._initialized = True
            logger.info(f"BM25 retriever initialized: {self.index_name}")
        except Exception as e:
            logger.warning(f"Elasticsearch connection failed: {e}")
            self.client = None

    async def _has_project_field(self) -> bool:
        """检测当前索引映射是否包含 project_id 字段"""
        if not self.client:
            return False
        try:
            mapping = await self.client.indices.get_mapping(index=self.index_name)
            props = (
                mapping.get(self.index_name, {})
                .get("mappings", {})
                .get("properties", {})
            )
            return "project_id" in props
        except Exception as e:
            logger.warning(f"Check project_id mapping failed: {e}")
            return False
    
    async def _create_index(self):
        """创建搜索索引"""
        if not self.client:
            return
        
        mappings = {
            "properties": {
                "project_id": {"type": "long"},
                "paper_id": {"type": "long"},
                "chunk_index": {"type": "integer"},
                "page_number": {"type": "integer"},
                "text": {
                    "type": "text",
                    "analyzer": "ik_max_word",
                    "search_analyzer": "ik_smart"
                },
                "text_en": {
                    "type": "text",
                    "analyzer": "english"
                },
                "parent_id": {"type": "keyword"},
                "section_path": {"type": "keyword"},
            }
        }
        
        settings = {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "analyzer": {
                    "default": {
                        "type": "standard"
                    }
                }
            }
        }
        
        try:
            await self.client.indices.create(
                index=self.index_name,
                body={"mappings": mappings, "settings": settings}
            )
            logger.info(f"Created index: {self.index_name}")
        except Exception as e:
            logger.warning(f"Using default index settings: {e}")
            await self.client.indices.create(index=self.index_name)
    
    async def search(
        self,
        query: str,
        top_k: int = 5,
        project_id: Optional[int] = None,
        paper_ids: Optional[List[int]] = None
    ) -> List[RetrievalResult]:
        """BM25搜索"""
        if not self.client:
            return []
        
        try:
            must_clauses = [
                {"multi_match": {
                    "query": query,
                    "fields": ["text", "text_en"],
                    "type": "best_fields"
                }}
            ]
            
            if project_id is not None and self._supports_project_filter:
                must_clauses.append({"term": {"project_id": project_id}})

            if paper_ids:
                must_clauses.append({"terms": {"paper_id": paper_ids}})
            
            response = await self.client.search(
                index=self.index_name,
                body={
                    "query": {"bool": {"must": must_clauses}},
                    "size": top_k,
                    "_source": ["paper_id", "chunk_index", "page_number", "text", "parent_id", "section_path"]
                }
            )
            
            results = []
            for hit in response["hits"]["hits"]:
                source = hit["_source"]
                results.append(RetrievalResult(
                    text=source.get("text", ""),
                    score=hit["_score"],
                    paper_id=source.get("paper_id", 0),
                    chunk_index=source.get("chunk_index", 0),
                    page_number=source.get("page_number"),
                    metadata={
                        "parent_id": source.get("parent_id"),
                        "section_path": source.get("section_path"),
                    },
                ))
            
            return results
        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []
    
    async def index(
        self,
        paper_id: int,
        project_id: Optional[int],
        chunks: List[Dict[str, Any]]
    ):
        """索引文档"""
        if not self.client:
            return
        
        try:
            for i, chunk in enumerate(chunks):
                doc = {
                    "project_id": project_id or 0,
                    "paper_id": paper_id,
                    "chunk_index": i,
                    "page_number": chunk.get("page_number", 0),
                    "text": chunk.get("text", ""),
                    "text_en": chunk.get("text", ""),
                    "parent_id": chunk.get("parent_id", ""),
                    "section_path": chunk.get("section_path", ""),
                }
                await self.client.index(
                    index=self.index_name,
                    body=doc
                )
            
            await self.client.indices.refresh(index=self.index_name)
        except Exception as e:
            logger.error(f"BM25 indexing failed: {e}")

    async def delete_paper(self, paper_id: int):
        """按 paper_id 删除索引文档"""
        if not self.client:
            return
        try:
            await self.client.delete_by_query(
                index=self.index_name,
                body={"query": {"term": {"paper_id": paper_id}}},
                refresh=True,
                conflicts="proceed",
            )
        except Exception as e:
            logger.warning(f"BM25 delete failed for paper {paper_id}: {e}")


class HybridRetriever:
    """
    混合检索器
    
    结合BM25和向量检索，使用RRF融合
    """
    
    def __init__(
        self,
        vector_weight: float = 0.5,
        bm25_weight: float = 0.5,
        rrf_k: int = 60
    ):
        self.vector_retriever = VectorRetriever()
        self.bm25_retriever = BM25Retriever()
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.rrf_k = rrf_k
        self._initialized = False
    
    async def initialize(
        self,
        milvus_host: str = "localhost",
        milvus_port: int = 19530,
        es_host: str = "localhost",
        es_port: int = 9200
    ):
        """初始化检索器"""
        if self._initialized:
            return
        
        await self.vector_retriever.initialize(milvus_host, milvus_port)
        await self.bm25_retriever.initialize(es_host, es_port)
        self._initialized = True
        logger.info("Hybrid retriever initialized")
    
    async def search(
        self,
        query: str,
        query_vector: List[float],
        top_k: int = 5,
        project_id: Optional[int] = None,
        paper_ids: Optional[List[int]] = None
    ) -> List[RetrievalResult]:
        """
        混合检索
        
        Args:
            query: 查询文本
            query_vector: 查询向量
            top_k: 返回数量
            paper_ids: 限定文献ID列表
            
        Returns:
            融合后的检索结果
        """
        # 并行执行两种检索
        filter_expr = None
        filter_parts = []
        if project_id is not None:
            filter_parts.append(f"project_id == {project_id}")
        if paper_ids:
            filter_parts.append(f"paper_id in {paper_ids}")
        if filter_parts:
            filter_expr = " && ".join(filter_parts)
        
        vector_task = self.vector_retriever.search(
            query_vector, 
            top_k * 2,  # 检索更多用于融合
            filter_expr
        )
        
        bm25_task = self.bm25_retriever.search(
            query,
            top_k * 2,
            project_id,
            paper_ids
        )
        
        vector_results, bm25_results = await asyncio.gather(
            vector_task, bm25_task
        )
        
        # RRF融合
        fused = self._rrf_fusion(vector_results, bm25_results)
        
        return fused[:top_k]
    
    def _rrf_fusion(
        self,
        vector_results: List[RetrievalResult],
        bm25_results: List[RetrievalResult]
    ) -> List[RetrievalResult]:
        """
        RRF (Reciprocal Rank Fusion) 融合
        
        score = sum(1 / (k + rank))
        """
        scores = {}
        results_map = {}
        
        # 处理向量检索结果
        for rank, result in enumerate(vector_results):
            key = (result.paper_id, result.chunk_index)
            score = self.vector_weight * (1 / (self.rrf_k + rank + 1))
            scores[key] = scores.get(key, 0) + score
            results_map[key] = result
        
        # 处理BM25检索结果
        for rank, result in enumerate(bm25_results):
            key = (result.paper_id, result.chunk_index)
            score = self.bm25_weight * (1 / (self.rrf_k + rank + 1))
            scores[key] = scores.get(key, 0) + score
            if key not in results_map:
                results_map[key] = result
        
        # 按融合分数排序
        sorted_keys = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
        
        # 更新分数并返回
        fused_results = []
        for key in sorted_keys:
            result = results_map[key]
            result.score = scores[key]
            result.metadata["fusion_score"] = scores[key]
            fused_results.append(result)
        
        return fused_results
    
    async def index_paper(
        self,
        paper_id: int,
        project_id: Optional[int],
        chunks: List[Dict[str, Any]],
        vectors: List[List[float]]
    ):
        """索引文献到两个检索系统"""
        await asyncio.gather(
            self.vector_retriever.insert(paper_id, chunks, vectors),
            self.bm25_retriever.index(paper_id, project_id, chunks)
        )
        logger.info(f"Indexed paper {paper_id}: {len(chunks)} chunks")

    async def delete_paper(self, paper_id: int):
        """删除文献在检索系统中的索引"""
        await self.bm25_retriever.delete_paper(paper_id)


# 默认检索器实例
hybrid_retriever = HybridRetriever()
