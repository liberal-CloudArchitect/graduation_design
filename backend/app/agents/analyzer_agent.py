"""
Analyzer Agent - 分析Agent

负责趋势分析、统计和数据洞察。
"""
from typing import Optional, Dict, Any
from loguru import logger

from app.agents.base_agent import BaseAgent, AgentType, AgentResponse


class AnalyzerAgent(BaseAgent):
    """
    分析Agent
    
    核心功能：
    1. 关键词频率分析
    2. 研究热点识别
    3. 趋势时间线分析
    4. 领域对比分析
    """
    
    agent_type = AgentType.ANALYZER
    description = "趋势分析与数据统计Agent"
    
    TRIGGER_KEYWORDS = [
        "分析", "趋势", "热点", "统计", "对比", "比较",
        "频率", "分布", "变化", "增长", "下降",
        "关键词", "热门", "突现", "领域",
        "analyze", "trend", "statistics", "compare",
        "distribution", "growth", "hotspot"
    ]
    
    def __init__(self, trend_service=None):
        super().__init__()
        self.trend_service = trend_service
    
    def set_trend_service(self, trend_service):
        self.trend_service = trend_service
    
    def can_handle(self, query: str) -> float:
        query_lower = query.lower()
        score = 0.1
        
        for keyword in self.TRIGGER_KEYWORDS:
            if keyword in query_lower:
                score += 0.2
        
        return min(score, 1.0)
    
    async def execute(
        self,
        query: str,
        project_id: Optional[int] = None,
        analysis_type: str = "auto",
        **kwargs
    ) -> AgentResponse:
        """执行分析任务"""
        try:
            # 确定分析类型
            if analysis_type == "auto":
                analysis_type = self._detect_analysis_type(query)
            
            result = await self._perform_analysis(
                query, project_id, analysis_type, **kwargs
            )
            
            # 保存分析记忆
            await self._save_to_memory(
                content=f"分析任务: {query}\n结果: {result.get('summary', '')}",
                metadata={"project_id": project_id or 0, "analysis_type": analysis_type}
            )
            
            return AgentResponse(
                agent_type=self.agent_type.value,
                content=result.get("summary", "分析完成"),
                references=[],
                metadata={
                    "analysis_type": analysis_type,
                    "data": result.get("data", {}),
                    "charts": result.get("charts", [])
                },
                confidence=0.8
            )
            
        except Exception as e:
            logger.error(f"AnalyzerAgent error: {e}")
            return AgentResponse(
                agent_type=self.agent_type.value,
                content=f"分析失败: {str(e)}",
                confidence=0.0
            )
    
    def _detect_analysis_type(self, query: str) -> str:
        """自动检测分析类型"""
        query_lower = query.lower()
        
        if any(kw in query_lower for kw in ["趋势", "时间", "变化", "trend", "timeline"]):
            return "timeline"
        if any(kw in query_lower for kw in ["热点", "热门", "hotspot", "hot"]):
            return "hotspot"
        if any(kw in query_lower for kw in ["关键词", "词频", "keyword", "frequency"]):
            return "keywords"
        if any(kw in query_lower for kw in ["对比", "比较", "compare"]):
            return "comparison"
        if any(kw in query_lower for kw in ["突现", "burst"]):
            return "burst"
        
        return "keywords"  # 默认
    
    async def _perform_analysis(
        self, query: str, project_id: Optional[int],
        analysis_type: str, **kwargs
    ) -> Dict[str, Any]:
        """执行具体分析"""
        if self.trend_service:
            if analysis_type == "keywords":
                data = await self.trend_service.get_keyword_frequency(project_id)
                return {
                    "summary": f"共发现{len(data)}个关键词",
                    "data": {"keywords": data},
                    "charts": ["wordcloud", "bar"]
                }
            elif analysis_type == "timeline":
                data = await self.trend_service.get_timeline(project_id)
                return {
                    "summary": "趋势时间线分析完成",
                    "data": {"timeline": data},
                    "charts": ["line"]
                }
            elif analysis_type == "hotspot":
                data = await self.trend_service.get_hotspots(project_id)
                return {
                    "summary": f"识别到{len(data)}个研究热点",
                    "data": {"hotspots": data},
                    "charts": ["heatmap", "wordcloud"]
                }
            elif analysis_type == "burst":
                data = await self.trend_service.get_burst_terms(project_id)
                return {
                    "summary": f"检测到{len(data)}个突现词",
                    "data": {"bursts": data},
                    "charts": ["timeline"]
                }
        
        # 无趋势服务时使用LLM分析
        if self._llm:
            prompt = f"""请分析以下研究问题并给出数据洞察：

问题：{query}
分析类型：{analysis_type}

请给出：
1. 主要发现
2. 数据趋势描述
3. 建议关注的方向"""
            
            response = await self._llm.ainvoke(prompt)
            return {
                "summary": response.content,
                "data": {},
                "charts": []
            }
        
        return {"summary": "分析服务未就绪", "data": {}, "charts": []}
