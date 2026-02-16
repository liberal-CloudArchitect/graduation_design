// Multi-Agent API服务
import { authAxios, API_BASE_URL, tokenUtils } from './axios';
import type { Reference } from '../types/models';

export interface AgentRequest {
    query: string;
    project_id?: number;
    agent_type?: string;
    conversation_id?: number;  // 对话ID，用于加载历史上下文
    params?: Record<string, unknown>;
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

/**
 * Agent 流式回调接口
 */
export interface AgentStreamCallbacks {
    /** 路由信息：告知用户当前由哪个 Agent 处理 */
    onRouting?: (info: { agent_type: string; label: string }) => void;
    /** 中间状态更新（思考中、检索中等） */
    onStatus?: (info: { stage: string; message: string }) => void;
    /** 流式文本块 */
    onChunk: (chunk: string) => void;
    /** 推理内容（思考过程） */
    onReasoning?: (chunk: string) => void;
    /** 引用来源 */
    onReferences?: (refs: Reference[]) => void;
    /** Agent 元数据（图表数据、skills_used 等） */
    onMetadata?: (metadata: Record<string, unknown>) => void;
    /** 流式结束 */
    onDone: (data: { answer: string; agent_type: string; conversation_id?: number }) => void;
    /** 错误 */
    onError: (error: string) => void;
}

export const agentsApi = {
    /** Agent协调问答 */
    ask: (params: AgentRequest) =>
        authAxios.post('/agent/ask', params),

    /**
     * Agent 流式问答 (SSE)
     * 
     * 通过 Agent Coordinator 自动路由，以 SSE 流式返回结果。
     * 支持事件类型: routing / chunk / references / metadata / done / error
     */
    stream: async (data: AgentRequest, callbacks: AgentStreamCallbacks) => {
        const token = tokenUtils.getAccessToken();

        try {
            const response = await fetch(`${API_BASE_URL}/agent/stream`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
                body: JSON.stringify(data),
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const reader = response.body?.getReader();
            const decoder = new TextDecoder();

            if (!reader) {
                callbacks.onError('无法读取响应流');
                return;
            }

            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                // 保留最后一个可能不完整的行
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (!line.startsWith('data:')) continue;

                    try {
                        const jsonStr = line.replace('data: ', '').replace('data:', '').trim();
                        if (!jsonStr) continue;

                        const json = JSON.parse(jsonStr);

                        switch (json.type) {
                            case 'routing':
                                callbacks.onRouting?.(json.data);
                                break;
                            case 'status':
                                callbacks.onStatus?.(json.data);
                                break;
                            case 'reasoning':
                                callbacks.onReasoning?.(json.data);
                                break;
                            case 'chunk':
                                callbacks.onChunk(json.data);
                                break;
                            case 'references':
                                callbacks.onReferences?.(json.data);
                                break;
                            case 'metadata':
                                callbacks.onMetadata?.(json.data);
                                break;
                            case 'done':
                                callbacks.onDone(json.data);
                                break;
                            case 'error':
                                callbacks.onError(json.data);
                                break;
                        }
                    } catch (e) {
                        // JSON 解析失败，可能是不完整的行，忽略
                        console.warn('SSE parse warning:', e);
                    }
                }
            }
        } catch (error: unknown) {
            const errorMsg = error instanceof Error ? error.message : '请求失败';
            callbacks.onError(errorMsg || '请求失败');
        }
    },

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
