# AI训练数据规划表

> **版本**: v1.0  
> **负责人**: AI工程师  
> **周期**: Phase 1 规划, Phase 4 执行

---

## 数据集总览

| 数据集 | 用途 | 数量 | 优先级 | 状态 |
|-------|------|------|--------|------|
| PDF布局分析 | LayoutLMv3训练 | 3,000篇 | P0 | 待收集 |
| 关键词NER | BERT微调 | 10,000篇 | P0 | 待收集 |
| BGE评测集 | 基线评测+可选微调 | 5,000对 | P1 | 待收集 |
| RAG评测集 | 端到端评估 | 500对 | P0 | 待构建 |

---

## 1. PDF布局分析数据 (LayoutLMv3)

### 需求说明
用于训练LayoutLMv3识别学术论文的布局结构，包括标题、作者、摘要、章节、表格、图片等区域。

### 数据规格

| 字段 | 说明 |
|-----|------|
| 数据来源 | arXiv论文、IEEE论文 |
| 总数量 | 3,000篇PDF |
| 标注类型 | 边界框 + 类别标签 |
| 标注工具 | Label Studio |

### 标签定义

```yaml
labels:
  - TITLE         # 标题
  - AUTHOR        # 作者信息
  - ABSTRACT      # 摘要
  - SECTION       # 章节标题
  - PARAGRAPH     # 正文段落
  - TABLE         # 表格
  - FIGURE        # 图片
  - CAPTION       # 图表标题
  - REFERENCE     # 参考文献
  - HEADER        # 页眉
  - FOOTER        # 页脚
```

### 数据格式

```json
{
    "file_name": "paper_001.pdf",
    "pages": [
        {
            "page_number": 1,
            "width": 612,
            "height": 792,
            "annotations": [
                {
                    "label": "TITLE",
                    "bbox": [72, 72, 540, 100],
                    "text": "Attention Is All You Need"
                }
            ]
        }
    ]
}
```

### 标注指南
1. 每篇论文标注前3页（关键元素集中）
2. 边界框应紧密包围目标区域
3. 重叠区域以语义为准归类
4. 跨页元素分别标注

---

## 2. 关键词NER数据 (BERT)

### 需求说明
用于训练BERT模型从论文摘要中提取关键词实体。

### 数据规格

| 字段 | 说明 |
|-----|------|
| 数据来源 | arXiv摘要、论文关键词 |
| 总数量 | 10,000篇论文摘要 |
| 标注类型 | BIO序列标注 |
| 标注工具 | Label Studio / Doccano |

### 标签定义

```yaml
labels:
  - B-KW    # 关键词开始
  - I-KW    # 关键词内部
  - O       # 非关键词
```

### 数据格式

```json
{
    "id": 1,
    "text": "We propose a new attention mechanism for transformers.",
    "tokens": ["We", "propose", "a", "new", "attention", "mechanism", "for", "transformers", "."],
    "labels": ["O", "O", "O", "O", "B-KW", "I-KW", "O", "B-KW", "O"]
}
```

### 构建策略
1. 使用论文自带的Keywords作为弱监督标签
2. 通过关键词在摘要中的出现自动标注
3. 人工校正样本 (20% 抽样校正)

---

## 3. BGE评测数据 (检索评测+可选微调)

### 需求说明
用于评估原版BGE-M3的学术检索性能，并在必要时进行微调。

### 数据规格

| 字段 | 说明 |
|-----|------|
| 数据来源 | 构造的查询-文档对 |
| 总数量 | 5,000对 |
| 用途 | 基线评测 (先) + 微调 (按需) |

### 数据格式

```json
{
    "query": "transformer自注意力机制的计算复杂度",
    "positive_doc": "Self-attention computes attention weights...",
    "negative_docs": [
        "Convolutional networks use filters...",
        "RNN processes sequences step by step..."
    ],
    "source_paper_id": 123
}
```

### 评测策略

```
Step 1: 使用原版BGE-M3进行基线评测
        |
        ├── Recall@10 > 85% → 跳过微调 ✓
        |
        └── Recall@10 < 85% → 执行微调
              ├── 使用对比学习
              ├── 小学习率 (1e-5)
              └── 少量epoch (3)
```

---

## 4. RAG评测数据

### 需求说明
用于评估完整RAG系统的端到端性能，包括检索准确性和答案质量。

### 数据规格

| 字段 | 说明 |
|-----|------|
| 数据来源 | 人工构建 |
| 总数量 | 500对 |
| 类型 | 问答对 + 相关文档 |

### 数据格式

```json
{
    "id": 1,
    "question": "BERT模型的预训练目标是什么？",
    "answer": "BERT使用两个预训练目标：掩码语言模型(MLM)和下一句预测(NSP)...",
    "relevant_paper_ids": [45, 67],
    "relevant_chunks": ["chunk_45_3", "chunk_67_1"],
    "difficulty": "medium",
    "category": "NLP"
}
```

### 评测指标

| 指标 | 权重 | 目标 |
|-----|------|------|
| Retrieve Recall@5 | 30% | ≥80% |
| Retrieve Recall@10 | 20% | ≥85% |
| Answer Correctness | 30% | ≥85% |
| Citation Accuracy | 20% | ≥90% |

---

## 数据收集计划

### Timeline

```
M1 (Week 1-4): 数据规划 + 标注工具搭建
    └── 完成本文档
    └── 部署Label Studio
    └── 定义标注规范

M4 (Week 13-16): 数据收集开始
    └── 下载arXiv论文
    └── 启动PDF布局标注
    └── 启动NER数据构建

M5 (Week 17-18): 数据标注
    └── 完成3000篇PDF标注
    └── 完成10000篇NER标注
    └── 构建BGE评测集

M5 (Week 19): 基线评测
    └── BGE-M3基线评测
    └── 决策是否微调
```

### 资源需求

| 资源 | 数量 | 说明 |
|-----|------|------|
| 标注人员 | 2-3人 | 兼职研究生 |
| GPU | RTX 4090 x 1 | 模型训练 |
| 存储 | 500GB | PDF文件+标注数据 |

---

## 下载脚本示例

```python
# scripts/download_arxiv.py
import arxiv

def download_papers(query: str, max_results: int = 1000):
    """
    从arXiv下载论文
    """
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate
    )
    
    for paper in search.results():
        paper.download_pdf(dirpath="./data/papers/")
        
# 下载NLP领域论文
download_papers("cat:cs.CL AND (transformer OR BERT OR GPT)", 2000)

# 下载CV领域论文  
download_papers("cat:cs.CV AND (vision transformer OR ViT)", 1000)
```

---

*AI训练数据规划 v1.0*
