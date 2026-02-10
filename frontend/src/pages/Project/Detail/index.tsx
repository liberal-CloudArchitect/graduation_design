// 项目详情页 - 包含论文管理、可视化、知识图谱、趋势分析、写作辅助标签页
import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
    Tabs, Card, Button, Upload, Table, Tag, Space, Drawer,
    Typography, Spin, Empty, Descriptions, message, Popconfirm, Progress
} from 'antd';
import {
    FileTextOutlined, BarChartOutlined, ShareAltOutlined,
    LineChartOutlined, EditOutlined, UploadOutlined,
    DeleteOutlined, ArrowLeftOutlined, ReloadOutlined,
    EyeOutlined, LinkOutlined, SyncOutlined, ExperimentOutlined
} from '@ant-design/icons';
import { projectsApi } from '../../../services/projects';
import { papersApi } from '../../../services/papers';
import type { Project, Paper } from '../../../types/models';
import Visualization from '../Visualization';
import KnowledgeGraph from '../KnowledgeGraph';
import TrendAnalysis from '../TrendAnalysis';
import WritingAssistant from '../WritingAssistant';
import MemoryDashboard from '../MemoryDashboard';
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

    // Paper detail drawer
    const [selectedPaper, setSelectedPaper] = useState<Paper | null>(null);
    const [drawerVisible, setDrawerVisible] = useState(false);
    const [paperDetailLoading, setPaperDetailLoading] = useState(false);

    // Polling for processing papers
    const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

    useEffect(() => {
        if (projectId) {
            loadProject();
            loadPapers();
        }
        return () => {
            if (pollingRef.current) clearInterval(pollingRef.current);
        };
    }, [projectId]);

    // Start polling when there are processing papers
    const startPolling = useCallback(() => {
        if (pollingRef.current) clearInterval(pollingRef.current);
        pollingRef.current = setInterval(async () => {
            try {
                const { data } = await papersApi.list({ project_id: projectId });
                const items = data.items || (Array.isArray(data) ? data : []);
                setPapers(items);
                const hasProcessing = items.some((p: Paper) => p.status === 'pending' || p.status === 'processing');
                if (!hasProcessing && pollingRef.current) {
                    clearInterval(pollingRef.current);
                    pollingRef.current = null;
                }
            } catch {
                // silently ignore polling errors
            }
        }, 5000);
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
            const items = data.items || (Array.isArray(data) ? data : []);
            setPapers(items);
            // Start polling if any papers are processing
            const hasProcessing = items.some((p: Paper) => p.status === 'pending' || p.status === 'processing');
            if (hasProcessing) startPolling();
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
            message.success('文献上传成功，正在解析中...');
            await loadPapers(); // Reload and start polling
        } catch (error) {
            message.error('上传失败');
        } finally {
            setUploading(false);
        }
        return false;
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

    const handleViewDetail = async (paper: Paper) => {
        setDrawerVisible(true);
        setPaperDetailLoading(true);
        try {
            const { data } = await papersApi.get(paper.id);
            setSelectedPaper(data);
        } catch {
            setSelectedPaper(paper); // fallback to table data
        } finally {
            setPaperDetailLoading(false);
        }
    };

    const formatAuthors = (authors: any): string => {
        if (!authors) return '-';
        if (typeof authors === 'string') return authors;
        if (Array.isArray(authors)) {
            return authors.map((a: any) => (typeof a === 'string' ? a : a.name)).join(', ') || '-';
        }
        return '-';
    };

    const getStatusTag = (status: string) => {
        const map: Record<string, { color: string; text: string; icon?: React.ReactNode }> = {
            pending: { color: 'default', text: '等待处理' },
            processing: { color: 'processing', text: '解析中', icon: <SyncOutlined spin /> },
            completed: { color: 'success', text: '已完成' },
            failed: { color: 'error', text: '失败' },
        };
        const info = map[status] || { color: 'default', text: status };
        return <Tag color={info.color} icon={info.icon}>{info.text}</Tag>;
    };

    const paperColumns = [
        {
            title: '标题',
            dataIndex: 'title',
            key: 'title',
            render: (title: string, record: Paper) => (
                <a onClick={() => handleViewDetail(record)}>{title || '未解析'}</a>
            ),
            ellipsis: true,
        },
        {
            title: '作者',
            dataIndex: 'authors',
            key: 'authors',
            render: formatAuthors,
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
            width: 180,
            render: (_: any, record: Paper) => (
                <Space>
                    <Button
                        type="link"
                        size="small"
                        icon={<EyeOutlined />}
                        onClick={() => handleViewDetail(record)}
                    >
                        详情
                    </Button>
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
        {
            key: 'memory',
            label: <span><ExperimentOutlined /> 记忆系统</span>,
            children: <MemoryDashboard projectId={projectId} />,
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

            {/* Paper Detail Drawer */}
            <Drawer
                title="文献详情"
                open={drawerVisible}
                onClose={() => { setDrawerVisible(false); setSelectedPaper(null); }}
                width={560}
            >
                {paperDetailLoading ? (
                    <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
                ) : selectedPaper ? (
                    <div>
                        <Descriptions column={1} bordered size="small">
                            <Descriptions.Item label="标题">
                                <Text strong>{selectedPaper.title || '未解析'}</Text>
                            </Descriptions.Item>
                            <Descriptions.Item label="作者">
                                {formatAuthors(selectedPaper.authors)}
                            </Descriptions.Item>
                            <Descriptions.Item label="状态">
                                {getStatusTag(selectedPaper.status)}
                            </Descriptions.Item>
                            {selectedPaper.abstract && (
                                <Descriptions.Item label="摘要">
                                    <Text style={{ fontSize: 13 }}>{selectedPaper.abstract}</Text>
                                </Descriptions.Item>
                            )}
                            {selectedPaper.keywords && selectedPaper.keywords.length > 0 && (
                                <Descriptions.Item label="关键词">
                                    <Space wrap>
                                        {selectedPaper.keywords.map((kw, i) => (
                                            <Tag key={i} color="blue">{kw}</Tag>
                                        ))}
                                    </Space>
                                </Descriptions.Item>
                            )}
                            {selectedPaper.doi && (
                                <Descriptions.Item label="DOI">
                                    <a
                                        href={`https://doi.org/${selectedPaper.doi}`}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                    >
                                        <LinkOutlined /> {selectedPaper.doi}
                                    </a>
                                </Descriptions.Item>
                            )}
                            {selectedPaper.arxiv_id && (
                                <Descriptions.Item label="ArXiv ID">
                                    <a
                                        href={`https://arxiv.org/abs/${selectedPaper.arxiv_id}`}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                    >
                                        <LinkOutlined /> {selectedPaper.arxiv_id}
                                    </a>
                                </Descriptions.Item>
                            )}
                            {selectedPaper.publication_date && (
                                <Descriptions.Item label="发表日期">
                                    {selectedPaper.publication_date}
                                </Descriptions.Item>
                            )}
                            {selectedPaper.venue && (
                                <Descriptions.Item label="发表期刊/会议">
                                    {selectedPaper.venue}
                                </Descriptions.Item>
                            )}
                            {selectedPaper.source && (
                                <Descriptions.Item label="来源">
                                    <Tag>{selectedPaper.source}</Tag>
                                </Descriptions.Item>
                            )}
                            <Descriptions.Item label="页数">
                                {selectedPaper.page_count ?? '-'}
                            </Descriptions.Item>
                            {selectedPaper.chunk_count != null && (
                                <Descriptions.Item label="文本块数">
                                    {selectedPaper.chunk_count}
                                </Descriptions.Item>
                            )}
                            {selectedPaper.file_size != null && (
                                <Descriptions.Item label="文件大小">
                                    {(selectedPaper.file_size / 1024 / 1024).toFixed(2)} MB
                                </Descriptions.Item>
                            )}
                            <Descriptions.Item label="上传时间">
                                {new Date(selectedPaper.created_at).toLocaleString()}
                            </Descriptions.Item>
                        </Descriptions>
                        <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
                            <Button
                                type="primary"
                                onClick={() => navigate(`/chat/${projectId}`)}
                            >
                                基于此文献问答
                            </Button>
                        </div>
                    </div>
                ) : (
                    <Empty description="未找到文献信息" />
                )}
            </Drawer>
        </div>
    );
};

export default ProjectDetail;
