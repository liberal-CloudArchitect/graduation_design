// 智能对话页面 - 含对话历史侧栏 + Agent Coordinator 智能路由 + 图表/KG 渲染
import React, { useState, useRef, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
    Card, Input, Button, List, Typography, Select, Empty,
    Avatar, Spin, Popconfirm, message, Tooltip, Tag
} from 'antd';
import {
    SendOutlined, RobotOutlined, UserOutlined, FileTextOutlined,
    PlusOutlined, DeleteOutlined, HistoryOutlined,
    SearchOutlined, BarChartOutlined, EditOutlined, BookOutlined,
    LoadingOutlined
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import { agentsApi } from '../../services/agents';
import { ragApi } from '../../services/rag';
import { projectsApi } from '../../services/projects';
import ChatChartRenderer from '../../components/ChatChartRenderer';
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

/** 斜杠命令定义 */
interface SlashCommand {
    command: string;
    label: string;
    description: string;
    agent_type: string;
    icon: React.ReactNode;
    color: string;
    params?: Record<string, any>;
}

const SLASH_COMMANDS: SlashCommand[] = [
    {
        command: '/analyze',
        label: '趋势分析',
        description: '分析关键词、时间线、热点、突现词等',
        agent_type: 'analyzer_agent',
        icon: <BarChartOutlined />,
        color: 'green',
    },
    {
        command: '/extract table',
        label: '提取表格',
        description: '从 PDF 文献中提取结构化表格',
        agent_type: 'analyzer_agent',
        icon: <BarChartOutlined />,
        color: 'green',
        params: { analysis_type: 'table_extraction' },
    },
    {
        command: '/build kg',
        label: '构建知识图谱',
        description: '从文献中提取实体和关系',
        agent_type: 'analyzer_agent',
        icon: <BarChartOutlined />,
        color: 'green',
        params: { analysis_type: 'knowledge_graph' },
    },
    {
        command: '/write',
        label: '写作辅助',
        description: '生成大纲、综述、润色等',
        agent_type: 'writer_agent',
        icon: <EditOutlined />,
        color: 'purple',
    },
    {
        command: '/search',
        label: '学术搜索',
        description: '搜索最新学术文献',
        agent_type: 'search_agent',
        icon: <SearchOutlined />,
        color: 'orange',
    },
    {
        command: '/retrieve',
        label: '文献检索',
        description: '从已上传的文献中检索相关内容',
        agent_type: 'retriever_agent',
        icon: <BookOutlined />,
        color: 'blue',
    },
];

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

    // Status message for intermediate agent stages
    const [statusMessage, setStatusMessage] = useState<string | null>(null);

    // Conversation history state
    const [conversations, setConversations] = useState<Conversation[]>([]);
    const [activeConversationId, setActiveConversationId] = useState<number | null>(null);
    const [conversationsLoading, setConversationsLoading] = useState(false);

    // Ref to accumulate metadata during streaming
    const pendingMetadataRef = useRef<Record<string, any> | null>(null);

    // Slash command state
    const [showSlashMenu, setShowSlashMenu] = useState(false);
    const [slashFilter, setSlashFilter] = useState('');
    const [slashSelectedIndex, setSlashSelectedIndex] = useState(0);
    const filteredCommands = SLASH_COMMANDS.filter(
        (cmd) =>
            cmd.command.includes(slashFilter.toLowerCase()) ||
            cmd.label.includes(slashFilter) ||
            cmd.description.includes(slashFilter)
    );

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
        } catch (error: any) {
            // 401 由 axios interceptor 自动刷新 token 并重试；
            // 若刷新也失败则跳转登录，此处无需额外处理。
            // 其它错误仅记录日志，不影响主流程。
            if (error?.response?.status !== 401) {
                console.error('Failed to load conversations:', error);
            }
        } finally {
            setConversationsLoading(false);
        }
    };

    const handleSelectConversation = async (conv: Conversation) => {
        const refs = [...(conv.messages || [])]
            .reverse()
            .find((m) => m.role === 'assistant' && m.references && m.references.length > 0)
            ?.references || [];

        setActiveConversationId(conv.id);
        setMessages(conv.messages || []);
        setReferences(refs);
        setRoutingAgent(null);
        setRoutingLabel(null);
        setStatusMessage(null);
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
        setStatusMessage(null);
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

    // Parse slash commands from input
    const parseSlashCommand = (text: string): { query: string; agent_type?: string; params?: Record<string, any> } => {
        const trimmed = text.trim();
        for (const cmd of SLASH_COMMANDS) {
            if (trimmed.toLowerCase().startsWith(cmd.command)) {
                const query = trimmed.slice(cmd.command.length).trim();
                return {
                    query: query || `${cmd.label}`,
                    agent_type: cmd.agent_type,
                    params: cmd.params || {},
                };
            }
        }
        return { query: trimmed };
    };

    // Handle slash command selection from the menu
    const handleSelectSlashCommand = (cmd: SlashCommand) => {
        setInput(cmd.command + ' ');
        setShowSlashMenu(false);
        setSlashFilter('');
        setSlashSelectedIndex(0);
    };

    // Handle input change - detect slash commands
    const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
        const val = e.target.value;
        setInput(val);

        if (val.startsWith('/')) {
            setShowSlashMenu(true);
            setSlashFilter(val);
            setSlashSelectedIndex(0);
        } else {
            setShowSlashMenu(false);
            setSlashFilter('');
        }
    };

    const handleSend = async () => {
        if (!input.trim() || loading) return;

        setShowSlashMenu(false);

        // Parse slash commands
        const parsed = parseSlashCommand(input);

        const userMessage: Message = {
            role: 'user',
            content: input,
            created_at: new Date().toISOString(),
        };

        setMessages((prev) => [...prev, userMessage]);
        setInput('');
        setLoading(true);
        setReferences([]);
        setRoutingAgent(null);
        setRoutingLabel(null);
        setStatusMessage(null);
        pendingMetadataRef.current = null;

        let assistantContent = '';

        try {
            await agentsApi.stream(
                {
                    query: parsed.query,
                    project_id: selectedProject,
                    agent_type: parsed.agent_type,
                    conversation_id: activeConversationId || undefined,
                    params: parsed.params || {},
                },
                {
                    onRouting: (info) => {
                        setRoutingAgent(info.agent_type);
                        setRoutingLabel(info.label);
                    },
                    onStatus: (info) => {
                        setStatusMessage(info.message);
                    },
                    onChunk: (chunk) => {
                        setStatusMessage(null); // clear status once content starts
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
                    onMetadata: (metadata) => {
                        // Store metadata and attach to the current assistant message
                        pendingMetadataRef.current = metadata;
                        setMessages((prev) => {
                            const updated = [...prev];
                            const lastMsg = updated[updated.length - 1];
                            if (lastMsg?.role === 'assistant') {
                                lastMsg.metadata = metadata;
                            }
                            return [...updated];
                        });
                    },
                    onDone: (data) => {
                        setLoading(false);
                        setStatusMessage(null);
                        // Attach final metadata if not yet attached
                        if (pendingMetadataRef.current) {
                            setMessages((prev) => {
                                const updated = [...prev];
                                const lastMsg = updated[updated.length - 1];
                                if (lastMsg?.role === 'assistant') {
                                    lastMsg.metadata = pendingMetadataRef.current!;
                                    lastMsg.agent_type = data.agent_type;
                                }
                                return [...updated];
                            });
                        }
                        if (data.conversation_id) {
                            setActiveConversationId(data.conversation_id);
                        }
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
                        setStatusMessage(null);
                    },
                }
            );
        } catch (error) {
            setLoading(false);
            setStatusMessage(null);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (showSlashMenu && filteredCommands.length > 0) {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                setSlashSelectedIndex((prev) => Math.min(prev + 1, filteredCommands.length - 1));
                return;
            }
            if (e.key === 'ArrowUp') {
                e.preventDefault();
                setSlashSelectedIndex((prev) => Math.max(prev - 1, 0));
                return;
            }
            if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
                e.preventDefault();
                handleSelectSlashCommand(filteredCommands[slashSelectedIndex]);
                return;
            }
            if (e.key === 'Escape') {
                setShowSlashMenu(false);
                return;
            }
        }

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
                                            <>
                                                <div className="message-text markdown-body">
                                                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                                                </div>
                                                {/* Render charts/KG/tables from metadata */}
                                                {msg.metadata && <ChatChartRenderer metadata={msg.metadata} />}
                                            </>
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
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                    <Spin size="small" indicator={<LoadingOutlined spin />} />
                                    <Text type="secondary" style={{ fontSize: 12 }}>
                                        {statusMessage || (routingLabel ? `${routingLabel}处理中...` : '思考中...')}
                                    </Text>
                                </div>
                            </div>
                        </div>
                    )}
                    <div ref={messagesEndRef} />
                </div>

                <div className="chat-input-area" style={{ position: 'relative' }}>
                    {/* Slash command autocomplete dropdown */}
                    {showSlashMenu && filteredCommands.length > 0 && (
                        <div
                            className="slash-command-menu"
                            style={{
                                position: 'absolute',
                                bottom: '100%',
                                left: 0,
                                right: 0,
                                background: '#fff',
                                border: '1px solid #e8e8e8',
                                borderRadius: 8,
                                boxShadow: '0 -4px 12px rgba(0,0,0,0.08)',
                                marginBottom: 4,
                                maxHeight: 240,
                                overflow: 'auto',
                                zIndex: 1000,
                            }}
                        >
                            {filteredCommands.map((cmd, i) => (
                                <div
                                    key={cmd.command}
                                    onClick={() => handleSelectSlashCommand(cmd)}
                                    style={{
                                        padding: '8px 12px',
                                        cursor: 'pointer',
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: 8,
                                        background: i === slashSelectedIndex ? '#f0f5ff' : 'transparent',
                                        borderLeft: i === slashSelectedIndex ? '3px solid #667eea' : '3px solid transparent',
                                    }}
                                    onMouseEnter={() => setSlashSelectedIndex(i)}
                                >
                                    <Tag icon={cmd.icon} color={cmd.color} style={{ margin: 0 }}>
                                        {cmd.command}
                                    </Tag>
                                    <div style={{ flex: 1 }}>
                                        <Text strong style={{ fontSize: 13 }}>{cmd.label}</Text>
                                        <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                                            {cmd.description}
                                        </Text>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                    <TextArea
                        value={input}
                        onChange={handleInputChange}
                        onKeyDown={handleKeyDown}
                        placeholder="输入您的问题，按 Enter 发送... 输入 / 查看快捷命令"
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
                                        <div style={{ marginTop: 4 }}>
                                            <Tag color="blue" style={{ marginInlineEnd: 0 }}>
                                                相关度 {Number(ref.score || 0).toFixed(3)}
                                            </Tag>
                                        </div>
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
