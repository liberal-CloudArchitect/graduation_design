// 项目API服务
// 基于 docs/api/02_projects.md

import { authAxios } from './axios';
import type { Project, PaginatedResponse } from '../types/models';

export interface CreateProjectData {
    name: string;
    description?: string;
}

export interface UpdateProjectData {
    name?: string;
    description?: string;
}

export const projectsApi = {
    /**
     * 获取项目列表
     */
    list: (page = 1, pageSize = 20) =>
        authAxios.get<PaginatedResponse<Project>>('/projects', {
            params: { page, page_size: pageSize },
        }),

    /**
     * 创建项目
     */
    create: (data: CreateProjectData) =>
        authAxios.post<Project>('/projects', data),

    /**
     * 获取项目详情
     */
    get: (id: number) =>
        authAxios.get<Project>(`/projects/${id}`),

    /**
     * 更新项目
     */
    update: (id: number, data: UpdateProjectData) =>
        authAxios.put<Project>(`/projects/${id}`, data),

    /**
     * 删除项目
     */
    delete: (id: number) =>
        authAxios.delete(`/projects/${id}`),
};
