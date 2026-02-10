// 路由保护组件
import React, { useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Spin } from 'antd';
import { useAuthStore } from '../stores/authStore';

interface ProtectedRouteProps {
    children: React.ReactNode;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
    const token = useAuthStore((state) => state.token);
    const isAuthChecked = useAuthStore((state) => state.isAuthChecked);
    const checkAuth = useAuthStore((state) => state.checkAuth);
    const location = useLocation();

    useEffect(() => {
        checkAuth();
    }, [checkAuth]);

    // Show loading while checking auth
    if (!isAuthChecked) {
        return (
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
                <Spin size="large" />
            </div>
        );
    }

    if (!token) {
        return <Navigate to="/login" state={{ from: location }} replace />;
    }

    return <>{children}</>;
};

export default ProtectedRoute;
