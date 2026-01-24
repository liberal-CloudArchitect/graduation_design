// 项目列表页面
import React, { useEffect, useState } from 'react';
import { Card, List, Button, Empty, Typography, Spin, Modal, Form, Input, message } from 'antd';
import { PlusOutlined, FolderOutlined, DeleteOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { projectsApi } from '../../services/projects';
import type { Project } from '../../types/models';
import './index.css';

const { Title, Text } = Typography;
const { TextArea } = Input;

const ProjectList: React.FC = () => {
    const navigate = useNavigate();
    const [projects, setProjects] = useState<Project[]>([]);
    const [loading, setLoading] = useState(true);
    const [modalVisible, setModalVisible] = useState(false);
    const [form] = Form.useForm();

    useEffect(() => {
        loadProjects();
    }, []);

    const loadProjects = async () => {
        try {
            const { data } = await projectsApi.list(1, 50);
            setProjects(data.items);
        } catch (error) {
            console.error('Failed to load projects:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleCreate = async (values: { name: string; description?: string }) => {
        try {
            await projectsApi.create(values);
            message.success('项目创建成功');
            setModalVisible(false);
            form.resetFields();
            loadProjects();
        } catch (error) {
            message.error('创建失败');
        }
    };

    const handleDelete = async (id: number, e: React.MouseEvent) => {
        e.stopPropagation();
        Modal.confirm({
            title: '确认删除',
            content: '删除后无法恢复，确定要删除这个项目吗？',
            okText: '删除',
            okType: 'danger',
            cancelText: '取消',
            onOk: async () => {
                try {
                    await projectsApi.delete(id);
                    message.success('删除成功');
                    loadProjects();
                } catch (error) {
                    message.error('删除失败');
                }
            },
        });
    };

    return (
        <div className="projects-page">
            <div className="page-header">
                <div>
                    <Title level={3}>我的项目</Title>
                    <Text type="secondary">管理您的文献研究项目</Text>
                </div>
                <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    onClick={() => setModalVisible(true)}
                >
                    新建项目
                </Button>
            </div>

            {loading ? (
                <div className="loading-container">
                    <Spin size="large" />
                </div>
            ) : projects.length > 0 ? (
                <List
                    grid={{ gutter: 24, xs: 1, sm: 2, md: 2, lg: 3, xl: 3, xxl: 4 }}
                    dataSource={projects}
                    renderItem={(project) => (
                        <List.Item>
                            <Card
                                className="project-card"
                                hoverable
                                onClick={() => navigate(`/project/${project.id}`)}
                                actions={[
                                    <Button
                                        key="delete"
                                        type="text"
                                        danger
                                        icon={<DeleteOutlined />}
                                        onClick={(e) => handleDelete(project.id, e)}
                                    >
                                        删除
                                    </Button>,
                                ]}
                            >
                                <Card.Meta
                                    avatar={<FolderOutlined className="project-icon" />}
                                    title={project.name}
                                    description={project.description || '无描述'}
                                />
                                <div className="project-stats">
                                    <Text type="secondary">{project.paper_count} 篇文献</Text>
                                </div>
                            </Card>
                        </List.Item>
                    )}
                />
            ) : (
                <Card className="empty-card">
                    <Empty description="还没有项目">
                        <Button type="primary" onClick={() => setModalVisible(true)}>
                            创建第一个项目
                        </Button>
                    </Empty>
                </Card>
            )}

            <Modal
                title="新建项目"
                open={modalVisible}
                onCancel={() => setModalVisible(false)}
                footer={null}
            >
                <Form form={form} layout="vertical" onFinish={handleCreate}>
                    <Form.Item
                        name="name"
                        label="项目名称"
                        rules={[{ required: true, message: '请输入项目名称' }]}
                    >
                        <Input placeholder="例如：毕业设计文献综述" />
                    </Form.Item>
                    <Form.Item name="description" label="项目描述">
                        <TextArea rows={3} placeholder="简要描述这个项目的目的" />
                    </Form.Item>
                    <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
                        <Button onClick={() => setModalVisible(false)} style={{ marginRight: 8 }}>
                            取消
                        </Button>
                        <Button type="primary" htmlType="submit">
                            创建
                        </Button>
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
};

export default ProjectList;
