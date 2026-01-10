# AI工程师实施计划

> **角色**: AI/算法工程师 (2人)  
> **负责人**: AI Lead + AI工程师  
> **技术栈**: PyTorch + Transformers + LangChain + PEFT

---

## 职责概览

| 工程师 | 主要负责 |
|-------|---------|
| **AI Lead** | 模型架构、微调策略、Agent系统、评估体系 |
| **AI工程师** | 数据标注、模型训练、推理优化 |

---

## 10个月开发时间线

```
┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐
│ M1  │ M2  │ M3  │ M4  │ M5  │ M6  │ M7  │ M8  │ M9  │ M10 │
├─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│数据 │GPU  │RAG  │RAG  │基线 │微调 │Agent│Agent│评估 │优化 │
│规划 │环境 │原型 │优化 │评测 │训练 │开发 │集成 │测试 │部署 │
└─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┘
```

---

## Phase 1: 数据规划与GPU环境 (M1-M2)

### Week 1-4: 训练数据规划

```yaml
数据集规划:

1. PDF布局分析数据 (LayoutLMv3):
   数量: 3,000篇学术论文
   标注: 布局区域标签 (title, author, abstract, section, table, figure)
   工具: Label Studio + PDF渲染
   
2. 关键词NER数据 (BERT):
   数量: 10,000篇论文摘要
   标注: BIO序列标注
   格式: {"tokens": [...], "labels": ["B-KW", "I-KW", "O", ...]}

3. BGE评测数据 (可选微调):
   数量: 5,000对查询-文档对
   用途: 基线评测 + 可选微调
   格式: {"query": "...", "positive": "...", "negative": "..."}

4. RAG评测数据:
   数量: 500个问答对
   格式: {"question": "...", "answer": "...", "source_papers": [...]}
```

### Week 5-8: GPU环境搭建

```bash
# GPU服务器环境
ssh user@gpu-server

# 创建环境
conda create -n llm python=3.10
conda activate llm

# PyTorch + CUDA
pip install torch==2.1.0 --index-url https://download.pytorch.org/whl/cu118

# Transformers生态
pip install transformers==4.36.0 datasets==2.16.0
pip install peft==0.7.0 accelerate==0.25.0 bitsandbytes==0.41.0

# 向量模型
pip install FlagEmbedding sentence-transformers

# RAG框架
pip install langchain==0.1.0 llama-index==0.9.30

# 布局分析
pip install pytesseract pdf2image layoutparser

# 下载模型
huggingface-cli download microsoft/layoutlmv3-base --local-dir ./models/layoutlmv3
huggingface-cli download BAAI/bge-m3 --local-dir ./models/bge-m3
huggingface-cli download bert-base-chinese --local-dir ./models/bert-base-chinese
```

---

## Phase 2-3: RAG原型与优化 (M3-M4)

### Week 9-12: RAG引擎原型

```python
# rag/retriever.py
from FlagEmbedding import BGEM3FlagModel

class HybridRetriever:
    """混合检索器 - MVP版本"""
    
    def __init__(self):
        # 使用原版BGE-M3 (不微调)
        self.bge = BGEM3FlagModel('BAAI/bge-m3')
        self.es = Elasticsearch()
        self.milvus = MilvusClient()
    
    async def retrieve(self, query: str, top_k: int = 10):
        # 1. BM25检索 (Elasticsearch)
        bm25_results = await self._bm25_search(query, top_k * 2)
        
        # 2. 向量检索 (Milvus + BGE-M3)
        query_emb = self.bge.encode(query)['dense_vecs'][0]
        dense_results = await self._dense_search(query_emb, top_k * 2)
        
        # 3. RRF融合
        fused = self._rrf_fusion([
            (bm25_results, 0.4),
            (dense_results, 0.6)
        ])
        
        return fused[:top_k]
    
    def _rrf_fusion(self, result_lists, k=60):
        """Reciprocal Rank Fusion"""
        scores = {}
        for results, weight in result_lists:
            for rank, doc in enumerate(results):
                doc_id = doc['id']
                scores[doc_id] = scores.get(doc_id, 0) + weight / (k + rank + 1)
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

### Week 13-16: Rerank与优化

```python
# rag/reranker.py
from FlagEmbedding import FlagReranker

class BGEReranker:
    """BGE重排序器"""
    
    def __init__(self):
        self.reranker = FlagReranker('BAAI/bge-reranker-large')
    
    def rerank(self, query: str, documents: List[str], top_k: int = 5):
        pairs = [[query, doc] for doc in documents]
        scores = self.reranker.compute_score(pairs)
        
        ranked = sorted(zip(documents, scores), key=lambda x: x[1], reverse=True)
        return [doc for doc, score in ranked[:top_k]]
```

---

## Phase 4: 基线评测与微调 ⭐ (M5-M6)

### Week 17-18: 基线评测

```python
# evaluation/baseline_eval.py

async def evaluate_bge_baseline():
    """评估原版BGE-M3性能"""
    
    model = BGEM3FlagModel('BAAI/bge-m3')
    test_data = load_test_data()  # 500个查询-答案对
    
    metrics = {
        'recall@5': [],
        'recall@10': [],
        'mrr': []
    }
    
    for item in test_data:
        query = item['query']
        relevant_ids = item['relevant_doc_ids']
        
        # 检索
        results = await retriever.retrieve(query, top_k=10)
        retrieved_ids = [r['id'] for r in results]
        
        # 计算指标
        metrics['recall@5'].append(
            len(set(retrieved_ids[:5]) & set(relevant_ids)) / len(relevant_ids)
        )
        metrics['recall@10'].append(
            len(set(retrieved_ids[:10]) & set(relevant_ids)) / len(relevant_ids)
        )
        # MRR计算...
    
    print(f"=== BGE-M3 基线评测 ===")
    print(f"Recall@5:  {np.mean(metrics['recall@5']):.2%}")
    print(f"Recall@10: {np.mean(metrics['recall@10']):.2%}")
    print(f"MRR:       {np.mean(metrics['mrr']):.4f}")
    
    # 决策: Recall@10 > 85% 则跳过微调
    if np.mean(metrics['recall@10']) > 0.85:
        print("✅ 基线足够好，跳过BGE微调")
        return False
    else:
        print("⚠️ 需要微调以提升效果")
        return True
```

### Week 19-20: 模型微调

#### 训练1: LayoutLMv3 布局分析

```python
# training/train_layoutlm.py
from transformers import (
    LayoutLMv3ForTokenClassification, 
    LayoutLMv3Processor,
    TrainingArguments, 
    Trainer
)

# 标签定义
LABELS = ["O", "B-TITLE", "I-TITLE", "B-AUTHOR", "I-AUTHOR", 
          "B-ABSTRACT", "I-ABSTRACT", "B-SECTION", "B-TABLE", "B-FIGURE"]

# 加载模型
processor = LayoutLMv3Processor.from_pretrained("microsoft/layoutlmv3-base")
model = LayoutLMv3ForTokenClassification.from_pretrained(
    "microsoft/layoutlmv3-base",
    num_labels=len(LABELS)
)

# 训练参数
training_args = TrainingArguments(
    output_dir="./models/layoutlmv3-paper",
    num_train_epochs=10,
    per_device_train_batch_size=4,
    per_device_eval_batch_size=4,
    learning_rate=5e-5,
    weight_decay=0.01,
    evaluation_strategy="epoch",
    save_strategy="epoch",
    load_best_model_at_end=True
)

# 训练
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    eval_dataset=eval_dataset,
    compute_metrics=compute_metrics
)
trainer.train()

# 保存
model.save_pretrained("./models/layoutlmv3-paper/final")
processor.save_pretrained("./models/layoutlmv3-paper/final")
```

#### 训练2: BERT 关键词NER

```python
# training/train_bert_ner.py
from transformers import BertForTokenClassification, BertTokenizer

# 标签
NER_LABELS = ["O", "B-KW", "I-KW"]

model = BertForTokenClassification.from_pretrained(
    "bert-base-chinese",
    num_labels=len(NER_LABELS)
)

training_args = TrainingArguments(
    output_dir="./models/bert-keyword",
    num_train_epochs=5,
    per_device_train_batch_size=16,
    learning_rate=2e-5,
    warmup_ratio=0.1
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=ner_dataset,
    eval_dataset=ner_eval_dataset
)
trainer.train()
```

#### 训练3: BGE-M3 (按需)

```python
# training/train_bge_optional.py
from sentence_transformers import SentenceTransformer, losses

def train_bge_if_needed(need_finetune: bool):
    if not need_finetune:
        print("跳过BGE微调")
        return
    
    model = SentenceTransformer('BAAI/bge-m3')
    
    # 对比学习
    train_loss = losses.MultipleNegativesRankingLoss(model)
    
    # 小学习率防止灾难性遗忘
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=3,  # 少量epoch
        warmup_steps=50,
        optimizer_params={'lr': 1e-5},  # 小学习率
        save_best_model=True,
        output_path="./models/bge-m3-finetuned"
    )
```

### Week 21-22: 模型评估

```python
# evaluation/model_eval.py

def evaluate_all_models():
    results = {}
    
    # 1. LayoutLMv3评估
    layout_model = LayoutLMv3ForTokenClassification.from_pretrained("models/layoutlmv3-paper")
    results['layoutlmv3'] = evaluate_layout_model(layout_model)
    
    # 2. BERT NER评估
    ner_model = BertForTokenClassification.from_pretrained("models/bert-keyword")
    results['bert_ner'] = evaluate_ner_model(ner_model)
    
    # 3. BGE评估 (如果微调了)
    if os.path.exists("models/bge-m3-finetuned"):
        bge_model = BGEM3FlagModel("models/bge-m3-finetuned")
    else:
        bge_model = BGEM3FlagModel("BAAI/bge-m3")
    results['bge'] = evaluate_retrieval(bge_model)
    
    print("=== 模型评估结果 ===")
    print(f"LayoutLMv3 F1: {results['layoutlmv3']['f1']:.2%}")
    print(f"BERT NER F1:   {results['bert_ner']['f1']:.2%}")
    print(f"BGE Recall@10: {results['bge']['recall_at_10']:.2%}")
```

---

## Phase 5: Agent系统开发 (M7-M8)

### Week 23-28: Multi-Agent实现

```python
# agents/coordinator.py
from langchain.agents import AgentExecutor
from langchain.tools import Tool

class ResearchAgentCoordinator:
    """研究Agent协调器"""
    
    def __init__(self):
        self.retriever = RetrieverAgent()
        self.analyzer = AnalyzerAgent()
        self.writer = WriterAgent()
        self.searcher = ExternalSearchAgent()
    
    async def generate_literature_review(self, topic: str) -> dict:
        """生成文献综述"""
        
        # Step 1: 检索相关文献
        local_papers = await self.retriever.search_local(topic)
        external_papers = await self.searcher.search_external(topic)
        all_papers = local_papers + external_papers
        
        # Step 2: 分析每篇论文
        analyses = []
        for paper in all_papers[:30]:
            analysis = await self.analyzer.analyze(paper)
            analyses.append(analysis)
        
        # Step 3: 生成综述
        review = await self.writer.write_review(topic, analyses)
        
        return {
            "review": review,
            "sources": all_papers,
            "analysis_count": len(analyses)
        }

# agents/retriever_agent.py
class RetrieverAgent:
    """检索Agent"""
    
    def __init__(self):
        self.rag_engine = RAGEngine()
        self.semantic_scholar = SemanticScholarClient()
    
    async def search_local(self, query: str, top_k: int = 20):
        return await self.rag_engine.search(query, top_k)
    
    async def search_external(self, query: str, top_k: int = 20):
        return await self.semantic_scholar.search(query, top_k)

# agents/writer_agent.py
class WriterAgent:
    """写作Agent"""
    
    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o")
    
    async def write_review(self, topic: str, analyses: List[dict]) -> str:
        prompt = f"""
        根据以下论文分析，撰写关于"{topic}"的文献综述。
        
        要求：
        1. 包含引言、主体(按主题分组)、结论
        2. 引用格式为[1][2]
        3. 客观总结研究现状
        
        论文分析：
        {json.dumps(analyses, ensure_ascii=False)}
        """
        
        response = await self.llm.ainvoke(prompt)
        return response.content
```

### Week 29-32: Agent工具集成

```python
# agents/tools.py
from langchain.tools import Tool

def create_agent_tools():
    return [
        Tool(
            name="search_papers",
            func=search_papers,
            description="搜索本地和外部论文"
        ),
        Tool(
            name="analyze_paper",
            func=analyze_paper,
            description="分析单篇论文"
        ),
        Tool(
            name="extract_keywords",
            func=extract_keywords,
            description="提取关键词"
        ),
        Tool(
            name="generate_summary",
            func=generate_summary,
            description="生成摘要"
        )
    ]
```

---

## Phase 6-7: 评估与优化 (M9-M10)

### Week 33-36: RAG评估

```python
# evaluation/rag_eval.py

class RAGEvaluator:
    """RAG系统评估器"""
    
    def evaluate(self, test_set: List[dict]) -> dict:
        metrics = {
            'retrieval_recall': [],
            'answer_correctness': [],
            'citation_accuracy': [],
            'latency': []
        }
        
        for item in test_set:
            start = time.time()
            result = await rag_engine.answer(item['question'])
            latency = time.time() - start
            
            # 评估指标
            metrics['retrieval_recall'].append(
                self._eval_retrieval(result['references'], item['relevant_docs'])
            )
            metrics['answer_correctness'].append(
                self._eval_answer(result['answer'], item['ground_truth'])
            )
            metrics['latency'].append(latency)
        
        return {
            'recall': np.mean(metrics['retrieval_recall']),
            'correctness': np.mean(metrics['answer_correctness']),
            'avg_latency': np.mean(metrics['latency'])
        }
```

### Week 37-40: 推理优化

```python
# optimization/quantization.py

def quantize_models():
    """模型量化优化"""
    
    # INT8量化 LayoutLMv3
    model = LayoutLMv3ForTokenClassification.from_pretrained("models/layoutlmv3-paper")
    quantized_model = torch.quantization.quantize_dynamic(
        model, {torch.nn.Linear}, dtype=torch.qint8
    )
    torch.save(quantized_model.state_dict(), "models/layoutlmv3-paper-int8.pt")
    
    print("✅ 模型量化完成")
```

---

## 交付物清单

| 阶段 | 交付物 |
|-----|-------|
| M2 | GPU环境、数据规划 |
| M4 | RAG引擎原型 |
| M6 | 微调模型 (LayoutLMv3, BERT) |
| M8 | Multi-Agent系统 |
| M10 | 评估报告、优化模型 |

---

## 预期训练时间 (RTX 4090)

| 模型 | 数据量 | 训练时间 |
|-----|-------|---------|
| LayoutLMv3 | 3,000篇 | ~8小时 |
| BERT NER | 10,000篇 | ~2小时 |
| BGE-M3 (可选) | 5,000对 | ~3小时 |

---

*AI工程师开发计划 v2.0*
