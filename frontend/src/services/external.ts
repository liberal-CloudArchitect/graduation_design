// 外部学术API服务
import { authAxios } from './axios';

export const externalApi = {
    /** 跨源论文搜索 */
    search: (query: string, limit = 10, sources?: string, year?: string) =>
        authAxios.get('/external/search', {
            params: { query, limit, sources, year }
        }),

    /** 获取论文详情 */
    getPaper: (paperId: string) =>
        authAxios.get(`/external/paper/${paperId}`),

    /** 获取引用网络 */
    getCitations: (paperId: string, depth = 1, limit = 20) =>
        authAxios.get(`/external/citations/${paperId}`, {
            params: { depth, limit }
        }),

    /** 获取论文推荐 */
    getRecommendations: (paperId: string, limit = 10) =>
        authAxios.get(`/external/recommendations/${paperId}`, {
            params: { limit }
        }),

    /** DOI解析 */
    resolveDoi: (doi: string) =>
        authAxios.get(`/external/doi/${doi}`),

    /** 获取热门研究概念 */
    getConcepts: (field?: string, limit = 20) =>
        authAxios.get('/external/concepts', {
            params: { field, limit }
        }),

    /** 搜索作者 */
    searchAuthor: (query: string, limit = 5) =>
        authAxios.get('/external/author/search', {
            params: { query, limit }
        }),
};
