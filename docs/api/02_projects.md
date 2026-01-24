# API接口文档 - 项目管理模块

> 模块路径: `/api/v1/projects`  
> 更新日期: 2026-01-20  
> 认证: ✅ 需要Bearer Token

---

## 1. 获取项目列表

**GET** `/api/v1/projects`

### 请求参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|-------|------|
| page | int | ❌ | 1 | 页码 |
| page_size | int | ❌ | 20 | 每页数量(1-100) |

### 响应

```json
{
  "items": [
    {
      "id": 1,
      "name": "毕业设计项目",
      "description": "文献综述研究",
      "paper_count": 5,
      "created_at": "2026-01-20T06:20:39.503259Z",
      "updated_at": "2026-01-20T06:20:39.503259Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

---

## 2. 创建项目

**POST** `/api/v1/projects`

### 请求

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | ✅ | 项目名称 |
| description | string | ❌ | 项目描述 |

```json
{
  "name": "毕业设计项目",
  "description": "文献综述研究"
}
```

### 响应

**201 Created**

```json
{
  "id": 1,
  "name": "毕业设计项目",
  "description": "文献综述研究",
  "paper_count": 0,
  "created_at": "2026-01-20T06:20:39Z",
  "updated_at": "2026-01-20T06:20:39Z"
}
```

---

## 3. 获取项目详情

**GET** `/api/v1/projects/{project_id}`

### 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| project_id | int | 项目ID |

### 响应

同创建响应格式

### 错误码

| 状态码 | 说明 |
|--------|------|
| 404 | 项目不存在 |

---

## 4. 更新项目

**PUT** `/api/v1/projects/{project_id}`

### 请求

```json
{
  "name": "新名称",
  "description": "新描述"
}
```

### 响应

同项目详情格式

---

## 5. 删除项目

**DELETE** `/api/v1/projects/{project_id}`

### 响应

**204 No Content**

---

## 前端集成示例

```typescript
// services/projects.ts
import { authAxios } from './axios';

export interface Project {
  id: number;
  name: string;
  description?: string;
  paper_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectList {
  items: Project[];
  total: number;
  page: number;
  page_size: number;
}

export const projectsApi = {
  list: (page = 1, pageSize = 20) =>
    authAxios.get<ProjectList>('/projects', { params: { page, page_size: pageSize } }),

  create: (data: { name: string; description?: string }) =>
    authAxios.post<Project>('/projects', data),

  get: (id: number) =>
    authAxios.get<Project>(`/projects/${id}`),

  update: (id: number, data: Partial<{ name: string; description: string }>) =>
    authAxios.put<Project>(`/projects/${id}`, data),

  delete: (id: number) =>
    authAxios.delete(`/projects/${id}`),
};
```
