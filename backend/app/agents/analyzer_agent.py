"""
Analyzer Agent - 分析Agent

负责趋势分析、统计和数据洞察。
集成 Skills:
- extract_tables_from_pdf（PDF表格提取）
- generate_statistical_chart（统计图表生成）
- build_knowledge_graph（知识图谱构建）
- generate_viz_code（可视化代码生成）
"""
from typing import Optional, Dict, Any, List
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
    5. [Skill] PDF 表格提取（extract_tables_from_pdf）
    6. [Skill] 知识图谱构建（build_knowledge_graph）
    7. [Skill] 统计图表生成（generate_statistical_chart）
    8. [Skill] 可视化代码生成（generate_viz_code）
    """
    
    agent_type = AgentType.ANALYZER
    description = "趋势分析与数据统计Agent"
    _skill_categories = ["academic", "analysis", "utility", "visualization"]  # 可使用学术类 + 分析类 + 工具类 + 可视化类 Skills
    
    TRIGGER_KEYWORDS = [
        "分析", "趋势", "热点", "统计", "对比", "比较",
        "频率", "分布", "变化", "增长", "下降",
        "关键词", "热门", "突现", "领域",
        "analyze", "trend", "statistics", "compare",
        "distribution", "growth", "hotspot"
    ]
    
    # Skill 触发关键词
    TABLE_KEYWORDS = ["表格", "table", "数据表", "实验数据", "提取表"]
    KG_KEYWORDS = ["知识图谱", "knowledge graph", "实体关系", "关系图", "概念图"]
    CHART_KEYWORDS = ["图表", "chart", "绘图", "可视化", "画图", "plot", "visualiz"]
    
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
        
        # Skill 相关关键词也增加匹配度
        for kw in self.TABLE_KEYWORDS + self.KG_KEYWORDS + self.CHART_KEYWORDS:
            if kw in query_lower:
                score += 0.15
        
        return min(score, 1.0)
    
    async def execute(
        self,
        query: str,
        project_id: Optional[int] = None,
        analysis_type: str = "auto",
        file_path: str = "",
        **kwargs
    ) -> AgentResponse:
        """
        执行分析任务
        
        增强流程：
        1. 检测是否需要调用 Skill（表格提取、知识图谱、图表生成）
        2. 执行 Skill 获取结构化数据
        3. 结合趋势服务或 LLM 进行分析
        4. 自动生成图表
        """
        skills_used = []
        skill_data = {}
        
        try:
            # 确定分析类型
            if analysis_type == "auto":
                analysis_type = self._detect_analysis_type(query)
            
            query_lower = query.lower()
            
            # ---- Skill: PDF 表格提取 ----
            if file_path and any(kw in query_lower for kw in self.TABLE_KEYWORDS):
                logger.info(f"[AnalyzerAgent] Extracting tables from: {file_path}")
                table_result = await self._execute_skill(
                    "extract_tables_from_pdf", file_path=file_path
                )
                if table_result.success:
                    skill_data["tables"] = table_result.data
                    skills_used.append("extract_tables_from_pdf")
            
            # ---- Skill: 知识图谱构建 ----
            if any(kw in query_lower for kw in self.KG_KEYWORDS):
                text = kwargs.get("text", query)
                logger.info("[AnalyzerAgent] Building knowledge graph")
                kg_result = await self._execute_skill(
                    "build_knowledge_graph", text=text
                )
                if kg_result.success:
                    skill_data["knowledge_graph"] = kg_result.data
                    skills_used.append("build_knowledge_graph")
            
            # ---- 核心分析逻辑 ----
            result = await self._perform_analysis(
                query, project_id, analysis_type, **kwargs
            )
            
            # ---- Skill: 自动生成图表 ----
            chart_images = []
            if any(kw in query_lower for kw in self.CHART_KEYWORDS) or result.get("charts"):
                chart_images = await self._generate_charts_for_data(
                    result, skills_used
                )
                if chart_images:
                    skills_used.append("generate_chart")
            
            # 合并 Skill 数据到结果
            if skill_data:
                result.setdefault("data", {}).update(skill_data)
            if chart_images:
                result["chart_images"] = chart_images
            
            # 保存分析记忆
            await self._save_to_memory(
                content=f"分析任务: {query}\n结果: {result.get('summary', '')}",
                metadata={
                    "project_id": project_id or 0,
                    "analysis_type": analysis_type,
                    "skills_used": skills_used,
                },
            )
            
            return AgentResponse(
                agent_type=self.agent_type.value,
                content=result.get("summary", "分析完成"),
                references=[],
                metadata={
                    "analysis_type": analysis_type,
                    "data": result.get("data", {}),
                    "charts": result.get("charts", []),
                    "chart_images": chart_images,
                    "skills_used": skills_used,
                },
                confidence=0.8,
            )
            
        except Exception as e:
            logger.error(f"AnalyzerAgent error: {e}")
            return AgentResponse(
                agent_type=self.agent_type.value,
                content=f"分析失败: {str(e)}",
                metadata={"skills_used": skills_used},
                confidence=0.0,
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
        if any(kw in query_lower for kw in self.KG_KEYWORDS):
            return "knowledge_graph"
        if any(kw in query_lower for kw in self.TABLE_KEYWORDS):
            return "table_extraction"
        
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
                    "charts": ["wordcloud", "bar"],
                }
            elif analysis_type == "timeline":
                data = await self.trend_service.get_timeline(project_id)
                return {
                    "summary": "趋势时间线分析完成",
                    "data": {"timeline": data},
                    "charts": ["line"],
                }
            elif analysis_type == "hotspot":
                data = await self.trend_service.get_hotspots(project_id)
                return {
                    "summary": f"识别到{len(data)}个研究热点",
                    "data": {"hotspots": data},
                    "charts": ["heatmap", "wordcloud"],
                }
            elif analysis_type == "burst":
                data = await self.trend_service.get_burst_terms(project_id)
                return {
                    "summary": f"检测到{len(data)}个突现词",
                    "data": {"bursts": data},
                    "charts": ["timeline"],
                }
        
        # 知识图谱类型已通过 Skill 处理
        if analysis_type == "knowledge_graph":
            return {
                "summary": "知识图谱已通过 build_knowledge_graph Skill 构建",
                "data": {},
                "charts": ["graph"],
            }
        
        if analysis_type == "table_extraction":
            return {
                "summary": "表格数据已通过 extract_tables_from_pdf Skill 提取",
                "data": {},
                "charts": ["table"],
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
                "charts": [],
            }
        
        return {"summary": "分析服务未就绪", "data": {}, "charts": []}
    
    async def _generate_charts_for_data(
        self, result: Dict[str, Any], skills_used: List[str]
    ) -> List[Dict]:
        """根据分析结果自动生成图表"""
        chart_images = []
        data = result.get("data", {})
        chart_types = result.get("charts", [])
        
        if not self._skill_registry:
            return []
        
        for chart_type in chart_types:
            try:
                chart_data = self._prepare_chart_data(chart_type, data)
                if not chart_data:
                    continue
                
                chart_result = await self._execute_skill(
                    "generate_chart",
                    chart_type=chart_type,
                    data=chart_data,
                    title=result.get("summary", "")[:50],
                )
                
                if chart_result.success:
                    chart_images.append({
                        "type": chart_type,
                        "image_base64": chart_result.data.get("image_base64", ""),
                    })
            except Exception as e:
                logger.warning(f"Chart generation failed for {chart_type}: {e}")
        
        return chart_images
    
    def _prepare_chart_data(
        self, chart_type: str, data: Dict[str, Any]
    ) -> Optional[Dict]:
        """为图表准备数据"""
        if chart_type in ("wordcloud", "bar") and "keywords" in data:
            keywords = data["keywords"]
            if isinstance(keywords, list) and keywords:
                if isinstance(keywords[0], dict):
                    labels = [k.get("keyword", "") for k in keywords[:20]]
                    values = [k.get("count", 0) for k in keywords[:20]]
                else:
                    return None
                if chart_type == "wordcloud":
                    return {"words": dict(zip(labels, values))}
                return {"labels": labels, "values": values}
        
        if chart_type == "line" and "timeline" in data:
            timeline = data["timeline"]
            if isinstance(timeline, list) and timeline:
                if isinstance(timeline[0], dict):
                    labels = [str(t.get("year", "")) for t in timeline]
                    values = [t.get("count", 0) for t in timeline]
                    return {"labels": labels, "values": values}
        
        if chart_type == "heatmap" and "hotspots" in data:
            # 热力图需要矩阵格式，这里做简单转换
            return None  # 需要更具体的数据结构
        
        return None
