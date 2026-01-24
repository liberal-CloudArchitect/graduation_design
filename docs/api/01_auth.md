# API接口文档 - 用户认证模块

> 模块路径: `/api/v1/auth`  
> 更新日期: 2026-01-20

---

## 1. 用户注册

**POST** `/api/v1/auth/register`

### 请求

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| email | string | ✅ | 邮箱地址 |
| username | string | ✅ | 用户名 |
| password | string | ✅ | 密码 |

```json
{
  "email": "user@example.com",
  "username": "张三",
  "password": "password123"
}
```

### 响应

**201 Created**

```json
{
  "id": 1,
  "email": "user@example.com",
  "username": "张三"
}
```

### 错误码

| 状态码 | 说明 |
|--------|------|
| 400 | 邮箱已被注册 / 用户名已被使用 |

---

## 2. 用户登录

**POST** `/api/v1/auth/login`

### 请求

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| email | string | ✅ | 邮箱地址 |
| password | string | ✅ | 密码 |

```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

### 响应

**200 OK**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### 错误码

| 状态码 | 说明 |
|--------|------|
| 401 | 邮箱或密码错误 |
| 400 | 用户已被禁用 |

---

## 3. 获取当前用户

**GET** `/api/v1/auth/me`

### 请求头

```
Authorization: Bearer <access_token>
```

### 响应

**200 OK**

```json
{
  "id": 1,
  "email": "user@example.com",
  "username": "张三"
}
```

---

## 前端集成示例

### Axios封装

```typescript
// services/auth.ts
import axios from 'axios';

const API_BASE = 'http://localhost:8000/api/v1';

export const authApi = {
  register: (data: { email: string; username: string; password: string }) =>
    axios.post(`${API_BASE}/auth/register`, data),

  login: (email: string, password: string) =>
    axios.post(`${API_BASE}/auth/login`, { email, password }),

  getMe: () =>
    axios.get(`${API_BASE}/auth/me`),
};
```

### Token存储

```typescript
// 登录后保存Token
const handleLogin = async (email: string, password: string) => {
  const { data } = await authApi.login(email, password);
  localStorage.setItem('token', data.access_token);
};

// 请求拦截器
axios.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
```
