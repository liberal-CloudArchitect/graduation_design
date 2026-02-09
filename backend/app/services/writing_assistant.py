"""
Writing Assistant - 写作辅助服务

提供论文大纲生成、文献综述、段落润色、引用建议等功能。
"""
from typing import List, Dict, Any, Optional
from loguru import logger


class WritingAssistant:
    """
    写作辅助服务
    
    功能：
    1. 论文大纲生成
    2. 文献综述生成
    3. 段落润色
    4. 引用建议
    """
    
    def __init__(self, llm=None, rag_engine=None):
        self._llm = llm
        self._rag_engine = rag_engine
    
    def set_llm(self, llm):
        self._llm = llm
    
    def set_rag_engine(self, rag_engine):
        self._rag_engine = rag_engine
    
    async def generate_outline(
        self,
        topic: str,
        project_id: Optional[int] = None,
        style: str = "standard",
        sections: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        生成论文大纲
        
        Args:
            topic: 研究主题
            project_id: 项目ID (用于检索相关文献)
            style: 论文风格 (standard, conference, journal)
            sections: 自定义章节列表
        """
        # 检索相关文献作为参考
        ref_context = ""
        references = []
        if self._rag_engine and project_id:
            try:
                results = await self._rag_engine.search(topic, project_id, top_k=5)
                references = await self._rag_engine._fetch_documents(results)
                ref_context = "\n".join(
                    f"[{i+1}] {r.get('text', '')[:300]}"
                    for i, r in enumerate(references)
                )
            except Exception as e:
                logger.warning(f"Reference search failed: {e}")
        
        if not self._llm:
            return {
                "outline": self._default_outline(topic, style),
                "references": references,
                "style": style
            }
        
        section_hint = ""
        if sections:
            section_hint = f"\n请按以下章节组织：{', '.join(sections)}"
        
        style_desc = {
            "standard": "标准学术论文格式",
            "conference": "会议论文格式（较简洁）",
            "journal": "期刊论文格式（较详细）"
        }.get(style, "标准学术论文格式")
        
        prompt = f"""请为以下研究主题生成一份详细的{style_desc}大纲。

研究主题：{topic}

相关文献参考：
{ref_context if ref_context else '（无可用参考文献，请基于通用知识生成）'}
{section_hint}

要求：
1. 使用Markdown格式
2. 每个一级标题下包含2-4个二级要点
3. 标注每个部分的建议字数
4. 在"相关工作"部分给出文献综述方向建议
5. 包含研究创新点说明

请使用以下结构：
# 论文标题建议
## 1. 引言
## 2. 相关工作  
## 3. 方法/模型
## 4. 实验
## 5. 结果与讨论
## 6. 结论
"""
        
        try:
            response = await self._llm.ainvoke(prompt)
            return {
                "outline": response.content,
                "references": references,
                "style": style
            }
        except Exception as e:
            logger.error(f"Outline generation failed: {e}")
            return {
                "outline": self._default_outline(topic, style),
                "references": references,
                "style": style,
                "error": str(e)
            }
    
    async def generate_review(
        self,
        topic: str,
        project_id: Optional[int] = None,
        max_words: int = 800,
        focus_areas: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        生成文献综述
        
        Args:
            topic: 研究主题
            project_id: 项目ID
            max_words: 最大字数
            focus_areas: 重点关注的领域
        """
        # 检索文献
        references = []
        ref_context = ""
        if self._rag_engine:
            try:
                project = project_id
                results = await self._rag_engine.search(topic, project, top_k=10)
                references = await self._rag_engine._fetch_documents(results)
                ref_context = "\n\n".join(
                    f"文献[{i+1}]:\n标题: {r.get('title', 'Unknown')}\n内容: {r.get('text', '')[:500]}"
                    for i, r in enumerate(references)
                )
            except Exception as e:
                logger.warning(f"Reference search failed: {e}")
        
        if not self._llm:
            return {
                "review": "LLM未初始化，无法生成文献综述。",
                "references": references,
                "word_count": 0
            }
        
        focus_hint = ""
        if focus_areas:
            focus_hint = f"\n请重点关注以下方面：{', '.join(focus_areas)}"
        
        prompt = f"""请基于以下参考文献，撰写一篇关于「{topic}」的文献综述。

参考文献：
{ref_context if ref_context else '（无可用参考文献，请基于通用知识撰写）'}
{focus_hint}

要求：
1. 学术写作风格，语言规范
2. 使用[1][2]等格式引用文献
3. 逻辑结构清晰，分段合理
4. 包含以下内容：
   - 研究背景和意义
   - 现有方法和技术的发展脉络
   - 各方法的优缺点对比
   - 现有研究的不足和未来方向
5. 字数约{max_words}字
"""
        
        try:
            response = await self._llm.ainvoke(prompt)
            content = response.content
            return {
                "review": content,
                "references": references,
                "word_count": len(content)
            }
        except Exception as e:
            logger.error(f"Review generation failed: {e}")
            return {"review": f"生成失败: {str(e)}", "references": [], "word_count": 0}
    
    async def polish_text(
        self,
        text: str,
        style: str = "academic",
        language: str = "auto"
    ) -> Dict[str, Any]:
        """
        润色学术文本
        
        Args:
            text: 需要润色的原文
            style: 润色风格 (academic, formal, concise)
            language: 语言 (auto, zh, en)
        """
        if not self._llm:
            return {"polished": text, "changes": [], "original": text}
        
        style_desc = {
            "academic": "学术论文风格，专业术语准确",
            "formal": "正式文体，语言严谨",
            "concise": "简洁精练，去除冗余"
        }.get(style, "学术论文风格")
        
        prompt = f"""请对以下学术文本进行润色和改进。

原文：
{text}

要求：
1. 润色风格：{style_desc}
2. 保持原意不变
3. 改善句式结构和逻辑连贯性
4. 使用更专业的学术表达
5. 修正语法和拼写错误

请按以下格式输出：

## 润色后文本
（完整的润色后文本）

## 主要修改说明
（列出主要改动，每条一行）
"""
        
        try:
            response = await self._llm.ainvoke(prompt)
            content = response.content
            
            # 尝试分离润色文本和修改说明
            polished = content
            changes = []
            
            if "## 润色后文本" in content and "## 主要修改说明" in content:
                parts = content.split("## 主要修改说明")
                polished = parts[0].replace("## 润色后文本", "").strip()
                if len(parts) > 1:
                    changes = [
                        line.strip().lstrip("- •")
                        for line in parts[1].strip().split("\n")
                        if line.strip()
                    ]
            
            return {
                "polished": polished,
                "changes": changes,
                "original": text,
                "style": style
            }
        except Exception as e:
            logger.error(f"Polish failed: {e}")
            return {"polished": text, "changes": [], "original": text, "error": str(e)}
    
    async def suggest_citations(
        self,
        text: str,
        project_id: Optional[int] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        根据文本内容推荐引用文献
        
        Args:
            text: 需要引用的文本段落
            project_id: 项目ID
            limit: 推荐数量
        """
        references = []
        if self._rag_engine:
            try:
                results = await self._rag_engine.search(text, project_id, top_k=limit)
                references = await self._rag_engine._fetch_documents(results)
            except Exception as e:
                logger.warning(f"Citation search failed: {e}")
        
        suggestions = []
        for i, ref in enumerate(references):
            suggestions.append({
                "index": i + 1,
                "title": ref.get("title", "Unknown"),
                "text_snippet": ref.get("text", "")[:200],
                "relevance_score": ref.get("score", 0),
                "citation_format": f"[{i+1}]"
            })
        
        return {
            "suggestions": suggestions,
            "total": len(suggestions),
            "input_text": text[:100] + "..."
        }
    
    def _default_outline(self, topic: str, style: str) -> str:
        """默认大纲模板"""
        return f"""# {topic}

## 1. 引言 (建议800-1000字)
- 1.1 研究背景
- 1.2 研究问题
- 1.3 研究目的和意义
- 1.4 论文结构

## 2. 相关工作 (建议1500-2000字)
- 2.1 领域综述
- 2.2 现有方法分析
- 2.3 研究不足

## 3. 方法 (建议2000-3000字)
- 3.1 总体框架
- 3.2 核心算法/模型
- 3.3 实现细节

## 4. 实验 (建议1500-2000字)
- 4.1 实验设置
- 4.2 数据集
- 4.3 评估指标
- 4.4 实验结果

## 5. 讨论 (建议800-1000字)
- 5.1 结果分析
- 5.2 局限性

## 6. 结论 (建议500-800字)
- 6.1 主要贡献
- 6.2 未来工作
"""


# 全局实例
writing_assistant = WritingAssistant()
