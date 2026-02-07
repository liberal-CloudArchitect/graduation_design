"""
Hippocampus Reflector (Memory Consolidation Worker)

海马体反思器 - 异步记忆整合工作器
负责后台记忆压缩、摘要生成和知识整合
"""
import asyncio
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from loguru import logger
import time
from collections import deque

from .base import MemoryNode, BaseMemoryEngine
from .dynamic_memory import DynamicMemoryEngine, dynamic_memory_engine


@dataclass
class ConsolidationTask:
    """
    记忆整合任务
    
    Attributes:
        task_id: 任务ID
        task_type: 任务类型 (summarize/compress/merge/decay)
        memories: 待处理的记忆列表
        priority: 优先级 (1-10, 10最高)
        created_at: 创建时间
        status: 任务状态
    """
    task_id: str
    task_type: str
    memories: List[MemoryNode] = field(default_factory=list)
    priority: int = 5
    created_at: int = field(default_factory=lambda: int(time.time()))
    status: str = "pending"  # pending/processing/completed/failed
    result: Optional[Any] = None
    
    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "memory_count": len(self.memories),
            "priority": self.priority,
            "created_at": self.created_at,
            "status": self.status
        }


class HippocampusReflector:
    """
    海马体反思器
    
    异步后台工作器，负责：
    1. 动态摘要生成 - 周期性压缩当日记忆
    2. 记忆整合 - 合并相似记忆片段
    3. 重要性重评估 - 根据访问模式更新重要性
    4. 遗忘触发 - 调用遗忘机制清理低价值记忆
    
    使用方式:
        reflector = HippocampusReflector()
        await reflector.start()
        
        # 提交整合任务
        task_id = await reflector.submit_task(
            task_type="summarize",
            memories=[mem1, mem2, mem3]
        )
        
        # 等待完成
        result = await reflector.wait_for_task(task_id)
        
        # 停止
        await reflector.stop()
    """
    
    # 队列容量
    MAX_QUEUE_SIZE = 100
    
    # 任务处理间隔（秒）
    PROCESS_INTERVAL = 1.0
    
    # 整合阈值 - 多少条记忆触发自动整合
    AUTO_CONSOLIDATE_THRESHOLD = 20
    
    def __init__(
        self,
        memory_engine: Optional[BaseMemoryEngine] = None,
        llm=None
    ):
        """
        初始化反思器
        
        Args:
            memory_engine: 记忆存储引擎
            llm: LLM实例（用于摘要生成）
        """
        self.memory_engine = memory_engine or dynamic_memory_engine
        self.llm = llm
        
        self._task_queue: asyncio.Queue = asyncio.Queue(maxsize=self.MAX_QUEUE_SIZE)
        self._pending_tasks: Dict[str, ConsolidationTask] = {}
        self._completed_tasks: deque = deque(maxlen=50)
        
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._task_counter = 0
    
    async def start(self) -> None:
        """启动反思器后台工作"""
        if self._running:
            logger.warning("HippocampusReflector already running")
            return
        
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("HippocampusReflector started")
    
    async def stop(self) -> None:
        """停止反思器"""
        self._running = False
        
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        
        logger.info("HippocampusReflector stopped")
    
    async def submit_task(
        self,
        task_type: str,
        memories: List[MemoryNode],
        priority: int = 5
    ) -> str:
        """
        提交整合任务
        
        Args:
            task_type: 任务类型 (summarize/compress/merge/decay)
            memories: 待处理记忆
            priority: 优先级
            
        Returns:
            任务ID
        """
        self._task_counter += 1
        task_id = f"task_{self._task_counter}_{int(time.time())}"
        
        task = ConsolidationTask(
            task_id=task_id,
            task_type=task_type,
            memories=memories,
            priority=priority
        )
        
        self._pending_tasks[task_id] = task
        await self._task_queue.put(task)
        
        logger.debug(f"Task {task_id} submitted: {task_type}, {len(memories)} memories")
        return task_id
    
    async def wait_for_task(
        self,
        task_id: str,
        timeout: float = 30.0
    ) -> Optional[Any]:
        """
        等待任务完成
        
        Args:
            task_id: 任务ID
            timeout: 超时时间（秒）
            
        Returns:
            任务结果
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if task_id in self._pending_tasks:
                task = self._pending_tasks[task_id]
                if task.status == "completed":
                    return task.result
                elif task.status == "failed":
                    return None
            
            await asyncio.sleep(0.1)
        
        logger.warning(f"Task {task_id} timeout")
        return None
    
    def get_task_status(self, task_id: str) -> Optional[str]:
        """获取任务状态"""
        if task_id in self._pending_tasks:
            return self._pending_tasks[task_id].status
        return None
    
    async def _worker_loop(self) -> None:
        """后台工作循环"""
        logger.info("Worker loop started")
        
        while self._running:
            try:
                # 尝试获取任务
                try:
                    task = await asyncio.wait_for(
                        self._task_queue.get(),
                        timeout=self.PROCESS_INTERVAL
                    )
                except asyncio.TimeoutError:
                    continue
                
                # 处理任务
                await self._process_task(task)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker error: {e}")
    
    async def _process_task(self, task: ConsolidationTask) -> None:
        """
        处理单个任务
        
        Args:
            task: 整合任务
        """
        task.status = "processing"
        logger.debug(f"Processing task {task.task_id}: {task.task_type}")
        
        try:
            if task.task_type == "summarize":
                result = await self._task_summarize(task.memories)
            elif task.task_type == "compress":
                result = await self._task_compress(task.memories)
            elif task.task_type == "merge":
                result = await self._task_merge(task.memories)
            elif task.task_type == "decay":
                result = await self._task_decay(task.memories)
            else:
                result = None
                logger.warning(f"Unknown task type: {task.task_type}")
            
            task.result = result
            task.status = "completed"
            
        except Exception as e:
            logger.error(f"Task {task.task_id} failed: {e}")
            task.status = "failed"
        
        # 移动到已完成队列
        self._completed_tasks.append(task)
    
    async def _task_summarize(self, memories: List[MemoryNode]) -> Optional[str]:
        """
        摘要任务 - 生成记忆摘要
        
        Args:
            memories: 待摘要的记忆
            
        Returns:
            摘要文本
        """
        if not memories:
            return None
        
        # 简单实现：拼接内容
        # 实际应用中使用LLM生成摘要
        contents = [m.content for m in memories]
        
        if self.llm:
            try:
                prompt = f"""请将以下{len(memories)}条记忆整合成一段简洁的摘要：

{chr(10).join(f"- {c}" for c in contents)}

摘要："""
                response = await self.llm.ainvoke(prompt)
                return response.content if hasattr(response, 'content') else str(response)
            except Exception as e:
                logger.warning(f"LLM summarize failed: {e}")
        
        # 无LLM时的简单摘要
        summary = f"[自动摘要] 包含{len(memories)}条相关记忆"
        for i, content in enumerate(contents[:3]):
            summary += f"\n{i+1}. {content[:50]}..."
        
        return summary
    
    async def _task_compress(self, memories: List[MemoryNode]) -> Dict[str, Any]:
        """
        压缩任务 - 压缩冗余记忆
        
        Args:
            memories: 待压缩的记忆
            
        Returns:
            压缩结果统计
        """
        # 简化实现：按内容相似度去重
        seen_contents = set()
        unique_memories = []
        
        for mem in memories:
            content_hash = hash(mem.content[:50])
            if content_hash not in seen_contents:
                seen_contents.add(content_hash)
                unique_memories.append(mem)
        
        return {
            "original_count": len(memories),
            "compressed_count": len(unique_memories),
            "removed": len(memories) - len(unique_memories)
        }
    
    async def _task_merge(self, memories: List[MemoryNode]) -> Optional[MemoryNode]:
        """
        合并任务 - 合并相似记忆
        
        Args:
            memories: 待合并的记忆
            
        Returns:
            合并后的记忆
        """
        if not memories:
            return None
        
        # 合并内容
        merged_content = "\n---\n".join([m.content for m in memories])
        
        # 取最高重要性
        max_importance = max(m.importance for m in memories)
        
        # 使用第一个记忆的embedding（简化处理）
        merged = MemoryNode.create(
            content=f"[合并记忆] {merged_content[:500]}",
            embedding=memories[0].embedding,
            importance=max_importance,
            memory_type="consolidated",
            project_id=memories[0].project_id
        )
        
        return merged
    
    async def _task_decay(self, memories: List[MemoryNode]) -> List[str]:
        """
        衰减任务 - 标记需要遗忘的记忆
        
        Args:
            memories: 待评估的记忆
            
        Returns:
            需要遗忘的记忆ID列表
        """
        # 简化：标记重要性低且长时间未访问的记忆
        current_time = int(time.time())
        decay_threshold = 0.2
        age_threshold = 7 * 24 * 3600  # 7天
        
        to_forget = []
        for mem in memories:
            age = current_time - mem.timestamp
            if mem.importance < decay_threshold and age > age_threshold:
                to_forget.append(mem.id)
        
        return to_forget
    
    def get_stats(self) -> Dict[str, Any]:
        """获取反思器统计"""
        return {
            "running": self._running,
            "pending_tasks": len(self._pending_tasks),
            "queue_size": self._task_queue.qsize(),
            "completed_total": len(self._completed_tasks),
            "total_submitted": self._task_counter
        }


# 全局实例
hippocampus_reflector = HippocampusReflector()
