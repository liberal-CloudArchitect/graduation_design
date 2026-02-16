// 写作辅助页面
import React, { useState } from 'react';
import {
    Row, Col, Card, Input, Button, Select, Tabs, Space,
    Typography, Spin, message, List, Tag, Divider
} from 'antd';
import {
    FileTextOutlined, EditOutlined, HighlightOutlined,
    BookOutlined, CopyOutlined
} from '@ant-design/icons';
import { writingApi } from '../../../services/writing';
import ReactMarkdown from 'react-markdown';

const { TextArea } = Input;
const { Text, Paragraph } = Typography;

interface Props {
    projectId: number;
}

const WritingAssistant: React.FC<Props> = ({ projectId }) => {
    // Outline state
    const [outlineTopic, setOutlineTopic] = useState('');
    const [outlineStyle, setOutlineStyle] = useState('standard');
    const [outlineResult, setOutlineResult] = useState('');
    const [outlineLoading, setOutlineLoading] = useState(false);

    // Review state
    const [reviewTopic, setReviewTopic] = useState('');
    const [reviewMaxWords, setReviewMaxWords] = useState(800);
    const [reviewResult, setReviewResult] = useState('');
    const [reviewLoading, setReviewLoading] = useState(false);

    // Polish state
    const [polishText, setPolishText] = useState('');
    const [polishStyle, setPolishStyle] = useState('academic');
    const [polishResult, setPolishResult] = useState<{ polished: string; changes: string[] } | null>(null);
    const [polishLoading, setPolishLoading] = useState(false);

    // Citation state
    const [citationText, setCitationText] = useState('');
    const [citationResults, setCitationResults] = useState<any[]>([]);
    const [citationLoading, setCitationLoading] = useState(false);

    const handleGenerateOutline = async () => {
        if (!outlineTopic.trim()) {
            message.warning('请输入研究主题');
            return;
        }
        setOutlineLoading(true);
        try {
            const { data } = await writingApi.generateOutline({
                topic: outlineTopic,
                project_id: projectId,
                style: outlineStyle as any,
            });
            setOutlineResult(data.outline);
        } catch (error) {
            message.error('大纲生成失败');
        } finally {
            setOutlineLoading(false);
        }
    };

    const handleGenerateReview = async () => {
        if (!reviewTopic.trim()) {
            message.warning('请输入研究主题');
            return;
        }
        setReviewLoading(true);
        try {
            const { data } = await writingApi.generateReview({
                topic: reviewTopic,
                project_id: projectId,
                max_words: reviewMaxWords,
            });
            setReviewResult(data.review);
        } catch (error) {
            message.error('综述生成失败');
        } finally {
            setReviewLoading(false);
        }
    };

    const handlePolish = async () => {
        if (!polishText.trim()) {
            message.warning('请输入需要润色的文本');
            return;
        }
        setPolishLoading(true);
        try {
            const { data } = await writingApi.polishText({
                text: polishText,
                style: polishStyle as any,
            });
            setPolishResult({ polished: data.polished, changes: data.changes || [] });
        } catch (error) {
            message.error('润色失败');
        } finally {
            setPolishLoading(false);
        }
    };

    const handleSuggestCitations = async () => {
        if (!citationText.trim()) {
            message.warning('请输入文本内容');
            return;
        }
        setCitationLoading(true);
        try {
            const { data } = await writingApi.suggestCitations({
                text: citationText,
                project_id: projectId,
            });
            setCitationResults(data.suggestions || []);
        } catch (error) {
            message.error('引用建议获取失败');
        } finally {
            setCitationLoading(false);
        }
    };

    const copyToClipboard = (text: string) => {
        navigator.clipboard.writeText(text);
        message.success('已复制到剪贴板');
    };

    const tabItems = [
        {
            key: 'outline',
            label: <span><FileTextOutlined /> 大纲生成</span>,
            children: (
                <Row gutter={[16, 16]}>
                    <Col xs={24} lg={10}>
                        <Card title="配置">
                            <Space direction="vertical" style={{ width: '100%' }}>
                                <div>
                                    <Text strong>研究主题</Text>
                                    <TextArea
                                        rows={3}
                                        placeholder="例如：基于深度学习的文本分类方法研究"
                                        value={outlineTopic}
                                        onChange={(e) => setOutlineTopic(e.target.value)}
                                        style={{ marginTop: 8 }}
                                    />
                                </div>
                                <div>
                                    <Text strong>论文风格</Text>
                                    <Select
                                        value={outlineStyle}
                                        onChange={setOutlineStyle}
                                        style={{ width: '100%', marginTop: 8 }}
                                        options={[
                                            { value: 'standard', label: '标准学术论文' },
                                            { value: 'conference', label: '会议论文' },
                                            { value: 'journal', label: '期刊论文' },
                                        ]}
                                    />
                                </div>
                                <Button
                                    type="primary"
                                    onClick={handleGenerateOutline}
                                    loading={outlineLoading}
                                    block
                                >
                                    生成大纲
                                </Button>
                            </Space>
                        </Card>
                    </Col>
                    <Col xs={24} lg={14}>
                        <Card
                            title="生成结果"
                            extra={outlineResult && (
                                <Button
                                    icon={<CopyOutlined />}
                                    onClick={() => copyToClipboard(outlineResult)}
                                    size="small"
                                >
                                    复制
                                </Button>
                            )}
                        >
                            {outlineLoading ? (
                                <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                            ) : outlineResult ? (
                                <div style={{ maxHeight: 500, overflow: 'auto' }}>
                                    <ReactMarkdown>{outlineResult}</ReactMarkdown>
                                </div>
                            ) : (
                                <Text type="secondary">输入研究主题后点击生成</Text>
                            )}
                        </Card>
                    </Col>
                </Row>
            ),
        },
        {
            key: 'review',
            label: <span><BookOutlined /> 文献综述</span>,
            children: (
                <Row gutter={[16, 16]}>
                    <Col xs={24} lg={10}>
                        <Card title="配置">
                            <Space direction="vertical" style={{ width: '100%' }}>
                                <div>
                                    <Text strong>研究主题</Text>
                                    <TextArea
                                        rows={3}
                                        placeholder="例如：自然语言处理中的预训练模型"
                                        value={reviewTopic}
                                        onChange={(e) => setReviewTopic(e.target.value)}
                                        style={{ marginTop: 8 }}
                                    />
                                </div>
                                <div>
                                    <Text strong>最大字数: {reviewMaxWords}</Text>
                                    <Input
                                        type="number"
                                        value={reviewMaxWords}
                                        onChange={(e) => setReviewMaxWords(Number(e.target.value))}
                                        min={200}
                                        max={3000}
                                        style={{ marginTop: 8 }}
                                    />
                                </div>
                                <Button
                                    type="primary"
                                    onClick={handleGenerateReview}
                                    loading={reviewLoading}
                                    block
                                >
                                    生成综述
                                </Button>
                            </Space>
                        </Card>
                    </Col>
                    <Col xs={24} lg={14}>
                        <Card
                            title="文献综述"
                            extra={reviewResult && (
                                <Button
                                    icon={<CopyOutlined />}
                                    onClick={() => copyToClipboard(reviewResult)}
                                    size="small"
                                >
                                    复制
                                </Button>
                            )}
                        >
                            {reviewLoading ? (
                                <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                            ) : reviewResult ? (
                                <div style={{ maxHeight: 500, overflow: 'auto' }}>
                                    <ReactMarkdown>{reviewResult}</ReactMarkdown>
                                </div>
                            ) : (
                                <Text type="secondary">输入主题后点击生成</Text>
                            )}
                        </Card>
                    </Col>
                </Row>
            ),
        },
        {
            key: 'polish',
            label: <span><HighlightOutlined /> 段落润色</span>,
            children: (
                <Row gutter={[16, 16]}>
                    <Col xs={24} lg={12}>
                        <Card title="原文">
                            <TextArea
                                rows={10}
                                placeholder="粘贴需要润色的学术文本..."
                                value={polishText}
                                onChange={(e) => setPolishText(e.target.value)}
                            />
                            <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
                                <Select
                                    value={polishStyle}
                                    onChange={setPolishStyle}
                                    style={{ width: 150 }}
                                    options={[
                                        { value: 'academic', label: '学术风格' },
                                        { value: 'formal', label: '正式文体' },
                                        { value: 'concise', label: '简洁精练' },
                                    ]}
                                />
                                <Button
                                    type="primary"
                                    onClick={handlePolish}
                                    loading={polishLoading}
                                >
                                    开始润色
                                </Button>
                            </div>
                        </Card>
                    </Col>
                    <Col xs={24} lg={12}>
                        <Card
                            title="润色结果"
                            extra={polishResult && (
                                <Button
                                    icon={<CopyOutlined />}
                                    onClick={() => copyToClipboard(polishResult.polished)}
                                    size="small"
                                >
                                    复制
                                </Button>
                            )}
                        >
                            {polishLoading ? (
                                <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                            ) : polishResult ? (
                                <div>
                                    <Paragraph>{polishResult.polished}</Paragraph>
                                    {polishResult.changes.length > 0 && (
                                        <>
                                            <Divider />
                                            <Text strong>修改说明：</Text>
                                            <List
                                                size="small"
                                                dataSource={polishResult.changes}
                                                renderItem={(item) => (
                                                    <List.Item>
                                                        <Text type="secondary">{item}</Text>
                                                    </List.Item>
                                                )}
                                            />
                                        </>
                                    )}
                                </div>
                            ) : (
                                <Text type="secondary">输入文本后点击润色</Text>
                            )}
                        </Card>
                    </Col>
                </Row>
            ),
        },
        {
            key: 'citations',
            label: <span><EditOutlined /> 引用建议</span>,
            children: (
                <Row gutter={[16, 16]}>
                    <Col xs={24} lg={10}>
                        <Card title="输入文本">
                            <TextArea
                                rows={6}
                                placeholder="输入您正在撰写的段落，系统将推荐合适的引用文献..."
                                value={citationText}
                                onChange={(e) => setCitationText(e.target.value)}
                            />
                            <Button
                                type="primary"
                                onClick={handleSuggestCitations}
                                loading={citationLoading}
                                style={{ marginTop: 16 }}
                                block
                            >
                                获取引用建议
                            </Button>
                        </Card>
                    </Col>
                    <Col xs={24} lg={14}>
                        <Card title="推荐引用">
                            {citationLoading ? (
                                <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                            ) : citationResults.length > 0 ? (
                                <List
                                    dataSource={citationResults}
                                    renderItem={(item) => (
                                        <List.Item>
                                            <List.Item.Meta
                                                title={
                                                    <Space>
                                                        <Tag color="blue">{item.citation_format}</Tag>
                                                        <Text>{item.title}</Text>
                                                    </Space>
                                                }
                                                description={item.text_snippet}
                                            />
                                        </List.Item>
                                    )}
                                />
                            ) : (
                                <Text type="secondary">输入文本后获取引用建议</Text>
                            )}
                        </Card>
                    </Col>
                </Row>
            ),
        },
    ];

    return <Tabs items={tabItems} />;
};

export default WritingAssistant;
