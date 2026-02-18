"""
关键质量回归测试

覆盖本轮修复的核心规则，避免后续回归：
1) PDF 解析标题质量判定
2) 知识图谱回退构建的噪声实体过滤
"""

from app.api.v1.papers import _is_reliable_paper_title
from app.skills.analysis.analysis_skills import _build_kg_regex


def test_reliable_paper_title_rejects_noise():
    noisy_title = (
        "AcademicEditors: HemingJia,Jose limited knowledge or because, "
        "despite their awareness, they apply only minimal protection"
    )
    assert _is_reliable_paper_title(noisy_title) is False


def test_reliable_paper_title_accepts_normal_title():
    normal_title = (
        "Improving the Cybersecurity Awareness of Young Adults "
        "through a Game-Based Informal Learning Strategy"
    )
    assert _is_reliable_paper_title(normal_title) is True


def test_kg_regex_filters_noise_entities():
    text = (
        "However, the paper introduces RAG and LLM integration. "
        "Moreover, RAG uses Retrieval and Generation modules. "
        "The CookieAware game improves Cybersecurity Awareness for Young Adults."
    )
    result = _build_kg_regex(text, max_entities=12)
    node_ids = {node["id"] for node in result["nodes"]}

    # 保留关键实体
    assert "RAG" in node_ids
    assert "LLM" in node_ids
    assert "Cybersecurity Awareness" in node_ids

    # 过滤连接词噪声
    assert "However" not in node_ids
    assert "Moreover" not in node_ids
