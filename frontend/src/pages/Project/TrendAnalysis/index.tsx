// 趋势分析页面
import React, { useEffect, useState } from 'react';
import { Row, Col, Card, Spin, Empty, Table, Tag, Tabs } from 'antd';
import ReactECharts from 'echarts-for-react';
import { trendsApi } from '../../../services/trends';

interface Props {
    projectId: number;
}

const TrendAnalysis: React.FC<Props> = ({ projectId }) => {
    const [loading, setLoading] = useState(true);
    const [hotspots, setHotspots] = useState<any[]>([]);
    const [timeline, setTimeline] = useState<any[]>([]);
    const [bursts, setBursts] = useState<any[]>([]);

    useEffect(() => {
        loadData();
    }, [projectId]);

    const loadData = async () => {
        setLoading(true);
        try {
            const [hsRes, tlRes, brRes] = await Promise.allSettled([
                trendsApi.getHotspots(projectId),
                trendsApi.getTimeline(projectId),
                trendsApi.getBursts(projectId),
            ]);
            if (hsRes.status === 'fulfilled') setHotspots(hsRes.value.data.hotspots || []);
            if (tlRes.status === 'fulfilled') setTimeline(tlRes.value.data.timeline || []);
            if (brRes.status === 'fulfilled') setBursts(brRes.value.data.bursts || []);
        } catch (error) {
            console.error('Failed to load trend data:', error);
        } finally {
            setLoading(false);
        }
    };

    // 热点雷达图
    const getRadarOption = () => {
        if (!hotspots.length) return {};
        const top10 = hotspots.slice(0, 10);
        return {
            title: { text: '研究热点分布', left: 'center' },
            tooltip: {},
            radar: {
                indicator: top10.map(h => ({
                    name: h.keyword.length > 8 ? h.keyword.substring(0, 8) + '...' : h.keyword,
                    max: 1
                })),
            },
            series: [{
                type: 'radar',
                data: [{
                    value: top10.map(h => h.hotness),
                    name: '热度',
                    areaStyle: { opacity: 0.3 }
                }]
            }]
        };
    };

    // 时间线多关键词演化图
    const getEvolutionOption = () => {
        if (!timeline.length) return {};

        // 收集所有关键词
        const allKeywords = new Set<string>();
        timeline.forEach(t => {
            (t.top_keywords || []).slice(0, 5).forEach((kw: any) => {
                allKeywords.add(kw.keyword);
            });
        });

        const keywordList = Array.from(allKeywords).slice(0, 8);
        const years = timeline.map(t => t.year);

        const series = keywordList.map(keyword => ({
            name: keyword,
            type: 'line' as const,
            smooth: true,
            data: years.map(year => {
                const entry = timeline.find(t => t.year === year);
                const kw = entry?.top_keywords?.find((k: any) => k.keyword === keyword);
                return kw?.count || 0;
            }),
        }));

        return {
            title: { text: '关键词演化趋势', left: 'center' },
            tooltip: { trigger: 'axis' },
            legend: { bottom: 0, data: keywordList },
            grid: { bottom: '15%' },
            xAxis: { type: 'category', data: years, name: '年份' },
            yAxis: { type: 'value', name: '频次' },
            series,
        };
    };

    // 突现词时间线图
    const getBurstOption = () => {
        if (!bursts.length) return {};
        const top15 = bursts.slice(0, 15);

        return {
            title: { text: '突现词检测', left: 'center' },
            tooltip: {},
            grid: { left: '20%', right: '10%' },
            yAxis: {
                type: 'category',
                data: top15.map(b => b.term).reverse(),
                axisLabel: { fontSize: 11 },
            },
            xAxis: { type: 'value', name: '突现强度' },
            series: [{
                type: 'bar',
                data: top15.map(b => b.strength).reverse(),
                itemStyle: {
                    color: (params: any) => {
                        const ratio = params.value / Math.max(...top15.map(b => b.strength));
                        return ratio > 0.7 ? '#f5222d' : ratio > 0.4 ? '#faad14' : '#1890ff';
                    }
                },
                label: {
                    show: true,
                    position: 'right',
                    formatter: (p: any) => {
                        const b = top15[top15.length - 1 - p.dataIndex];
                        return `${b.start_year}-${b.end_year}`;
                    },
                    fontSize: 10,
                }
            }]
        };
    };

    const burstColumns = [
        { title: '突现词', dataIndex: 'term', key: 'term' },
        { title: '开始年份', dataIndex: 'start_year', key: 'start_year' },
        { title: '结束年份', dataIndex: 'end_year', key: 'end_year' },
        {
            title: '强度',
            dataIndex: 'strength',
            key: 'strength',
            render: (v: number) => (
                <Tag color={v > 3 ? 'red' : v > 1.5 ? 'orange' : 'blue'}>
                    {v.toFixed(2)}
                </Tag>
            ),
        },
    ];

    if (loading) {
        return <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>;
    }

    if (!hotspots.length && !timeline.length && !bursts.length) {
        return <Empty description="暂无趋势数据，请先上传文献" />;
    }

    const tabItems = [
        {
            key: 'hotspots',
            label: '研究热点',
            children: (
                <Row gutter={[16, 16]}>
                    <Col xs={24} lg={12}>
                        <Card>
                            {hotspots.length > 0 ? (
                                <ReactECharts option={getRadarOption()} style={{ height: 400 }} />
                            ) : (
                                <Empty />
                            )}
                        </Card>
                    </Col>
                    <Col xs={24} lg={12}>
                        <Card title="热点关键词排行">
                            <Table
                                dataSource={hotspots.slice(0, 20)}
                                columns={[
                                    { title: '排名', render: (_: any, __: any, i: number) => i + 1, width: 60 },
                                    { title: '关键词', dataIndex: 'keyword' },
                                    { title: '频次', dataIndex: 'count', width: 80 },
                                    {
                                        title: '热度',
                                        dataIndex: 'hotness',
                                        width: 100,
                                        render: (v: number) => (
                                            <div style={{
                                                width: `${v * 100}%`,
                                                height: 16,
                                                background: v > 0.7 ? '#f5222d' : v > 0.4 ? '#faad14' : '#1890ff',
                                                borderRadius: 4,
                                                minWidth: 10
                                            }} />
                                        ),
                                    },
                                ]}
                                rowKey="keyword"
                                pagination={false}
                                size="small"
                            />
                        </Card>
                    </Col>
                </Row>
            ),
        },
        {
            key: 'evolution',
            label: '关键词演化',
            children: (
                <Card>
                    {timeline.length > 0 ? (
                        <ReactECharts option={getEvolutionOption()} style={{ height: 450 }} />
                    ) : (
                        <Empty description="无时间线数据" />
                    )}
                </Card>
            ),
        },
        {
            key: 'bursts',
            label: '突现词检测',
            children: (
                <Row gutter={[16, 16]}>
                    <Col xs={24} lg={14}>
                        <Card>
                            {bursts.length > 0 ? (
                                <ReactECharts option={getBurstOption()} style={{ height: 450 }} />
                            ) : (
                                <Empty description="无突现词数据" />
                            )}
                        </Card>
                    </Col>
                    <Col xs={24} lg={10}>
                        <Card title="突现词列表">
                            <Table
                                dataSource={bursts}
                                columns={burstColumns}
                                rowKey="term"
                                pagination={{ pageSize: 10 }}
                                size="small"
                            />
                        </Card>
                    </Col>
                </Row>
            ),
        },
    ];

    return <Tabs items={tabItems} />;
};

export default TrendAnalysis;
