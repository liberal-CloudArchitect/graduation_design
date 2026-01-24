# 前后端开发规范

> 更新日期: 2026-01-20

---

## 一、接口规范

### 基础URL

| 环境 | 地址 |
|------|------|
| 开发 | `http://localhost:8000/api/v1` |
| 生产 | `https://api.xxx.com/api/v1` |

### 请求头

```
Content-Type: application/json
Authorization: Bearer <token>
```

### 分页格式

**请求**
```
GET /xxx?page=1&page_size=20
```

**响应**
```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

---

## 二、时间格式

统一使用 **ISO 8601** 格式

```
2026-01-20T06:20:39.503259Z
```

### 前端解析

```typescript
import dayjs from 'dayjs';

const formatDate = (iso: string) => dayjs(iso).format('YYYY-MM-DD HH:mm');
```

---

## 三、命名规范

| 场景 | 规范 | 示例 |
|------|------|------|
| API路径 | 小写+连字符 | `/paper-status` |
| 请求体字段 | snake_case | `project_id` |
| TS类型 | PascalCase | `PaperResponse` |
| TS变量 | camelCase | `projectId` |

---

## 四、文件上传

### 请求格式

```
POST /papers/upload?project_id=1
Content-Type: multipart/form-data

file: <二进制文件>
```

### 限制

| 项目 | 限制 |
|------|------|
| 文件类型 | .pdf |
| 文件大小 | ≤50MB |

---

## 五、流式响应

### SSE格式

```
data: {"type": "chunk", "data": "内容"}

data: {"type": "done", "data": {...}}
```

### EventSource使用

```typescript
const es = new EventSource(url);
es.onmessage = (e) => {
  const data = JSON.parse(e.data);
  // 处理数据
};
```

---

## 六、CORS配置

后端已配置:
```python
allow_origins=["*"]
allow_methods=["*"]
allow_headers=["*"]
```

---

## 七、API文档

| 地址 | 说明 |
|------|------|
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/openapi.json` | OpenAPI JSON |

---

## 八、开发工具

### 推荐

| 工具 | 用途 |
|------|------|
| Swagger UI | 接口测试 |
| Postman | API调试 |
| React DevTools | 前端调试 |
