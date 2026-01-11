"""
RAG Engine - Core Implementation
"""
from typing import List, Optional, Dict, Any
from loguru import logger

from app.core.config import settings


class RAGEngine:
    """
    RAG引擎核心类
    
    负责文档向量化、检索和生成流程
    
    使用方式:
        engine = RAGEngine()
        await engine.initialize()
        
        # 索引文档
        await engine.index_paper(paper_id, chunks)
        
        # 检索
        results = await engine.search(query, project_id)
        
        # 问答
        answer = await engine.answer(question, project_id)
    """
    
    def __init__(self):
        self.embedder = None
        self.milvus = None
        self.llm = None
        self._initialized = False
    
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
        
        self._initialized = True
        logger.info("RAG Engine initialized successfully")
    
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
        """初始化Milvus客户端"""
        try:
            from pymilvus import MilvusClient
            self.milvus = MilvusClient(
                uri=f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}"
            )
            logger.info(f"Connected to Milvus at {settings.MILVUS_HOST}:{settings.MILVUS_PORT}")
        except Exception as e:
            logger.warning(f"Failed to connect Milvus: {e}")
            self.milvus = None
    
    async def _init_llm(self):
        """初始化LLM (使用OpenRouter)"""
        try:
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(
                model=settings.OPENROUTER_MODEL,
                api_key=settings.OPENROUTER_API_KEY,
                base_url=settings.OPENROUTER_BASE_URL,
                temperature=0.3,
                default_headers={
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "Literature Analysis Platform"
                }
            )
            logger.info(f"LLM initialized with OpenRouter model: {settings.OPENROUTER_MODEL}")
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
        chunks: List[str],
        project_id: Optional[int] = None
    ) -> List[str]:
        """
        将文献分块索引到向量库
        
        Args:
            paper_id: 文献ID
            chunks: 文本分块列表
            project_id: 项目ID
            
        Returns:
            向量ID列表
        """
        if not chunks:
            return []
        
        # 向量化
        embeddings = self.embed(chunks)
        
        # 构建实体
        entities = []
        vector_ids = []
        for i, (emb, chunk) in enumerate(zip(embeddings, chunks)):
            vector_id = f"{paper_id}_{i}"
            vector_ids.append(vector_id)
            entities.append({
                "id": vector_id,
                "paper_id": paper_id,
                "chunk_index": i,
                "project_id": project_id or 0,
                "vector": emb
            })
        
        # 插入Milvus
        if self.milvus:
            self.milvus.insert(
                collection_name="paper_vectors",
                data=entities
            )
            logger.info(f"Indexed {len(chunks)} chunks for paper {paper_id}")
        
        return vector_ids
    
    async def search(
        self,
        query: str,
        project_id: Optional[int] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        向量检索
        
        Args:
            query: 查询文本
            project_id: 项目ID筛选
            top_k: 返回数量
            
        Returns:
            检索结果列表
        """
        # 向量化查询
        query_embedding = self.embed([query])[0]
        
        # 构建过滤条件
        filter_expr = None
        if project_id:
            filter_expr = f"project_id == {project_id}"
        
        # 执行搜索
        if self.milvus:
            results = self.milvus.search(
                collection_name="paper_vectors",
                data=[query_embedding],
                limit=top_k,
                filter=filter_expr,
                output_fields=["paper_id", "chunk_index"]
            )
            return results[0] if results else []
        
        return []
    
    async def answer(
        self,
        question: str,
        project_id: Optional[int] = None,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        RAG问答
        
        Args:
            question: 用户问题
            project_id: 项目ID
            top_k: 检索文档数量
            
        Returns:
            包含答案和引用的字典
        """
        # 1. 检索相关文档
        search_results = await self.search(question, project_id, top_k)
        
        # 2. 获取文档内容
        docs = await self._fetch_documents(search_results)
        
        # 3. 构建上下文
        context = self._build_context(docs)
        
        # 4. 生成答案
        if self.llm:
            prompt = f"""根据以下参考文献回答用户问题。

参考文献:
{context}

用户问题: {question}

要求:
1. 仅基于提供的参考文献回答
2. 如有引用，使用[1][2]格式标注
3. 如果文献中没有相关信息，请明确说明
"""
            response = await self.llm.ainvoke(prompt)
            answer = response.content
        else:
            answer = "LLM未初始化，无法生成答案"
        
        return {
            "answer": answer,
            "references": docs,
            "method": "rag_mvp"
        }
    
    async def _fetch_documents(
        self, 
        search_results: List[Dict]
    ) -> List[Dict[str, Any]]:
        """从MongoDB获取文档内容"""
        # TODO: 实现MongoDB查询
        docs = []
        for result in search_results:
            docs.append({
                "paper_id": result.get("paper_id"),
                "chunk_index": result.get("chunk_index"),
                "text": "[待获取文档内容]",
                "score": result.get("distance", 0)
            })
        return docs
    
    def _build_context(self, docs: List[Dict]) -> str:
        """构建Prompt上下文"""
        context_parts = []
        for i, doc in enumerate(docs, 1):
            context_parts.append(f"[{i}] {doc.get('text', '')}")
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
