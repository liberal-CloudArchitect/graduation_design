// 趋势分析API服务
import { authAxios } from './axios';

export const trendsApi = {
    /** 获取关键词频率 */
    getKeywords: (projectId?: number, limit = 50, source = 'metadata') =>
        authAxios.get('/trends/keywords', {
            params: { project_id: projectId, limit, source }
        }),

    /** 获取研究热点 */
    getHotspots: (projectId?: number, limit = 20) =>
        authAxios.get('/trends/hotspots', {
            params: { project_id: projectId, limit }
        }),

    /** 获取时间趋势 */
    getTimeline: (projectId?: number, keyword?: string) =>
        authAxios.get('/trends/timeline', {
            params: { project_id: projectId, keyword }
        }),

    /** 获取突现词 */
    getBursts: (projectId?: number, minFrequency = 2) =>
        authAxios.get('/trends/bursts', {
            params: { project_id: projectId, min_frequency: minFrequency }
        }),

    /** 获取领域分布 */
    getDistribution: (projectId?: number) =>
        authAxios.get('/trends/distribution', {
            params: { project_id: projectId }
        }),
};
