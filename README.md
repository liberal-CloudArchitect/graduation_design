# 文献分析大数据平台 (Paper BigData Platform)

## 📚 项目简介

文献分析大数据平台是一个基于**RAG架构**的智能学术文献分析工具，通过大语言模型(LLM)、自然语言处理(NLP)和数据挖掘技术，帮助研究人员高效地分析文献、撰写论文、识别研究热点、把握学科发展趋势。

### 核心功能

- 📤 **文献上传**: 支持PDF文献批量上传,自动解析和元数据提取
- 🔍 **关键词提取**: 基于TF-IDF、TextRank和BERT的智能关键词提取
- 💬 **RAG智能问答**: 基于文献的自然语言问答，带引用溯源
- 📊 **数据可视化**: 词云图、趋势图、知识图谱、网络关系图
- 🔗 **关系分析**: 文献引用关系、相似文献推荐、主题聚类
- 📈 **趋势预测**: 研究热点识别、突现词检测、发展趋势预测
- 🤝 **团队协作**: 项目管理、多人协作、数据共享

### 扩展功能（V2.0）

- 🖊️ **AI写作助手**: 论文大纲生成、段落润色、学术写作辅助
- 📝 **自动文献综述**: 一键生成结构化文献综述报告
- 🔬 **研究空白检测**: 识别领域研究空白和创新机会
- 🖼️ **多模态分析**: 分析论文图表、公式、表格
- 📚 **引文管理集成**: 对接Zotero、EndNote等工具
- 🌐 **浏览器插件**: 一键收藏和分析网页论文

### 技术亮点

- 🤖 **RAG架构**: 检索增强生成，混合检索(BM25+向量+稀疏)
- 🧠 **大模型驱动**: 集成ChatGLM、Claude、GPT等多模型
- 🌐 **外部集成**: Semantic Scholar、OpenAlex 1.25亿+学术文献
- 🚀 **高性能**: 异步任务处理,支持1000+并发
- 🎨 **现代化UI**: React + Ant Design,响应式设计
- 🔒 **安全可靠**: JWT认证,数据加密,权限控制
- 📦 **容器化部署**: Docker一键启动,易于扩展

---

## 📁 项目文档

### 核心文档

| 文档名称 | 描述 | 链接 |
|---------|------|------|
| 可行性分析报告 | 技术、市场、经济、运营、法律等多维度可行性分析 | [查看](./doc/可行性分析报告.md) |
| 项目实现报告 | 系统架构、数据库设计、核心模块实现、API接口设计 | [查看](./doc/项目实现报告.md) |
| 详细开发计划 | 9个月完整开发计划,包含任务分解和里程碑 | [查看](./doc/详细开发计划.md) |
| **可行性分析(优化版)** | 含RAG架构、扩展功能、更新投资回报分析 | [查看](./improve_doc/可行性分析报告_优化版.md) |
| **详细实施计划(优化版)** | 12个月完整计划,含6大扩展功能实现 | [查看](./improve_doc/详细实施计划_优化版.md) |
| **项目分析报告** | 技术趋势分析与优化建议 | [查看](./improve_doc/analyse.md) |

### 项目概况

- **开发周期**: 12个月 (核心9个月 + 扩展3个月)
- **团队规模**: 10人核心团队
- **技术栈**: React + FastAPI + RAG + LangChain + 多数据库
- **总投资**: 377万元
- **预期回报**: 第三年ROI **603%**

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────┐
│              前端层 (Frontend)                       │
│    React + TypeScript + Ant Design + ECharts + G6  │
└─────────────────────────────────────────────────────┘
                          ↓ ↑
┌─────────────────────────────────────────────────────┐
│            API网关层 (Nginx)                         │
│      负载均衡 │ 限流 │ HTTPS │ 跨域 │ 缓存         │
└─────────────────────────────────────────────────────┘
                          ↓ ↑
┌─────────────────────────────────────────────────────┐
│           应用服务层 (Backend)                       │
│    FastAPI + SQLAlchemy + Pydantic + Celery        │
└─────────────────────────────────────────────────────┘
                          ↓ ↑
┌─────────────────────────────────────────────────────┐
│              RAG引擎层 (新增)                         │
│  LangChain + BGE-M3 + 混合检索 + Multi-Agent       │
└─────────────────────────────────────────────────────┘
                          ↓ ↑
┌─────────────────────────────────────────────────────┐
│                数据层                                │
│  PostgreSQL │ MongoDB │ Redis │ MinIO │ Milvus    │
│  Elasticsearch │ Semantic Scholar API              │
└─────────────────────────────────────────────────────┘
```

---

## 💻 技术栈

### 前端技术

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18+ | UI框架 |
| TypeScript | 5+ | 类型安全 |
| Ant Design | 5+ | UI组件库 |
| ECharts | 5+ | 数据可视化 |
| G6 | 5+ | 关系图谱 |
| Redux Toolkit | 2+ | 状态管理 |
| Axios | 1+ | HTTP客户端 |
| Vite | 5+ | 构建工具 |

### 后端技术

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.11 | 编程语言 |
| FastAPI | 0.104+ | Web框架 |
| SQLAlchemy | 2+ | ORM |
| Pydantic | 2+ | 数据验证 |
| Celery | 5+ | 异步任务 |
| jieba | 0.42+ | 中文分词 |
| transformers | 4+ | BERT模型 |
| pdfplumber | 0.10+ | PDF解析 |

### 数据库技术

| 技术 | 版本 | 用途 |
|------|------|------|
| PostgreSQL | 14+ | 关系数据库 |
| MongoDB | 6+ | 文档数据库 |
| Redis | 7+ | 缓存/消息队列 |
| Elasticsearch | 8+ | 全文检索 |
| Milvus | 2+ | 向量数据库 |
| MinIO | - | 对象存储 |

---

## 🚀 快速开始

### 前置要求

- Docker & Docker Compose
- Node.js 18+
- Python 3.11+

### 一键启动(Docker)

```bash
# 1. 克隆代码
git clone https://github.com/your-org/paper-bigdata-platform.git
cd paper-bigdata-platform

# 2. 启动所有服务
docker-compose up -d

# 3. 访问应用
# 前端: http://localhost:3000
# 后端API: http://localhost:8000
# API文档: http://localhost:8000/docs
# MinIO控制台: http://localhost:9001
```

### 本地开发

#### 后端开发

```bash
# 1. 进入后端目录
cd backend

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑.env文件,配置数据库连接等

# 5. 数据库迁移
alembic upgrade head

# 6. 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 7. 启动Celery Worker(新终端)
celery -A app.celery worker --loglevel=info
```

#### 前端开发

```bash
# 1. 进入前端目录
cd frontend

# 2. 安装依赖
npm install

# 3. 配置环境变量
cp .env.example .env
# 编辑.env文件,配置API地址

# 4. 启动开发服务器
npm run dev

# 5. 访问应用
# http://localhost:3000
```

---

## 📖 核心功能演示

### 1. 文献上传

```typescript
// 上传文件到服务器
const uploadPaper = async (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  
  const response = await axios.post('/api/v1/papers/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
  
  return response.data;
};
```

### 2. 关键词提取

```python
# services/nlp_analyzer.py
def extract_keywords(text: str, top_k: int = 20) -> List[Dict]:
    # TF-IDF提取
    tfidf_keywords = jieba.analyse.extract_tags(
        text, topK=top_k, withWeight=True
    )
    
    # TextRank提取
    textrank_keywords = jieba.analyse.textrank(
        text, topK=top_k, withWeight=True
    )
    
    # 合并结果
    return merge_keywords(tfidf_keywords, textrank_keywords)
```

### 3. 趋势分析

```python
# services/trend_analyzer.py
def analyze_trends(papers: List[Dict], time_window: str) -> Dict:
    # 按时间分组
    time_series = group_by_time(papers, time_window)
    
    # 计算趋势
    trends = calculate_trends(time_series)
    
    # 识别热点
    hot_keywords = identify_hotspots(trends)
    
    return {'trends': trends, 'hotspots': hot_keywords}
```

---

## 🧪 测试

### 后端测试

```bash
# 运行所有测试
pytest

# 运行测试并生成覆盖率报告
pytest --cov=app --cov-report=html

# 查看覆盖率报告
open htmlcov/index.html
```

### 前端测试

```bash
# 运行单元测试
npm run test

# 运行测试并生成覆盖率报告
npm run test:coverage

# E2E测试
npm run test:e2e
```

---

## 📊 API文档

启动后端服务后,访问以下地址查看自动生成的API文档:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 核心API接口

#### 认证接口

```http
POST /api/v1/auth/register   # 用户注册
POST /api/v1/auth/login      # 用户登录
POST /api/v1/auth/refresh    # 刷新token
```

#### 文献接口

```http
POST   /api/v1/papers/upload      # 上传文献
GET    /api/v1/papers             # 获取文献列表
GET    /api/v1/papers/{id}        # 获取文献详情
PUT    /api/v1/papers/{id}        # 更新文献
DELETE /api/v1/papers/{id}        # 删除文献
```

#### 分析接口

```http
POST /api/v1/analysis/keywords    # 关键词分析
POST /api/v1/analysis/trends      # 趋势分析
POST /api/v1/analysis/similarity  # 相似度分析
GET  /api/v1/papers/{id}/similar  # 相似文献推荐
```

---

## 🔒 安全措施

### 认证与授权

- **JWT Token**: 有状态的身份认证
- **刷新Token**: 支持无感刷新
- **权限控制**: 基于角色的访问控制(RBAC)

### 数据安全

- **密码加密**: bcrypt哈希算法
- **数据加密**: AES-256加密敏感数据
- **HTTPS**: 生产环境强制HTTPS
- **SQL注入防护**: 参数化查询

### API安全

- **限流**: 防止API滥用
- **CORS配置**: 跨域请求控制
- **输入验证**: Pydantic数据验证
- **XSS防护**: 输出转义
- **CSRF防护**: Token验证

---

## 📈 性能指标

### 目标性能

| 指标 | 目标值 |
|------|--------|
| 首屏加载时间 | < 2秒 |
| API响应时间(P95) | < 500ms |
| 页面切换时间 | < 300ms |
| 并发用户数 | 1000+ |
| 数据库查询时间 | < 100ms |
| PDF解析时间 | < 10秒/篇 |

### 优化措施

- **前端**: 代码分割、懒加载、虚拟滚动、CDN加速
- **后端**: 异步处理、连接池、查询优化、缓存策略
- **数据库**: 索引优化、读写分离、查询缓存
- **网络**: Gzip压缩、HTTP/2、CDN分发

---

## 🛠️ 开发规范

### 代码规范

#### Python代码规范

```python
# 遵循PEP8规范
# 使用类型提示
def calculate_tfidf(text: str, top_k: int = 20) -> List[Dict[str, float]]:
    """
    计算TF-IDF关键词
    
    Args:
        text: 输入文本
        top_k: 返回前K个关键词
        
    Returns:
        关键词列表,包含word和weight
    """
    pass
```

#### TypeScript代码规范

```typescript
// 使用ESLint + Prettier
// 严格模式TypeScript
interface Keyword {
  word: string;
  weight: number;
  frequency: number;
}

const extractKeywords = async (
  text: string,
  topK: number = 20
): Promise<Keyword[]> => {
  // 实现
};
```

### Git提交规范

```bash
# Conventional Commits规范
feat: 新功能
fix: Bug修复
docs: 文档更新
style: 代码格式调整
refactor: 重构代码
test: 测试相关
chore: 构建/工具相关

# 示例
git commit -m "feat: 添加关键词提取功能"
git commit -m "fix: 修复PDF解析中文乱码问题"
git commit -m "docs: 更新API文档"
```

---

## 🤝 贡献指南

### 如何贡献

1. Fork项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交代码 (`git commit -m 'feat: Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交Pull Request

### 代码审查流程

1. 提交PR后自动运行CI检查
2. 至少1名reviewer审查代码
3. 所有检查通过后合并

---

## 📝 开发日志

### Version 1.0.0 (2025-11-12)

#### 新增功能
- ✨ 用户注册与登录
- ✨ PDF文献上传与解析
- ✨ 关键词自动提取
- ✨ 词云图可视化
- ✨ 趋势分析功能
- ✨ 相似文献推荐

#### 技术优化
- ⚡ 异步任务处理
- ⚡ 数据库查询优化
- ⚡ 前端代码分割

#### Bug修复
- 🐛 修复中文PDF解析乱码
- 🐛 修复大文件上传超时
- 🐛 修复词云图渲染问题

---

## 📞 联系我们

- **项目主页**: https://github.com/your-org/paper-bigdata-platform
- **问题反馈**: https://github.com/your-org/paper-bigdata-platform/issues
- **邮箱**: support@paperbigdata.com
- **文档**: https://docs.paperbigdata.com

---

## 📄 许可证

本项目采用 MIT 许可证。详见 [LICENSE](./LICENSE) 文件。

---

## 🙏 致谢

感谢以下开源项目:

- [React](https://react.dev/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Ant Design](https://ant.design/)
- [ECharts](https://echarts.apache.org/)
- [jieba](https://github.com/fxsjy/jieba)
- [transformers](https://huggingface.co/docs/transformers)

---

**⭐ 如果这个项目对您有帮助,请给我们一个Star!**

---

*最后更新: 2025-11-12*  
*维护团队: Paper BigData开发团队*

