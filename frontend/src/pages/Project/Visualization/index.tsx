// 可视化页面 - 词云、趋势图、分布图
import React, { useEffect, useState } from 'react';
import { Row, Col, Card, Spin, Empty, Select, Segmented } from 'antd';
import ReactECharts from 'echarts-for-react';
import { trendsApi } from '../../../services/trends';

interface Props {
    projectId: number;
}

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

    // 词云图 (用散点图模拟)
    const getWordCloudOption = () => {
        if (!keywords.length) return {};
        const maxCount = Math.max(...keywords.map(k => k.count));
        return {
            title: { text: '关键词词云', left: 'center' },
            tooltip: { formatter: (p: any) => `${p.data[2]}: ${p.data[3]}次` },
            xAxis: { show: false, min: 0, max: 100 },
            yAxis: { show: false, min: 0, max: 100 },
            series: [{
                type: 'scatter',
                symbolSize: (val: any) => Math.max(10, (val[3] / maxCount) * 60),
                data: keywords.map((k, i) => [
                    Math.random() * 80 + 10,
                    Math.random() * 80 + 10,
                    k.keyword,
                    k.count
                ]),
                label: {
                    show: true,
                    formatter: (p: any) => p.data[2],
                    fontSize: (params: any) => Math.max(10, (params.data[3] / maxCount) * 24),
                    color: '#333'
                },
                itemStyle: {
                    color: () => {
                        const colors = ['#1890ff', '#13c2c2', '#52c41a', '#faad14', '#f5222d', '#722ed1', '#eb2f96'];
                        return colors[Math.floor(Math.random() * colors.length)];
                    }
                }
            }]
        };
    };

    // 关键词柱状图
    const getBarOption = () => {
        if (!keywords.length) return {};
        const top20 = keywords.slice(0, 20);
        return {
            title: { text: '关键词频率 Top 20', left: 'center' },
            tooltip: { trigger: 'axis' },
            grid: { left: '15%', right: '5%', bottom: '15%' },
            xAxis: {
                type: 'category',
                data: top20.map(k => k.keyword),
                axisLabel: { rotate: 45, fontSize: 10 }
            },
            yAxis: { type: 'value', name: '频次' },
            series: [{
                type: 'bar',
                data: top20.map(k => k.count),
                itemStyle: {
                    color: (params: any) => {
                        const colors = ['#1890ff', '#13c2c2', '#52c41a', '#faad14', '#f5222d'];
                        return colors[params.dataIndex % colors.length];
                    }
                }
            }]
        };
    };

    // 发表趋势折线图
    const getTimelineOption = () => {
        if (!timeline.length) return {};
        return {
            title: { text: '发表趋势', left: 'center' },
            tooltip: { trigger: 'axis' },
            xAxis: {
                type: 'category',
                data: timeline.map(t => t.year),
                name: '年份'
            },
            yAxis: { type: 'value', name: '论文数量' },
            series: [{
                type: 'line',
                data: timeline.map(t => t.paper_count),
                smooth: true,
                areaStyle: { opacity: 0.3 },
                itemStyle: { color: '#1890ff' }
            }]
        };
    };

    // 领域分布饼图
    const getPieOption = () => {
        if (!distribution.length) return {};
        // 按类别聚合
        const categoryMap: Record<string, number> = {};
        distribution.forEach(d => {
            categoryMap[d.category] = (categoryMap[d.category] || 0) + d.count;
        });

        return {
            title: { text: '领域分布', left: 'center' },
            tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
            legend: { bottom: 10 },
            series: [{
                type: 'pie',
                radius: ['40%', '70%'],
                data: Object.entries(categoryMap).map(([name, value]) => ({ name, value })),
                emphasis: {
                    itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.5)' }
                }
            }]
        };
    };

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
                            <ReactECharts option={getWordCloudOption()} style={{ height: 400 }} />
                        )}
                        {chartType === 'bar' && keywords.length > 0 && (
                            <ReactECharts option={getBarOption()} style={{ height: 400 }} />
                        )}
                        {chartType === 'timeline' && timeline.length > 0 && (
                            <ReactECharts option={getTimelineOption()} style={{ height: 400 }} />
                        )}
                        {chartType === 'pie' && distribution.length > 0 && (
                            <ReactECharts option={getPieOption()} style={{ height: 400 }} />
                        )}
                    </Card>
                </Col>
            </Row>

            <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
                <Col xs={24} lg={12}>
                    <Card title="发表趋势">
                        {timeline.length > 0 ? (
                            <ReactECharts option={getTimelineOption()} style={{ height: 300 }} />
                        ) : (
                            <Empty description="无趋势数据" />
                        )}
                    </Card>
                </Col>
                <Col xs={24} lg={12}>
                    <Card title="领域分布">
                        {distribution.length > 0 ? (
                            <ReactECharts option={getPieOption()} style={{ height: 300 }} />
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
