// 智能对话页面
import React, { useState, useRef, useEffect } from 'react';
import { Card, Input, Button, List, Typography, Select, Empty, Avatar, Spin } from 'antd';
import { SendOutlined, RobotOutlined, UserOutlined, FileTextOutlined } from '@ant-design/icons';
import { ragApi } from '../../services/rag';
import { projectsApi } from '../../services/projects';
import type { Project, Message, Reference } from '../../types/models';
import './index.css';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

const ChatPage: React.FC = () => {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [projects, setProjects] = useState<Project[]>([]);
    const [selectedProject, setSelectedProject] = useState<number | undefined>();
    const [references, setReferences] = useState<Reference[]>([]);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        loadProjects();
    }, []);

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const loadProjects = async () => {
        try {
            const { data } = await projectsApi.list(1, 100);
            setProjects(data.items);
        } catch (error) {
            console.error('Failed to load projects:', error);
        }
    };

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    const handleSend = async () => {
        if (!input.trim() || loading) return;

        const userMessage: Message = {
            role: 'user',
            content: input,
            created_at: new Date().toISOString(),
        };

        setMessages((prev) => [...prev, userMessage]);
        setInput('');
        setLoading(true);
        setReferences([]);

        let assistantContent = '';

        try {
            await ragApi.stream(
                { question: input, project_id: selectedProject, top_k: 5 },
                {
                    onChunk: (chunk) => {
                        assistantContent += chunk;
                        setMessages((prev) => {
                            const updated = [...prev];
                            const lastMsg = updated[updated.length - 1];
                            if (lastMsg?.role === 'assistant') {
                                lastMsg.content = assistantContent;
                            } else {
                                updated.push({
                                    role: 'assistant',
                                    content: assistantContent,
                                    created_at: new Date().toISOString(),
                                });
                            }
                            return [...updated];
                        });
                    },
                    onReferences: (refs) => {
                        setReferences(refs);
                    },
                    onDone: () => {
                        setLoading(false);
                    },
                    onError: (error) => {
                        setMessages((prev) => [
                            ...prev,
                            {
                                role: 'assistant',
                                content: `抱歉，出现了错误：${error}`,
                                created_at: new Date().toISOString(),
                            },
                        ]);
                        setLoading(false);
                    },
                }
            );
        } catch (error) {
            setLoading(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    return (
        <div className="chat-page">
            <div className="chat-main">
                <div className="chat-header">
                    <div className="chat-title">
                        <RobotOutlined className="chat-icon" />
                        <span>智能文献问答</span>
                    </div>
                    <Select
                        placeholder="选择项目范围"
                        allowClear
                        style={{ width: 200 }}
                        value={selectedProject}
                        onChange={setSelectedProject}
                        options={projects.map((p) => ({ label: p.name, value: p.id }))}
                    />
                </div>

                <div className="chat-messages">
                    {messages.length === 0 ? (
                        <div className="chat-empty">
                            <Empty
                                image={<RobotOutlined style={{ fontSize: 64, color: '#d1d5db' }} />}
                                description={
                                    <div>
                                        <Text strong>开始与文献对话</Text>
                                        <br />
                                        <Text type="secondary">基于您上传的文献，智能回答问题</Text>
                                    </div>
                                }
                            />
                        </div>
                    ) : (
                        <List
                            dataSource={messages}
                            renderItem={(msg) => (
                                <div className={`message-item ${msg.role}`}>
                                    <Avatar
                                        icon={msg.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
                                        className={`message-avatar ${msg.role}`}
                                    />
                                    <div className="message-content">
                                        <Paragraph className="message-text">{msg.content}</Paragraph>
                                    </div>
                                </div>
                            )}
                        />
                    )}
                    {loading && (
                        <div className="message-item assistant">
                            <Avatar icon={<RobotOutlined />} className="message-avatar assistant" />
                            <div className="message-content">
                                <Spin size="small" />
                            </div>
                        </div>
                    )}
                    <div ref={messagesEndRef} />
                </div>

                <div className="chat-input-area">
                    <TextArea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="输入您的问题，按 Enter 发送..."
                        autoSize={{ minRows: 1, maxRows: 4 }}
                        disabled={loading}
                    />
                    <Button
                        type="primary"
                        icon={<SendOutlined />}
                        onClick={handleSend}
                        loading={loading}
                        disabled={!input.trim()}
                    >
                        发送
                    </Button>
                </div>
            </div>

            <div className="chat-sidebar">
                <Card title="引用来源" size="small" className="references-card">
                    {references.length > 0 ? (
                        <List
                            size="small"
                            dataSource={references}
                            renderItem={(ref, index) => (
                                <List.Item className="reference-item">
                                    <div>
                                        <Text strong>[{index + 1}]</Text>
                                        <Text className="ref-title">{ref.paper_title || '未知文献'}</Text>
                                        {ref.page_number && (
                                            <Text type="secondary"> (第{ref.page_number}页)</Text>
                                        )}
                                        <Paragraph ellipsis={{ rows: 2 }} className="ref-text">
                                            {ref.text}
                                        </Paragraph>
                                    </div>
                                </List.Item>
                            )}
                        />
                    ) : (
                        <Empty
                            image={<FileTextOutlined style={{ fontSize: 32, color: '#d1d5db' }} />}
                            description="暂无引用"
                            imageStyle={{ height: 40 }}
                        />
                    )}
                </Card>
            </div>
        </div>
    );
};

export default ChatPage;
