# 文献分析大数据平台 - 前端

> **技术栈**: React 18 + TypeScript + Vite + Ant Design  
> **Node版本**: >= 18

---

## 项目结构

```
frontend/
├── src/
│   ├── components/       # 通用组件
│   │   ├── Chat/         # RAG对话组件
│   │   ├── Upload/       # 文件上传
│   │   └── Charts/       # 可视化图表
│   ├── pages/            # 页面
│   │   ├── Home/
│   │   ├── Papers/       # 文献管理
│   │   ├── QA/           # RAG问答
│   │   └── Analysis/     # 分析仪表盘
│   ├── store/            # Redux状态
│   ├── services/         # API调用
│   ├── hooks/            # 自定义hooks
│   └── utils/            # 工具函数
├── public/
├── package.json
└── vite.config.ts
```

---

## 快速开始

### 1. 安装依赖

```bash
npm install
```

### 2. 启动开发服务器

```bash
npm run dev
```

访问 http://localhost:5173

### 3. 构建生产版本

```bash
npm run build
```

---

## 已安装依赖

- **UI组件**: antd, @ant-design/icons
- **路由**: react-router-dom
- **状态管理**: @reduxjs/toolkit, react-redux
- **HTTP请求**: axios
- **图表**: echarts, echarts-for-react
- **知识图谱**: @antv/g6

---

## 环境变量

在根目录创建 `.env.local`:

```
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

---

*前端项目 v1.0*
