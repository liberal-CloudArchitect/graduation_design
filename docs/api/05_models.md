# 数据模型文档

> 更新日期: 2026-01-20

---

## 用户 (User)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 用户ID |
| email | string | 邮箱 |
| username | string | 用户名 |
| is_active | bool | 是否激活 |
| created_at | datetime | 创建时间 |

---

## 项目 (Project)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 项目ID |
| name | string | 项目名称 |
| description | string? | 描述 |
| paper_count | int | 文献数量 |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

---

## 文献 (Paper)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 文献ID |
| title | string? | 标题 |
| authors | string? | 作者(逗号分隔) |
| abstract | string? | 摘要 |
| status | string | 状态 |
| page_count | int | 页数 |
| project_id | int | 所属项目ID |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

### 状态枚举

```typescript
type PaperStatus = 'pending' | 'processing' | 'completed' | 'failed';
```

---

## 对话 (Conversation)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 对话ID |
| project_id | int? | 关联项目 |
| messages | Message[] | 消息列表 |
| created_at | datetime | 创建时间 |

### 消息结构

```typescript
interface Message {
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}
```

---

## 引用 (Reference)

| 字段 | 类型 | 说明 |
|------|------|------|
| paper_id | int | 文献ID |
| paper_title | string? | 文献标题 |
| chunk_index | int | 分块索引 |
| page_number | int? | 页码 |
| text | string | 原文片段 |
| score | float | 相关性得分 |

---

## TypeScript类型定义

```typescript
// types/models.ts

export interface User {
  id: number;
  email: string;
  username: string;
}

export interface Project {
  id: number;
  name: string;
  description?: string;
  paper_count: number;
  created_at: string;
  updated_at: string;
}

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

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface Conversation {
  id: number;
  project_id?: number;
  messages: Message[];
  created_at: string;
}

export interface Reference {
  paper_id: number;
  paper_title?: string;
  chunk_index: number;
  page_number?: number;
  text: string;
  score: number;
}

export interface AnswerResponse {
  answer: string;
  references: Reference[];
  conversation_id?: number;
  method: string;
}
```
