// 主布局组件
import React, { useState } from 'react';
import { Layout, Menu, Avatar, Dropdown, Typography } from 'antd';
import {
    HomeOutlined,
    FolderOutlined,
    MessageOutlined,
    LogoutOutlined,
    UserOutlined,
    MenuFoldOutlined,
    MenuUnfoldOutlined,
    GlobalOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';
import './index.css';

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

const MainLayout: React.FC = () => {
    const navigate = useNavigate();
    const location = useLocation();
    const { user, logout } = useAuthStore();
    const [collapsed, setCollapsed] = useState(false);

    // Determine selected key from location
    const getSelectedKey = () => {
        const { pathname } = location;
        if (pathname === '/') return '/';
        if (pathname.startsWith('/project')) return '/projects';
        if (pathname.startsWith('/chat')) return '/chat';
        if (pathname.startsWith('/search')) return '/search';
        return pathname;
    };

    const menuItems = [
        {
            key: '/',
            icon: <HomeOutlined />,
            label: '首页',
        },
        {
            key: '/projects',
            icon: <FolderOutlined />,
            label: '我的项目',
        },
        {
            key: '/chat',
            icon: <MessageOutlined />,
            label: '智能对话',
        },
        {
            key: '/search',
            icon: <GlobalOutlined />,
            label: '文献搜索',
        },
    ];

    const handleMenuClick = ({ key }: { key: string }) => {
        navigate(key);
    };

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    const userMenuItems = [
        {
            key: 'profile',
            icon: <UserOutlined />,
            label: '个人资料',
        },
        {
            key: 'logout',
            icon: <LogoutOutlined />,
            label: '退出登录',
            onClick: handleLogout,
        },
    ];

    return (
        <Layout className="main-layout">
            <Sider
                trigger={null}
                collapsible
                collapsed={collapsed}
                className="main-sider"
            >
                <div className="logo">
                    <Text strong style={{ color: '#fff', fontSize: collapsed ? 14 : 18 }}>
                        {collapsed ? 'RAG' : '文献分析平台'}
                    </Text>
                </div>
                <Menu
                    theme="dark"
                    mode="inline"
                    selectedKeys={[getSelectedKey()]}
                    items={menuItems}
                    onClick={handleMenuClick}
                />
            </Sider>
            <Layout>
                <Header className="main-header">
                    <div className="header-left">
                        {React.createElement(
                            collapsed ? MenuUnfoldOutlined : MenuFoldOutlined,
                            {
                                className: 'trigger',
                                onClick: () => setCollapsed(!collapsed),
                            }
                        )}
                    </div>
                    <div className="header-right">
                        <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
                            <div className="user-info">
                                <Avatar icon={<UserOutlined />} />
                                <Text className="username">{user?.username || '用户'}</Text>
                            </div>
                        </Dropdown>
                    </div>
                </Header>
                <Content className="main-content">
                    <Outlet />
                </Content>
            </Layout>
        </Layout>
    );
};

export default MainLayout;
