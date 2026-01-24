// 认证API服务
// 基于 docs/api/01_auth.md

import { publicAxios, authAxios } from './axios';
import type { User, TokenResponse } from '../types/models';

export interface RegisterData {
    email: string;
    username: string;
    password: string;
}

export interface LoginData {
    email: string;
    password: string;
}

export const authApi = {
    /**
     * 用户注册
     */
    register: (data: RegisterData) =>
        publicAxios.post<User>('/auth/register', data),

    /**
     * 用户登录
     */
    login: (data: LoginData) =>
        publicAxios.post<TokenResponse>('/auth/login', data),

    /**
     * 获取当前用户信息
     */
    getMe: () =>
        authAxios.get<User>('/auth/me'),
};
