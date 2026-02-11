// Axios配置
// 基于 docs/api/06_authentication.md

import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { message } from 'antd';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

// ============ Token 工具函数 ============

export const tokenUtils = {
    getAccessToken: () => localStorage.getItem('token'),
    getRefreshToken: () => localStorage.getItem('refresh_token'),

    setTokens: (accessToken: string, refreshToken?: string) => {
        if (
            typeof accessToken !== 'string' ||
            accessToken.trim() === '' ||
            accessToken === 'undefined' ||
            accessToken === 'null'
        ) {
            localStorage.removeItem('token');
            localStorage.removeItem('refresh_token');
            return;
        }
        localStorage.setItem('token', accessToken);
        if (
            typeof refreshToken === 'string' &&
            refreshToken.trim() !== '' &&
            refreshToken !== 'undefined' &&
            refreshToken !== 'null'
        ) {
            localStorage.setItem('refresh_token', refreshToken);
        }
    },

    clearTokens: () => {
        localStorage.removeItem('token');
        localStorage.removeItem('refresh_token');
    },
};

function setAuthorizationHeader(headers: any, token: string) {
    const value = `Bearer ${token}`;
    if (!headers) return { Authorization: value };
    if (typeof headers.set === 'function') {
        headers.set('Authorization', value);
        return headers;
    }
    headers.Authorization = value;
    return headers;
}

// ============ 刷新 Token 锁（防止并发刷新） ============

let isRefreshing = false;
let refreshSubscribers: Array<(token: string) => void> = [];

/** 将等待刷新的请求加入队列 */
function subscribeTokenRefresh(cb: (token: string) => void) {
    refreshSubscribers.push(cb);
}

/** 刷新完成后，逐一放行所有排队请求 */
function onTokenRefreshed(newToken: string) {
    refreshSubscribers.forEach((cb) => cb(newToken));
    refreshSubscribers = [];
}

/** 尝试使用 refresh_token 获取新 access_token */
async function tryRefreshToken(): Promise<string | null> {
    const refreshToken = tokenUtils.getRefreshToken();
    if (
        !refreshToken ||
        refreshToken.trim() === '' ||
        refreshToken === 'undefined' ||
        refreshToken === 'null'
    ) {
        return null;
    }

    try {
        const { data } = await publicAxios.post('/auth/refresh', {
            refresh_token: refreshToken,
        });
        const newAccessToken: string = data.access_token;
        tokenUtils.setTokens(newAccessToken, data.refresh_token || refreshToken);
        return newAccessToken;
    } catch {
        // refresh_token 也失效了，需要重新登录
        return null;
    }
}

// ============ 创建 axios 实例 ============

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
        const token = tokenUtils.getAccessToken();
        if (token) {
            config.headers = setAuthorizationHeader(config.headers, token);
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// 响应拦截器 - 统一错误处理 + 自动刷新Token
authAxios.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
        const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
        const statusCode = error.response?.status;
        const data = error.response?.data as any;

        // —— 401: 尝试自动刷新 Token ——
        if (statusCode === 401 && originalRequest && !originalRequest._retry) {
            // 如果已经有人在刷新，排队等待
            if (isRefreshing) {
                return new Promise((resolve) => {
                    subscribeTokenRefresh((newToken: string) => {
                        originalRequest.headers = setAuthorizationHeader(originalRequest.headers, newToken);
                        resolve(authAxios(originalRequest));
                    });
                });
            }

            originalRequest._retry = true;
            isRefreshing = true;

            try {
                const newToken = await tryRefreshToken();
                if (newToken) {
                    // 刷新成功：用新 token 重试原始请求 + 放行队列
                    originalRequest.headers = setAuthorizationHeader(originalRequest.headers, newToken);
                    onTokenRefreshed(newToken);
                    return authAxios(originalRequest);
                }

                // refresh 也失败 → 真正过期，跳转登录
                tokenUtils.clearTokens();
                message.error('登录已过期，请重新登录');
                window.location.href = '/login';
            } finally {
                isRefreshing = false;
            }

            return Promise.reject(error);
        }

        // —— 其它状态码保持原有处理逻辑 ——
        switch (statusCode) {
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
                if (statusCode !== 401) {
                    message.error(data?.detail || '请求失败');
                }
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
