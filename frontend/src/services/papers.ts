// 文献API服务
// 基于 docs/api/03_papers.md

import { authAxios } from './axios';
import type { Paper, PaginatedResponse, UploadResponse } from '../types/models';

export interface ListPapersParams {
    project_id?: number;
    status_filter?: string;
    search?: string;
    page?: number;
    page_size?: number;
}

export interface PaperStatus {
    id: number;
    status: string;
    title?: string;
    updated_at: string;
}

export const papersApi = {
    /**
     * 获取文献列表
     */
    list: (params: ListPapersParams = {}) =>
        authAxios.get<PaginatedResponse<Paper>>('/papers', { params }),

    /**
     * 上传文献
     */
    upload: (projectId: number, file: File) => {
        const formData = new FormData();
        formData.append('file', file);
        return authAxios.post<UploadResponse>('/papers/upload', formData, {
            params: { project_id: projectId },
            headers: { 'Content-Type': 'multipart/form-data' },
        });
    },

    /**
     * 获取文献详情
     */
    get: (id: number) =>
        authAxios.get<Paper>(`/papers/${id}`),

    /**
     * 获取处理状态
     */
    getStatus: (id: number) =>
        authAxios.get<PaperStatus>(`/papers/${id}/status`),

    /**
     * 删除文献
     */
    delete: (id: number) =>
        authAxios.delete(`/papers/${id}`),
};

/**
 * 轮询文献处理状态
 */
export const pollPaperStatus = (
    paperId: number,
    onUpdate: (status: PaperStatus) => void,
    interval = 3000
): (() => void) => {
    let stopped = false;

    const poll = async () => {
        if (stopped) return;

        try {
            const { data } = await papersApi.getStatus(paperId);
            onUpdate(data);

            if (data.status !== 'completed' && data.status !== 'failed') {
                setTimeout(poll, interval);
            }
        } catch (error) {
            console.error('Poll error:', error);
        }
    };

    poll();

    return () => {
        stopped = true;
    };
};
