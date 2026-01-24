// Axios配置
// 基于 docs/api/06_authentication.md

import axios from 'axios';
import { message } from 'antd';

const API_BASE_URL = 'http://localhost:8000/api/v1';

// 创建axios实例
export const authAxios = axios.create({
    baseURL: API_BASE_URL,
    timeout: 30000,
    headers: {
        'Content-Type': 'application/json',
    },
});

// 请求拦截器 - 自动附加Token
authAxios.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem('token');
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// 响应拦截器 - 统一错误处理
authAxios.interceptors.response.use(
    (response) => response,
    (error) => {
        const { status, data } = error.response || {};

        switch (status) {
            case 401:
                message.error('登录已过期，请重新登录');
                localStorage.removeItem('token');
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

// 公开API (无需Token)
export const publicAxios = axios.create({
    baseURL: API_BASE_URL,
    timeout: 30000,
    headers: {
        'Content-Type': 'application/json',
    },
});

export { API_BASE_URL };
