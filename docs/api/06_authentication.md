# 认证规范文档

> 更新日期: 2026-01-20

---

## 认证方式

采用 **JWT Bearer Token** 认证

---

## Token获取

### 登录接口

```
POST /api/v1/auth/login
Content-Type: application/json

{"email": "user@example.com", "password": "xxx"}
```

### 响应

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

---

## Token使用

### 请求头格式

```
Authorization: Bearer <access_token>
```

### 示例

```bash
curl -X GET http://localhost:8000/api/v1/projects \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1..."
```

---

## Token结构

### Payload

```json
{
  "sub": "1",        // 用户ID
  "exp": 1706123456  // 过期时间戳
}
```

### 配置

| 项目 | 值 |
|------|-----|
| 算法 | HS256 |
| 有效期 | 24小时 |

---

## 前端集成

### Axios拦截器

```typescript
// services/axios.ts
import axios from 'axios';

const authAxios = axios.create({
  baseURL: 'http://localhost:8000/api/v1',
});

// 请求拦截
authAxios.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 响应拦截
authAxios.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export { authAxios };
```

### 登录流程

```typescript
// stores/authStore.ts
import { create } from 'zustand';

interface AuthState {
  token: string | null;
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem('token'),
  user: null,

  login: async (email, password) => {
    const { data } = await axios.post('/api/v1/auth/login', { email, password });
    localStorage.setItem('token', data.access_token);
    set({ token: data.access_token });
  },

  logout: () => {
    localStorage.removeItem('token');
    set({ token: null, user: null });
  },
}));
```

---

## 错误处理

| 状态码 | 说明 | 处理方式 |
|--------|------|----------|
| 401 | Token无效/过期 | 跳转登录页 |
| 403 | 无权限 | 显示提示 |

---

## 路由保护

```tsx
// components/ProtectedRoute.tsx
import { Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';

export const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const token = useAuthStore((state) => state.token);

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
};
```
