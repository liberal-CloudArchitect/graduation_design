// 仪表盘页面
import React, { useEffect, useState } from 'react';
import { Row, Col, Card, Statistic, Button, List, Empty, Typography, Spin, Space } from 'antd';
import {
    FolderAddOutlined,
    FileTextOutlined,
    MessageOutlined,
    RocketOutlined,
    PlusOutlined,
    GlobalOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { projectsApi } from '../../services/projects';
import { ragApi } from '../../services/rag';
import { useAuthStore } from '../../stores/authStore';
import type { Project } from '../../types/models';
import './index.css';

const { Title, Text } = Typography;

const Dashboard: React.FC = () => {
    const navigate = useNavigate();
    const { user } = useAuthStore();
    const [projects, setProjects] = useState<Project[]>([]);
    const [loading, setLoading] = useState(true);
    const [stats, setStats] = useState({ projectCount: 0, paperCount: 0, conversationCount: 0 });

    useEffect(() => {
        loadProjects();
        loadConversationCount();
    }, []);

    const loadProjects = async () => {
        try {
            const { data } = await projectsApi.list(1, 5);
            setProjects(data.items);
            const totalPapers = data.items.reduce((sum: number, p: Project) => sum + p.paper_count, 0);
            setStats(prev => ({ ...prev, projectCount: data.total, paperCount: totalPapers }));
        } catch (error) {
            console.error('Failed to load projects:', error);
        } finally {
            setLoading(false);
        }
    };

    const loadConversationCount = async () => {
        try {
            const { data } = await ragApi.getConversationCount();
            setStats(prev => ({ ...prev, conversationCount: data.count }));
        } catch (error) {
            console.error('Failed to load conversation count:', error);
        }
    };

    const handleCreateProject = () => {
        navigate('/projects?create=true');
    };

    return (
        <div className="dashboard">
            <div className="dashboard-header">
                <Title level={3}>
                    {user?.username ? `欢迎回来，${user.username}` : '欢迎使用文献分析平台'}
                </Title>
                <Text type="secondary">基于RAG技术，智能分析您的学术文献</Text>
            </div>

            {/* 统计卡片 */}
            <Row gutter={[24, 24]} className="stats-row">
                <Col xs={24} sm={12} lg={6}>
                    <Card className="stat-card" hoverable onClick={() => navigate('/projects')}>
                        <Statistic
                            title="我的项目"
                            value={stats.projectCount}
                            prefix={<FolderAddOutlined />}
                        />
                    </Card>
                </Col>
                <Col xs={24} sm={12} lg={6}>
                    <Card className="stat-card" hoverable onClick={() => navigate('/projects')}>
                        <Statistic
                            title="文献总数"
                            value={stats.paperCount}
                            prefix={<FileTextOutlined />}
                        />
                    </Card>
                </Col>
                <Col xs={24} sm={12} lg={6}>
                    <Card className="stat-card" hoverable onClick={() => navigate('/chat')}>
                        <Statistic
                            title="对话次数"
                            value={stats.conversationCount}
                            prefix={<MessageOutlined />}
                        />
                    </Card>
                </Col>
                <Col xs={24} sm={12} lg={6}>
                    <Card className="stat-card quick-actions">
                        <Button
                            type="primary"
                            icon={<RocketOutlined />}
                            onClick={() => navigate('/chat')}
                            block
                            size="large"
                        >
                            开始对话
                        </Button>
                    </Card>
                </Col>
            </Row>

            {/* 快捷操作 */}
            <Card title="快捷操作" className="quick-actions-card" style={{ marginBottom: 24 }}>
                <Space size="middle" wrap>
                    <Button
                        icon={<PlusOutlined />}
                        onClick={handleCreateProject}
                    >
                        创建项目
                    </Button>
                    <Button
                        icon={<MessageOutlined />}
                        onClick={() => navigate('/chat')}
                    >
                        开始问答
                    </Button>
                    <Button
                        icon={<GlobalOutlined />}
                        onClick={() => navigate('/search')}
                    >
                        搜索文献
                    </Button>
                </Space>
            </Card>

            {/* 最近项目 */}
            <Card
                title="最近项目"
                className="recent-projects"
                extra={
                    <Button type="link" onClick={() => navigate('/projects')}>
                        查看全部
                    </Button>
                }
            >
                {loading ? (
                    <div className="loading-container">
                        <Spin />
                    </div>
                ) : projects.length > 0 ? (
                    <List
                        dataSource={projects}
                        renderItem={(project) => (
                            <List.Item
                                className="project-item"
                                onClick={() => navigate(`/project/${project.id}`)}
                            >
                                <List.Item.Meta
                                    avatar={<FolderAddOutlined style={{ fontSize: 24 }} />}
                                    title={project.name}
                                    description={project.description || '无描述'}
                                />
                                <div className="project-stats">
                                    <Text type="secondary">{project.paper_count} 篇文献</Text>
                                </div>
                            </List.Item>
                        )}
                    />
                ) : (
                    <Empty description="还没有项目">
                        <Button type="primary" onClick={handleCreateProject}>
                            创建第一个项目
                        </Button>
                    </Empty>
                )}
            </Card>
        </div>
    );
};

export default Dashboard;
