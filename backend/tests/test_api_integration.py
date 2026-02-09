"""
API集成测试

测试所有API端点的基本功能。
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock


# ============ Auth API Tests ============

class TestAuthAPI:
    """认证API测试"""
    
    def test_register_schema(self):
        """测试注册请求Schema"""
        from app.api.v1.auth import UserCreate
        user = UserCreate(email="test@example.com", username="testuser", password="password123")
        assert user.email == "test@example.com"
        assert user.username == "testuser"
    
    def test_token_schema(self):
        """测试Token Schema"""
        from app.api.v1.auth import Token
        token = Token(access_token="abc123")
        assert token.access_token == "abc123"
        assert token.token_type == "bearer"


# ============ Agent API Tests ============

class TestAgentSystem:
    """Multi-Agent系统测试"""
    
    def test_agent_types(self):
        """测试Agent类型枚举"""
        from app.agents.base_agent import AgentType
        assert AgentType.RETRIEVER == "retriever_agent"
        assert AgentType.ANALYZER == "analyzer_agent"
        assert AgentType.WRITER == "writer_agent"
        assert AgentType.SEARCH == "search_agent"
    
    def test_agent_response(self):
        """测试Agent响应数据类"""
        from app.agents.base_agent import AgentResponse
        response = AgentResponse(
            agent_type="retriever_agent",
            content="Test answer",
            references=[{"text": "ref1"}],
            confidence=0.9
        )
        assert response.agent_type == "retriever_agent"
        assert response.confidence == 0.9
        
        d = response.to_dict()
        assert d["content"] == "Test answer"
        assert len(d["references"]) == 1
    
    def test_retriever_can_handle(self):
        """测试检索Agent的意图识别"""
        from app.agents.retriever_agent import RetrieverAgent
        agent = RetrieverAgent()
        
        # 检索类查询应有高分
        assert agent.can_handle("查找关于深度学习的论文") > 0.4
        assert agent.can_handle("什么是注意力机制？") > 0.3
        
    def test_analyzer_can_handle(self):
        """测试分析Agent的意图识别"""
        from app.agents.analyzer_agent import AnalyzerAgent
        agent = AnalyzerAgent()
        
        # 分析类查询
        assert agent.can_handle("分析近年来的研究趋势") > 0.4
        assert agent.can_handle("对比两种方法的优缺点") > 0.3
    
    def test_writer_can_handle(self):
        """测试写作Agent的意图识别"""
        from app.agents.writer_agent import WriterAgent
        agent = WriterAgent()
        
        assert agent.can_handle("帮我生成论文大纲") > 0.4
        assert agent.can_handle("润色这段文字") > 0.3
    
    def test_search_can_handle(self):
        """测试搜索Agent的意图识别"""
        from app.agents.search_agent import SearchAgent
        agent = SearchAgent()
        
        assert agent.can_handle("搜索arXiv上最新的论文") > 0.3
        assert agent.can_handle("查找Semantic Scholar上的引用") > 0.3
    
    def test_coordinator_routing(self):
        """测试协调器路由逻辑"""
        from app.agents.coordinator import AgentCoordinator
        from app.agents.base_agent import AgentType
        
        coordinator = AgentCoordinator()
        coordinator._register_agents()
        
        # 检索类应路由到RetrieverAgent
        agent, score = coordinator._route_query("查找深度学习论文")
        assert agent.agent_type == AgentType.RETRIEVER
        
        # 分析类应路由到AnalyzerAgent
        agent, score = coordinator._route_query("分析研究趋势变化")
        assert agent.agent_type == AgentType.ANALYZER


# ============ External API Tests ============

class TestExternalAPIs:
    """外部API客户端测试"""
    
    def test_s2_paper_from_api(self):
        """测试Semantic Scholar论文解析"""
        from app.services.external_apis.semantic_scholar import S2Paper
        
        data = {
            "paperId": "abc123",
            "title": "Test Paper",
            "abstract": "This is a test.",
            "year": 2024,
            "citationCount": 10,
            "referenceCount": 5,
            "authors": [{"name": "John Doe", "authorId": "1"}],
            "venue": "NeurIPS",
            "url": "https://example.com",
            "externalIds": {"DOI": "10.1234/test"},
            "fieldsOfStudy": ["Computer Science"],
            "tldr": {"text": "A test paper"},
            "isOpenAccess": True,
        }
        
        paper = S2Paper.from_api(data)
        assert paper.paper_id == "abc123"
        assert paper.title == "Test Paper"
        assert paper.year == 2024
        assert paper.citation_count == 10
        assert len(paper.authors) == 1
        assert paper.doi == "10.1234/test"
    
    def test_openalex_work_from_api(self):
        """测试OpenAlex作品解析"""
        from app.services.external_apis.openalex import OpenAlexWork
        
        data = {
            "id": "W123",
            "title": "Test Work",
            "publication_year": 2024,
            "cited_by_count": 15,
            "authorships": [{
                "author": {"display_name": "Alice", "id": "A1"},
                "institutions": [{"display_name": "MIT"}]
            }],
            "concepts": [{"display_name": "ML", "level": 1, "score": 0.9}],
            "open_access": {"is_oa": True, "oa_url": "https://example.com/pdf"},
            "primary_location": {"source": {"display_name": "Nature"}},
        }
        
        work = OpenAlexWork.from_api(data)
        assert work.title == "Test Work"
        assert work.year == 2024
        assert work.citation_count == 15
        assert len(work.authors) == 1
        assert work.authors[0]["institution"] == "MIT"
    
    def test_crossref_work_from_api(self):
        """测试CrossRef作品解析"""
        from app.services.external_apis.crossref import CrossRefWork
        
        data = {
            "DOI": "10.1234/test",
            "title": ["Test Paper"],
            "author": [{"given": "John", "family": "Doe"}],
            "published-print": {"date-parts": [[2024, 1]]},
            "container-title": ["Nature"],
            "is-referenced-by-count": 20,
            "references-count": 30,
        }
        
        work = CrossRefWork.from_api(data)
        assert work.doi == "10.1234/test"
        assert work.title == "Test Paper"
        assert work.year == 2024
        assert len(work.authors) == 1
        assert work.citation_count == 20
    
    def test_arxiv_paper_to_dict(self):
        """测试arXiv论文序列化"""
        from app.services.external_apis.arxiv_client import ArxivPaper
        
        paper = ArxivPaper(
            arxiv_id="2401.12345",
            title="Test Paper",
            abstract="Abstract text",
            authors=["Author A"],
            categories=["cs.CL"],
            published="2024-01-15"
        )
        
        d = paper.to_dict()
        assert d["source"] == "arxiv"
        assert d["arxiv_id"] == "2401.12345"


# ============ Trend Analyzer Tests ============

class TestTrendAnalyzer:
    """趋势分析测试"""
    
    def test_burst_term_dataclass(self):
        """测试突现词数据类"""
        from app.services.trend_analyzer import BurstTerm
        
        burst = BurstTerm(term="deep learning", start_year=2020, end_year=2023, strength=2.5)
        d = burst.to_dict()
        assert d["term"] == "deep learning"
        assert d["strength"] == 2.5
    
    def test_keyword_frequency_dataclass(self):
        """测试关键词频率数据类"""
        from app.services.trend_analyzer import KeywordFrequency
        
        kf = KeywordFrequency(keyword="neural network", count=50, percentage=12.5)
        d = kf.to_dict()
        assert d["count"] == 50
        assert d["percentage"] == 12.5


# ============ Layout Analyzer Tests ============

class TestLayoutAnalyzer:
    """布局分析测试"""
    
    def test_region_types(self):
        """测试区域类型枚举"""
        from app.services.layout_analyzer import RegionType
        
        assert RegionType.TITLE == "title"
        assert RegionType.PARAGRAPH == "paragraph"
        assert RegionType.ABSTRACT == "abstract"
    
    def test_layout_region(self):
        """测试布局区域数据类"""
        from app.services.layout_analyzer import LayoutRegion, RegionType
        
        region = LayoutRegion(
            region_type=RegionType.TITLE,
            text="Test Title",
            bbox=[100, 50, 900, 100],
            confidence=0.95,
            page_number=1,
            order=0
        )
        assert region.region_type == RegionType.TITLE
        assert region.confidence == 0.95
    
    def test_page_layout(self):
        """测试页面布局"""
        from app.services.layout_analyzer import PageLayout, LayoutRegion, RegionType
        
        layout = PageLayout(
            page_number=1,
            width=612,
            height=792,
            regions=[
                LayoutRegion(RegionType.TITLE, "Title", [0, 0, 1000, 100], 0.9),
                LayoutRegion(RegionType.PARAGRAPH, "Body text", [0, 200, 1000, 800], 0.7),
            ]
        )
        
        assert len(layout.regions) == 2
        titles = layout.get_regions_by_type(RegionType.TITLE)
        assert len(titles) == 1
        assert titles[0].text == "Title"
    
    def test_heuristic_classify_line(self):
        """测试启发式行分类"""
        from app.services.layout_analyzer import LayoutAnalyzer, RegionType
        
        analyzer = LayoutAnalyzer()
        
        # 标题检测 (Abstract)
        rtype, conf = analyzer._classify_line("Abstract", [100, 300, 300, 320], 1)
        assert rtype == RegionType.ABSTRACT
        
        # Section header
        rtype, conf = analyzer._classify_line("1. Introduction", [50, 200, 400, 220], 2)
        assert rtype == RegionType.SECTION_HEADER
        
        # Reference
        rtype, conf = analyzer._classify_line("References", [50, 800, 300, 820], 10)
        assert rtype == RegionType.REFERENCE
        
        # Figure caption
        rtype, conf = analyzer._classify_line("Figure 1: System overview", [50, 500, 600, 520], 3)
        assert rtype == RegionType.CAPTION


# ============ Writing Assistant Tests ============

class TestWritingAssistant:
    """写作辅助测试"""
    
    def test_default_outline(self):
        """测试默认大纲模板"""
        from app.services.writing_assistant import WritingAssistant
        
        wa = WritingAssistant()
        outline = wa._default_outline("Deep Learning for NLP", "standard")
        assert "Deep Learning for NLP" in outline
        assert "引言" in outline
        assert "方法" in outline
        assert "实验" in outline
        assert "结论" in outline
