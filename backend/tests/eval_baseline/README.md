# 基线评测框架 (eval_baseline)

阶段 0 交付物 — 评测数据集、采集脚本、对照工具。

## 目录结构

```
eval_baseline/
├── README.md                        # 本文件
├── __init__.py
├── conftest.py                      # pytest 配置
├── eval_metrics.py                  # 指标计算（Recall@K, nDCG@K, 引用一致性等）
├── eval_runner.py                   # 评测主入口（连接后端 API 运行评测）
├── compare.py                       # baseline vs candidate 对照脚本
├── high_value_queries.json          # 高价值评测样本（22 条）
├── parse_bench/
│   ├── parse_bench_manifest.json    # PDF 解析评测集清单（21 篇）
│   └── annotations/                 # 逐篇标注
├── retrieval_bench/
│   └── retrieval_bench.json         # 检索评测集（50 条）
├── answer_bench/
│   └── answer_bench.json            # 回答评测集（30 条）
└── reports/                         # 评测报告输出目录
```

## 快速使用

### 1. 运行全量基线评测（含 LatencyBench 3 轮）

```bash
# 确保后端服务已启动
cd backend
python -m tests.eval_baseline.eval_runner \
    --base-url http://127.0.0.1:8000 \
    --output tests/eval_baseline/reports/ \
    --rounds 3
```

### 2. 运行单个评测集

```bash
python -m tests.eval_baseline.eval_runner --bench retrieval
python -m tests.eval_baseline.eval_runner --bench answer
python -m tests.eval_baseline.eval_runner --bench parse
python -m tests.eval_baseline.eval_runner --bench latency --rounds 3
```

### 3. 对比两次评测报告

```bash
python -m tests.eval_baseline.compare \
    --baseline reports/baseline_20260303_120000.json \
    --candidate reports/baseline_20260310_120000.json
```

CI 模式（返回非零退出码表示有回归）：

```bash
python -m tests.eval_baseline.compare --baseline ... --candidate ... --json
```

## 评测数据集

| 数据集 | 文件 | 规模 | 用途 |
|--------|------|------|------|
| ParseBench | `parse_bench/parse_bench_manifest.json` | 21 篇（5 类覆盖） | PDF 解析质量 |
| RetrievalBench | `retrieval_bench/retrieval_bench.json` | 50 条 | 检索质量 |
| AnswerBench | `answer_bench/answer_bench.json` | 30 条 | 回答质量 |
| LatencyBench | 复用 retrieval+answer 查询集 | 同上 × N 轮 | 延迟性能基准 |
| HighValue | `high_value_queries.json` | 22 条 | 核心场景评测 |

## 指标说明

| 指标 | 定义 | 回归门槛 |
|------|------|---------|
| Recall@K | Top-K 结果中包含相关文档的比例 | >= 基线 |
| nDCG@K | 考虑排序位置的检索质量 | >= 基线 |
| 引用一致性 | 回答中引用编号在有效范围内的比例 | >= 基线 |
| 答案完整度 | 标准答案要点被覆盖的比例 | >= 基线 |
| 解析质量 | 标题/摘要/章节/表格/公式等综合评分 | >= 基线 |
| P95 延迟 | 95% 分位请求延迟（连续 3 轮取均值） | <= 基线 × 1.2 |

## 可重复性

LatencyBench 默认执行 3 轮 (`--rounds 3`)，所有延迟指标取 3 轮汇总后计算，
保证同集重复偏差 < 2%（P95 级别）。报告中记录 `per_round` 明细可供校验。
