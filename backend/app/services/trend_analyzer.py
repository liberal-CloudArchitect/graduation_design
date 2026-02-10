"""
Trend Analyzer - 趋势分析服务

提供关键词频率统计、研究热点识别、时间趋势分析、突现词检测等功能。
"""
import math
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter, defaultdict
from dataclasses import dataclass
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class KeywordFrequency:
    """关键词频率"""
    keyword: str
    count: int
    percentage: float = 0.0
    
    def to_dict(self):
        return {"keyword": self.keyword, "count": self.count, "percentage": self.percentage}


@dataclass
class BurstTerm:
    """突现词"""
    term: str
    start_year: int
    end_year: int
    strength: float
    
    def to_dict(self):
        return {
            "term": self.term,
            "start_year": self.start_year,
            "end_year": self.end_year,
            "strength": self.strength
        }


class TrendAnalyzer:
    """
    趋势分析器
    
    功能：
    1. 关键词频率统计
    2. 研究热点识别 (TF-IDF评分)
    3. 时间趋势分析 (按年份统计)
    4. 突现词检测 (简化Kleinberg算法)
    5. 领域分布分析
    """
    
    # 中英文停用词
    STOP_WORDS = {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
        "都", "一", "这", "中", "大", "为", "上", "个", "到", "说",
        "们", "也", "会", "着", "要", "而", "去", "之", "过", "与",
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "shall", "can",
        "for", "and", "but", "or", "not", "no", "nor", "so", "yet",
        "to", "of", "in", "on", "at", "by", "from", "with", "as",
        "into", "about", "between", "through", "during", "before",
        "after", "above", "below", "this", "that", "these", "those",
        "it", "its", "they", "them", "their", "we", "our", "you",
    }
    
    async def get_keyword_frequency(
        self,
        db: AsyncSession,
        project_id: Optional[int] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        获取关键词频率统计
        
        从项目中所有论文的关键词字段统计频率。
        如果关键词字段为空，自动从摘要中提取关键词作为回退。
        """
        from app.models.paper import Paper
        
        query = select(Paper.keywords)
        if project_id:
            query = query.where(Paper.project_id == project_id)
        query = query.where(Paper.keywords.isnot(None))
        
        result = await db.execute(query)
        rows = result.scalars().all()
        
        # 统计关键词
        counter = Counter()
        for keywords in rows:
            if isinstance(keywords, list):
                for kw in keywords:
                    kw_clean = kw.strip().lower()
                    if kw_clean and kw_clean not in self.STOP_WORDS and len(kw_clean) > 1:
                        counter[kw_clean] += 1
            elif isinstance(keywords, str):
                import re
                parts = re.split(r'[,;，；]', keywords)
                for kw in parts:
                    kw_clean = kw.strip().lower()
                    if kw_clean and kw_clean not in self.STOP_WORDS and len(kw_clean) > 1:
                        counter[kw_clean] += 1
        
        # 回退：如果关键词字段全部为空，从摘要中提取
        if not counter:
            counter = await self._extract_keywords_from_abstracts(db, project_id, limit)
        
        total = sum(counter.values()) or 1
        
        frequencies = [
            KeywordFrequency(
                keyword=kw,
                count=count,
                percentage=round(count / total * 100, 2)
            )
            for kw, count in counter.most_common(limit)
        ]
        
        return [f.to_dict() for f in frequencies]
    
    async def _extract_keywords_from_abstracts(
        self,
        db: AsyncSession,
        project_id: Optional[int] = None,
        limit: int = 50
    ) -> Counter:
        """从论文摘要中提取关键词（回退方案）"""
        import re
        from app.models.paper import Paper
        
        query = select(Paper.abstract)
        if project_id:
            query = query.where(Paper.project_id == project_id)
        query = query.where(Paper.abstract.isnot(None))
        
        result = await db.execute(query)
        abstracts = result.scalars().all()
        
        counter = Counter()
        for abstract in abstracts:
            if not abstract:
                continue
            words = re.findall(r'[a-zA-Z]{3,}|[\u4e00-\u9fff]{2,6}', abstract.lower())
            for word in words:
                if word not in self.STOP_WORDS and len(word) > 1:
                    counter[word] += 1
        
        return counter
    
    async def get_text_keyword_frequency(
        self,
        db: AsyncSession,
        project_id: Optional[int] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        从论文全文中提取高频词 (TF-IDF风格)
        """
        from app.models.paper import Paper
        
        query = select(Paper.abstract)
        if project_id:
            query = query.where(Paper.project_id == project_id)
        query = query.where(Paper.abstract.isnot(None))
        
        result = await db.execute(query)
        abstracts = result.scalars().all()
        
        if not abstracts:
            return []
        
        # 简单词频统计
        import re
        word_counter = Counter()
        doc_counter = Counter()  # 文档频率
        
        for abstract in abstracts:
            if not abstract:
                continue
            # 分词 (简单空格分词 + 中文字符处理)
            words = re.findall(r'[a-zA-Z]{3,}|[\u4e00-\u9fff]{2,}', abstract.lower())
            unique_words = set()
            for word in words:
                if word not in self.STOP_WORDS:
                    word_counter[word] += 1
                    unique_words.add(word)
            for word in unique_words:
                doc_counter[word] += 1
        
        # TF-IDF 评分
        n_docs = len(abstracts)
        tfidf_scores = {}
        for word, tf in word_counter.items():
            df = doc_counter.get(word, 1)
            idf = math.log(n_docs / df + 1)
            tfidf_scores[word] = tf * idf
        
        # 按TF-IDF排序
        sorted_words = sorted(tfidf_scores.items(), key=lambda x: x[1], reverse=True)[:limit]
        
        return [
            {"keyword": word, "count": word_counter[word], "tfidf": round(score, 2)}
            for word, score in sorted_words
        ]
    
    async def get_timeline(
        self,
        db: AsyncSession,
        project_id: Optional[int] = None,
        keyword: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取时间趋势数据
        
        按年份统计论文数量和关键词分布。
        """
        from app.models.paper import Paper
        
        query = select(Paper)
        if project_id:
            query = query.where(Paper.project_id == project_id)
        
        result = await db.execute(query)
        papers = result.scalars().all()
        
        # 按年份分组
        year_data = defaultdict(lambda: {"count": 0, "keywords": Counter()})
        
        for paper in papers:
            year = None
            if paper.publication_date:
                year = paper.publication_date.year
            elif paper.created_at:
                year = paper.created_at.year
            
            if year is None:
                continue
            
            year_data[year]["count"] += 1
            
            keywords = paper.keywords if isinstance(paper.keywords, list) else []
            if isinstance(paper.keywords, str):
                import re
                keywords = [k.strip() for k in re.split(r'[,;，；]', paper.keywords)]
            
            for kw in keywords:
                kw_clean = kw.strip().lower()
                if kw_clean:
                    year_data[year]["keywords"][kw_clean] += 1
        
        # 构建时间线
        timeline = []
        for year in sorted(year_data.keys()):
            entry = {
                "year": year,
                "paper_count": year_data[year]["count"],
                "top_keywords": [
                    {"keyword": kw, "count": c}
                    for kw, c in year_data[year]["keywords"].most_common(10)
                ]
            }
            timeline.append(entry)
        
        return timeline
    
    async def get_hotspots(
        self,
        db: AsyncSession,
        project_id: Optional[int] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        识别研究热点
        
        基于关键词频率、引用数、近期趋势综合评分。
        """
        # 获取关键词频率
        keywords = await self.get_keyword_frequency(db, project_id, limit=100)
        
        if not keywords:
            return []
        
        # 计算热度分数 (简单模型)
        max_count = max(kw["count"] for kw in keywords) if keywords else 1
        
        hotspots = []
        for kw in keywords[:limit]:
            # 归一化频率作为热度
            hotness = kw["count"] / max_count
            hotspots.append({
                "keyword": kw["keyword"],
                "count": kw["count"],
                "hotness": round(hotness, 3),
                "percentage": kw["percentage"]
            })
        
        return hotspots
    
    async def get_burst_terms(
        self,
        db: AsyncSession,
        project_id: Optional[int] = None,
        min_frequency: int = 2
    ) -> List[Dict[str, Any]]:
        """
        突现词检测 (简化Kleinberg算法)
        
        检测在特定时间段内频率突然增高的关键词。
        """
        timeline = await self.get_timeline(db, project_id)
        
        if len(timeline) < 2:
            return []
        
        # 统计每个关键词在每个时间段的频率
        keyword_timeline: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        
        for entry in timeline:
            year = entry["year"]
            for kw_data in entry["top_keywords"]:
                keyword_timeline[kw_data["keyword"]][year] = kw_data["count"]
        
        years = sorted(set(e["year"] for e in timeline))
        
        bursts = []
        for keyword, yearly_counts in keyword_timeline.items():
            total = sum(yearly_counts.values())
            if total < min_frequency:
                continue
            
            # 计算平均频率
            avg_freq = total / len(years)
            
            # 检测频率突增的年份
            burst_start = None
            burst_strength = 0
            
            for year in years:
                count = yearly_counts.get(year, 0)
                if count > avg_freq * 1.5:  # 超过平均值1.5倍视为突现
                    if burst_start is None:
                        burst_start = year
                    burst_strength = max(burst_strength, count / max(avg_freq, 0.1))
                else:
                    if burst_start is not None:
                        bursts.append(BurstTerm(
                            term=keyword,
                            start_year=burst_start,
                            end_year=year - 1,
                            strength=round(burst_strength, 2)
                        ))
                        burst_start = None
                        burst_strength = 0
            
            # 如果突现持续到最后
            if burst_start is not None:
                bursts.append(BurstTerm(
                    term=keyword,
                    start_year=burst_start,
                    end_year=years[-1],
                    strength=round(burst_strength, 2)
                ))
        
        # 按强度排序
        bursts.sort(key=lambda b: b.strength, reverse=True)
        
        return [b.to_dict() for b in bursts[:30]]
    
    async def get_field_distribution(
        self,
        db: AsyncSession,
        project_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        获取领域分布
        
        基于关键词聚类或论文类别统计。
        """
        keywords = await self.get_keyword_frequency(db, project_id, limit=100)
        
        # 简单分类：按词频分层
        if not keywords:
            return []
        
        total = sum(kw["count"] for kw in keywords)
        
        # 按累计占比分为：核心、热门、一般、边缘
        fields = []
        cumulative = 0
        for kw in keywords:
            cumulative += kw["count"]
            ratio = cumulative / total
            
            if ratio <= 0.3:
                category = "核心领域"
            elif ratio <= 0.6:
                category = "热门领域"
            elif ratio <= 0.85:
                category = "一般领域"
            else:
                category = "边缘领域"
            
            fields.append({
                "keyword": kw["keyword"],
                "count": kw["count"],
                "category": category,
                "cumulative_ratio": round(ratio, 3)
            })
        
        return fields


# 全局实例
trend_analyzer = TrendAnalyzer()
