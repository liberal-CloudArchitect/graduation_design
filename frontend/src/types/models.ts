// 数据模型类型定义
// 基于 docs/api/05_models.md

export interface User {
    id: number;
    email: string;
    username: string;
    avatar_url?: string;
    role?: string;
}

export interface Project {
    id: number;
    name: string;
    description?: string;
    paper_count: number;
    is_public?: boolean;
    created_at: string;
    updated_at: string;
}

export interface PaperAuthor {
    name: string;
    affiliation?: string;
    email?: string;
}

export interface Paper {
    id: number;
    title?: string;
    authors?: PaperAuthor[] | string;
    abstract?: string;
    keywords?: string[];
    source?: string;
    doi?: string;
    arxiv_id?: string;
    publication_date?: string;
    venue?: string;
    file_path?: string;
    file_size?: number;
    page_count?: number;
    chunk_count?: number;
    status: 'pending' | 'processing' | 'completed' | 'failed';
    project_id?: number;
    created_at: string;
    updated_at: string;
}

export interface Message {
    role: 'user' | 'assistant';
    content: string;
    created_at: string;
    references?: Reference[];
    metadata?: Record<string, any>;
    agent_type?: string;
}

export interface Conversation {
    id: number;
    project_id?: number;
    title?: string;
    messages: Message[];
    created_at: string;
    updated_at?: string;
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

// External search types
export interface ExternalPaper {
    paper_id?: string;
    title: string;
    authors?: string[];
    year?: number;
    venue?: string;
    citation_count?: number;
    abstract?: string;
    doi?: string;
    arxiv_id?: string;
    url?: string;
    source?: string;
}

export interface ExternalSearchResult {
    results: ExternalPaper[];
    total: number;
    query: string;
}
