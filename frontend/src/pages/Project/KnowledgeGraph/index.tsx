// 知识图谱页面 - 使用 @antv/g6 展示论文引用网络
import React, { useEffect, useRef, useState } from 'react';
import { Card, Input, Button, Spin, Empty, Space, Tag, message, Tooltip } from 'antd';
import { SearchOutlined, ZoomInOutlined, ZoomOutOutlined, AimOutlined } from '@ant-design/icons';
import { externalApi } from '../../../services/external';

interface Props {
    projectId: number;
}

interface GraphNode {
    id: string;
    title: string;
    year?: number;
    citation_count?: number;
    type: string;
}

interface GraphEdge {
    source: string;
    target: string;
    type: string;
}

const KnowledgeGraph: React.FC<Props> = ({ projectId }) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const graphRef = useRef<any>(null);
    const [loading, setLoading] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
    const [graphData, setGraphData] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null);

    const loadCitationNetwork = async (paperId: string) => {
        setLoading(true);
        try {
            const { data } = await externalApi.getCitations(paperId, 1, 15);
            setGraphData(data);
            renderGraph(data);
        } catch (error) {
            message.error('加载引用网络失败');
        } finally {
            setLoading(false);
        }
    };

    const handleSearch = async () => {
        if (!searchQuery.trim()) {
            message.warning('请输入论文ID或搜索关键词');
            return;
        }
        // 先搜索论文获取ID
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

    const renderGraph = async (data: { nodes: GraphNode[]; edges: GraphEdge[] }) => {
        if (!containerRef.current || !data.nodes.length) return;

        // 清除旧图
        if (graphRef.current) {
            graphRef.current.destroy();
        }

        try {
            const G6 = await import('@antv/g6');
            
            // 节点颜色映射
            const typeColors: Record<string, string> = {
                center: '#1890ff',
                citing: '#52c41a',
                referenced: '#faad14',
                cited: '#13c2c2',
            };

            const nodes = data.nodes.map((n, i) => ({
                id: n.id,
                data: {
                    label: n.title.length > 20 ? n.title.substring(0, 20) + '...' : n.title,
                    fullTitle: n.title,
                    year: n.year,
                    citationCount: n.citation_count,
                    nodeType: n.type,
                },
            }));

            const edges = data.edges.map((e, i) => ({
                id: `edge-${i}`,
                source: e.source,
                target: e.target,
            }));

            // 过滤无效边（确保source和target节点存在）
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
                        fill: (d: any) => typeColors[d.data?.nodeType] || '#999',
                    },
                },
                edge: {
                    style: {
                        stroke: '#ccc',
                        endArrow: true,
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

    return (
        <div>
            <Card>
                <Space direction="vertical" style={{ width: '100%' }}>
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

                    <Space>
                        <Tag color="blue">中心论文</Tag>
                        <Tag color="green">引用论文</Tag>
                        <Tag color="orange">参考文献</Tag>
                    </Space>
                </Space>
            </Card>

            <Card style={{ marginTop: 16 }}>
                {loading ? (
                    <div style={{ textAlign: 'center', padding: 80 }}>
                        <Spin size="large" tip="加载引用网络中..." />
                    </div>
                ) : graphData && graphData.nodes.length > 0 ? (
                    <div ref={containerRef} style={{ width: '100%', height: 500 }} />
                ) : (
                    <Empty description="请搜索论文以查看引用网络知识图谱" />
                )}
            </Card>

            {selectedNode && (
                <Card title="论文详情" style={{ marginTop: 16 }}>
                    <p><strong>标题:</strong> {selectedNode.title}</p>
                    <p><strong>年份:</strong> {selectedNode.year || 'N/A'}</p>
                    <p><strong>引用数:</strong> {selectedNode.citation_count || 0}</p>
                </Card>
            )}
        </div>
    );
};

export default KnowledgeGraph;
