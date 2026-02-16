/**
 * ChatChartRenderer - 在聊天气泡中渲染 Agent 返回的结构化数据
 *
 * 支持:
 * - ECharts 图表（keywords/timeline/hotspots 等分析数据）
 * - 知识图谱数据（nodes/edges）
 * - 表格数据
 * - Base64 图片
 */
import React, { useMemo } from 'react';
import { Card, Table, Image, Space } from 'antd';
import { BarChartOutlined, ShareAltOutlined, TableOutlined, PictureOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import {
    buildWordCloudOption,
    buildBarOption,
    buildTimelineOption,
} from '../../utils/chartOptions';

interface Props {
    metadata: Record<string, any>;
}

const ChatChartRenderer: React.FC<Props> = ({ metadata }) => {
    if (!metadata) return null;

    const data = metadata.data || {};
    const charts = metadata.charts || [];
    const chartImages = metadata.chart_images || [];
    const kg = data.knowledge_graph;
    const tables = data.tables;

    // ---------- ECharts ----------
    const chartOptions = useMemo(() => {
        const options: { type: string; option: Record<string, any> }[] = [];

        if (data.keywords && Array.isArray(data.keywords) && data.keywords.length > 0) {
            if (charts.includes('wordcloud')) {
                options.push({ type: 'wordcloud', option: buildWordCloudOption(data.keywords) });
            }
            if (charts.includes('bar')) {
                options.push({ type: 'bar', option: buildBarOption(data.keywords) });
            }
        }

        if (data.timeline && Array.isArray(data.timeline) && data.timeline.length > 0) {
            if (charts.includes('line') || charts.includes('timeline')) {
                options.push({ type: 'line', option: buildTimelineOption(data.timeline) });
            }
        }

        if (data.hotspots && Array.isArray(data.hotspots) && data.hotspots.length > 0) {
            if (charts.includes('heatmap') || charts.includes('wordcloud')) {
                options.push({
                    type: 'hotspot',
                    option: buildBarOption(
                        data.hotspots.map((h: any) => ({ keyword: h.keyword || h.name, count: h.score || h.count || 1 })),
                        '研究热点'
                    ),
                });
            }
        }

        if (data.bursts && Array.isArray(data.bursts) && data.bursts.length > 0) {
            options.push({
                type: 'burst',
                option: buildBarOption(
                    data.bursts.map((b: any) => ({ keyword: b.term || b.keyword, count: b.weight || b.strength || 1 })),
                    '突现词检测'
                ),
            });
        }

        return options;
    }, [data, charts]);

    // ---------- Knowledge Graph (mini) ----------
    const kgOption = useMemo(() => {
        if (!kg || !kg.nodes || !kg.edges) return null;

        const typeColors: Record<string, string> = {
            entity: '#667eea', concept: '#764ba2', method: '#43e97b',
            dataset: '#4facfe', person: '#fa709a', default: '#aaa',
        };

        return {
            tooltip: {},
            series: [{
                type: 'graph',
                layout: 'force',
                roam: true,
                symbolSize: 30,
                label: { show: true, fontSize: 10, position: 'right' },
                force: { repulsion: 200, edgeLength: 100 },
                data: kg.nodes.map((n: any) => ({
                    name: n.id,
                    symbolSize: 24,
                    itemStyle: { color: typeColors[n.type?.toLowerCase()] || typeColors.default },
                })),
                links: kg.edges.map((e: any) => ({
                    source: e.source,
                    target: e.target,
                    label: { show: !!e.relation, formatter: e.relation || '', fontSize: 9, color: '#999' },
                })),
                lineStyle: { opacity: 0.6, width: 1.5, curveness: 0.2 },
            }],
        };
    }, [kg]);

    // ---------- Table data ----------
    const tableData = useMemo(() => {
        if (!tables || !Array.isArray(tables) || tables.length === 0) return null;
        // tables can be array of {headers, rows} or array of dicts
        return tables.map((tbl: any, idx: number) => {
            if (tbl.headers && tbl.rows) {
                const columns = tbl.headers.map((h: string) => ({ title: h, dataIndex: h, key: h }));
                const dataSource = tbl.rows.map((row: any[], i: number) => {
                    const obj: Record<string, any> = { key: i };
                    tbl.headers.forEach((h: string, j: number) => { obj[h] = row[j]; });
                    return obj;
                });
                return { key: idx, columns, dataSource, title: tbl.title || `表格 ${idx + 1}` };
            }
            return null;
        }).filter(Boolean);
    }, [tables]);

    // ---------- Nothing to render ----------
    const hasContent = chartOptions.length > 0 || kgOption || tableData || chartImages.length > 0;
    if (!hasContent) return null;

    return (
        <div style={{ marginTop: 12 }}>
            {/* ECharts */}
            {chartOptions.map((co, i) => (
                <Card
                    key={`chart-${i}`}
                    size="small"
                    title={<span><BarChartOutlined /> 分析图表</span>}
                    style={{ marginBottom: 8 }}
                >
                    <ReactECharts option={co.option} style={{ height: 320 }} />
                </Card>
            ))}

            {/* Knowledge Graph */}
            {kgOption && (
                <Card
                    size="small"
                    title={<span><ShareAltOutlined /> 知识图谱 ({kg.node_count} 节点, {kg.edge_count} 边)</span>}
                    style={{ marginBottom: 8 }}
                >
                    <ReactECharts option={kgOption} style={{ height: 360 }} />
                </Card>
            )}

            {/* Tables */}
            {tableData && tableData.map((td: any) => (
                <Card
                    key={td.key}
                    size="small"
                    title={<span><TableOutlined /> {td.title}</span>}
                    style={{ marginBottom: 8 }}
                >
                    <Table
                        columns={td.columns}
                        dataSource={td.dataSource}
                        size="small"
                        pagination={false}
                        scroll={{ x: 'max-content' }}
                    />
                </Card>
            ))}

            {/* Base64 images */}
            {chartImages.length > 0 && (
                <Card
                    size="small"
                    title={<span><PictureOutlined /> 生成的图表</span>}
                    style={{ marginBottom: 8 }}
                >
                    <Space wrap>
                        {chartImages.map((img: any, i: number) => (
                            img.image_base64 && (
                                <Image
                                    key={i}
                                    src={`data:image/png;base64,${img.image_base64}`}
                                    alt={img.type || 'chart'}
                                    style={{ maxHeight: 300, borderRadius: 4 }}
                                />
                            )
                        ))}
                    </Space>
                </Card>
            )}
        </div>
    );
};

export default ChatChartRenderer;
