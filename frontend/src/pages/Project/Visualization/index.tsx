// 可视化页面 - 词云、趋势图、分布图
import React, { useEffect, useState, useMemo } from 'react';
import { Row, Col, Card, Spin, Empty, Segmented } from 'antd';
import ReactECharts from 'echarts-for-react';
import { trendsApi } from '../../../services/trends';

interface Props {
    projectId: number;
}

const COLORS = ['#667eea', '#764ba2', '#f093fb', '#f5576c', '#4facfe', '#00f2fe', '#43e97b', '#fa709a', '#fee140', '#30cfd0', '#a18cd1', '#fbc2eb'];

const Visualization: React.FC<Props> = ({ projectId }) => {
    const [loading, setLoading] = useState(true);
    const [keywords, setKeywords] = useState<any[]>([]);
    const [timeline, setTimeline] = useState<any[]>([]);
    const [distribution, setDistribution] = useState<any[]>([]);
    const [chartType, setChartType] = useState<string>('wordcloud');

    useEffect(() => {
        loadData();
    }, [projectId]);

    const loadData = async () => {
        setLoading(true);
        try {
            const [kwRes, tlRes, distRes] = await Promise.allSettled([
                trendsApi.getKeywords(projectId, 50),
                trendsApi.getTimeline(projectId),
                trendsApi.getDistribution(projectId),
            ]);
            if (kwRes.status === 'fulfilled') setKeywords(kwRes.value.data.keywords || []);
            if (tlRes.status === 'fulfilled') setTimeline(tlRes.value.data.timeline || []);
            if (distRes.status === 'fulfilled') setDistribution(distRes.value.data.distribution || []);
        } catch (error) {
            console.error('Failed to load visualization data:', error);
        } finally {
            setLoading(false);
        }
    };

    // Improved word cloud using scatter with deterministic positioning
    const wordCloudOption = useMemo(() => {
        if (!keywords.length) return {};
        const maxCount = Math.max(...keywords.map(k => k.count));
        const minCount = Math.min(...keywords.map(k => k.count));
        const range = maxCount - minCount || 1;

        // Generate stable spiral positions for a word cloud-like layout
        const data = keywords.slice(0, 40).map((k, i) => {
            // Use golden angle spiral for even distribution
            const angle = i * 2.4; // golden angle in radians
            const radius = 5 + Math.sqrt(i) * 8;
            const x = 50 + radius * Math.cos(angle);
            const y = 50 + radius * Math.sin(angle);
            const normalized = (k.count - minCount) / range;
            return {
                value: [
                    Math.max(5, Math.min(95, x)),
                    Math.max(5, Math.min(95, y)),
                    k.keyword,
                    k.count,
                ],
                itemStyle: {
                    color: COLORS[i % COLORS.length],
                    opacity: 0.85,
                },
                label: {
                    fontSize: Math.max(11, Math.round(normalized * 28 + 11)),
                    color: COLORS[i % COLORS.length],
                    fontWeight: normalized > 0.5 ? 'bold' : 'normal',
                },
            };
        });

        return {
            title: { text: '关键词词云', left: 'center', textStyle: { fontSize: 16 } },
            tooltip: {
                formatter: (p: any) => `<b>${p.data.value[2]}</b><br/>频次: ${p.data.value[3]}`,
            },
            xAxis: { show: false, min: 0, max: 100 },
            yAxis: { show: false, min: 0, max: 100 },
            grid: { top: 40, bottom: 10, left: 10, right: 10 },
            series: [{
                type: 'scatter',
                symbolSize: (val: any) => {
                    const norm = (val[3] - minCount) / range;
                    return Math.max(8, Math.round(norm * 50 + 8));
                },
                data,
                label: {
                    show: true,
                    formatter: (p: any) => p.data.value[2],
                    position: 'inside',
                },
                emphasis: {
                    label: { fontSize: 20, fontWeight: 'bold' },
                    itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' },
                },
                animationDuration: 1500,
                animationEasing: 'elasticOut',
            }],
        };
    }, [keywords]);

    // Keyword bar chart
    const barOption = useMemo(() => {
        if (!keywords.length) return {};
        const top20 = keywords.slice(0, 20);
        return {
            title: { text: '关键词频率 Top 20', left: 'center', textStyle: { fontSize: 16 } },
            tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
            grid: { left: '15%', right: '5%', bottom: '20%', top: '15%' },
            xAxis: {
                type: 'category',
                data: top20.map(k => k.keyword),
                axisLabel: { rotate: 45, fontSize: 10, interval: 0 },
            },
            yAxis: { type: 'value', name: '频次' },
            series: [{
                type: 'bar',
                data: top20.map((k, i) => ({
                    value: k.count,
                    itemStyle: {
                        color: {
                            type: 'linear',
                            x: 0, y: 0, x2: 0, y2: 1,
                            colorStops: [
                                { offset: 0, color: COLORS[i % COLORS.length] },
                                { offset: 1, color: COLORS[(i + 1) % COLORS.length] },
                            ],
                        },
                        borderRadius: [4, 4, 0, 0],
                    },
                })),
                barMaxWidth: 40,
                animationDuration: 1200,
            }],
        };
    }, [keywords]);

    // Timeline chart
    const timelineOption = useMemo(() => {
        if (!timeline.length) return {};
        return {
            title: { text: '发表趋势', left: 'center', textStyle: { fontSize: 16 } },
            tooltip: { trigger: 'axis' },
            grid: { left: '8%', right: '5%', bottom: '10%', top: '15%' },
            xAxis: {
                type: 'category',
                data: timeline.map(t => t.year),
                name: '年份',
                boundaryGap: false,
            },
            yAxis: { type: 'value', name: '论文数量' },
            series: [{
                type: 'line',
                data: timeline.map(t => t.paper_count),
                smooth: true,
                areaStyle: {
                    color: {
                        type: 'linear',
                        x: 0, y: 0, x2: 0, y2: 1,
                        colorStops: [
                            { offset: 0, color: 'rgba(102, 126, 234, 0.5)' },
                            { offset: 1, color: 'rgba(102, 126, 234, 0.05)' },
                        ],
                    },
                },
                lineStyle: { color: '#667eea', width: 3 },
                itemStyle: { color: '#667eea' },
                symbol: 'circle',
                symbolSize: 8,
                animationDuration: 1500,
            }],
        };
    }, [timeline]);

    // Pie chart
    const pieOption = useMemo(() => {
        if (!distribution.length) return {};
        const categoryMap: Record<string, number> = {};
        distribution.forEach(d => {
            categoryMap[d.category] = (categoryMap[d.category] || 0) + d.count;
        });

        return {
            title: { text: '领域分布', left: 'center', textStyle: { fontSize: 16 } },
            tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
            legend: { bottom: 10, type: 'scroll' },
            color: COLORS,
            series: [{
                type: 'pie',
                radius: ['40%', '70%'],
                center: ['50%', '45%'],
                data: Object.entries(categoryMap).map(([name, value]) => ({ name, value })),
                emphasis: {
                    itemStyle: {
                        shadowBlur: 10,
                        shadowOffsetX: 0,
                        shadowColor: 'rgba(0,0,0,0.3)',
                    },
                },
                label: { fontSize: 12 },
                animationType: 'scale',
                animationDuration: 1200,
            }],
        };
    }, [distribution]);

    if (loading) {
        return <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>;
    }

    if (!keywords.length && !timeline.length) {
        return <Empty description="暂无可视化数据，请先上传文献" />;
    }

    return (
        <div>
            <Row gutter={[16, 16]}>
                <Col span={24}>
                    <Card>
                        <Segmented
                            options={[
                                { label: '词云', value: 'wordcloud' },
                                { label: '柱状图', value: 'bar' },
                                { label: '趋势图', value: 'timeline' },
                                { label: '分布图', value: 'pie' },
                            ]}
                            value={chartType}
                            onChange={(v) => setChartType(v as string)}
                            style={{ marginBottom: 16 }}
                        />
                        {chartType === 'wordcloud' && keywords.length > 0 && (
                            <ReactECharts option={wordCloudOption} style={{ height: 450 }} />
                        )}
                        {chartType === 'bar' && keywords.length > 0 && (
                            <ReactECharts option={barOption} style={{ height: 450 }} />
                        )}
                        {chartType === 'timeline' && timeline.length > 0 && (
                            <ReactECharts option={timelineOption} style={{ height: 450 }} />
                        )}
                        {chartType === 'pie' && distribution.length > 0 && (
                            <ReactECharts option={pieOption} style={{ height: 450 }} />
                        )}
                    </Card>
                </Col>
            </Row>

            <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
                <Col xs={24} lg={12}>
                    <Card title="发表趋势">
                        {timeline.length > 0 ? (
                            <ReactECharts option={timelineOption} style={{ height: 300 }} />
                        ) : (
                            <Empty description="无趋势数据" />
                        )}
                    </Card>
                </Col>
                <Col xs={24} lg={12}>
                    <Card title="领域分布">
                        {distribution.length > 0 ? (
                            <ReactECharts option={pieOption} style={{ height: 300 }} />
                        ) : (
                            <Empty description="无分布数据" />
                        )}
                    </Card>
                </Col>
            </Row>
        </div>
    );
};

export default Visualization;
