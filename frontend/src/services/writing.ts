// 写作辅助API服务
import { authAxios } from './axios';

export interface OutlineParams {
    topic: string;
    project_id?: number;
    style?: 'standard' | 'conference' | 'journal';
    sections?: string[];
}

export interface ReviewParams {
    topic: string;
    project_id?: number;
    max_words?: number;
    focus_areas?: string[];
}

export interface PolishParams {
    text: string;
    style?: 'academic' | 'formal' | 'concise';
    language?: string;
}

export interface CitationParams {
    text: string;
    project_id?: number;
    limit?: number;
}

export const writingApi = {
    /** 生成论文大纲 */
    generateOutline: (params: OutlineParams) =>
        authAxios.post('/writing/outline', params),

    /** 生成文献综述 */
    generateReview: (params: ReviewParams) =>
        authAxios.post('/writing/review', params),

    /** 段落润色 */
    polishText: (params: PolishParams) =>
        authAxios.post('/writing/polish', params),

    /** 引用建议 */
    suggestCitations: (params: CitationParams) =>
        authAxios.post('/writing/suggest-citations', params),
};
