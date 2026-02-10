// Memory System API 服务
import { authAxios } from './axios';

export interface MemoryItem {
    id: string;
    content: string;
    timestamp: number;
    importance: number;
    access_count: number;
    memory_type: string;
    agent_source: string;
    project_id: number;
    relations?: Record<string, any>;
}

export interface MemoryStats {
    memory_engine: {
        status: string;
        collection: string;
        row_count: number;
        type_breakdown: Record<string, number>;
        agent_breakdown: Record<string, number>;
    };
    forgetting: {
        decay_rate?: number;
        protection_period_hours?: number;
        min_importance?: number;
        max_age_days?: number;
        status?: string;
    };
    cross_memory: {
        total_agents?: number;
        total_shared_memories?: number;
        agents?: Record<string, { shared: number; received: number }>;
        status?: string;
    };
}

export interface DecayPreviewItem {
    memory_id: string;
    content_preview: string;
    age_days: number;
    access_count: number;
    current_importance: number;
    decayed_importance: number;
    is_protected: boolean;
    should_forget: boolean;
}

export interface ReconstructResult {
    cue: Record<string, any>;
    trace_seeds: MemoryItem[];
    expanded: MemoryItem[];
    reconstruction: {
        content: string;
        confidence: number;
        is_reconstructed: boolean;
        fragment_count: number;
    };
    timing: {
        cue_extraction_ms: number;
        trace_ms: number;
        expand_ms: number;
        reconstruct_ms: number;
        total_ms: number;
    };
}

export const memoryApi = {
    /** 获取记忆系统聚合统计 */
    getStats: () =>
        authAxios.get<MemoryStats>('/memory/stats'),

    /** 分页列出记忆 */
    list: (params?: {
        project_id?: number;
        memory_type?: string;
        agent_source?: string;
        page?: number;
        page_size?: number;
    }) =>
        authAxios.get<{ items: MemoryItem[]; total: number; page: number; page_size: number }>(
            '/memory/list',
            { params }
        ),

    /** 获取单条记忆详情 */
    get: (memoryId: string) =>
        authAxios.get<MemoryItem>(`/memory/${memoryId}`),

    /** 删除记忆 */
    delete: (memoryId: string) =>
        authAxios.delete(`/memory/${memoryId}`),

    /** 重构记忆演示 */
    reconstruct: (data: { query: string; project_id?: number; use_llm?: boolean }) =>
        authAxios.post<ReconstructResult>('/memory/reconstruct', data),

    /** 遗忘衰减预览 */
    decayPreview: (projectId?: number) =>
        authAxios.get<{
            previews: DecayPreviewItem[];
            summary: { total: number; protected: number; decaying: number; to_forget: number };
        }>('/memory/decay-preview', { params: { project_id: projectId } }),

    /** 执行记忆清理 */
    cleanup: (projectId?: number, dryRun = true) =>
        authAxios.post('/memory/cleanup', null, {
            params: { project_id: projectId, dry_run: dryRun },
        }),

    /** 跨Agent记忆网络统计 */
    crossNetwork: () =>
        authAxios.get('/memory/cross-network'),
};
