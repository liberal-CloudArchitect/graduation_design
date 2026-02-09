"""
Multi-Agent 系统

包含4个专业Agent和1个协调器：
- RetrieverAgent: 文献检索与RAG问答
- AnalyzerAgent: 趋势分析与统计
- WriterAgent: 写作辅助（大纲/综述/润色）
- SearchAgent: 外部学术API搜索
- AgentCoordinator: 任务路由与结果整合
"""
from app.agents.coordinator import AgentCoordinator, agent_coordinator

__all__ = ["AgentCoordinator", "agent_coordinator"]
