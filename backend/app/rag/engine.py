"""
RAG Engine - Core Implementation

统一的 RAG 引擎，负责文档向量化、混合检索、重排序和生成流程。
支持记忆增强、流式输出、对话历史、extra_context 注入和 paper_ids 筛选。
"""
from typing import List, Optional, Dict, Any, AsyncGenerator, Tuple
from loguru import logger
import json
import re
from sqlalchemy import select

from app.core.config import settings
from app.rag.memory_engine import DynamicMemoryEngine
from app.rag.prompts import build_rag_prompt, build_conversation_history_text
from app.models.database import async_session_maker
from app.models.paper import Paper


class RAGEngine:
    """
    RAG引擎核心类
    
    负责文档向量化、混合检索、重排序和生成流程
    
    使用方式:
        engine = RAGEngine()
        await engine.initialize()
        
        # 索引文档
        await engine.index_paper(paper_id, chunks)
        
        # 检索
        results = await engine.search(query, project_id)
        
        # 问答（非流式）
        answer = await engine.answer(question, project_id)
        
        # 问答（流式）
        async for event in engine.answer_stream(question, project_id):
            print(event)
    """
    
    def __init__(self):
        self.embedder = None
        self.milvus = None
        self.llm = None
        self.memory_engine = None  # 动态记忆引擎
        self.hybrid_retriever = None  # 混合检索器
        self._initialized = False
        self._chunk_cache: Dict[str, str] = {}  # 内存缓存

    _REFERENCE_SECTION_PATTERN = re.compile(
        r"^\s*(references?|参考文献|bibliography)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    _REFERENCE_ENTRY_PATTERNS = [
        re.compile(r"^\s*\[\d{1,3}\]\s+"),
        re.compile(r"^\s*\d{1,3}\.\s+[A-Z]"),
        re.compile(r"\bet al\.\b", re.IGNORECASE),
        re.compile(r"\bdoi:\s*10\.\d{4,9}/", re.IGNORECASE),
    ]
    _ADMIN_NOISE_PATTERNS = [
        re.compile(r"课程负责人签字"),
        re.compile(r"研究生教育主管部门公章"),
        re.compile(r"同意该课程资源按要求接入"),
        re.compile(r"无违法违纪行为"),
        re.compile(r"不存在师德师风问题"),
        re.compile(r"学术不端"),
        re.compile(r"思想导向正确"),
        re.compile(r"联系方式[:：]\s*\d{7,}"),
    ]

    
    async def initialize(self):
        """初始化RAG引擎组件"""
        if self._initialized:
            return
        
        logger.info("Initializing RAG Engine...")
        
        # 1. 初始化向量化模型 (BGE-M3)
        await self._init_embedder()
        
        # 2. 初始化向量数据库 (Milvus)
        await self._init_milvus()
        
        # 3. 初始化LLM
        await self._init_llm()
        
        # 4. 初始化动态记忆引擎
        await self._init_memory_engine()
        
        # 5. 初始化混合检索器 (Milvus + Elasticsearch)
        await self._init_hybrid_retriever()
        
        self._initialized = True
        logger.info("RAG Engine initialized successfully")
    
    async def _init_memory_engine(self):
        """初始化动态记忆引擎"""
        try:
            self.memory_engine = DynamicMemoryEngine()
            await self.memory_engine.initialize()
            logger.info("Memory engine initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize memory engine: {e}")
            self.memory_engine = None
    
    async def _init_hybrid_retriever(self):
        """初始化混合检索器 (Milvus + Elasticsearch)"""
        try:
            from app.rag.retriever import HybridRetriever
            self.hybrid_retriever = HybridRetriever(
                vector_weight=0.6, bm25_weight=0.4
            )
            await self.hybrid_retriever.initialize(
                milvus_host=settings.MILVUS_HOST,
                milvus_port=settings.MILVUS_PORT,
                es_host=settings.ES_HOST,
                es_port=settings.ES_PORT
            )
            logger.info("Hybrid retriever initialized (Milvus + Elasticsearch)")
        except Exception as e:
            logger.warning(f"Hybrid retriever init failed, will use vector-only: {e}")
            self.hybrid_retriever = None
    
    async def _init_embedder(self):
        """初始化BGE-M3向量化模型"""
        try:
            from FlagEmbedding import BGEM3FlagModel
            self.embedder = BGEM3FlagModel(
                settings.BGE_MODEL_PATH,
                use_fp16=True
            )
            logger.info(f"BGE-M3 model loaded from {settings.BGE_MODEL_PATH}")
        except Exception as e:
            logger.warning(f"Failed to load BGE-M3: {e}, using mock embedder")
            self.embedder = MockEmbedder()
    
    async def _init_milvus(self):
        """初始化Milvus客户端，并确保集合存在"""
        try:
            from pymilvus import MilvusClient
            self.milvus = MilvusClient(
                uri=f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}"
            )
            logger.info(f"Connected to Milvus at {settings.MILVUS_HOST}:{settings.MILVUS_PORT}")
            
            # 确保 paper_vectors 集合存在
            await self._ensure_paper_collection()
        except Exception as e:
            logger.warning(f"Failed to connect Milvus: {e}")
            self.milvus = None

    async def _ensure_paper_collection(self):
        """确保 paper_vectors 集合存在"""
        if not self.milvus:
            return
        
        collection_name = "paper_vectors"
        try:
            collections = self.milvus.list_collections()
            if collection_name in collections:
                logger.info(f"Milvus collection '{collection_name}' already exists")
                return
            
            # 使用 ORM API 创建集合
            from pymilvus import (
                FieldSchema, CollectionSchema, DataType,
                Collection, connections
            )
            
            alias = "default"
            if not connections.has_connection(alias):
                connections.connect(
                    alias=alias,
                    host=settings.MILVUS_HOST,
                    port=settings.MILVUS_PORT
                )
            
            fields = [
                FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=64),
                FieldSchema(name="paper_id", dtype=DataType.INT64),
                FieldSchema(name="chunk_index", dtype=DataType.INT64),
                FieldSchema(name="project_id", dtype=DataType.INT64),
                FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=1024),
            ]
            
            schema = CollectionSchema(
                fields=fields,
                description="Paper chunk vectors for RAG",
                enable_dynamic_field=True
            )
            
            collection = Collection(
                name=collection_name,
                schema=schema,
                using=alias
            )
            
            index_params = {
                "index_type": "IVF_FLAT",
                "metric_type": "COSINE",
                "params": {"nlist": 128}
            }
            collection.create_index(field_name="vector", index_params=index_params)
            collection.load()
            
            logger.info(f"Created Milvus collection: {collection_name}")
        except Exception as e:
            logger.error(f"Failed to ensure paper_vectors collection: {e}")
    
    async def _init_llm(self):
        """初始化LLM（OpenAI兼容接口，支持 DeepSeek/OpenRouter）"""
        try:
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(
                model=settings.EFFECTIVE_LLM_MODEL,
                api_key=settings.EFFECTIVE_LLM_API_KEY,
                base_url=settings.EFFECTIVE_LLM_BASE_URL,
                temperature=0.3,
                default_headers={
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "Literature Analysis Platform"
                }
            )
            logger.info(
                "LLM initialized: model={} base_url={}",
                settings.EFFECTIVE_LLM_MODEL,
                settings.EFFECTIVE_LLM_BASE_URL,
            )
        except Exception as e:
            logger.warning(f"Failed to initialize LLM: {e}")
            self.llm = None
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        将文本转换为向量
        
        Args:
            texts: 文本列表
            
        Returns:
            向量列表 (1024维)
        """
        if self.embedder is None:
            raise RuntimeError("Embedder not initialized")
        
        result = self.embedder.encode(texts, return_dense=True)
        return result['dense_vecs'].tolist()
    
    async def index_paper(
        self, 
        paper_id: int, 
        chunks: List[Any],
        project_id: Optional[int] = None
    ) -> List[str]:
        """
        将文献分块索引到向量库
        
        Args:
            paper_id: 文献ID
            chunks: 文本分块列表（支持 str 或 {"text", "page_number", "metadata"}）
            project_id: 项目ID
            
        Returns:
            向量ID列表
        """
        if not chunks:
            return []
        
        from app.services.mongodb_service import mongodb_service
        
        # 统一为结构化分块
        normalized_chunks = []
        for item in chunks:
            if isinstance(item, dict):
                text = str(item.get("text", "") or "")
                page_number = item.get("page_number")
                metadata = item.get("metadata", {}) or {}
            else:
                text = str(item or "")
                page_number = None
                metadata = {}

            if not text.strip():
                continue

            normalized_chunks.append(
                {
                    "text": text,
                    "page_number": page_number,
                    "metadata": metadata,
                }
            )

        if not normalized_chunks:
            return []

        # 向量化
        embeddings = self.embed([c["text"] for c in normalized_chunks])
        
        # 构建实体
        entities = []
        vector_ids = []
        chunk_docs = []
        
        for i, (emb, chunk) in enumerate(zip(embeddings, normalized_chunks)):
            vector_id = f"{paper_id}_{i}"
            vector_ids.append(vector_id)
            entities.append({
                "id": vector_id,
                "paper_id": paper_id,
                "chunk_index": i,
                "project_id": project_id or 0,
                "vector": emb
            })
            chunk_docs.append({
                "index": i,
                "text": chunk.get("text", ""),
                "page_number": chunk.get("page_number"),
                "metadata": chunk.get("metadata", {}),
            })
            # 内存缓存
            self._chunk_cache[f"{paper_id}_{i}"] = chunk.get("text", "")
        
        # 存储到MongoDB
        await mongodb_service.insert_chunks(paper_id, chunk_docs)
        
        # 插入Milvus
        if self.milvus:
            try:
                self.milvus.insert(
                    collection_name="paper_vectors",
                    data=entities
                )
            except Exception as e:
                logger.warning(f"Milvus insert failed: {e}")
        
        # 同步索引到 Elasticsearch（如果混合检索器可用）
        if self.hybrid_retriever and self.hybrid_retriever.bm25_retriever.client:
            try:
                await self.hybrid_retriever.bm25_retriever.index(
                    paper_id, project_id, chunk_docs
                )
                logger.info(f"BM25 index updated for paper {paper_id}")
            except Exception as e:
                logger.warning(f"BM25 indexing failed: {e}")
        
        logger.info(f"Indexed {len(chunks)} chunks for paper {paper_id}")
        return vector_ids

    async def delete_paper_index(self, paper_id: int):
        """删除文献在检索系统中的索引数据"""
        if self.milvus:
            try:
                self.milvus.delete(
                    collection_name="paper_vectors",
                    filter=f"paper_id == {paper_id}",
                )
            except Exception as e:
                logger.warning(f"Milvus delete failed for paper {paper_id}: {e}")

        if self.hybrid_retriever:
            try:
                await self.hybrid_retriever.delete_paper(paper_id)
            except Exception as e:
                logger.warning(f"BM25 delete failed for paper {paper_id}: {e}")

        stale_keys = [k for k in self._chunk_cache.keys() if k.startswith(f"{paper_id}_")]
        for key in stale_keys:
            self._chunk_cache.pop(key, None)
    
    async def search(
        self,
        query: str,
        project_id: Optional[int] = None,
        top_k: int = 5,
        paper_ids: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        混合检索（优先）或向量检索（降级）
        
        Args:
            query: 查询文本
            project_id: 项目ID筛选
            top_k: 返回数量
            paper_ids: 限定文献ID列表
            
        Returns:
            检索结果列表
        """
        # 向量化查询
        query_embedding = self.embed([query])[0]
        
        # 优先使用混合检索器 (BM25 + Vector + RRF)
        if self.hybrid_retriever and self.hybrid_retriever._initialized:
            # 旧索引可能缺少 project_id 字段，无法在 BM25 侧做项目隔离。
            # 这种情况下回退到纯向量检索，避免跨项目串检。
            if (
                project_id is not None
                and not paper_ids
                and hasattr(self.hybrid_retriever.bm25_retriever, "_supports_project_filter")
                and not self.hybrid_retriever.bm25_retriever._supports_project_filter
            ):
                return await self._vector_search(query_embedding, project_id, top_k, paper_ids)
            try:
                hybrid_results = await self.hybrid_retriever.search(
                    query=query,
                    query_vector=query_embedding,
                    top_k=top_k,
                    project_id=project_id,
                    paper_ids=paper_ids
                )
                if hybrid_results:
                    return [
                        {
                            "paper_id": r.paper_id,
                            "chunk_index": r.chunk_index,
                            "distance": r.score,
                            "text": r.text,
                            "entity": {
                                "paper_id": r.paper_id,
                                "chunk_index": r.chunk_index,
                            }
                        }
                        for r in hybrid_results
                    ]
            except Exception as e:
                logger.warning(f"Hybrid retrieval failed, falling back to vector-only: {e}")
        
        # 降级：纯向量检索
        return await self._vector_search(query_embedding, project_id, top_k, paper_ids)
    
    async def _vector_search(
        self,
        query_embedding: List[float],
        project_id: Optional[int] = None,
        top_k: int = 5,
        paper_ids: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """纯向量检索（Milvus）"""
        # 构建过滤条件
        filter_parts = []
        if project_id is not None:
            filter_parts.append(f"project_id == {project_id}")
        if paper_ids:
            filter_parts.append(f"paper_id in {paper_ids}")
        filter_expr = " && ".join(filter_parts) if filter_parts else None
        
        if self.milvus:
            try:
                results = self.milvus.search(
                    collection_name="paper_vectors",
                    data=[query_embedding],
                    limit=top_k,
                    filter=filter_expr,
                    output_fields=["paper_id", "chunk_index"]
                )
                return results[0] if results else []
            except Exception as e:
                logger.error(f"Vector search failed: {e}")
        
        return []
    
    async def answer(
        self,
        question: str,
        project_id: Optional[int] = None,
        top_k: int = 5,
        use_memory: bool = True,
        extra_context: str = "",
        conversation_history: Optional[List[Dict]] = None,
        paper_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        RAG问答 (含记忆增强, 混合检索, 重排序)
        
        Args:
            question: 用户问题（保持原始查询，不拼接额外内容）
            project_id: 项目ID
            top_k: 检索文档数量
            use_memory: 是否使用记忆系统
            extra_context: 额外上下文（如 PDF 解析结果），与 query 分离
            conversation_history: 对话历史消息列表
            paper_ids: 限定文献ID列表
            
        Returns:
            包含答案和引用的字典
        """
        # 1. 准备证据（记忆 + 检索 + 去噪 + 覆盖增强）
        memory_results, docs, retrieval_meta = await self._prepare_evidence(
            question=question,
            project_id=project_id,
            top_k=top_k,
            use_memory=use_memory,
            paper_ids=paper_ids,
        )

        # 2. 构建上下文 (融合记忆与文献)
        context = self._build_context_with_memory(docs, memory_results)

        # 3. 构建 Prompt（使用统一模板，extra_context 独立注入）
        history_text = build_conversation_history_text(conversation_history or [])
        prompt = build_rag_prompt(
            question=question,
            context=context,
            extra_context=extra_context,
            conversation_history=history_text,
        )

        # 4. 生成答案
        if self.llm:
            response = await self.llm.ainvoke(prompt)
            answer = response.content
        else:
            answer = "LLM未初始化，无法生成答案"

        # 5. 保存本次交互为新记忆
        if use_memory and self.memory_engine:
            try:
                await self.memory_engine.add_memory(
                    content=f"Q: {question}\nA: {answer}",
                    metadata={"project_id": project_id or 0, "agent_source": "qa_agent"}
                )
            except Exception as e:
                logger.warning(f"Failed to save memory: {e}")
        
        return {
            "answer": answer,
            "references": docs,
            "memory_used": len(memory_results) > 0,
            "memory_count": len(memory_results),
            "retrieval_meta": retrieval_meta,
            "method": "rag_memory_enhanced"
        }
    
    async def answer_stream(
        self,
        question: str,
        project_id: Optional[int] = None,
        top_k: int = 5,
        use_memory: bool = True,
        extra_context: str = "",
        conversation_history: Optional[List[Dict]] = None,
        paper_ids: Optional[List[int]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式 RAG 问答（记忆增强）- async generator
        
        统一的流式输出方法，集成记忆检索、混合检索、重排序、
        上下文构建、流式 LLM 输出和记忆保存。
        
        Yields:
            {"type": "references", "data": [...]}
            {"type": "chunk", "data": "文本片段"}
            {"type": "done", "data": {"answer": "...", "memory_used": bool, ...}}
        """
        import asyncio

        # 1. 准备证据（记忆 + 检索 + 去噪 + 覆盖增强）
        memory_results, docs, retrieval_meta = await self._prepare_evidence(
            question=question,
            project_id=project_id,
            top_k=top_k,
            use_memory=use_memory,
            paper_ids=paper_ids,
        )

        # 2. 发送引用（检索结果）
        yield {"type": "references", "data": docs}

        # 3. 构建上下文
        context = self._build_context_with_memory(docs, memory_results)

        # 4. 构建 Prompt
        history_text = build_conversation_history_text(conversation_history or [])
        prompt = build_rag_prompt(
            question=question,
            context=context,
            extra_context=extra_context,
            conversation_history=history_text,
        )

        # 5. 流式生成答案
        full_answer = ""
        if self.llm:
            async for chunk in self.llm.astream(prompt):
                if hasattr(chunk, 'content') and chunk.content:
                    full_answer += chunk.content
                    yield {"type": "chunk", "data": chunk.content}
                    await asyncio.sleep(0.01)
        else:
            full_answer = "LLM未初始化，无法生成答案"
            yield {"type": "chunk", "data": full_answer}

        # 6. 保存本次交互为新记忆
        if use_memory and self.memory_engine:
            try:
                await self.memory_engine.add_memory(
                    content=f"Q: {question}\nA: {full_answer}",
                    metadata={"project_id": project_id or 0, "agent_source": "qa_agent"}
                )
            except Exception as e:
                logger.warning(f"[stream] Failed to save memory: {e}")

        # 7. 发送完成信号
        yield {
            "type": "done",
            "data": {
                "answer": full_answer,
                "memory_used": len(memory_results) > 0,
                "memory_count": len(memory_results),
                "retrieval_meta": retrieval_meta,
                "method": "rag_memory_enhanced",
            }
        }

    async def _prepare_evidence(
        self,
        question: str,
        project_id: Optional[int],
        top_k: int,
        use_memory: bool,
        paper_ids: Optional[List[int]],
    ) -> Tuple[List[Any], List[Dict[str, Any]], Dict[str, Any]]:
        """统一准备可用于回答的证据：记忆 + 检索 + 去噪 + 覆盖增强。"""
        memory_results = []
        if use_memory and self.memory_engine:
            try:
                memory_results = await self.memory_engine.retrieve(
                    question, project_id, top_k=3
                )
            except Exception as e:
                logger.warning(f"Memory retrieval failed: {e}")

        search_results = await self.search(question, project_id, top_k * 3, paper_ids)
        raw_docs = await self._fetch_documents(search_results)
        filtered_docs, filtered_count = self._filter_reference_like_docs(raw_docs)
        candidate_docs = filtered_docs if filtered_docs else raw_docs
        candidate_docs, filtered_admin_count, filtered_low_score_count = self._filter_low_signal_docs(
            candidate_docs,
            target_k=max(top_k * 2, top_k),
        )
        if not candidate_docs:
            candidate_docs = filtered_docs if filtered_docs else raw_docs

        reranked_docs = await self._rerank(question, candidate_docs, max(top_k * 2, top_k))
        final_docs = self._diversify_docs_by_paper(reranked_docs, top_k)

        paper_ids_in_docs = sorted(
            {
                int(d.get("paper_id"))
                for d in final_docs
                if isinstance(d, dict) and d.get("paper_id") is not None
            }
        )
        retrieval_meta = {
            "search_hit_count": len(search_results),
            "raw_doc_count": len(raw_docs),
            "filtered_reference_docs": filtered_count,
            "filtered_admin_docs": filtered_admin_count,
            "filtered_low_score_docs": filtered_low_score_count,
            "candidate_doc_count": len(candidate_docs),
            "final_doc_count": len(final_docs),
            "covered_paper_ids": paper_ids_in_docs,
            "covered_paper_count": len(paper_ids_in_docs),
        }

        return memory_results, final_docs, retrieval_meta

    def _is_reference_like_text(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """判断片段是否更像参考文献内容，避免进入最终推理上下文。"""
        if not text:
            return False

        if metadata and isinstance(metadata, dict):
            region_types = metadata.get("region_types") or []
            region_types = [str(rt).lower() for rt in region_types if rt]
            if "reference" in region_types:
                return True

        snippet = text[:500]
        if self._REFERENCE_SECTION_PATTERN.search(snippet):
            return True

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return False

        hit = 0
        for ln in lines:
            if any(p.search(ln) for p in self._REFERENCE_ENTRY_PATTERNS):
                hit += 1

        ratio = hit / max(1, len(lines))
        return hit >= 3 and ratio >= 0.2

    def _filter_reference_like_docs(
        self,
        docs: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], int]:
        """过滤参考文献噪声文档，若过滤后为空则由上层回退使用原始结果。"""
        filtered: List[Dict[str, Any]] = []
        filtered_count = 0

        for d in docs:
            text = str((d or {}).get("text", "") or "")
            metadata = (d or {}).get("metadata") or {}
            if self._is_reference_like_text(text, metadata):
                filtered_count += 1
                continue
            filtered.append(d)

        return filtered, filtered_count

    def _is_administrative_noise(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """判断片段是否属于签字/声明/联系方式等行政噪声。"""
        if not text:
            return False

        snippet = str(text)[:1200]
        hits = sum(1 for p in self._ADMIN_NOISE_PATTERNS if p.search(snippet))
        if hits >= 2:
            return True

        # 兜底：出现多个高风险关键词时判定为低价值行政文本
        lower = snippet.lower()
        weak_hits = 0
        for hint in ("签字", "公章", "真实性", "遵纪守法", "知识产权", "国家安全", "联系方式"):
            if hint in lower:
                weak_hits += 1
        if weak_hits >= 3:
            return True

        return False

    def _filter_low_signal_docs(
        self,
        docs: List[Dict[str, Any]],
        target_k: int,
    ) -> Tuple[List[Dict[str, Any]], int, int]:
        """
        过滤低信号证据：
        1) 行政噪声文本
        2) 明显低于主簇的低分尾部文档（保留数量安全阈值）
        """
        if not docs:
            return [], 0, 0

        non_admin_docs: List[Dict[str, Any]] = []
        admin_filtered = 0
        for d in docs:
            text = str((d or {}).get("text", "") or "")
            metadata = (d or {}).get("metadata") or {}
            if self._is_administrative_noise(text, metadata):
                admin_filtered += 1
                continue
            non_admin_docs.append(d)

        if len(non_admin_docs) <= max(target_k, 1):
            return non_admin_docs, admin_filtered, 0

        scored_docs = [
            (idx, float((d or {}).get("score", 0) or 0.0))
            for idx, d in enumerate(non_admin_docs)
        ]
        max_score = max((s for _, s in scored_docs), default=0.0)
        if max_score <= 0:
            return non_admin_docs, admin_filtered, 0

        # 动态阈值：保留主簇，剪掉明显尾部噪声
        score_threshold = max_score * 0.65
        kept = [d for d in non_admin_docs if float((d or {}).get("score", 0) or 0.0) >= score_threshold]
        if len(kept) < max(target_k, 1):
            return non_admin_docs, admin_filtered, 0

        low_score_filtered = len(non_admin_docs) - len(kept)
        return kept, admin_filtered, low_score_filtered

    def _diversify_docs_by_paper(
        self,
        docs: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """保证最终证据尽量覆盖多篇文献，避免被单篇文献垄断。"""
        if top_k <= 0 or not docs:
            return []
        if len(docs) <= top_k:
            return docs

        selected: List[Dict[str, Any]] = []
        used_indices = set()
        seen_papers = set()

        # 第一轮：每篇文献优先选1条
        for idx, d in enumerate(docs):
            pid = d.get("paper_id")
            if pid in seen_papers:
                continue
            selected.append(d)
            used_indices.add(idx)
            seen_papers.add(pid)
            if len(selected) >= top_k:
                return selected

        # 第二轮：按原排序补齐剩余名额
        for idx, d in enumerate(docs):
            if idx in used_indices:
                continue
            selected.append(d)
            if len(selected) >= top_k:
                break

        return selected[:top_k]
    
    async def _rerank(
        self,
        query: str,
        docs: List[Dict[str, Any]],
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        对检索结果进行重排序
        
        使用 LLM 对候选文档按相关性重新排序，从中选出 top_k 个最相关的。
        如果 LLM 不可用或文档数量已经 <= top_k，则直接截断。
        
        Args:
            query: 用户查询
            docs: 候选文档列表
            top_k: 需要返回的文档数量
            
        Returns:
            重排序后的文档列表
        """
        if not docs:
            return []
        if len(docs) <= top_k or not self.llm:
            return docs[:top_k]
        
        try:
            doc_summaries = "\n".join(
                f"[{i}] {d.get('text', '')[:300]}"
                for i, d in enumerate(docs)
            )
            rerank_prompt = f"""你是一个学术文献相关性评估专家。请根据用户查询，对以下文档片段按相关性从高到低排序。

用户查询：{query}

候选文档：
{doc_summaries}

请仅返回一个 JSON 数组，包含按相关性从高到低排列的文档编号（从0开始），例如：[2, 0, 4, 1, 3]
不要输出任何其他内容，仅输出 JSON 数组。"""
            
            response = await self.llm.ainvoke(rerank_prompt)
            content = response.content.strip()
            
            # 提取 JSON 数组
            # 尝试从回复中找到 JSON 数组
            start = content.find("[")
            end = content.rfind("]") + 1
            if start >= 0 and end > start:
                indices = json.loads(content[start:end])
                # 验证并按排序返回
                reranked = []
                seen = set()
                for idx in indices:
                    if isinstance(idx, int) and 0 <= idx < len(docs) and idx not in seen:
                        reranked.append(docs[idx])
                        seen.add(idx)
                        if len(reranked) >= top_k:
                            break
                
                # 如果解析到了有效结果，使用重排后的
                if reranked:
                    logger.debug(f"Reranked {len(docs)} docs -> top {len(reranked)}")
                    return reranked
            
            logger.warning(f"Rerank parsing failed, using original order. LLM output: {content[:200]}")
        except Exception as e:
            logger.warning(f"Rerank failed, using original order: {e}")
        
        return docs[:top_k]
    
    async def _fetch_documents(
        self, 
        search_results: List[Dict]
    ) -> List[Dict[str, Any]]:
        """从MongoDB获取文档内容
        
        兼容 pymilvus MilvusClient 返回格式:
        - pymilvus 2.3.x: {"id": ..., "distance": ..., "entity": {"paper_id": ..., "chunk_index": ...}}
        - pymilvus 2.4+:  {"id": ..., "distance": ..., "paper_id": ..., "chunk_index": ...}
        """
        from app.services.mongodb_service import mongodb_service
        
        docs = []
        for result in search_results:
            # 兼容两种 pymilvus 返回格式: 嵌套 entity 或扁平字段
            entity = result.get("entity", result)
            paper_id = entity.get("paper_id")
            chunk_index = entity.get("chunk_index")
            
            if paper_id is None or chunk_index is None:
                logger.warning(f"Milvus result missing paper_id/chunk_index: {result}")
                continue
            
            # 尝试从MongoDB获取
            chunk = await mongodb_service.get_chunk_by_index(paper_id, chunk_index)
            
            if chunk:
                docs.append({
                    "paper_id": paper_id,
                    "chunk_index": chunk_index,
                    "text": chunk.get("text", ""),
                    "page_number": chunk.get("page_number"),
                    "metadata": chunk.get("metadata", {}),
                    "score": result.get("distance", 0)
                })
            else:
                # 回退1：使用混合检索器返回的内联文本
                inline_text = result.get("text", "") or entity.get("text", "")
                if inline_text:
                    docs.append({
                        "paper_id": paper_id,
                        "chunk_index": chunk_index,
                        "text": inline_text,
                        "metadata": {},
                        "score": result.get("distance", 0)
                    })
                    continue
                
                # 回退2：使用内存缓存中的数据
                cache_key = f"{paper_id}_{chunk_index}"
                cached_text = self._chunk_cache.get(cache_key, "")
                if cached_text:
                    docs.append({
                        "paper_id": paper_id,
                        "chunk_index": chunk_index,
                        "text": cached_text,
                        "metadata": {},
                        "score": result.get("distance", 0)
                    })
                else:
                    logger.warning(f"Chunk not found: paper_id={paper_id}, chunk_index={chunk_index}")

        # 统一补全文献标题，避免下游显示 Unknown
        await self._attach_paper_titles(docs)
        return docs

    async def _attach_paper_titles(self, docs: List[Dict[str, Any]]) -> None:
        """为检索文档补全文献标题（就地修改 docs）。"""
        if not docs:
            return

        paper_ids = {
            int(d.get("paper_id"))
            for d in docs
            if isinstance(d, dict) and d.get("paper_id") is not None
        }
        if not paper_ids:
            return

        try:
            async with async_session_maker() as db:
                result = await db.execute(
                    select(Paper.id, Paper.title).where(Paper.id.in_(paper_ids))
                )
                id_to_title = {int(pid): title for pid, title in result.all() if pid is not None}

            for doc in docs:
                if not isinstance(doc, dict):
                    continue
                pid = doc.get("paper_id")
                if pid is None:
                    continue
                title = id_to_title.get(int(pid))
                if title:
                    doc["title"] = title
                    doc["paper_title"] = title
        except Exception as e:
            logger.warning(f"Attach paper titles failed: {e}")
    
    def _build_context(self, docs: List[Dict]) -> str:
        """构建Prompt上下文"""
        context_parts = []
        for i, doc in enumerate(docs, 1):
            paper_id = doc.get("paper_id")
            page_number = doc.get("page_number")
            source_hint = (
                f"(paper:{paper_id}, page:{page_number})"
                if page_number
                else f"(paper:{paper_id})"
            )
            context_parts.append(f"[{i}] {source_hint} {doc.get('text', '')}")
        return "\n\n".join(context_parts)
    
    def _build_context_with_memory(
        self, 
        docs: List[Dict], 
        memories: List
    ) -> str:
        """
        构建融合记忆的Prompt上下文
        
        Args:
            docs: 文献检索结果
            memories: 历史记忆列表
            
        Returns:
            融合后的上下文字符串
        """
        context_parts = []
        
        # 添加历史记忆 (如果有)
        if memories:
            context_parts.append("【历史对话记忆】")
            for i, mem in enumerate(memories, 1):
                content = getattr(mem, 'content', str(mem))
                context_parts.append(f"[M{i}] {content}")
            context_parts.append("")  # 空行分隔
        
        # 添加文献内容
        if docs:
            context_parts.append("【文献参考】")
            for i, doc in enumerate(docs, 1):
                paper_id = doc.get("paper_id")
                page_number = doc.get("page_number")
                source_hint = (
                    f"(paper:{paper_id}, page:{page_number})"
                    if page_number
                    else f"(paper:{paper_id})"
                )
                context_parts.append(f"[{i}] {source_hint} {doc.get('text', '')}")
        
        return "\n\n".join(context_parts)


class MockEmbedder:
    """模拟向量化器 (用于开发测试)"""
    
    def encode(self, texts: List[str], return_dense: bool = True) -> Dict:
        import numpy as np
        # 生成随机向量用于测试
        vectors = np.random.randn(len(texts), 1024).astype(np.float32)
        return {"dense_vecs": vectors}


# 全局RAG引擎实例
rag_engine = RAGEngine()
