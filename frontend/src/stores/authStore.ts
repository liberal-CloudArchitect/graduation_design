// 认证状态管理
import { create } from 'zustand';
import { authApi } from '../services/auth';
import { authAxios, tokenUtils } from '../services/axios';
import type { LoginData, RegisterData } from '../services/auth';
import type { User } from '../types/models';

interface AuthState {
    token: string | null;
    user: User | null;
    isLoading: boolean;
    isAuthChecked: boolean;

    // Actions
    login: (data: LoginData) => Promise<void>;
    register: (data: RegisterData) => Promise<void>;
    logout: () => void;
    setUser: (user: User) => void;
    checkAuth: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
    token: tokenUtils.getAccessToken(),
    user: null,
    isLoading: false,
    isAuthChecked: false,

    login: async (data: LoginData) => {
        set({ isLoading: true });
        try {
            const response = await authApi.login(data);
            const { access_token, refresh_token } = response.data;
            tokenUtils.setTokens(access_token, refresh_token);
            authAxios.defaults.headers.common.Authorization = `Bearer ${access_token}`;
            set({ token: access_token, isLoading: false });
            // Fetch user info after login
            const userRes = await authApi.getMe();
            set({ user: userRes.data });
        } catch (error) {
            set({ isLoading: false });
            throw error;
        }
    },

    register: async (data: RegisterData) => {
        set({ isLoading: true });
        try {
            await authApi.register(data);
            set({ isLoading: false });
        } catch (error) {
            set({ isLoading: false });
            throw error;
        }
    },

    logout: () => {
        tokenUtils.clearTokens();
        delete authAxios.defaults.headers.common.Authorization;
        set({ token: null, user: null, isAuthChecked: false });
    },

    setUser: (user: User) => {
        set({ user });
    },

    checkAuth: async () => {
        const { token, user } = get();
        if (!token) {
            set({ isAuthChecked: true });
            return;
        }
        if (user) {
            set({ isAuthChecked: true });
            return;
        }
        try {
            const response = await authApi.getMe();
            set({ user: response.data, isAuthChecked: true });
        } catch {
            // Token is invalid or expired — axios interceptor 会尝试自动刷新
            // 如果刷新也失败了，interceptor 会清理 token 并跳转登录
            tokenUtils.clearTokens();
            set({ token: null, user: null, isAuthChecked: true });
        }
    },
}));
