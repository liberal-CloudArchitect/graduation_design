// 智能对话页面 - 含对话历史侧栏 + Agent Coordinator 智能路由
import React, { useState, useRef, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
    Card, Input, Button, List, Typography, Select, Empty,
    Avatar, Spin, Popconfirm, message, Tooltip, Tag
} from 'antd';
import {
    SendOutlined, RobotOutlined, UserOutlined, FileTextOutlined,
    PlusOutlined, DeleteOutlined, HistoryOutlined,
    SearchOutlined, BarChartOutlined, EditOutlined, BookOutlined
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import { agentsApi } from '../../services/agents';
import { ragApi } from '../../services/rag';
import { projectsApi } from '../../services/projects';
import type { Project, Message, Reference, Conversation } from '../../types/models';
import './index.css';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

/** Agent 类型对应的图标和颜色 */
const AGENT_CONFIG: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
    retriever_agent: { icon: <BookOutlined />, color: 'blue', label: '文献检索' },
    analyzer_agent: { icon: <BarChartOutlined />, color: 'green', label: '趋势分析' },
    writer_agent: { icon: <EditOutlined />, color: 'purple', label: '写作辅助' },
    search_agent: { icon: <SearchOutlined />, color: 'orange', label: '学术搜索' },
};

const ChatPage: React.FC = () => {
    const { projectId: routeProjectId } = useParams<{ projectId: string }>();

    // Chat state
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [projects, setProjects] = useState<Project[]>([]);
    const [selectedProject, setSelectedProject] = useState<number | undefined>(
        routeProjectId ? Number(routeProjectId) : undefined
    );
    const [references, setReferences] = useState<Reference[]>([]);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    // Agent routing state
    const [routingAgent, setRoutingAgent] = useState<string | null>(null);
    const [routingLabel, setRoutingLabel] = useState<string | null>(null);

    // Conversation history state
    const [conversations, setConversations] = useState<Conversation[]>([]);
    const [activeConversationId, setActiveConversationId] = useState<number | null>(null);
    const [conversationsLoading, setConversationsLoading] = useState(false);

    useEffect(() => {
        loadProjects();
        loadConversations();
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

    const loadConversations = async () => {
        setConversationsLoading(true);
        try {
            const { data } = await ragApi.getConversations(undefined, 50);
            setConversations(data);
        } catch (error) {
            console.error('Failed to load conversations:', error);
        } finally {
            setConversationsLoading(false);
        }
    };

    const handleSelectConversation = async (conv: Conversation) => {
        setActiveConversationId(conv.id);
        setMessages(conv.messages || []);
        setReferences([]);
        setRoutingAgent(null);
        setRoutingLabel(null);
        if (conv.project_id) {
            setSelectedProject(conv.project_id);
        }
    };

    const handleNewConversation = () => {
        setActiveConversationId(null);
        setMessages([]);
        setReferences([]);
        setRoutingAgent(null);
        setRoutingLabel(null);
    };

    const handleDeleteConversation = async (convId: number) => {
        try {
            await ragApi.deleteConversation(convId);
            setConversations((prev) => prev.filter((c) => c.id !== convId));
            if (activeConversationId === convId) {
                handleNewConversation();
            }
            message.success('对话已删除');
        } catch {
            message.error('删除失败');
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
        const currentInput = input;
        setInput('');
        setLoading(true);
        setReferences([]);
        setRoutingAgent(null);
        setRoutingLabel(null);

        let assistantContent = '';

        try {
            await agentsApi.stream(
                { query: currentInput, project_id: selectedProject },
                {
                    onRouting: (info) => {
                        setRoutingAgent(info.agent_type);
                        setRoutingLabel(info.label);
                    },
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
                    onMetadata: (_metadata) => {
                        // 可在此处理图表数据等元信息，暂存备用
                    },
                    onDone: (data) => {
                        setLoading(false);
                        if (data.conversation_id) {
                            setActiveConversationId(data.conversation_id);
                        }
                        // Refresh conversation list to include new conversation
                        loadConversations();
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

    const getConversationTitle = (conv: Conversation) => {
        if (conv.title) return conv.title;
        const firstUserMsg = conv.messages?.find((m) => m.role === 'user');
        if (firstUserMsg) {
            return firstUserMsg.content.length > 30
                ? firstUserMsg.content.substring(0, 30) + '...'
                : firstUserMsg.content;
        }
        return '新对话';
    };

    // Suggested questions for empty state - showcasing different Agent capabilities
    const suggestedQuestions = [
        '这些论文的主要研究方法有哪些？',
        '帮我分析一下这个领域的研究趋势',
        '请帮我生成一份文献综述大纲',
        '搜索最新的RAG相关论文',
    ];

    return (
        <div className="chat-page">
            {/* Left: Conversation History */}
            <div className="chat-history-sidebar">
                <div className="history-header">
                    <Text strong><HistoryOutlined /> 对话历史</Text>
                    <Tooltip title="新建对话">
                        <Button
                            type="primary"
                            size="small"
                            icon={<PlusOutlined />}
                            onClick={handleNewConversation}
                        />
                    </Tooltip>
                </div>
                <div className="history-list">
                    {conversationsLoading ? (
                        <div style={{ textAlign: 'center', padding: 24 }}><Spin size="small" /></div>
                    ) : conversations.length > 0 ? (
                        conversations.map((conv) => (
                            <div
                                key={conv.id}
                                className={`history-item ${activeConversationId === conv.id ? 'active' : ''}`}
                                onClick={() => handleSelectConversation(conv)}
                            >
                                <div className="history-item-content">
                                    <Text ellipsis className="history-title">
                                        {getConversationTitle(conv)}
                                    </Text>
                                    <Text type="secondary" className="history-date">
                                        {new Date(conv.created_at).toLocaleDateString()}
                                    </Text>
                                </div>
                                <Popconfirm
                                    title="删除此对话？"
                                    onConfirm={(e) => {
                                        e?.stopPropagation();
                                        handleDeleteConversation(conv.id);
                                    }}
                                    onCancel={(e) => e?.stopPropagation()}
                                >
                                    <Button
                                        type="text"
                                        size="small"
                                        danger
                                        icon={<DeleteOutlined />}
                                        className="history-delete-btn"
                                        onClick={(e) => e.stopPropagation()}
                                    />
                                </Popconfirm>
                            </div>
                        ))
                    ) : (
                        <Empty description="暂无对话" imageStyle={{ height: 40 }} />
                    )}
                </div>
            </div>

            {/* Center: Chat Area */}
            <div className="chat-main">
                <div className="chat-header">
                    <div className="chat-title">
                        <RobotOutlined className="chat-icon" />
                        <span>智能文献问答</span>
                        {routingAgent && (
                            <Tag
                                icon={AGENT_CONFIG[routingAgent]?.icon}
                                color={AGENT_CONFIG[routingAgent]?.color || 'default'}
                                style={{ marginLeft: 8 }}
                            >
                                {routingLabel || AGENT_CONFIG[routingAgent]?.label || routingAgent}
                            </Tag>
                        )}
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
                            <div className="chat-welcome">
                                <RobotOutlined style={{ fontSize: 48, color: '#667eea', marginBottom: 16 }} />
                                <Text strong style={{ fontSize: 18 }}>智能文献助手</Text>
                                <Text type="secondary" style={{ marginTop: 4 }}>
                                    系统将自动识别您的意图，调度最合适的 Agent 来处理
                                </Text>
                                <div className="agent-hints" style={{ margin: '12px 0', display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
                                    {Object.entries(AGENT_CONFIG).map(([key, cfg]) => (
                                        <Tag key={key} icon={cfg.icon} color={cfg.color}>
                                            {cfg.label}
                                        </Tag>
                                    ))}
                                </div>
                                <div className="suggested-questions">
                                    <Text type="secondary" style={{ marginBottom: 8, display: 'block' }}>
                                        试试这些问题：
                                    </Text>
                                    {suggestedQuestions.map((q, i) => (
                                        <Button
                                            key={i}
                                            className="suggested-btn"
                                            onClick={() => {
                                                setInput(q);
                                            }}
                                        >
                                            {q}
                                        </Button>
                                    ))}
                                </div>
                            </div>
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
                                        {msg.role === 'assistant' ? (
                                            <div className="message-text markdown-body">
                                                <ReactMarkdown>{msg.content}</ReactMarkdown>
                                            </div>
                                        ) : (
                                            <Paragraph className="message-text">{msg.content}</Paragraph>
                                        )}
                                    </div>
                                </div>
                            )}
                        />
                    )}
                    {loading && (
                        <div className="message-item assistant">
                            <Avatar icon={<RobotOutlined />} className="message-avatar assistant" />
                            <div className="message-content">
                                {routingLabel ? (
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                        <Spin size="small" />
                                        <Text type="secondary" style={{ fontSize: 12 }}>
                                            {routingLabel}处理中...
                                        </Text>
                                    </div>
                                ) : (
                                    <Spin size="small" />
                                )}
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

            {/* Right: References */}
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
