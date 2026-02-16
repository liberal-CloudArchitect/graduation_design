// 智能对话页面 - 含对话历史侧栏 + Agent Coordinator 智能路由 + 图表/KG 渲染
import React, { useState, useRef, useEffect, useMemo, type ReactNode } from 'react';
import { useParams } from 'react-router-dom';
import {
    Card, Input, Button, List, Typography, Select, Empty, Modal,
    Avatar, Spin, Popconfirm, message, Tooltip, Tag
} from 'antd';
import {
    SendOutlined, RobotOutlined, UserOutlined, FileTextOutlined,
    PlusOutlined, DeleteOutlined, HistoryOutlined,
    SearchOutlined, BarChartOutlined, EditOutlined, BookOutlined,
    LoadingOutlined, BulbOutlined, CopyOutlined, AimOutlined,
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

interface StreamParseState {
    buffer: string;
    inThink: boolean;
    answer: string;
    reasoning: string;
}

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
    params?: Record<string, unknown>;
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

const THINK_OPEN = '<think>';
const THINK_CLOSE = '</think>';
const INLINE_CITATION_REGEX = /\[(\d{1,3})\]/g;

const normalizeQueryTokens = (text: string): string[] => {
    const tokens = text
        .toLowerCase()
        .match(/[a-z0-9]{3,}|[\u4e00-\u9fff]{2,}/g);
    return tokens ? Array.from(new Set(tokens)) : [];
};

const parseCitationNumbers = (text: string): number[] => {
    const hit = new Set<number>();
    const regex = /\[(\d{1,3})\]/g;
    let m: RegExpExecArray | null = regex.exec(text);
    while (m) {
        const n = Number(m[1]);
        if (Number.isFinite(n) && n > 0) hit.add(n);
        m = regex.exec(text);
    }
    return Array.from(hit).sort((a, b) => a - b);
};

const buildCitationContext = (answer: string, citationNo: number): string => {
    const marker = `[${citationNo}]`;
    const idx = answer.indexOf(marker);
    if (idx < 0) return '';
    const start = Math.max(0, idx - 42);
    const end = Math.min(answer.length, idx + marker.length + 42);
    return answer.slice(start, end).replace(/\n/g, ' ').trim();
};

const escapeRegExp = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const highlightText = (text: string, keywords: string[]): React.ReactNode => {
    const valid = keywords.filter((k) => k.length >= 2).slice(0, 4);
    if (!valid.length) return text;

    const regex = new RegExp(`(${valid.map((k) => escapeRegExp(k)).join('|')})`, 'ig');
    const parts = text.split(regex);

    return parts.map((part, idx) => {
        const matched = valid.some((k) => part.toLowerCase() === k.toLowerCase());
        return matched ? <mark key={`${part}-${idx}`}>{part}</mark> : <React.Fragment key={`${part}-${idx}`}>{part}</React.Fragment>;
    });
};

const renderTextWithInlineCitations = (
    text: string,
    keyPrefix: string,
    activeCitationNo: number | null,
    focusedCitationNo: number | null,
    onCitationClick: (citationNo: number) => void
): ReactNode => {
    const nodes: ReactNode[] = [];
    let last = 0;
    let match = INLINE_CITATION_REGEX.exec(text);
    let idx = 0;

    while (match) {
        const start = match.index;
        const end = start + match[0].length;
        const citationNo = Number(match[1]);

        if (start > last) {
            nodes.push(text.slice(last, start));
        }

        const active = activeCitationNo === citationNo;
        const focused = focusedCitationNo === citationNo;
        nodes.push(
            <button
                key={`${keyPrefix}-inline-cite-${idx}`}
                type="button"
                data-inline-cite={citationNo}
                className={`inline-citation-btn ${active ? 'active' : ''} ${focused ? 'focused' : ''}`}
                onClick={() => onCitationClick(citationNo)}
            >
                [{citationNo}]
            </button>
        );

        idx += 1;
        last = end;
        match = INLINE_CITATION_REGEX.exec(text);
    }
    INLINE_CITATION_REGEX.lastIndex = 0;

    if (last < text.length) {
        nodes.push(text.slice(last));
    }
    return nodes.length ? nodes : text;
};

const renderInlineCitationNode = (
    node: ReactNode,
    keyPrefix: string,
    activeCitationNo: number | null,
    focusedCitationNo: number | null,
    onCitationClick: (citationNo: number) => void
): ReactNode => {
    if (typeof node === 'string') {
        return renderTextWithInlineCitations(
            node,
            keyPrefix,
            activeCitationNo,
            focusedCitationNo,
            onCitationClick
        );
    }

    if (Array.isArray(node)) {
        return node.map((child, idx) =>
            renderInlineCitationNode(
                child,
                `${keyPrefix}-${idx}`,
                activeCitationNo,
                focusedCitationNo,
                onCitationClick
            )
        );
    }

    if (React.isValidElement(node)) {
        const elementTag = typeof node.type === 'string' ? node.type : '';
        if (['code', 'pre', 'a'].includes(elementTag)) {
            return node;
        }

        const props = node.props as { children?: ReactNode };
        if (!props?.children) return node;

        const nextChildren = renderInlineCitationNode(
            props.children,
            `${keyPrefix}-child`,
            activeCitationNo,
            focusedCitationNo,
            onCitationClick
        );
        return React.cloneElement(node, undefined, nextChildren);
    }

    return node;
};

const extractReasoningFromText = (raw: string): { answer: string; reasoning: string } => {
    if (!raw.includes(THINK_OPEN)) {
        return { answer: raw, reasoning: '' };
    }

    const parts: string[] = [];
    let answer = raw;
    const regex = /<think>([\s\S]*?)<\/think>/g;
    answer = answer.replace(regex, (_match, group: string) => {
        if (group?.trim()) parts.push(group.trim());
        return '';
    });

    return {
        answer: answer.trimStart(),
        reasoning: parts.join('\n\n').trim(),
    };
};

const consumeStreamChunk = (state: StreamParseState, chunk: string): StreamParseState => {
    let text = `${state.buffer}${chunk}`;
    let nextBuffer = '';
    let inThink = state.inThink;
    let answer = state.answer;
    let reasoning = state.reasoning;

    while (text.length > 0) {
        if (inThink) {
            const closeIdx = text.indexOf(THINK_CLOSE);
            if (closeIdx < 0) {
                reasoning += text;
                text = '';
                break;
            }
            reasoning += text.slice(0, closeIdx);
            text = text.slice(closeIdx + THINK_CLOSE.length);
            inThink = false;
            continue;
        }

        const openIdx = text.indexOf(THINK_OPEN);
        if (openIdx < 0) {
            const partialStart = text.lastIndexOf('<');
            if (partialStart >= 0) {
                const maybeTag = text.slice(partialStart);
                if (THINK_OPEN.startsWith(maybeTag) || THINK_CLOSE.startsWith(maybeTag)) {
                    answer += text.slice(0, partialStart);
                    nextBuffer = maybeTag;
                    text = '';
                    break;
                }
            }
            answer += text;
            text = '';
            break;
        }

        answer += text.slice(0, openIdx);
        text = text.slice(openIdx + THINK_OPEN.length);
        inThink = true;
    }

    return {
        buffer: nextBuffer,
        inThink,
        answer,
        reasoning,
    };
};

const normalizeConversationMessages = (msgs: Message[]): Message[] =>
    msgs.map((m) => {
        if (m.role !== 'assistant') return m;
        const parsed = extractReasoningFromText(m.content || '');
        return {
            ...m,
            content: parsed.answer,
            reasoning_content: m.reasoning_content || parsed.reasoning,
        };
    });

const computeDisplayReferences = (refs: Reference[], query: string, answer: string): Reference[] => {
    if (!refs.length) return [];

    const rawScores = refs.map((r) => Number(r.score || 0));
    const maxRaw = Math.max(...rawScores);
    const minRaw = Math.min(...rawScores);
    const queryTokens = normalizeQueryTokens(query);
    const querySet = new Set(queryTokens);
    const citedNumbers = new Set(parseCitationNumbers(answer));

    const normalized = refs.map((ref, idx) => {
        const raw = Number(ref.score || 0);
        const rawNorm = maxRaw > minRaw ? (raw - minRaw) / (maxRaw - minRaw) : 0.5;

        const refTokens = new Set(normalizeQueryTokens(`${ref.paper_title || ''} ${ref.text || ''}`));
        let overlapCount = 0;
        querySet.forEach((t) => {
            if (refTokens.has(t)) overlapCount += 1;
        });
        const overlap = querySet.size ? overlapCount / querySet.size : 0;
        const candidateCitationNo = Number(ref.citation_number);
        const citationNo = Number.isFinite(candidateCitationNo) && candidateCitationNo > 0
            ? candidateCitationNo
            : idx + 1;
        const citedBoost = citedNumbers.has(citationNo) ? 1 : 0;

        const displayScore = Math.max(0, Math.min(1, rawNorm * 0.55 + overlap * 0.3 + citedBoost * 0.15));

        return {
            ...ref,
            raw_score: raw,
            display_score: displayScore,
            citation_number: citationNo,
            citation_context: buildCitationContext(answer, citationNo),
        };
    });

    return normalized.sort((a, b) => (b.display_score || 0) - (a.display_score || 0));
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
    const [historyProjectFilter, setHistoryProjectFilter] = useState<number | undefined>(
        routeProjectId ? Number(routeProjectId) : undefined
    );
    const HISTORY_ALL_VALUE = -1;
    const [rawReferences, setRawReferences] = useState<Reference[]>([]);
    const [latestQuery, setLatestQuery] = useState('');
    const [activeCitationNo, setActiveCitationNo] = useState<number | null>(null);
    const [focusedCitationNo, setFocusedCitationNo] = useState<number | null>(null);
    const [expandedReasoning, setExpandedReasoning] = useState<Record<string, boolean>>({});
    const [previewRef, setPreviewRef] = useState<Reference | null>(null);
    const [previewOpen, setPreviewOpen] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const latestAssistantRef = useRef<HTMLDivElement | null>(null);

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
    const pendingMetadataRef = useRef<Record<string, unknown> | null>(null);
    const streamParseRef = useRef<StreamParseState>({
        buffer: '',
        inThink: false,
        answer: '',
        reasoning: '',
    });

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

    const latestAssistantContent = useMemo(
        () => [...messages].reverse().find((m) => m.role === 'assistant')?.content || '',
        [messages]
    );

    const references = useMemo(
        () => computeDisplayReferences(rawReferences, latestQuery, latestAssistantContent),
        [rawReferences, latestQuery, latestAssistantContent]
    );

    const queryKeywords = useMemo(() => normalizeQueryTokens(latestQuery), [latestQuery]);
    const lastAssistantIndex = useMemo(
        () => messages.map((m, i) => ({ m, i })).filter((x) => x.m.role === 'assistant').map((x) => x.i).at(-1) ?? -1,
        [messages]
    );

    useEffect(() => {
        loadProjects();
    }, []);

    useEffect(() => {
        loadConversations(historyProjectFilter);
    }, [historyProjectFilter]);

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    useEffect(() => {
        if (!activeConversationId) return;
        const stillVisible = conversations.some((conv) => conv.id === activeConversationId);
        if (!stillVisible) {
            setActiveConversationId(null);
            setMessages([]);
            setRawReferences([]);
            setActiveCitationNo(null);
            setFocusedCitationNo(null);
        }
    }, [activeConversationId, conversations]);

    const loadProjects = async () => {
        try {
            const { data } = await projectsApi.list(1, 100);
            setProjects(data.items);
        } catch (error) {
            console.error('Failed to load projects:', error);
        }
    };

    const loadConversations = async (projectId?: number) => {
        setConversationsLoading(true);
        try {
            const { data } = await ragApi.getConversations(projectId, 100);
            setConversations(data);
        } catch (error: unknown) {
            const status = typeof error === 'object' && error !== null && 'response' in error
                ? (error as { response?: { status?: number } }).response?.status
                : undefined;
            if (status !== 401) {
                console.error('Failed to load conversations:', error);
            }
        } finally {
            setConversationsLoading(false);
        }
    };

    const handleSelectConversation = async (conv: Conversation) => {
        const normalizedMessages = normalizeConversationMessages(conv.messages || []);
        const refs = [...normalizedMessages]
            .reverse()
            .find((m) => m.role === 'assistant' && m.references && m.references.length > 0)
            ?.references || [];

        const lastUser = [...normalizedMessages].reverse().find((m) => m.role === 'user')?.content || '';

        setActiveConversationId(conv.id);
        setMessages(normalizedMessages);
        setRawReferences(refs);
        setLatestQuery(lastUser);
        setActiveCitationNo(null);
        setFocusedCitationNo(null);
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
        setRawReferences([]);
        setLatestQuery('');
        setActiveCitationNo(null);
        setFocusedCitationNo(null);
        setRoutingAgent(null);
        setRoutingLabel(null);
        setStatusMessage(null);
        streamParseRef.current = {
            buffer: '',
            inThink: false,
            answer: '',
            reasoning: '',
        };
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

    const flashCitation = (citationNo: number) => {
        setFocusedCitationNo(citationNo);
        window.setTimeout(() => {
            setFocusedCitationNo((prev) => (prev === citationNo ? null : prev));
        }, 1800);
    };

    const findBestAnswerTarget = (container: HTMLElement, ref: Reference): HTMLElement | null => {
        const candidates = Array.from(container.querySelectorAll<HTMLElement>('p, li, blockquote, h1, h2, h3, h4, h5, h6'));
        if (!candidates.length) return null;

        let refSectionTop = Number.POSITIVE_INFINITY;
        candidates.forEach((el) => {
            const text = (el.textContent || '').trim();
            if (text.includes('参考来源') || text.includes('引用来源')) {
                refSectionTop = Math.min(refSectionTop, el.offsetTop);
            }
        });

        const targetNo = ref.citation_number || 0;
        const contextTokens = normalizeQueryTokens(ref.citation_context || '');
        let best: { score: number; el: HTMLElement | null } = { score: -1, el: null };

        candidates.forEach((el) => {
            const text = (el.textContent || '').trim();
            if (!text) return;

            const textTokens = normalizeQueryTokens(text);
            let overlap = 0;
            contextTokens.forEach((t) => {
                if (textTokens.includes(t)) overlap += 1;
            });

            const overlapScore = contextTokens.length ? overlap / contextTokens.length : 0;
            const markerScore = targetNo && text.includes(`[${targetNo}]`) ? 0.6 : 0;
            const sectionPenalty = el.offsetTop > refSectionTop ? -0.35 : 0;
            const score = overlapScore + markerScore + sectionPenalty;

            if (score > best.score) {
                best = { score, el };
            }
        });

        if (best.el && best.score > 0.1) return best.el;
        if (targetNo) {
            return candidates.find((el) => (el.textContent || '').includes(`[${targetNo}]`)) || null;
        }
        return null;
    };

    const scrollToCitationMarker = (ref: Reference) => {
        const container = latestAssistantRef.current;
        const citationNo = ref.citation_number || 1;

        if (container) {
            const inlineEl = container.querySelector<HTMLElement>(`[data-inline-cite="${citationNo}"]`);
            if (inlineEl) {
                inlineEl.classList.add('inline-citation-focus');
                inlineEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                flashCitation(citationNo);
                window.setTimeout(() => inlineEl.classList.remove('inline-citation-focus'), 2000);
                return;
            }

            const prevHighlighted = container.querySelectorAll('.citation-target-highlight');
            prevHighlighted.forEach((node) => node.classList.remove('citation-target-highlight'));

            const targetEl = findBestAnswerTarget(container, ref);
            if (targetEl) {
                targetEl.classList.add('citation-target-highlight');
                targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                flashCitation(citationNo);
                window.setTimeout(() => targetEl.classList.remove('citation-target-highlight'), 2200);
                return;
            }
        }

        // 兜底回退到锚点按钮区
        const markerEl = document.querySelector<HTMLElement>(`[data-citation-marker="${citationNo}"]`);
        if (markerEl) {
            markerEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
            flashCitation(citationNo);
        }
    };

    const handleInlineCitationClick = (citationNo: number) => {
        setActiveCitationNo(citationNo);
        scrollToReferenceCard(citationNo);
    };

    const scrollToReferenceCard = (citationNo: number) => {
        const refEl = document.getElementById(`ref-card-${citationNo}`);
        if (refEl) {
            refEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            flashCitation(citationNo);
        }
    };

    // Parse slash commands from input
    const parseSlashCommand = (text: string): { query: string; agent_type?: string; params?: Record<string, unknown> } => {
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
        setRawReferences([]);
        setActiveCitationNo(null);
        setFocusedCitationNo(null);
        setLatestQuery(parsed.query || input);
        setRoutingAgent(null);
        setRoutingLabel(null);
        setStatusMessage(null);
        pendingMetadataRef.current = null;
        streamParseRef.current = {
            buffer: '',
            inThink: false,
            answer: '',
            reasoning: '',
        };

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
                        setStatusMessage(null);
                        streamParseRef.current = consumeStreamChunk(streamParseRef.current, chunk);

                        setMessages((prev) => {
                            const updated = [...prev];
                            const lastMsg = updated[updated.length - 1];
                            const nextContent = streamParseRef.current.answer;
                            const nextReasoning = streamParseRef.current.reasoning.trim();

                            if (lastMsg?.role === 'assistant') {
                                lastMsg.content = nextContent;
                                lastMsg.reasoning_content = nextReasoning;
                            } else {
                                updated.push({
                                    role: 'assistant',
                                    content: nextContent,
                                    reasoning_content: nextReasoning,
                                    created_at: new Date().toISOString(),
                                });
                            }
                            return [...updated];
                        });
                    },
                    onReasoning: (chunk) => {
                        if (!chunk) return;
                        setStatusMessage(null);
                        setMessages((prev) => {
                            const updated = [...prev];
                            const lastMsg = updated[updated.length - 1];
                            if (lastMsg?.role === 'assistant') {
                                lastMsg.reasoning_content = `${lastMsg.reasoning_content || ''}${chunk}`;
                            } else {
                                updated.push({
                                    role: 'assistant',
                                    content: '',
                                    reasoning_content: chunk,
                                    created_at: new Date().toISOString(),
                                });
                            }
                            return [...updated];
                        });
                    },
                    onReferences: (refs) => {
                        setRawReferences(refs);
                    },
                    onMetadata: (metadata) => {
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

                        setMessages((prev) => {
                            const updated = [...prev];
                            const lastMsg = updated[updated.length - 1];
                            if (lastMsg?.role === 'assistant') {
                                const fallback = extractReasoningFromText(data.answer || '');
                                if (!lastMsg.content && fallback.answer) {
                                    lastMsg.content = fallback.answer;
                                }
                                if (!lastMsg.reasoning_content && fallback.reasoning) {
                                    lastMsg.reasoning_content = fallback.reasoning;
                                }
                                if (lastMsg.content?.includes(THINK_OPEN) || lastMsg.content?.includes(THINK_CLOSE)) {
                                    lastMsg.content = fallback.answer || lastMsg.content;
                                }
                                if (pendingMetadataRef.current) {
                                    lastMsg.metadata = pendingMetadataRef.current;
                                }
                                lastMsg.agent_type = data.agent_type;
                            }
                            return [...updated];
                        });

                        if (data.conversation_id) {
                            setActiveConversationId(data.conversation_id);
                        }
                        loadConversations(historyProjectFilter);
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
        } catch {
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
                ? `${firstUserMsg.content.substring(0, 30)}...`
                : firstUserMsg.content;
        }
        return '新对话';
    };

    const getProjectName = (projectId?: number) => {
        if (!projectId) return '未绑定项目';
        return projects.find((p) => p.id === projectId)?.name || `项目 #${projectId}`;
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
                <div className="history-filter-row">
                    <Select
                        size="small"
                        style={{ width: '100%' }}
                        value={historyProjectFilter ?? HISTORY_ALL_VALUE}
                        onChange={(v) => setHistoryProjectFilter(v === HISTORY_ALL_VALUE ? undefined : v)}
                        placeholder="按项目筛选历史"
                        options={[
                            { label: '全部项目', value: HISTORY_ALL_VALUE },
                            ...projects.map((p) => ({ label: p.name, value: p.id })),
                        ]}
                    />
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
                                    <div className="history-subline">
                                        <Text type="secondary" className="history-date">
                                            {new Date(conv.created_at).toLocaleDateString()}
                                        </Text>
                                        <Tag className="history-project-tag">{getProjectName(conv.project_id)}</Tag>
                                    </div>
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
                        style={{ width: 220 }}
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
                            renderItem={(msg, msgIdx) => {
                                const reasoningText = msg.reasoning_content?.trim();
                                const msgKey = `${msg.created_at}-${msgIdx}`;

                                return (
                                    <div className={`message-item ${msg.role}`}>
                                        <Avatar
                                            icon={msg.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
                                            className={`message-avatar ${msg.role}`}
                                        />
                                        <div
                                            className="message-content"
                                            ref={msgIdx === lastAssistantIndex ? (node) => { latestAssistantRef.current = node; } : undefined}
                                        >
                                            {msg.role === 'assistant' ? (
                                                <>
                                                    {reasoningText && (
                                                        <div className="reasoning-panel">
                                                            <div
                                                                className="reasoning-header"
                                                                role="button"
                                                                tabIndex={0}
                                                                onClick={() => setExpandedReasoning((prev) => ({ ...prev, [msgKey]: !prev[msgKey] }))}
                                                                onKeyDown={(e) => {
                                                                    if (e.key === 'Enter' || e.key === ' ') {
                                                                        e.preventDefault();
                                                                        setExpandedReasoning((prev) => ({ ...prev, [msgKey]: !prev[msgKey] }));
                                                                    }
                                                                }}
                                                            >
                                                                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                                                    <BulbOutlined style={{ color: '#d97706' }} />
                                                                    <Text strong>{loading ? '思考中' : '思考过程'}</Text>
                                                                </div>
                                                                <Button
                                                                    type="text"
                                                                    size="small"
                                                                    icon={<CopyOutlined />}
                                                                    onClick={(e) => {
                                                                        e.stopPropagation();
                                                                        navigator.clipboard?.writeText(reasoningText);
                                                                        message.success('思考过程已复制');
                                                                    }}
                                                                >
                                                                    复制
                                                                </Button>
                                                            </div>
                                                            {expandedReasoning[msgKey] && (
                                                                <div className="reasoning-body">
                                                                    {reasoningText}
                                                                </div>
                                                            )}
                                                        </div>
                                                    )}

                                                    <div className="message-text markdown-body">
                                                        <ReactMarkdown
                                                            components={{
                                                                p: ({ children }) => (
                                                                    <p>
                                                                        {renderInlineCitationNode(
                                                                            children,
                                                                            `${msgKey}-p`,
                                                                            activeCitationNo,
                                                                            focusedCitationNo,
                                                                            handleInlineCitationClick
                                                                        )}
                                                                    </p>
                                                                ),
                                                                li: ({ children }) => (
                                                                    <li>
                                                                        {renderInlineCitationNode(
                                                                            children,
                                                                            `${msgKey}-li`,
                                                                            activeCitationNo,
                                                                            focusedCitationNo,
                                                                            handleInlineCitationClick
                                                                        )}
                                                                    </li>
                                                                ),
                                                                blockquote: ({ children }) => (
                                                                    <blockquote>
                                                                        {renderInlineCitationNode(
                                                                            children,
                                                                            `${msgKey}-blockquote`,
                                                                            activeCitationNo,
                                                                            focusedCitationNo,
                                                                            handleInlineCitationClick
                                                                        )}
                                                                    </blockquote>
                                                                ),
                                                                h1: ({ children }) => (
                                                                    <h1>
                                                                        {renderInlineCitationNode(
                                                                            children,
                                                                            `${msgKey}-h1`,
                                                                            activeCitationNo,
                                                                            focusedCitationNo,
                                                                            handleInlineCitationClick
                                                                        )}
                                                                    </h1>
                                                                ),
                                                                h2: ({ children }) => (
                                                                    <h2>
                                                                        {renderInlineCitationNode(
                                                                            children,
                                                                            `${msgKey}-h2`,
                                                                            activeCitationNo,
                                                                            focusedCitationNo,
                                                                            handleInlineCitationClick
                                                                        )}
                                                                    </h2>
                                                                ),
                                                                h3: ({ children }) => (
                                                                    <h3>
                                                                        {renderInlineCitationNode(
                                                                            children,
                                                                            `${msgKey}-h3`,
                                                                            activeCitationNo,
                                                                            focusedCitationNo,
                                                                            handleInlineCitationClick
                                                                        )}
                                                                    </h3>
                                                                ),
                                                            }}
                                                        >
                                                            {msg.content}
                                                        </ReactMarkdown>
                                                    </div>

                                                    {msg.metadata && <ChatChartRenderer metadata={msg.metadata} />}
                                                </>
                                            ) : (
                                                <Paragraph className="message-text">{msg.content}</Paragraph>
                                            )}
                                        </div>
                                    </div>
                                );
                            }}
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
                            rowKey={(ref) => String(ref.citation_number || 0)}
                            renderItem={(ref) => {
                                const citationNo = ref.citation_number || 1;
                                const active = activeCitationNo === citationNo || focusedCitationNo === citationNo;

                                return (
                                    <List.Item
                                        className={`reference-item ${active ? 'active' : ''}`}
                                        id={`ref-card-${citationNo}`}
                                        onClick={() => {
                                            setActiveCitationNo(citationNo);
                                            setPreviewRef(ref);
                                            setPreviewOpen(true);
                                        }}
                                    >
                                        <div>
                                            <div className="ref-top-row">
                                                <Text strong>[{citationNo}]</Text>
                                                <Button
                                                    type="text"
                                                    size="small"
                                                    icon={<AimOutlined />}
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        setActiveCitationNo(citationNo);
                                                        scrollToCitationMarker(ref);
                                                    }}
                                                >
                                                    定位
                                                </Button>
                                            </div>
                                            <Text className="ref-title">{ref.paper_title || '未知文献'}</Text>
                                            {ref.page_number && (
                                                <Text type="secondary"> (第{ref.page_number}页)</Text>
                                            )}

                                            <div className="ref-score-row">
                                                <Tag color={active ? 'geekblue' : 'blue'} style={{ marginInlineEnd: 6 }}>
                                                    相关度 {Math.round((ref.display_score || 0) * 100)}%
                                                </Tag>
                                                <Tag>原始分 {Number(ref.raw_score ?? ref.score ?? 0).toFixed(3)}</Tag>
                                            </div>

                                            {ref.citation_context && (
                                                <div className="citation-context-box">
                                                    <Text type="secondary" style={{ fontSize: 12 }}>引用范围</Text>
                                                    <div className="citation-context-text">
                                                        {highlightText(ref.citation_context, queryKeywords)}
                                                    </div>
                                                </div>
                                            )}

                                            <Paragraph ellipsis={{ rows: 3 }} className="ref-text">
                                                {highlightText(ref.text, queryKeywords)}
                                            </Paragraph>
                                        </div>
                                    </List.Item>
                                );
                            }}
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

            <Modal
                title={previewRef?.paper_title || '原始文献片段'}
                open={previewOpen}
                onCancel={() => setPreviewOpen(false)}
                footer={null}
                width={760}
            >
                {previewRef && (
                    <div className="source-preview-modal">
                        <div className="source-preview-meta">
                            <Tag color="blue">引用 #{previewRef.citation_number || '-'}</Tag>
                            {previewRef.page_number && <Tag>第 {previewRef.page_number} 页</Tag>}
                            <Tag>相关度 {Math.round((previewRef.display_score || 0) * 100)}%</Tag>
                            <Tag>原始分 {Number(previewRef.raw_score ?? previewRef.score ?? 0).toFixed(3)}</Tag>
                        </div>

                        {previewRef.citation_context && (
                            <div className="source-preview-block">
                                <Text type="secondary">在回答中的命中位置</Text>
                                <div className="source-preview-hit">
                                    {highlightText(previewRef.citation_context, queryKeywords)}
                                </div>
                            </div>
                        )}

                        <div className="source-preview-block">
                            <Text type="secondary">文献原始内容</Text>
                            <div className="source-preview-origin">
                                {highlightText(previewRef.text || '', queryKeywords)}
                            </div>
                        </div>
                    </div>
                )}
            </Modal>
        </div>
    );
};

export default ChatPage;
