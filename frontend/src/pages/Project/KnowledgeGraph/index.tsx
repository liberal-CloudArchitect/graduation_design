// 知识图谱页面 - 双模式: 引用网络(Citation Network) + 内容知识图谱(Content KG)
import React, { useEffect, useRef, useState } from 'react';
import { Card, Input, Button, Spin, Empty, Space, Tag, message, Tooltip, Segmented } from 'antd';
import { SearchOutlined, ShareAltOutlined, BookOutlined } from '@ant-design/icons';
import { externalApi } from '../../../services/external';
import { authAxios } from '../../../services/axios';

interface Props {
    projectId: number;
}

interface GraphNode {
    id: string;
    title?: string;
    type: string;
    year?: number;
    citation_count?: number;
}

interface GraphEdge {
    source: string;
    target: string;
    type?: string;
    relation?: string;
}

const KnowledgeGraph: React.FC<Props> = ({ projectId }) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const graphRef = useRef<any>(null);
    const [loading, setLoading] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
    const [graphData, setGraphData] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null);
    const [mode, setMode] = useState<string>('content'); // 'citation' or 'content'

    // Auto-load content KG when switching to content mode
    useEffect(() => {
        if (mode === 'content') {
            loadContentKG();
        }
    }, [mode, projectId]);

    const loadCitationNetwork = async (paperId: string) => {
        setLoading(true);
        try {
            const { data } = await externalApi.getCitations(paperId, 1, 15);
            setGraphData(data);
            renderGraph(data, 'citation');
        } catch (error) {
            message.error('加载引用网络失败');
        } finally {
            setLoading(false);
        }
    };

    const loadContentKG = async () => {
        setLoading(true);
        try {
            // Use the dedicated knowledge-graph endpoint
            const { data: kgData } = await authAxios.post('/agent/knowledge-graph', {
                project_id: projectId,
                max_entities: 30,
            });

            if (kgData.nodes && kgData.nodes.length > 0) {
                const formattedData = {
                    nodes: kgData.nodes.map((n: any) => ({
                        id: n.id,
                        title: n.id,
                        type: n.type || 'entity',
                    })),
                    edges: kgData.edges.map((e: any) => ({
                        source: e.source,
                        target: e.target,
                        type: e.relation || 'related',
                        relation: e.relation,
                    })),
                };
                setGraphData(formattedData);
                renderGraph(formattedData, 'content');
            } else {
                setGraphData({ nodes: [], edges: [] });
                message.info(kgData.message || '未发现实体关系，请先上传文献');
            }
        } catch (error) {
            console.error('Content KG failed:', error);
            message.error('知识图谱构建失败');
            setGraphData({ nodes: [], edges: [] });
        } finally {
            setLoading(false);
        }
    };

    const handleSearch = async () => {
        if (!searchQuery.trim()) {
            message.warning('请输入论文ID或搜索关键词');
            return;
        }
        setLoading(true);
        try {
            const { data } = await externalApi.search(searchQuery, 1);
            const results = data.results || [];
            if (results.length > 0) {
                const paperId = results[0].paper_id;
                if (paperId) {
                    await loadCitationNetwork(paperId);
                } else {
                    message.info('未找到论文ID');
                }
            } else {
                message.info('未找到相关论文');
            }
        } catch (error) {
            message.error('搜索失败');
        } finally {
            setLoading(false);
        }
    };

    const renderGraph = async (data: { nodes: GraphNode[]; edges: GraphEdge[] }, graphMode: string) => {
        if (!containerRef.current || !data.nodes.length) return;

        if (graphRef.current) {
            graphRef.current.destroy();
        }

        try {
            const G6 = await import('@antv/g6');

            // Node color mapping based on mode
            const citationColors: Record<string, string> = {
                center: '#1890ff',
                citing: '#52c41a',
                referenced: '#faad14',
                cited: '#13c2c2',
            };

            const contentColors: Record<string, string> = {
                entity: '#667eea',
                concept: '#764ba2',
                method: '#43e97b',
                dataset: '#4facfe',
                person: '#fa709a',
                technology: '#f093fb',
                model: '#f5576c',
                metric: '#fee140',
                task: '#30cfd0',
            };

            const colorMap = graphMode === 'citation' ? citationColors : contentColors;

            const nodes = data.nodes.map((n) => ({
                id: n.id,
                data: {
                    label: (n.title || n.id).length > 20
                        ? (n.title || n.id).substring(0, 20) + '...'
                        : (n.title || n.id),
                    fullTitle: n.title || n.id,
                    year: n.year,
                    citationCount: n.citation_count,
                    nodeType: n.type,
                },
            }));

            const edges = data.edges.map((e, i) => ({
                id: `edge-${i}`,
                source: e.source,
                target: e.target,
                data: {
                    label: e.relation || '',
                },
            }));

            const nodeIds = new Set(nodes.map(n => n.id));
            const validEdges = edges.filter(e => nodeIds.has(e.source) && nodeIds.has(e.target));

            const graph = new G6.Graph({
                container: containerRef.current,
                width: containerRef.current.offsetWidth,
                height: 500,
                data: { nodes, edges: validEdges },
                layout: {
                    type: 'force',
                    preventOverlap: true,
                    nodeStrength: -200,
                    edgeStrength: 0.1,
                },
                node: {
                    style: {
                        size: 30,
                        labelText: (d: any) => d.data?.label || '',
                        labelFontSize: 10,
                        fill: (d: any) => colorMap[d.data?.nodeType] || '#999',
                    },
                },
                edge: {
                    style: {
                        stroke: '#ccc',
                        endArrow: true,
                        labelText: graphMode === 'content' ? (d: any) => d.data?.label || '' : undefined,
                        labelFontSize: 9,
                        labelFill: '#999',
                    },
                },
                behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element'],
            });

            graph.render();
            graphRef.current = graph;

        } catch (error) {
            console.error('G6 render failed:', error);
            message.error('图谱渲染失败');
        }
    };

    useEffect(() => {
        return () => {
            if (graphRef.current) {
                graphRef.current.destroy();
            }
        };
    }, []);

    // Legend tags based on mode
    const citationLegend = (
        <Space>
            <Tag color="blue">中心论文</Tag>
            <Tag color="green">引用论文</Tag>
            <Tag color="orange">参考文献</Tag>
        </Space>
    );

    const contentLegend = (
        <Space wrap>
            <Tag color="#667eea">实体</Tag>
            <Tag color="#764ba2">概念</Tag>
            <Tag color="#43e97b">方法</Tag>
            <Tag color="#4facfe">数据集</Tag>
            <Tag color="#fa709a">人物</Tag>
            <Tag color="#f093fb">技术</Tag>
        </Space>
    );

    return (
        <div>
            <Card>
                <Space direction="vertical" style={{ width: '100%' }}>
                    <Segmented
                        options={[
                            { label: '内容知识图谱', value: 'content', icon: <ShareAltOutlined /> },
                            { label: '引用网络', value: 'citation', icon: <BookOutlined /> },
                        ]}
                        value={mode}
                        onChange={(v) => {
                            setMode(v as string);
                            setGraphData(null);
                            setSelectedNode(null);
                        }}
                    />

                    {mode === 'citation' && (
                        <Space>
                            <Input
                                placeholder="输入论文关键词搜索引用网络..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                onPressEnter={handleSearch}
                                style={{ width: 400 }}
                                prefix={<SearchOutlined />}
                            />
                            <Button type="primary" onClick={handleSearch} loading={loading}>
                                搜索
                            </Button>
                        </Space>
                    )}

                    {mode === 'content' && (
                        <Space>
                            <Button type="primary" onClick={loadContentKG} loading={loading}>
                                重新构建
                            </Button>
                        </Space>
                    )}

                    {mode === 'citation' ? citationLegend : contentLegend}
                </Space>
            </Card>

            <Card style={{ marginTop: 16 }}>
                {loading ? (
                    <div style={{ textAlign: 'center', padding: 80 }}>
                        <Spin size="large" tip={mode === 'content' ? '正在从文献中提取实体关系...' : '加载引用网络中...'} />
                    </div>
                ) : graphData && graphData.nodes.length > 0 ? (
                    <div>
                        <div style={{ marginBottom: 8 }}>
                            <Tag>{graphData.nodes.length} 个节点</Tag>
                            <Tag>{graphData.edges.length} 条边</Tag>
                        </div>
                        <div ref={containerRef} style={{ width: '100%', height: 500 }} />
                    </div>
                ) : (
                    <Empty description={
                        mode === 'content'
                            ? '请先上传文献，然后系统将自动提取实体关系'
                            : '请搜索论文以查看引用网络'
                    } />
                )}
            </Card>

            {selectedNode && (
                <Card title="节点详情" style={{ marginTop: 16 }}>
                    <p><strong>名称:</strong> {selectedNode.title || selectedNode.id}</p>
                    <p><strong>类型:</strong> {selectedNode.type}</p>
                    {selectedNode.year && <p><strong>年份:</strong> {selectedNode.year}</p>}
                    {selectedNode.citation_count != null && <p><strong>引用数:</strong> {selectedNode.citation_count}</p>}
                </Card>
            )}
        </div>
    );
};

export default KnowledgeGraph;
