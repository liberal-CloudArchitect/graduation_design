// 知识图谱页面 - 双模式: 引用网络(Citation Network) + 内容知识图谱(Content KG)
// 支持 3D (react-force-graph-3d) 和 2D (@antv/g6) 渲染
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Card, Input, Button, Spin, Empty, Space, Tag, message, Segmented } from 'antd';
import {
    SearchOutlined, ShareAltOutlined, BookOutlined,
    AppstoreOutlined, GlobalOutlined,
} from '@ant-design/icons';
import { externalApi } from '../../../services/external';
import { authAxios } from '../../../services/axios';
import * as THREE from 'three';
import SpriteText from 'three-spritetext';

// Lazy import for ForceGraph3D (heavy Three.js dependency)
const ForceGraph3D = React.lazy(() => import('react-force-graph-3d'));

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

// -- Color maps (high-contrast, vibrant for dark bg) --
const citationColors: Record<string, string> = {
    center: '#60a5fa',
    citing: '#34d399',
    referenced: '#fbbf24',
    cited: '#22d3ee',
};

const contentColors: Record<string, string> = {
    entity: '#818cf8',
    concept: '#c084fc',
    method: '#34d399',
    dataset: '#38bdf8',
    person: '#fb7185',
    technology: '#e879f9',
    model: '#f87171',
    metric: '#facc15',
    task: '#22d3ee',
};

// Background
const BG_COLOR = '#161b22';

const KnowledgeGraph: React.FC<Props> = ({ projectId }) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const graphRef = useRef<any>(null);
    const fg3dRef = useRef<any>(null);
    const [loading, setLoading] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
    const [graphData, setGraphData] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null);
    const [mode, setMode] = useState<string>('content');      // 'citation' | 'content'
    const [viewMode, setViewMode] = useState<string>('3d');    // '3d' | '2d'
    const [containerWidth, setContainerWidth] = useState(800);
    const wrapperRef = useRef<HTMLDivElement>(null);

    // Track container width for responsive 3D canvas
    useEffect(() => {
        const measure = () => {
            if (wrapperRef.current) {
                setContainerWidth(wrapperRef.current.offsetWidth);
            }
        };
        measure();
        window.addEventListener('resize', measure);
        return () => window.removeEventListener('resize', measure);
    }, []);

    // Auto-load content KG when switching to content mode
    useEffect(() => {
        if (mode === 'content') {
            loadContentKG();
        }
    }, [mode, projectId]);

    // -- Data loading --
    const loadCitationNetwork = async (paperId: string) => {
        setLoading(true);
        try {
            const { data } = await externalApi.getCitations(paperId, 1, 15);
            const nodes = data?.nodes || [];
            const edges = data?.edges || [];
            if (nodes.length === 0) {
                setGraphData({ nodes: [], edges: [] });
                message.info('未获取到引用网络数据，可能外部API暂时不可用');
                return;
            }
            const formatted = { nodes, edges };
            setGraphData(formatted);
            if (viewMode === '2d') {
                renderGraph2D(formatted, 'citation');
            }
        } catch {
            message.error('加载引用网络失败，请稍后重试');
            setGraphData({ nodes: [], edges: [] });
        } finally {
            setLoading(false);
        }
    };

    const loadContentKG = async () => {
        setLoading(true);
        try {
            const { data: kgData } = await authAxios.post('/agent/knowledge-graph', {
                project_id: projectId,
                max_entities: 30,
            }, {
                timeout: 300000,
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
                if (viewMode === '2d') {
                    renderGraph2D(formattedData, 'content');
                }
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
        } catch {
            message.error('搜索失败');
        } finally {
            setLoading(false);
        }
    };

    // -- 2D rendering (G6, legacy fallback) --
    const renderGraph2D = async (data: { nodes: GraphNode[]; edges: GraphEdge[] }, graphMode: string) => {
        if (!containerRef.current || !data.nodes.length) return;
        if (graphRef.current) {
            graphRef.current.destroy();
        }

        try {
            const G6 = await import('@antv/g6');
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
                data: { label: e.relation || '' },
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

    // Re-render 2D when viewMode switches to 2D (with existing data)
    useEffect(() => {
        if (viewMode === '2d' && graphData && graphData.nodes.length > 0) {
            // Small delay to let the container mount
            const timer = setTimeout(() => renderGraph2D(graphData, mode), 100);
            return () => clearTimeout(timer);
        }
    }, [viewMode]);

    // Cleanup G6 on unmount
    useEffect(() => {
        return () => {
            if (graphRef.current) {
                graphRef.current.destroy();
            }
        };
    }, []);

    // Hover highlight state
    const [hoverNode, setHoverNode] = useState<any>(null);
    const linkedNodes = useRef<Set<string>>(new Set());

    // -- 3D data preparation --
    const graph3DData = useMemo(() => {
        if (!graphData || !graphData.nodes.length) return { nodes: [], links: [] };

        const colorMap = mode === 'citation' ? citationColors : contentColors;
        const nodeIds = new Set(graphData.nodes.map(n => n.id));

        // Compute node degree for sizing
        const degreeMap: Record<string, number> = {};
        graphData.edges.forEach(e => {
            if (nodeIds.has(e.source) && nodeIds.has(e.target)) {
                degreeMap[e.source] = (degreeMap[e.source] || 0) + 1;
                degreeMap[e.target] = (degreeMap[e.target] || 0) + 1;
            }
        });

        const nodes = graphData.nodes.map(n => ({
            id: n.id,
            name: n.title || n.id,
            type: n.type,
            year: n.year,
            citationCount: n.citation_count,
            color: colorMap[n.type] || '#94a3b8',
            val: Math.max(1.5, Math.min(6, (degreeMap[n.id] || 0) * 0.8 + 1)),
        }));

        const links = graphData.edges
            .filter(e => nodeIds.has(e.source) && nodeIds.has(e.target))
            .map(e => ({
                source: e.source,
                target: e.target,
                label: e.relation || '',
            }));

        return { nodes, links };
    }, [graphData, mode]);

    // Build adjacency for hover highlight
    const adjacency = useMemo(() => {
        const adj = new Map<string, Set<string>>();
        if (!graphData) return adj;
        graphData.edges.forEach(e => {
            if (!adj.has(e.source)) adj.set(e.source, new Set());
            if (!adj.has(e.target)) adj.set(e.target, new Set());
            adj.get(e.source)!.add(e.target);
            adj.get(e.target)!.add(e.source);
        });
        return adj;
    }, [graphData]);

    // 3D node click handler
    const handleNodeClick3D = useCallback((node: any) => {
        setSelectedNode({
            id: node.id,
            title: node.name,
            type: node.type,
            year: node.year,
            citation_count: node.citationCount,
        });
        if (fg3dRef.current) {
            const distance = 120;
            const distRatio = 1 + distance / Math.hypot(node.x || 0, node.y || 0, node.z || 0);
            fg3dRef.current.cameraPosition(
                { x: (node.x || 0) * distRatio, y: (node.y || 0) * distRatio, z: (node.z || 0) * distRatio },
                node,
                1500
            );
        }
    }, []);

    // Hover handler
    const handleNodeHover3D = useCallback((node: any) => {
        setHoverNode(node || null);
        if (node) {
            linkedNodes.current = adjacency.get(node.id) || new Set();
        } else {
            linkedNodes.current = new Set();
        }
    }, [adjacency]);

    // Custom 3D node object: sphere + floating label
    const nodeThreeObject = useCallback((node: any) => {
        const group = new THREE.Group();

        // Sphere with emissive glow
        const radius = Math.cbrt(node.val || 1) * 2.8;
        const color = new THREE.Color(node.color);
        const geo = new THREE.SphereGeometry(radius, 24, 24);
        const mat = new THREE.MeshPhongMaterial({
            color,
            emissive: color,
            emissiveIntensity: 0.35,
            transparent: true,
            opacity: 0.88,
            shininess: 80,
        });
        const mesh = new THREE.Mesh(geo, mat);
        group.add(mesh);

        // Label sprite above the sphere
        const label = node.name.length > 16 ? node.name.substring(0, 16) + '...' : node.name;
        const sprite = new SpriteText(label);
        sprite.color = '#e2e8f0';
        sprite.textHeight = 2.5;
        sprite.fontFace = 'system-ui, -apple-system, sans-serif';
        sprite.backgroundColor = 'rgba(0,0,0,0.45)';
        sprite.padding = [1, 2] as any;
        sprite.borderRadius = 2 as any;
        sprite.position.y = radius + 4;
        group.add(sprite);

        return group;
    }, []);

    // Custom link color based on hover state
    const linkColorFn = useCallback((link: any) => {
        if (!hoverNode) return 'rgba(136, 170, 230, 0.35)';
        const srcId = typeof link.source === 'object' ? link.source.id : link.source;
        const tgtId = typeof link.target === 'object' ? link.target.id : link.target;
        if (srcId === hoverNode.id || tgtId === hoverNode.id) {
            return 'rgba(250, 204, 21, 0.9)'; // highlight gold
        }
        return 'rgba(136, 170, 230, 0.12)'; // dim others
    }, [hoverNode]);

    // Link width based on hover
    const linkWidthFn = useCallback((link: any) => {
        if (!hoverNode) return 1;
        const srcId = typeof link.source === 'object' ? link.source.id : link.source;
        const tgtId = typeof link.target === 'object' ? link.target.id : link.target;
        return (srcId === hoverNode.id || tgtId === hoverNode.id) ? 2.2 : 0.5;
    }, [hoverNode]);

    // -- Legends --
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
                <Space direction="vertical" style={{ width: '100%' }} size="middle">
                    <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
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
                                if (graphRef.current) {
                                    graphRef.current.destroy();
                                    graphRef.current = null;
                                }
                            }}
                        />
                        <Segmented
                            options={[
                                { label: '3D 视图', value: '3d', icon: <GlobalOutlined /> },
                                { label: '2D 视图', value: '2d', icon: <AppstoreOutlined /> },
                            ]}
                            value={viewMode}
                            onChange={(v) => {
                                // Destroy old G6 graph when switching away from 2D
                                if (graphRef.current) {
                                    graphRef.current.destroy();
                                    graphRef.current = null;
                                }
                                setViewMode(v as string);
                            }}
                        />
                    </Space>

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
                <div ref={wrapperRef}>
                    {loading ? (
                        <div style={{ textAlign: 'center', padding: 80 }}>
                            <Spin size="large" tip={mode === 'content' ? '正在从文献中提取实体关系...' : '加载引用网络中...'} />
                        </div>
                    ) : graphData && graphData.nodes.length > 0 ? (
                        <div>
                            <div style={{ marginBottom: 8 }}>
                                <Tag>{graphData.nodes.length} 个节点</Tag>
                                <Tag>{graphData.edges.length} 条边</Tag>
                                {viewMode === '3d' && (
                                    <Tag color="geekblue">拖拽旋转 | 滚轮缩放 | 点击聚焦</Tag>
                                )}
                            </div>

                            {viewMode === '3d' ? (
                                <div style={{
                                    borderRadius: 8,
                                    overflow: 'hidden',
                                    background: BG_COLOR,
                                }}>
                                    <React.Suspense fallback={
                                        <div style={{ textAlign: 'center', padding: 80, color: '#e2e8f0', background: BG_COLOR }}>
                                            <Spin size="large" tip="加载 3D 引擎..." />
                                        </div>
                                    }>
                                        <ForceGraph3D
                                            ref={fg3dRef}
                                            graphData={graph3DData}
                                            nodeThreeObject={nodeThreeObject}
                                            nodeThreeObjectExtend={false}
                                            onNodeClick={handleNodeClick3D}
                                            onNodeHover={handleNodeHover3D}
                                            linkColor={linkColorFn}
                                            linkWidth={linkWidthFn}
                                            linkDirectionalArrowLength={4}
                                            linkDirectionalArrowRelPos={0.92}
                                            linkDirectionalArrowColor={linkColorFn}
                                            linkDirectionalParticles={2}
                                            linkDirectionalParticleWidth={1.2}
                                            linkDirectionalParticleSpeed={0.004}
                                            linkDirectionalParticleColor={() => 'rgba(200, 210, 255, 0.6)'}
                                            linkLabel={mode === 'content' ? 'label' : undefined}
                                            linkCurvature={0.15}
                                            width={containerWidth - 48}
                                            height={520}
                                            backgroundColor={BG_COLOR}
                                            showNavInfo={false}
                                            warmupTicks={60}
                                            cooldownTime={3000}
                                        />
                                    </React.Suspense>
                                </div>
                            ) : (
                                <div ref={containerRef} style={{ width: '100%', height: 500 }} />
                            )}
                        </div>
                    ) : (
                        <Empty description={
                            mode === 'content'
                                ? '请先上传文献，然后系统将自动提取实体关系'
                                : '请搜索论文以查看引用网络'
                        } />
                    )}
                </div>
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
