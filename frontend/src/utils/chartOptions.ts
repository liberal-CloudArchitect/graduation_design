/**
 * Shared ECharts option builders
 * 
 * Extracted from Visualization page for reuse in Chat messages,
 * Memory Dashboard, and other components.
 */

const COLORS = [
    '#667eea', '#764ba2', '#f093fb', '#f5576c', '#4facfe',
    '#00f2fe', '#43e97b', '#fa709a', '#fee140', '#30cfd0',
    '#a18cd1', '#fbc2eb',
];

export { COLORS };

/**
 * Generate a word cloud scatter chart option from keyword data
 */
export function buildWordCloudOption(
    keywords: { keyword: string; count: number }[],
    title = '关键词词云'
): Record<string, any> {
    if (!keywords.length) return {};

    const maxCount = Math.max(...keywords.map(k => k.count));
    const minCount = Math.min(...keywords.map(k => k.count));
    const range = maxCount - minCount || 1;

    const data = keywords.slice(0, 40).map((k, i) => {
        const angle = i * 2.4;
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
            itemStyle: { color: COLORS[i % COLORS.length], opacity: 0.85 },
            label: {
                fontSize: Math.max(11, Math.round(normalized * 28 + 11)),
                color: COLORS[i % COLORS.length],
                fontWeight: normalized > 0.5 ? ('bold' as const) : ('normal' as const),
            },
        };
    });

    return {
        title: { text: title, left: 'center', textStyle: { fontSize: 14 } },
        tooltip: { formatter: (p: any) => `<b>${p.data.value[2]}</b><br/>频次: ${p.data.value[3]}` },
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
            label: { show: true, formatter: (p: any) => p.data.value[2], position: 'inside' },
            emphasis: {
                label: { fontSize: 20, fontWeight: 'bold' },
                itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' },
            },
            animationDuration: 1500,
        }],
    };
}

/**
 * Generate a bar chart option from keyword data
 */
export function buildBarOption(
    keywords: { keyword: string; count: number }[],
    title = '关键词频率 Top 20'
): Record<string, any> {
    if (!keywords.length) return {};
    const top20 = keywords.slice(0, 20);
    return {
        title: { text: title, left: 'center', textStyle: { fontSize: 14 } },
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
                        type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
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
}

/**
 * Generate a line chart option from timeline data
 */
export function buildTimelineOption(
    timeline: { year: number | string; paper_count?: number; count?: number }[],
    title = '发表趋势'
): Record<string, any> {
    if (!timeline.length) return {};
    return {
        title: { text: title, left: 'center', textStyle: { fontSize: 14 } },
        tooltip: { trigger: 'axis' },
        grid: { left: '8%', right: '5%', bottom: '10%', top: '15%' },
        xAxis: {
            type: 'category',
            data: timeline.map(t => String(t.year)),
            name: '年份',
            boundaryGap: false,
        },
        yAxis: { type: 'value', name: '数量' },
        series: [{
            type: 'line',
            data: timeline.map(t => t.paper_count ?? t.count ?? 0),
            smooth: true,
            areaStyle: {
                color: {
                    type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
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
}

/**
 * Generate a pie chart option from distribution data
 */
export function buildPieOption(
    distribution: { category?: string; name?: string; count?: number; value?: number }[],
    title = '领域分布'
): Record<string, any> {
    if (!distribution.length) return {};

    const categoryMap: Record<string, number> = {};
    distribution.forEach(d => {
        const name = d.category || d.name || 'unknown';
        categoryMap[name] = (categoryMap[name] || 0) + (d.count ?? d.value ?? 0);
    });

    return {
        title: { text: title, left: 'center', textStyle: { fontSize: 14 } },
        tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
        legend: { bottom: 10, type: 'scroll' },
        color: COLORS,
        series: [{
            type: 'pie',
            radius: ['40%', '70%'],
            center: ['50%', '45%'],
            data: Object.entries(categoryMap).map(([name, value]) => ({ name, value })),
            emphasis: {
                itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.3)' },
            },
            label: { fontSize: 12 },
            animationType: 'scale',
            animationDuration: 1200,
        }],
    };
}
