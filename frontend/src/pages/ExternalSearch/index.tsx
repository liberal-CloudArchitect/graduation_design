// 外部文献搜索页面 - 搜索 Semantic Scholar, ArXiv, OpenAlex, CrossRef
import React, { useState } from 'react';
import {
    Card, Input, Button, Table, Tag, Space, Select, Typography,
    Empty, message, Tooltip, Descriptions, Drawer, InputNumber, Row, Col
} from 'antd';
import {
    SearchOutlined, GlobalOutlined, BookOutlined,
    LinkOutlined, StarOutlined, CalendarOutlined, EyeOutlined
} from '@ant-design/icons';
import { externalApi } from '../../services/external';
import type { ExternalPaper } from '../../types/models';
import './index.css';

const { Title, Text, Paragraph } = Typography;
const { Search } = Input;

const ExternalSearchPage: React.FC = () => {
    const [query, setQuery] = useState('');
    const [results, setResults] = useState<ExternalPaper[]>([]);
    const [loading, setLoading] = useState(false);
    const [total, setTotal] = useState(0);
    const [limit, setLimit] = useState(20);

    // Detail drawer
    const [detailPaper, setDetailPaper] = useState<ExternalPaper | null>(null);
    const [detailDrawerOpen, setDetailDrawerOpen] = useState(false);
    const [detailLoading, setDetailLoading] = useState(false);

    // Recommendations
    const [recommendations, setRecommendations] = useState<ExternalPaper[]>([]);
    const [recLoading, setRecLoading] = useState(false);

    const handleSearch = async (searchQuery?: string) => {
        const q = searchQuery || query;
        if (!q.trim()) {
            message.warning('请输入搜索关键词');
            return;
        }
        setLoading(true);
        try {
            const { data } = await externalApi.search(q, limit);
            setResults(data.results || []);
            setTotal(data.total || data.results?.length || 0);
        } catch (error) {
            message.error('搜索失败，请稍后重试');
        } finally {
            setLoading(false);
        }
    };

    const handleViewDetail = async (paper: ExternalPaper) => {
        setDetailPaper(paper);
        setDetailDrawerOpen(true);
        setRecommendations([]);

        if (paper.paper_id) {
            setDetailLoading(true);
            try {
                const { data } = await externalApi.getPaper(paper.paper_id);
                setDetailPaper({ ...paper, ...data });
            } catch {
                // Keep original data
            } finally {
                setDetailLoading(false);
            }

            // Load recommendations
            setRecLoading(true);
            try {
                const { data } = await externalApi.getRecommendations(paper.paper_id, 5);
                setRecommendations(data.recommendations || []);
            } catch {
                // silently ignore
            } finally {
                setRecLoading(false);
            }
        }
    };

    const columns = [
        {
            title: '标题',
            dataIndex: 'title',
            key: 'title',
            render: (title: string, record: ExternalPaper) => (
                <a onClick={() => handleViewDetail(record)}>
                    {title}
                </a>
            ),
            ellipsis: true,
        },
        {
            title: '作者',
            dataIndex: 'authors',
            key: 'authors',
            width: 200,
            ellipsis: true,
            render: (authors: string[]) =>
                authors?.slice(0, 3).join(', ') + (authors?.length > 3 ? ' 等' : '') || '-',
        },
        {
            title: '年份',
            dataIndex: 'year',
            key: 'year',
            width: 80,
            render: (year: number) => year || '-',
        },
        {
            title: '期刊/会议',
            dataIndex: 'venue',
            key: 'venue',
            width: 180,
            ellipsis: true,
            render: (venue: string) => venue || '-',
        },
        {
            title: '引用数',
            dataIndex: 'citation_count',
            key: 'citation_count',
            width: 90,
            sorter: (a: ExternalPaper, b: ExternalPaper) =>
                (a.citation_count || 0) - (b.citation_count || 0),
            render: (count: number) =>
                count != null ? (
                    <Tag color={count > 100 ? 'red' : count > 20 ? 'orange' : 'default'}>
                        <StarOutlined /> {count}
                    </Tag>
                ) : '-',
        },
        {
            title: '来源',
            dataIndex: 'source',
            key: 'source',
            width: 100,
            render: (source: string) => {
                const colorMap: Record<string, string> = {
                    semantic_scholar: 'blue',
                    arxiv: 'red',
                    openalex: 'green',
                    crossref: 'purple',
                };
                return source ? <Tag color={colorMap[source] || 'default'}>{source}</Tag> : '-';
            },
        },
        {
            title: '操作',
            key: 'actions',
            width: 80,
            render: (_: any, record: ExternalPaper) => (
                <Button
                    type="link"
                    size="small"
                    icon={<EyeOutlined />}
                    onClick={() => handleViewDetail(record)}
                >
                    详情
                </Button>
            ),
        },
    ];

    return (
        <div className="external-search-page">
            <div className="search-header">
                <Title level={3}>
                    <GlobalOutlined /> 学术文献搜索
                </Title>
                <Text type="secondary">
                    跨平台搜索 Semantic Scholar, ArXiv, OpenAlex 等学术数据库
                </Text>
            </div>

            <Card className="search-card">
                <Row gutter={12} align="middle">
                    <Col flex="auto">
                        <Search
                            placeholder="输入论文标题、关键词或作者名..."
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            onSearch={handleSearch}
                            enterButton={
                                <Button type="primary" icon={<SearchOutlined />}>
                                    搜索
                                </Button>
                            }
                            size="large"
                            loading={loading}
                        />
                    </Col>
                    <Col>
                        <Space>
                            <Text type="secondary">数量:</Text>
                            <InputNumber
                                min={5}
                                max={50}
                                value={limit}
                                onChange={(v) => setLimit(v || 20)}
                                style={{ width: 70 }}
                            />
                        </Space>
                    </Col>
                </Row>
            </Card>

            <Card style={{ marginTop: 16 }}>
                {results.length > 0 && (
                    <div style={{ marginBottom: 12 }}>
                        <Text type="secondary">找到 {total} 条结果</Text>
                    </div>
                )}
                <Table
                    columns={columns}
                    dataSource={results}
                    rowKey={(record, index) => record.paper_id || `result-${index}`}
                    loading={loading}
                    pagination={{ pageSize: 20, showSizeChanger: false }}
                    locale={{
                        emptyText: (
                            <Empty
                                image={<BookOutlined style={{ fontSize: 48, color: '#d1d5db' }} />}
                                description="输入关键词开始搜索学术文献"
                            />
                        ),
                    }}
                />
            </Card>

            {/* Paper Detail Drawer */}
            <Drawer
                title="论文详情"
                open={detailDrawerOpen}
                onClose={() => { setDetailDrawerOpen(false); setDetailPaper(null); }}
                width={600}
            >
                {detailPaper && (
                    <div>
                        <Title level={4}>{detailPaper.title}</Title>
                        <Space wrap style={{ marginBottom: 16 }}>
                            {detailPaper.year && (
                                <Tag icon={<CalendarOutlined />}>{detailPaper.year}</Tag>
                            )}
                            {detailPaper.citation_count != null && (
                                <Tag icon={<StarOutlined />} color="orange">
                                    引用 {detailPaper.citation_count}
                                </Tag>
                            )}
                            {detailPaper.source && (
                                <Tag color="blue">{detailPaper.source}</Tag>
                            )}
                        </Space>

                        <Descriptions column={1} size="small" bordered>
                            {detailPaper.authors && (
                                <Descriptions.Item label="作者">
                                    {detailPaper.authors.join(', ')}
                                </Descriptions.Item>
                            )}
                            {detailPaper.venue && (
                                <Descriptions.Item label="期刊/会议">
                                    {detailPaper.venue}
                                </Descriptions.Item>
                            )}
                            {detailPaper.doi && (
                                <Descriptions.Item label="DOI">
                                    <a
                                        href={`https://doi.org/${detailPaper.doi}`}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                    >
                                        <LinkOutlined /> {detailPaper.doi}
                                    </a>
                                </Descriptions.Item>
                            )}
                            {detailPaper.arxiv_id && (
                                <Descriptions.Item label="ArXiv">
                                    <a
                                        href={`https://arxiv.org/abs/${detailPaper.arxiv_id}`}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                    >
                                        <LinkOutlined /> {detailPaper.arxiv_id}
                                    </a>
                                </Descriptions.Item>
                            )}
                            {detailPaper.url && (
                                <Descriptions.Item label="链接">
                                    <a href={detailPaper.url} target="_blank" rel="noopener noreferrer">
                                        <LinkOutlined /> 查看原文
                                    </a>
                                </Descriptions.Item>
                            )}
                        </Descriptions>

                        {detailPaper.abstract && (
                            <Card title="摘要" size="small" style={{ marginTop: 16 }}>
                                <Paragraph style={{ fontSize: 13 }}>
                                    {detailPaper.abstract}
                                </Paragraph>
                            </Card>
                        )}

                        {recommendations.length > 0 && (
                            <Card
                                title="相关推荐论文"
                                size="small"
                                style={{ marginTop: 16 }}
                                loading={recLoading}
                            >
                                {recommendations.map((rec, i) => (
                                    <div key={i} style={{ marginBottom: 12 }}>
                                        <Text strong style={{ fontSize: 13 }}>
                                            {i + 1}. {rec.title}
                                        </Text>
                                        <br />
                                        <Text type="secondary" style={{ fontSize: 12 }}>
                                            {rec.authors?.slice(0, 3).join(', ')}
                                            {rec.year ? ` (${rec.year})` : ''}
                                            {rec.citation_count ? ` · 引用 ${rec.citation_count}` : ''}
                                        </Text>
                                    </div>
                                ))}
                            </Card>
                        )}
                    </div>
                )}
            </Drawer>
        </div>
    );
};

export default ExternalSearchPage;
