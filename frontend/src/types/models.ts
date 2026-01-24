// 数据模型类型定义
// 基于 docs/api/05_models.md

export interface User {
    id: number;
    email: string;
    username: string;
}

export interface Project {
    id: number;
    name: string;
    description?: string;
    paper_count: number;
    created_at: string;
    updated_at: string;
}

export interface Paper {
    id: number;
    title?: string;
    authors?: string;
    abstract?: string;
    status: 'pending' | 'processing' | 'completed' | 'failed';
    page_count: number;
    project_id: number;
    created_at: string;
    updated_at: string;
}

export interface Message {
    role: 'user' | 'assistant';
    content: string;
    created_at: string;
}

export interface Conversation {
    id: number;
    project_id?: number;
    messages: Message[];
    created_at: string;
}

export interface Reference {
    paper_id: number;
    paper_title?: string;
    chunk_index: number;
    page_number?: number;
    text: string;
    score: number;
}

export interface AnswerResponse {
    answer: string;
    references: Reference[];
    conversation_id?: number;
    method: string;
}

// API响应类型
export interface PaginatedResponse<T> {
    items: T[];
    total: number;
    page: number;
    page_size: number;
}

export interface TokenResponse {
    access_token: string;
    token_type: string;
}

export interface UploadResponse {
    id: number;
    filename: string;
    status: string;
    message: string;
}
