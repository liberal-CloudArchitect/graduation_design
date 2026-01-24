// 认证状态管理
import { create } from 'zustand';
import { authApi } from '../services/auth';
import type { LoginData, RegisterData } from '../services/auth';
import type { User } from '../types/models';

interface AuthState {
    token: string | null;
    user: User | null;
    isLoading: boolean;

    // Actions
    login: (data: LoginData) => Promise<void>;
    register: (data: RegisterData) => Promise<void>;
    logout: () => void;
    setUser: (user: User) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
    token: localStorage.getItem('token'),
    user: null,
    isLoading: false,

    login: async (data: LoginData) => {
        set({ isLoading: true });
        try {
            const response = await authApi.login(data);
            const { access_token } = response.data;
            localStorage.setItem('token', access_token);
            set({ token: access_token, isLoading: false });
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
        set({ token: null, user: null });
    },

    setUser: (user: User) => {
        set({ user });
    },
}));
