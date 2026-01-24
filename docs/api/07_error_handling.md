# 错误处理规范

> 更新日期: 2026-01-20

---

## 统一错误格式

```json
{
  "detail": "错误描述文字"
}
```

---

## HTTP状态码

| 状态码 | 场景 | 说明 |
|--------|------|------|
| 200 | OK | 请求成功 |
| 201 | Created | 资源创建成功 |
| 204 | No Content | 删除成功 |
| 400 | Bad Request | 请求参数错误 |
| 401 | Unauthorized | 未认证/Token无效 |
| 403 | Forbidden | 无权限 |
| 404 | Not Found | 资源不存在 |
| 422 | Validation Error | 数据校验失败 |
| 500 | Server Error | 服务器内部错误 |

---

## 常见错误

### 认证错误

```json
// 401
{"detail": "Could not validate credentials"}
{"detail": "邮箱或密码错误"}
```

### 资源不存在

```json
// 404
{"detail": "项目不存在"}
{"detail": "文献不存在"}
{"detail": "对话不存在"}
```

### 业务错误

```json
// 400
{"detail": "邮箱已被注册"}
{"detail": "用户名已被使用"}
{"detail": "只支持PDF文件"}
{"detail": "文件大小不能超过50MB"}
```

### 验证错误

```json
// 422
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "value is not a valid email address",
      "type": "value_error.email"
    }
  ]
}
```

---

## 前端错误处理

### 全局拦截

```typescript
// services/axios.ts
authAxios.interceptors.response.use(
  (response) => response,
  (error) => {
    const { status, data } = error.response || {};
    
    switch (status) {
      case 401:
        message.error('登录已过期，请重新登录');
        window.location.href = '/login';
        break;
      case 403:
        message.error('没有权限执行此操作');
        break;
      case 404:
        message.error(data?.detail || '资源不存在');
        break;
      case 422:
        message.error('请检查输入数据');
        break;
      case 500:
        message.error('服务器错误，请稍后重试');
        break;
      default:
        message.error(data?.detail || '请求失败');
    }
    
    return Promise.reject(error);
  }
);
```

### 表单错误

```typescript
const handleSubmit = async (values: FormValues) => {
  try {
    await authApi.register(values);
    message.success('注册成功');
  } catch (error: any) {
    if (error.response?.status === 400) {
      form.setFields([
        { name: 'email', errors: [error.response.data.detail] }
      ]);
    }
  }
};
```
