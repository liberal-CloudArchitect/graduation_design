"""
Reconstructive Memory

重构性记忆系统，实现 Trace → Expand → Reconstruct 流程
模仿人脑基于线索重构完整记忆的能力
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from loguru import logger
import time

from .base import MemoryNode, BaseMemoryEngine
from .cue_extractor import CueExtractor, StructuredCue, cue_extractor as default_cue_extractor
from .dynamic_memory import DynamicMemoryEngine, dynamic_memory_engine


def _to_builtin(value: Any) -> Any:
    """将 numpy 标量转换为 Python 原生类型，避免 JSON 序列化失败。"""
    if value is None:
        return None
    if type(value).__module__ == "numpy":
        return value.item()
    return value


@dataclass
class ReconstructedMemory:
    """
    重构后的记忆结果
    
    Attributes:
        content: 重构的完整内容
        fragments: 原始记忆片段
        cue: 使用的结构化线索
        confidence: 重构置信度
        is_reconstructed: 是否经过LLM重构
        processing_time: 处理耗时(ms)
    """
    content: str
    fragments: List[MemoryNode] = field(default_factory=list)
    cue: Optional[StructuredCue] = None
    confidence: float = 1.0
    is_reconstructed: bool = False
    processing_time: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "fragment_count": len(self.fragments),
            "cue": self.cue.to_dict() if self.cue else None,
            "confidence": self.confidence,
            "is_reconstructed": self.is_reconstructed,
            "processing_time_ms": self.processing_time
        }


# 重构Prompt模板
RECONSTRUCT_PROMPT = """你是一个记忆重构助手。根据以下零散的记忆片段，还原当时对话的完整场景和结论。

用户查询: {query}

记忆片段:
{fragments}

请根据这些片段：
1. 还原对话的主要内容和场景
2. 提取关键的结论或观点
3. 如果信息不足，明确指出哪些部分是推测

输出格式:
根据历史记忆，[还原的内容]...

注意：
- 如果片段之间存在矛盾，指出矛盾点
- 保持客观，不要添加片段中没有的内容
- 语言风格自然流畅
"""


class ReconstructiveMemory:
    """
    重构性记忆系统
    
    核心流程：Trace → Expand → Reconstruct
    
    使用方式:
        rm = ReconstructiveMemory()
        await rm.initialize()
        
        result = await rm.reconstruct(
            query="上次我们讨论的Transformer变体是什么？",
            project_id=1
        )
        print(result.content)
    """
    
    # 时序扩展窗口（秒）
    TEMPORAL_WINDOW = 3600  # 1小时内的记忆可能相关
    
    # 最大检索数量
    MAX_TRACE_RESULTS = 10
    MAX_EXPAND_RESULTS = 5
    
    def __init__(
        self,
        memory_engine: Optional[BaseMemoryEngine] = None,
        cue_extractor_instance: Optional[CueExtractor] = None,
        llm=None
    ):
        """
        初始化重构记忆系统
        
        Args:
            memory_engine: 记忆存储引擎
            cue_extractor_instance: 线索提取器
            llm: LLM实例（用于重构）
        """
        self.memory_engine = memory_engine or dynamic_memory_engine
        self._cue_extractor = cue_extractor_instance or default_cue_extractor
        self.llm = llm
        self._initialized = False
    
    async def initialize(self) -> None:
        """初始化重构记忆系统"""
        if self._initialized:
            return
        
        if hasattr(self.memory_engine, 'initialize'):
            await self.memory_engine.initialize()
        
        self._initialized = True
        logger.info("ReconstructiveMemory initialized")
    
    async def reconstruct(
        self,
        query: str,
        project_id: Optional[int] = None,
        use_llm: bool = True
    ) -> ReconstructedMemory:
        """
        重构记忆
        
        Args:
            query: 用户查询
            project_id: 项目ID
            use_llm: 是否使用LLM进行生成式重构
            
        Returns:
            ReconstructedMemory 重构结果
        """
        start_time = time.time()
        
        # Step 1: Trace - 提取线索并检索
        cue = await self._cue_extractor.extract(query)
        trace_results = await self._trace(cue, project_id)
        
        if not trace_results:
            return ReconstructedMemory(
                content="未找到相关的历史记忆。",
                cue=cue,
                confidence=0.0,
                processing_time=(time.time() - start_time) * 1000
            )
        
        # Step 2: Expand - 时序关联扩展
        expanded_results = await self._expand(trace_results, project_id)
        
        # Step 3: Reconstruct - 生成式重构
        if use_llm and self.llm:
            content, confidence = await self._reconstruct_with_llm(
                query, expanded_results
            )
            is_reconstructed = True
        else:
            content, confidence = self._reconstruct_simple(expanded_results)
            is_reconstructed = False
        
        processing_time = (time.time() - start_time) * 1000
        
        result = ReconstructedMemory(
            content=content,
            fragments=expanded_results,
            cue=cue,
            confidence=confidence,
            is_reconstructed=is_reconstructed,
            processing_time=processing_time
        )
        
        logger.info(
            f"Memory reconstructed: {len(expanded_results)} fragments, "
            f"{processing_time:.0f}ms, confidence={confidence:.2f}"
        )
        
        return result
    
    async def _trace(
        self,
        cue: StructuredCue,
        project_id: Optional[int]
    ) -> List[MemoryNode]:
        """
        Trace阶段：基于线索检索相关记忆
        
        Args:
            cue: 结构化线索
            project_id: 项目ID
            
        Returns:
            检索到的记忆节点列表
        """
        # 构建检索查询
        search_query = self._build_search_query(cue)
        
        # 执行向量检索
        results = await self.memory_engine.retrieve(
            query=search_query,
            project_id=project_id,
            top_k=self.MAX_TRACE_RESULTS
        )
        
        logger.debug(f"Trace: found {len(results)} memories for cue: {cue.topic}")
        return results
    
    async def _expand(
        self,
        seeds: List[MemoryNode],
        project_id: Optional[int]
    ) -> List[MemoryNode]:
        """
        Expand阶段：时序关联扩展
        
        检索种子记忆时间点前后的相关记忆（模仿情景记忆）
        
        Args:
            seeds: 种子记忆节点
            project_id: 项目ID
            
        Returns:
            扩展后的记忆列表
        """
        if not seeds:
            return []
        
        expanded = list(seeds)
        seen_ids = {m.id for m in seeds}
        
        # 对每个种子记忆，查找时间相邻的记忆
        for seed in seeds[:3]:  # 只对前3个种子进行扩展
            temporal_memories = await self._find_temporal_neighbors(
                seed, project_id, seen_ids
            )
            
            for mem in temporal_memories:
                if mem.id not in seen_ids:
                    expanded.append(mem)
                    seen_ids.add(mem.id)
                    
                    if len(expanded) >= self.MAX_TRACE_RESULTS + self.MAX_EXPAND_RESULTS:
                        break
        
        # 按时间排序
        expanded.sort(key=lambda m: m.timestamp)
        
        logger.debug(f"Expand: {len(seeds)} -> {len(expanded)} memories")
        return expanded
    
    async def _find_temporal_neighbors(
        self,
        seed: MemoryNode,
        project_id: Optional[int],
        exclude_ids: set
    ) -> List[MemoryNode]:
        """
        查找时间相邻的记忆（基于 Milvus 时间戳范围过滤）
        
        使用种子记忆的 timestamp ± TEMPORAL_WINDOW 构建时间窗口，
        通过 Milvus 标量过滤检索同一时间区间内的记忆，
        实现真正的时序关联扩展（而非语义重复检索）。
        
        Args:
            seed: 种子记忆
            project_id: 项目ID
            exclude_ids: 已包含的ID集合
            
        Returns:
            时间相邻的记忆列表
        """
        # 检查底层引擎是否具备 Milvus 连接
        if not hasattr(self.memory_engine, 'milvus') or not self.memory_engine.milvus:
            # 无 Milvus 连接时降级：使用语义检索
            neighbors = await self.memory_engine.retrieve(
                query=seed.content[:100],
                project_id=project_id,
                top_k=3
            )
            return [m for m in neighbors if m.id not in exclude_ids]
        
        try:
            # 构建时间窗口
            t_min = seed.timestamp - self.TEMPORAL_WINDOW
            t_max = seed.timestamp + self.TEMPORAL_WINDOW
            
            # 构建 Milvus 标量过滤表达式
            filter_parts = [
                f"timestamp >= {t_min}",
                f"timestamp <= {t_max}",
            ]
            if project_id is not None:
                filter_parts.append(f"project_id == {project_id}")
            
            filter_expr = " && ".join(filter_parts)
            
            # 使用 Milvus query（标量过滤，非向量搜索）
            results = self.memory_engine.milvus.query(
                collection_name=self.memory_engine.COLLECTION_NAME,
                filter=filter_expr,
                output_fields=[
                    "id", "content", "timestamp", "importance",
                    "access_count", "memory_type", "agent_source", "project_id"
                ],
                limit=self.MAX_EXPAND_RESULTS + len(exclude_ids)
            )
            
            # 转换为 MemoryNode，排除已有 ID
            neighbors = []
            for r in (results or []):
                rid = r.get("id", "")
                if rid in exclude_ids:
                    continue
                neighbors.append(MemoryNode(
                    id=str(_to_builtin(rid)),
                    content=str(_to_builtin(r.get("content", ""))),
                    embedding=[],
                    timestamp=int(_to_builtin(r.get("timestamp", 0))),
                    importance=float(_to_builtin(r.get("importance", 1.0))),
                    access_count=int(_to_builtin(r.get("access_count", 0))),
                    memory_type=str(_to_builtin(r.get("memory_type", "dynamic"))),
                    relations={},
                    agent_source=str(_to_builtin(r.get("agent_source", "qa_agent"))),
                    project_id=int(_to_builtin(r.get("project_id", 0))),
                ))
            
            # 按与种子时间的距离排序（最近优先）
            neighbors.sort(key=lambda m: abs(m.timestamp - seed.timestamp))
            
            logger.debug(
                f"Temporal neighbors: found {len(neighbors)} within "
                f"[{t_min}, {t_max}] for seed {seed.id[:8]}"
            )
            return neighbors[:self.MAX_EXPAND_RESULTS]
            
        except Exception as e:
            logger.warning(f"Temporal neighbor search failed, falling back: {e}")
            # 降级到语义检索
            neighbors = await self.memory_engine.retrieve(
                query=seed.content[:100],
                project_id=project_id,
                top_k=3
            )
            return [m for m in neighbors if m.id not in exclude_ids]
    
    async def _reconstruct_with_llm(
        self,
        query: str,
        fragments: List[MemoryNode]
    ) -> tuple[str, float]:
        """
        使用LLM进行生成式重构
        
        Args:
            query: 原始查询
            fragments: 记忆片段
            
        Returns:
            (重构内容, 置信度)
        """
        if not self.llm or not fragments:
            return self._reconstruct_simple(fragments)
        
        try:
            # 格式化片段
            fragments_text = "\n\n".join([
                f"[{i+1}] ({self._format_timestamp(f.timestamp)}) {f.content}"
                for i, f in enumerate(fragments)
            ])
            
            prompt = RECONSTRUCT_PROMPT.format(
                query=query,
                fragments=fragments_text
            )
            
            response = await self.llm.ainvoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            
            # 基于片段数量估算置信度
            confidence = min(0.5 + len(fragments) * 0.1, 0.95)
            
            return content, confidence
            
        except Exception as e:
            logger.warning(f"LLM reconstruction failed: {e}")
            return self._reconstruct_simple(fragments)
    
    def _reconstruct_simple(
        self,
        fragments: List[MemoryNode]
    ) -> tuple[str, float]:
        """
        简单重构（无LLM）
        
        直接拼接记忆片段
        
        Args:
            fragments: 记忆片段
            
        Returns:
            (重构内容, 置信度)
        """
        if not fragments:
            return "未找到相关记忆。", 0.0
        
        # 按时间排序拼接
        sorted_fragments = sorted(fragments, key=lambda m: m.timestamp)
        
        content_parts = []
        for f in sorted_fragments:
            time_str = self._format_timestamp(f.timestamp)
            content_parts.append(f"[{time_str}] {f.content}")
        
        content = "根据历史记忆：\n\n" + "\n\n".join(content_parts)
        
        # 简单拼接的置信度较低
        confidence = min(0.3 + len(fragments) * 0.05, 0.6)
        
        return content, confidence
    
    def _build_search_query(self, cue: StructuredCue) -> str:
        """
        根据线索构建搜索查询
        
        Args:
            cue: 结构化线索
            
        Returns:
            搜索查询字符串
        """
        parts = []
        
        if cue.topic:
            parts.append(cue.topic)
        
        if cue.entities:
            parts.extend(cue.entities[:3])
        
        if cue.context_hints:
            parts.extend(cue.context_hints[:2])
        
        return " ".join(parts) if parts else cue.topic
    
    def _format_timestamp(self, timestamp: int) -> str:
        """格式化时间戳"""
        import datetime
        dt = datetime.datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M")


# 全局实例
reconstructive_memory = ReconstructiveMemory()
