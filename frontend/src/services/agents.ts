// Multi-Agent API服务
import { authAxios } from './axios';

export interface AgentRequest {
    query: string;
    project_id?: number;
    agent_type?: string;
    params?: Record<string, any>;
}

export interface WritingAgentRequest {
    query: string;
    project_id?: number;
    task_type?: 'auto' | 'outline' | 'review' | 'polish' | 'citation' | 'general';
    context?: string;
}

export interface AnalysisAgentRequest {
    query: string;
    project_id?: number;
    analysis_type?: 'auto' | 'keywords' | 'timeline' | 'hotspot' | 'burst' | 'comparison';
}

export const agentsApi = {
    /** Agent协调问答 */
    ask: (params: AgentRequest) =>
        authAxios.post('/agent/ask', params),

    /** 多Agent并行 */
    multi: (params: { query: string; project_id?: number; agent_types?: string[] }) =>
        authAxios.post('/agent/multi', params),

    /** 写作辅助 */
    write: (params: WritingAgentRequest) =>
        authAxios.post('/agent/write', params),

    /** 分析 */
    analyze: (params: AnalysisAgentRequest) =>
        authAxios.post('/agent/analyze', params),

    /** 搜索 */
    search: (params: AgentRequest) =>
        authAxios.post('/agent/search', params),
};
