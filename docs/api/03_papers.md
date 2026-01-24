# API接口文档 - 文献管理模块

> 模块路径: `/api/v1/papers`  
> 更新日期: 2026-01-20  
> 认证: ✅ 需要Bearer Token

---

## 1. 获取文献列表

**GET** `/api/v1/papers`

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| project_id | int | ❌ | 按项目筛选 |
| status_filter | string | ❌ | 按状态筛选 |
| search | string | ❌ | 按标题搜索 |
| page | int | ❌ | 页码(默认1) |
| page_size | int | ❌ | 每页数量(默认20) |

### 状态枚举

| 值 | 说明 |
|----|------|
| pending | 待处理 |
| processing | 处理中 |
| completed | 已完成 |
| failed | 处理失败 |

### 响应

```json
{
  "items": [
    {
      "id": 1,
      "title": "论文标题.pdf",
      "authors": "张三, 李四",
      "abstract": "摘要内容...",
      "file_path": "/uploads/1/uuid.pdf",
      "status": "completed",
      "page_count": 15,
      "project_id": 1,
      "created_at": "2026-01-20T06:20:39Z",
      "updated_at": "2026-01-20T06:25:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

---

## 2. 上传文献

**POST** `/api/v1/papers/upload`

### 请求

**Content-Type**: `multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| project_id | int | ✅ | 目标项目ID |
| file | File | ✅ | PDF文件(≤50MB) |

### 响应

**200 OK**

```json
{
  "id": 1,
  "filename": "论文标题.pdf",
  "status": "pending",
  "message": "文件已上传，正在后台处理"
}
```

### 错误码

| 状态码 | 说明 |
|--------|------|
| 400 | 只支持PDF文件 / 文件大小超限 |
| 404 | 项目不存在 |

---

## 3. 获取文献详情

**GET** `/api/v1/papers/{paper_id}`

### 响应

同列表中单个文献格式

---

## 4. 获取处理状态

**GET** `/api/v1/papers/{paper_id}/status`

### 响应

```json
{
  "id": 1,
  "status": "processing",
  "title": "论文标题.pdf",
  "updated_at": "2026-01-20T06:22:00Z"
}
```

> 💡 **前端轮询**: 建议每3秒调用一次，直到status为`completed`或`failed`

---

## 5. 删除文献

**DELETE** `/api/v1/papers/{paper_id}`

### 响应

**204 No Content**

---

## 前端集成示例

```typescript
// services/papers.ts
import { authAxios } from './axios';

export interface Paper {
  id: number;
  title?: string;
  authors?: string;
  abstract?: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  page_count: number;
  project_id: number;
  created_at: string;
  updated_at: string;
}

export const papersApi = {
  list: (params: { project_id?: number; status_filter?: string; search?: string }) =>
    authAxios.get('/papers', { params }),

  upload: (projectId: number, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return authAxios.post('/papers/upload', formData, {
      params: { project_id: projectId },
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  get: (id: number) =>
    authAxios.get<Paper>(`/papers/${id}`),

  getStatus: (id: number) =>
    authAxios.get(`/papers/${id}/status`),

  delete: (id: number) =>
    authAxios.delete(`/papers/${id}`),
};

// 轮询状态示例
export const pollPaperStatus = async (paperId: number, onUpdate: (status: string) => void) => {
  const poll = async () => {
    const { data } = await papersApi.getStatus(paperId);
    onUpdate(data.status);
    if (data.status !== 'completed' && data.status !== 'failed') {
      setTimeout(poll, 3000);
    }
  };
  poll();
};
```
