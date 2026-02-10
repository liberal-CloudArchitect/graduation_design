// 认证状态管理
import { create } from 'zustand';
import { authApi } from '../services/auth';
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
    token: localStorage.getItem('token'),
    user: null,
    isLoading: false,
    isAuthChecked: false,

    login: async (data: LoginData) => {
        set({ isLoading: true });
        try {
            const response = await authApi.login(data);
            const { access_token } = response.data;
            localStorage.setItem('token', access_token);
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
        localStorage.removeItem('token');
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
            // Token is invalid or expired
            localStorage.removeItem('token');
            set({ token: null, user: null, isAuthChecked: true });
        }
    },
}));
