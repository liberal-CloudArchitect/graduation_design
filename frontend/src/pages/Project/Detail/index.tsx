// 项目详情页 - 包含论文管理、可视化、知识图谱、趋势分析、写作辅助标签页
import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
    Tabs, Card, Button, Upload, Table, Tag, Space, Modal,
    Typography, Spin, Empty, Descriptions, message, Popconfirm
} from 'antd';
import {
    FileTextOutlined, BarChartOutlined, ShareAltOutlined,
    LineChartOutlined, EditOutlined, UploadOutlined,
    DeleteOutlined, ArrowLeftOutlined, ReloadOutlined
} from '@ant-design/icons';
import { projectsApi } from '../../../services/projects';
import { papersApi } from '../../../services/papers';
import type { Project, Paper } from '../../../types/models';
import Visualization from '../Visualization';
import KnowledgeGraph from '../KnowledgeGraph';
import TrendAnalysis from '../TrendAnalysis';
import WritingAssistant from '../WritingAssistant';
import './index.css';

const { Title, Text } = Typography;

const ProjectDetail: React.FC = () => {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const projectId = Number(id);

    const [project, setProject] = useState<Project | null>(null);
    const [papers, setPapers] = useState<Paper[]>([]);
    const [loading, setLoading] = useState(true);
    const [papersLoading, setPapersLoading] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [activeTab, setActiveTab] = useState('papers');

    useEffect(() => {
        if (projectId) {
            loadProject();
            loadPapers();
        }
    }, [projectId]);

    const loadProject = async () => {
        try {
            const { data } = await projectsApi.get(projectId);
            setProject(data);
        } catch (error) {
            message.error('加载项目失败');
        } finally {
            setLoading(false);
        }
    };

    const loadPapers = async () => {
        setPapersLoading(true);
        try {
            const { data } = await papersApi.list({ project_id: projectId });
            setPapers(data.items || (Array.isArray(data) ? data : []));
        } catch (error) {
            console.error('Failed to load papers:', error);
        } finally {
            setPapersLoading(false);
        }
    };

    const handleUpload = async (file: File) => {
        setUploading(true);
        try {
            await papersApi.upload(projectId, file);
            message.success('文献上传成功');
            loadPapers();
        } catch (error) {
            message.error('上传失败');
        } finally {
            setUploading(false);
        }
        return false; // prevent default upload
    };

    const handleDelete = async (paperId: number) => {
        try {
            await papersApi.delete(paperId);
            message.success('已删除');
            loadPapers();
        } catch (error) {
            message.error('删除失败');
        }
    };

    const getStatusTag = (status: string) => {
        const map: Record<string, { color: string; text: string }> = {
            pending: { color: 'default', text: '等待处理' },
            processing: { color: 'processing', text: '解析中' },
            completed: { color: 'success', text: '已完成' },
            failed: { color: 'error', text: '失败' },
        };
        const info = map[status] || { color: 'default', text: status };
        return <Tag color={info.color}>{info.text}</Tag>;
    };

    const paperColumns = [
        {
            title: '标题',
            dataIndex: 'title',
            key: 'title',
            render: (title: string) => title || '未解析',
            ellipsis: true,
        },
        {
            title: '作者',
            dataIndex: 'authors',
            key: 'authors',
            render: (authors: string) => authors || '-',
            ellipsis: true,
            width: 200,
        },
        {
            title: '状态',
            dataIndex: 'status',
            key: 'status',
            render: getStatusTag,
            width: 120,
        },
        {
            title: '页数',
            dataIndex: 'page_count',
            key: 'page_count',
            width: 80,
        },
        {
            title: '上传时间',
            dataIndex: 'created_at',
            key: 'created_at',
            render: (date: string) => new Date(date).toLocaleDateString(),
            width: 120,
        },
        {
            title: '操作',
            key: 'actions',
            width: 120,
            render: (_: any, record: Paper) => (
                <Space>
                    <Button
                        type="link"
                        size="small"
                        onClick={() => navigate(`/chat/${projectId}`)}
                    >
                        问答
                    </Button>
                    <Popconfirm title="确定删除？" onConfirm={() => handleDelete(record.id)}>
                        <Button type="link" size="small" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    const tabItems = [
        {
            key: 'papers',
            label: <span><FileTextOutlined /> 论文管理</span>,
            children: (
                <div>
                    <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
                        <Upload
                            accept=".pdf"
                            showUploadList={false}
                            beforeUpload={handleUpload}
                        >
                            <Button type="primary" icon={<UploadOutlined />} loading={uploading}>
                                上传文献
                            </Button>
                        </Upload>
                        <Button icon={<ReloadOutlined />} onClick={loadPapers}>刷新</Button>
                    </div>
                    <Table
                        columns={paperColumns}
                        dataSource={papers}
                        rowKey="id"
                        loading={papersLoading}
                        pagination={{ pageSize: 10 }}
                        locale={{ emptyText: <Empty description="暂无文献，点击上传按钮添加" /> }}
                    />
                </div>
            ),
        },
        {
            key: 'visualization',
            label: <span><BarChartOutlined /> 可视化</span>,
            children: <Visualization projectId={projectId} />,
        },
        {
            key: 'knowledge-graph',
            label: <span><ShareAltOutlined /> 知识图谱</span>,
            children: <KnowledgeGraph projectId={projectId} />,
        },
        {
            key: 'trend-analysis',
            label: <span><LineChartOutlined /> 趋势分析</span>,
            children: <TrendAnalysis projectId={projectId} />,
        },
        {
            key: 'writing',
            label: <span><EditOutlined /> 写作辅助</span>,
            children: <WritingAssistant projectId={projectId} />,
        },
    ];

    if (loading) {
        return (
            <div style={{ textAlign: 'center', padding: 100 }}>
                <Spin size="large" />
            </div>
        );
    }

    if (!project) {
        return <Empty description="项目不存在" />;
    }

    return (
        <div className="project-detail">
            <div className="project-detail-header">
                <Button
                    type="text"
                    icon={<ArrowLeftOutlined />}
                    onClick={() => navigate('/projects')}
                >
                    返回项目列表
                </Button>
                <div style={{ marginTop: 8 }}>
                    <Title level={3}>{project.name}</Title>
                    {project.description && (
                        <Text type="secondary">{project.description}</Text>
                    )}
                    <div style={{ marginTop: 8 }}>
                        <Tag>{papers.length} 篇文献</Tag>
                        <Tag>创建于 {new Date(project.created_at).toLocaleDateString()}</Tag>
                    </div>
                </div>
            </div>

            <Card style={{ marginTop: 16 }}>
                <Tabs
                    activeKey={activeTab}
                    onChange={setActiveTab}
                    items={tabItems}
                    size="large"
                />
            </Card>
        </div>
    );
};

export default ProjectDetail;
