// 记忆系统仪表板 - 展示 DynamicMemory / ReconstructiveMemory / Forgetting / CrossMemory
import React, { useEffect, useState } from 'react';
import {
    Tabs, Card, Statistic, Row, Col, Table, Tag, Button, Input, Spin,
    Empty, Progress, Space, Typography, Popconfirm, message
} from 'antd';
import {
    DatabaseOutlined, BranchesOutlined, ExperimentOutlined,
    DeleteOutlined, ThunderboltOutlined, SearchOutlined,
    ClockCircleOutlined, SafetyOutlined, WarningOutlined
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { memoryApi } from '../../../services/memory';
import type { MemoryItem, MemoryStats, DecayPreviewItem, ReconstructResult } from '../../../services/memory';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

interface Props {
    projectId: number;
}

// ==================== Overview Tab ====================
const OverviewTab: React.FC = () => {
    const [stats, setStats] = useState<MemoryStats | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => { loadStats(); }, []);

    const loadStats = async () => {
        setLoading(true);
        try {
            const { data } = await memoryApi.getStats();
            setStats(data);
        } catch { /* ignore */ } finally { setLoading(false); }
    };

    if (loading) return <Spin style={{ display: 'block', textAlign: 'center', padding: 60 }} />;
    if (!stats) return <Empty description="无法获取记忆统计" />;

    const engine = stats.memory_engine;
    const typeData = Object.entries(engine.type_breakdown || {}).map(([name, value]) => ({ name, value }));
    const agentData = Object.entries(engine.agent_breakdown || {}).map(([name, value]) => ({ name, value }));

    const pieOption = (data: { name: string; value: number }[], title: string) => ({
        title: { text: title, left: 'center', textStyle: { fontSize: 14 } },
        tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
        color: ['#667eea', '#764ba2', '#f093fb', '#43e97b', '#fa709a', '#4facfe'],
        series: [{
            type: 'pie',
            radius: ['40%', '70%'],
            center: ['50%', '55%'],
            data,
            label: { fontSize: 11 },
        }],
    });

    const crossAgents = stats.cross_memory.agents || {};
    const crossNodes = Object.keys(crossAgents);
    const crossGraphOption = crossNodes.length > 0 ? {
        title: { text: 'Agent 记忆共享网络', left: 'center', textStyle: { fontSize: 14 } },
        tooltip: {},
        series: [{
            type: 'graph',
            layout: 'circular',
            symbolSize: 50,
            roam: true,
            label: { show: true, fontSize: 10 },
            data: crossNodes.map(name => ({
                name: name.replace('_agent', ''),
                value: (crossAgents[name]?.shared || 0) + (crossAgents[name]?.received || 0),
            })),
            links: crossNodes.flatMap((s, i) =>
                crossNodes.slice(i + 1).map(t => ({
                    source: s.replace('_agent', ''),
                    target: t.replace('_agent', ''),
                }))
            ),
            lineStyle: { opacity: 0.5, width: 2, curveness: 0.2 },
        }],
    } : null;

    return (
        <div>
            <Row gutter={[16, 16]}>
                <Col xs={24} sm={8}>
                    <Card>
                        <Statistic
                            title="记忆总量"
                            value={engine.row_count || 0}
                            prefix={<DatabaseOutlined />}
                        />
                        <Tag color={engine.status === 'connected' ? 'green' : 'red'} style={{ marginTop: 8 }}>
                            {engine.status === 'connected' ? 'Milvus 已连接' : '未连接'}
                        </Tag>
                    </Card>
                </Col>
                <Col xs={24} sm={8}>
                    <Card>
                        <Statistic
                            title="注册 Agent 数"
                            value={stats.cross_memory.total_agents || 0}
                            prefix={<BranchesOutlined />}
                        />
                        <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
                            共享记忆: {stats.cross_memory.total_shared_memories || 0} 条
                        </Text>
                    </Card>
                </Col>
                <Col xs={24} sm={8}>
                    <Card>
                        <Statistic
                            title="遗忘衰减率"
                            value={stats.forgetting.decay_rate ?? '-'}
                            suffix="/ day"
                            prefix={<ClockCircleOutlined />}
                        />
                        <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
                            保护期: {stats.forgetting.protection_period_hours ?? '-'}h
                        </Text>
                    </Card>
                </Col>
            </Row>

            <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
                <Col xs={24} md={12}>
                    <Card title="按记忆类型分布" size="small">
                        {typeData.length > 0
                            ? <ReactECharts option={pieOption(typeData, '')} style={{ height: 260 }} />
                            : <Empty description="暂无数据" />}
                    </Card>
                </Col>
                <Col xs={24} md={12}>
                    <Card title="按来源 Agent 分布" size="small">
                        {agentData.length > 0
                            ? <ReactECharts option={pieOption(agentData, '')} style={{ height: 260 }} />
                            : <Empty description="暂无数据" />}
                    </Card>
                </Col>
            </Row>

            {crossGraphOption && (
                <Card title="跨Agent记忆网络" size="small" style={{ marginTop: 16 }}>
                    <ReactECharts option={crossGraphOption} style={{ height: 320 }} />
                </Card>
            )}
        </div>
    );
};

// ==================== Memory List Tab ====================
const MemoryListTab: React.FC<{ projectId: number }> = ({ projectId }) => {
    const [items, setItems] = useState<MemoryItem[]>([]);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [loading, setLoading] = useState(true);

    useEffect(() => { loadList(); }, [page, projectId]);

    const loadList = async () => {
        setLoading(true);
        try {
            const { data } = await memoryApi.list({ project_id: projectId, page, page_size: 15 });
            setItems(data.items);
            setTotal(data.total);
        } catch { /* ignore */ } finally { setLoading(false); }
    };

    const handleDelete = async (id: string) => {
        try {
            await memoryApi.delete(id);
            message.success('已删除');
            loadList();
        } catch { message.error('删除失败'); }
    };

    const typeColors: Record<string, string> = {
        dynamic: 'blue', reconstructive: 'purple', cross_memory: 'green',
    };
    const agentColors: Record<string, string> = {
        retriever_agent: 'blue', analyzer_agent: 'green',
        writer_agent: 'purple', search_agent: 'orange', qa_agent: 'cyan',
    };

    const columns = [
        {
            title: '内容',
            dataIndex: 'content',
            key: 'content',
            render: (text: string) => (
                <Paragraph ellipsis={{ rows: 2, expandable: true, symbol: '展开' }} style={{ marginBottom: 0, fontSize: 13 }}>
                    {text}
                </Paragraph>
            ),
        },
        {
            title: '类型',
            dataIndex: 'memory_type',
            key: 'memory_type',
            width: 110,
            render: (t: string) => <Tag color={typeColors[t] || 'default'}>{t}</Tag>,
        },
        {
            title: '来源',
            dataIndex: 'agent_source',
            key: 'agent_source',
            width: 130,
            render: (a: string) => <Tag color={agentColors[a] || 'default'}>{a.replace('_agent', '')}</Tag>,
        },
        {
            title: '重要性',
            dataIndex: 'importance',
            key: 'importance',
            width: 100,
            render: (v: number) => <Progress percent={Math.round(v * 100)} size="small" strokeColor={v > 0.7 ? '#52c41a' : v > 0.3 ? '#faad14' : '#ff4d4f'} />,
        },
        {
            title: '时间',
            dataIndex: 'timestamp',
            key: 'timestamp',
            width: 140,
            render: (t: number) => new Date(t * 1000).toLocaleString(),
        },
        {
            title: '操作',
            key: 'actions',
            width: 80,
            render: (_: any, record: MemoryItem) => (
                <Popconfirm title="确定删除？" onConfirm={() => handleDelete(record.id)}>
                    <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
            ),
        },
    ];

    return (
        <Table
            columns={columns}
            dataSource={items}
            rowKey="id"
            loading={loading}
            pagination={{ current: page, total, pageSize: 15, onChange: setPage, showTotal: t => `共 ${t} 条` }}
            size="small"
        />
    );
};

// ==================== Reconstructive Demo Tab ====================
const ReconstructiveTab: React.FC<{ projectId: number }> = ({ projectId }) => {
    const [query, setQuery] = useState('');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<ReconstructResult | null>(null);

    const handleReconstruct = async () => {
        if (!query.trim()) { message.warning('请输入查询'); return; }
        setLoading(true);
        setResult(null);
        try {
            const { data } = await memoryApi.reconstruct({ query, project_id: projectId });
            setResult(data);
        } catch {
            message.error('重构失败');
        } finally { setLoading(false); }
    };

    const stageCard = (title: string, icon: React.ReactNode, color: string, timeMs: number, children: React.ReactNode) => (
        <Card size="small" style={{ borderLeft: `3px solid ${color}`, marginBottom: 12 }}>
            <Space style={{ marginBottom: 8 }}>
                {icon}
                <Text strong>{title}</Text>
                <Tag color="default">{timeMs.toFixed(0)}ms</Tag>
            </Space>
            {children}
        </Card>
    );

    return (
        <div>
            <Card size="small" style={{ marginBottom: 16 }}>
                <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
                    输入一个问题或线索，系统将演示完整的 Trace → Expand → Reconstruct 记忆重构流程
                </Text>
                <Space.Compact style={{ width: '100%' }}>
                    <TextArea
                        value={query}
                        onChange={e => setQuery(e.target.value)}
                        placeholder="例如：上次我们讨论的Transformer变体有哪些？"
                        autoSize={{ minRows: 1, maxRows: 3 }}
                        style={{ flex: 1 }}
                        onPressEnter={e => { if (!e.shiftKey) { e.preventDefault(); handleReconstruct(); } }}
                    />
                    <Button type="primary" icon={<ExperimentOutlined />} onClick={handleReconstruct} loading={loading}>
                        重构
                    </Button>
                </Space.Compact>
            </Card>

            {loading && <Spin style={{ display: 'block', textAlign: 'center', padding: 40 }} tip="正在重构记忆..." />}

            {result && (
                <div>
                    {/* Step 1: Cue Extraction */}
                    {stageCard('1. 线索提取 (Cue Extraction)', <SearchOutlined />, '#667eea', result.timing.cue_extraction_ms, (
                        <div>
                            {result.cue.topic && <Tag color="blue">主题: {result.cue.topic}</Tag>}
                            {result.cue.intent && <Tag color="green">意图: {result.cue.intent}</Tag>}
                            {(result.cue.entities || []).map((e: string, i: number) => <Tag key={i} color="purple">实体: {e}</Tag>)}
                        </div>
                    ))}

                    {/* Step 2: Trace */}
                    {stageCard('2. 记忆追踪 (Trace)', <DatabaseOutlined />, '#52c41a', result.timing.trace_ms, (
                        <div>
                            <Text type="secondary">检索到 {result.trace_seeds.length} 条种子记忆</Text>
                            {result.trace_seeds.map((m, i) => (
                                <Card key={i} size="small" style={{ marginTop: 8, background: '#f6ffed' }}>
                                    <Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 4, fontSize: 12 }}>{m.content}</Paragraph>
                                    <Space size={4}>
                                        <Tag color="blue" style={{ fontSize: 11 }}>{m.memory_type}</Tag>
                                        <Tag style={{ fontSize: 11 }}>重要性: {m.importance}</Tag>
                                        <Text type="secondary" style={{ fontSize: 11 }}>{new Date(m.timestamp * 1000).toLocaleString()}</Text>
                                    </Space>
                                </Card>
                            ))}
                            {result.trace_seeds.length === 0 && <Empty description="未检索到种子记忆" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
                        </div>
                    ))}

                    {/* Step 3: Expand */}
                    {stageCard('3. 时序扩展 (Temporal Expansion)', <BranchesOutlined />, '#faad14', result.timing.expand_ms, (
                        <div>
                            <Text type="secondary">
                                {result.trace_seeds.length} → {result.expanded.length} 条片段（通过时间窗口扩展）
                            </Text>
                            {result.expanded.filter(m => !result.trace_seeds.find(s => s.id === m.id)).map((m, i) => (
                                <Card key={i} size="small" style={{ marginTop: 8, background: '#fff7e6' }}>
                                    <Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 4, fontSize: 12 }}>{m.content}</Paragraph>
                                    <Tag color="orange" style={{ fontSize: 11 }}>时序邻居</Tag>
                                    <Text type="secondary" style={{ fontSize: 11 }}> {new Date(m.timestamp * 1000).toLocaleString()}</Text>
                                </Card>
                            ))}
                        </div>
                    ))}

                    {/* Step 4: Reconstruct */}
                    {stageCard('4. 生成式重构 (Reconstruct)', <ThunderboltOutlined />, '#f5576c', result.timing.reconstruct_ms, (
                        <div>
                            <Space style={{ marginBottom: 8 }}>
                                <Tag color={result.reconstruction.is_reconstructed ? 'green' : 'orange'}>
                                    {result.reconstruction.is_reconstructed ? 'LLM 重构' : '拼接重构'}
                                </Tag>
                                <Text type="secondary">
                                    置信度: {(result.reconstruction.confidence * 100).toFixed(0)}% | 片段数: {result.reconstruction.fragment_count}
                                </Text>
                            </Space>
                            <Card size="small" style={{ background: '#f9f0ff' }}>
                                <Paragraph style={{ marginBottom: 0 }}>{result.reconstruction.content}</Paragraph>
                            </Card>
                        </div>
                    ))}

                    {/* Timing Summary */}
                    <Card size="small" style={{ marginTop: 8 }}>
                        <Space>
                            <Text strong>总耗时: {result.timing.total_ms.toFixed(0)}ms</Text>
                            <Tag>线索 {result.timing.cue_extraction_ms.toFixed(0)}ms</Tag>
                            <Tag>追踪 {result.timing.trace_ms.toFixed(0)}ms</Tag>
                            <Tag>扩展 {result.timing.expand_ms.toFixed(0)}ms</Tag>
                            <Tag>重构 {result.timing.reconstruct_ms.toFixed(0)}ms</Tag>
                        </Space>
                    </Card>
                </div>
            )}
        </div>
    );
};

// ==================== Forgetting Preview Tab ====================
const ForgettingTab: React.FC<{ projectId: number }> = ({ projectId }) => {
    const [previews, setPreviews] = useState<DecayPreviewItem[]>([]);
    const [summary, setSummary] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => { loadPreview(); }, [projectId]);

    const loadPreview = async () => {
        setLoading(true);
        try {
            const { data } = await memoryApi.decayPreview(projectId);
            setPreviews(data.previews);
            setSummary(data.summary);
        } catch { /* ignore */ } finally { setLoading(false); }
    };

    const handleCleanup = async (dryRun: boolean) => {
        try {
            const { data } = await memoryApi.cleanup(projectId, dryRun);
            message.success(data.message);
            if (!dryRun) loadPreview();
        } catch { message.error('清理失败'); }
    };

    const columns = [
        {
            title: '内容预览',
            dataIndex: 'content_preview',
            key: 'content_preview',
            render: (t: string) => <Text style={{ fontSize: 13 }}>{t}</Text>,
        },
        {
            title: '年龄(天)',
            dataIndex: 'age_days',
            key: 'age_days',
            width: 90,
            render: (v: number) => v.toFixed(1),
        },
        {
            title: '访问次数',
            dataIndex: 'access_count',
            key: 'access_count',
            width: 90,
        },
        {
            title: '当前重要性',
            dataIndex: 'current_importance',
            key: 'current_importance',
            width: 110,
            render: (v: number) => <Progress percent={Math.round(v * 100)} size="small" />,
        },
        {
            title: '衰减后',
            dataIndex: 'decayed_importance',
            key: 'decayed_importance',
            width: 110,
            render: (v: number, record: DecayPreviewItem) => (
                <Progress
                    percent={Math.round(v * 100)}
                    size="small"
                    strokeColor={record.is_protected ? '#52c41a' : record.should_forget ? '#ff4d4f' : '#faad14'}
                />
            ),
        },
        {
            title: '状态',
            key: 'status',
            width: 100,
            render: (_: any, record: DecayPreviewItem) => {
                if (record.is_protected) return <Tag icon={<SafetyOutlined />} color="green">受保护</Tag>;
                if (record.should_forget) return <Tag icon={<WarningOutlined />} color="red">待遗忘</Tag>;
                return <Tag icon={<ClockCircleOutlined />} color="orange">衰减中</Tag>;
            },
        },
    ];

    return (
        <div>
            {summary && (
                <Row gutter={16} style={{ marginBottom: 16 }}>
                    <Col span={6}><Card size="small"><Statistic title="总记忆数" value={summary.total} /></Card></Col>
                    <Col span={6}><Card size="small"><Statistic title="受保护" value={summary.protected} valueStyle={{ color: '#52c41a' }} /></Card></Col>
                    <Col span={6}><Card size="small"><Statistic title="衰减中" value={summary.decaying} valueStyle={{ color: '#faad14' }} /></Card></Col>
                    <Col span={6}><Card size="small"><Statistic title="待遗忘" value={summary.to_forget} valueStyle={{ color: '#ff4d4f' }} /></Card></Col>
                </Row>
            )}
            <Space style={{ marginBottom: 12 }}>
                <Button onClick={() => handleCleanup(true)}>模拟清理</Button>
                <Popconfirm title="确定执行清理？将删除所有低重要性记忆" onConfirm={() => handleCleanup(false)}>
                    <Button danger>执行清理</Button>
                </Popconfirm>
                <Button onClick={loadPreview}>刷新</Button>
            </Space>
            <Table
                columns={columns}
                dataSource={previews}
                rowKey="memory_id"
                loading={loading}
                size="small"
                pagination={{ pageSize: 10 }}
            />
        </div>
    );
};

// ==================== Main Component ====================
const MemoryDashboard: React.FC<Props> = ({ projectId }) => {
    const tabItems = [
        {
            key: 'overview',
            label: <span><DatabaseOutlined /> 概览</span>,
            children: <OverviewTab />,
        },
        {
            key: 'list',
            label: <span><DatabaseOutlined /> 记忆列表</span>,
            children: <MemoryListTab projectId={projectId} />,
        },
        {
            key: 'reconstruct',
            label: <span><ExperimentOutlined /> 重构演示</span>,
            children: <ReconstructiveTab projectId={projectId} />,
        },
        {
            key: 'forgetting',
            label: <span><ClockCircleOutlined /> 遗忘预览</span>,
            children: <ForgettingTab projectId={projectId} />,
        },
    ];

    return (
        <Tabs items={tabItems} size="small" />
    );
};

export default MemoryDashboard;
