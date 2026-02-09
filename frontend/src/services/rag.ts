// RAG API服务
// 基于 docs/api/04_rag.md

import { authAxios, API_BASE_URL } from './axios';
import type { AnswerResponse, Conversation, Reference } from '../types/models';

export interface AskQuestionData {
    question: string;
    project_id?: number;
    paper_ids?: number[];
    top_k?: number;
}

export interface StreamCallbacks {
    onChunk: (chunk: string) => void;
    onReferences: (refs: Reference[]) => void;
    onDone: (answer: string) => void;
    onError: (error: string) => void;
}

export const ragApi = {
    /**
     * 同步问答
     */
    ask: (data: AskQuestionData) =>
        authAxios.post<AnswerResponse>('/rag/ask', data),

    /**
     * 流式问答 (SSE)
     */
    stream: async (data: AskQuestionData, callbacks: StreamCallbacks) => {
        const token = localStorage.getItem('token');

        try {
            const response = await fetch(`${API_BASE_URL}/rag/stream`, {
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

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const text = decoder.decode(value);
                const lines = text.split('\n').filter(line => line.startsWith('data:'));

                for (const line of lines) {
                    try {
                        const jsonStr = line.replace('data: ', '').trim();
                        if (!jsonStr) continue;

                        const json = JSON.parse(jsonStr);

                        switch (json.type) {
                            case 'references':
                                callbacks.onReferences(json.data);
                                break;
                            case 'chunk':
                                callbacks.onChunk(json.data);
                                break;
                            case 'done':
                                callbacks.onDone(json.data.answer);
                                break;
                            case 'error':
                                callbacks.onError(json.data);
                                break;
                        }
                    } catch (e) {
                        console.error('Parse error:', e);
                    }
                }
            }
        } catch (error: any) {
            callbacks.onError(error.message || '请求失败');
        }
    },

    /**
     * 获取对话总数
     */
    getConversationCount: () =>
        authAxios.get<{ count: number }>('/rag/conversations/count'),

    /**
     * 获取对话历史列表
     */
    getConversations: (projectId?: number, limit = 20) =>
        authAxios.get<Conversation[]>('/rag/conversations', {
            params: { project_id: projectId, limit },
        }),

    /**
     * 获取对话详情
     */
    getConversation: (id: number) =>
        authAxios.get<Conversation>(`/rag/conversations/${id}`),

    /**
     * 删除对话
     */
    deleteConversation: (id: number) =>
        authAxios.delete(`/rag/conversations/${id}`),
};
