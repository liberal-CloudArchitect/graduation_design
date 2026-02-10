---
name: Frontend Improvement Plan
overview: Based on thorough code review, the frontend has all major pages implemented but needs critical fixes for end-to-end functionality, missing feature pages, and UI polish to properly connect with the fully-featured backend.
todos:
  - id: phase1-vite-proxy
    content: Add Vite dev proxy for /api/v1 and make API base URL configurable via env variable
    status: completed
  - id: phase1-chat-markdown
    content: "Fix Chat page: add ReactMarkdown for assistant messages, read projectId from useParams"
    status: completed
  - id: phase1-auth-restore
    content: "Fix auth state restoration on refresh: add checkAuth() to authStore, call from ProtectedRoute"
    status: completed
  - id: phase1-authors-fix
    content: Fix authors JSONB array rendering in Project Detail paper table
    status: completed
  - id: phase2-conversation-history
    content: Add conversation history sidebar to Chat page with list/select/delete/new conversation support
    status: completed
  - id: phase2-paper-detail
    content: Add paper detail modal/drawer showing abstract, keywords, DOI, venue etc.
    status: completed
  - id: phase2-external-search
    content: Create External Search page for Semantic Scholar/ArXiv/OpenAlex with import-to-project feature
    status: completed
  - id: phase2-upload-polling
    content: Add paper upload status polling with progress indicator and auto-refresh
    status: completed
  - id: phase3-nav-and-ui
    content: Expand sidebar navigation, add suggested questions in Chat, improve Dashboard quick actions
    status: completed
  - id: phase3-wordcloud-error
    content: Install echarts-wordcloud for proper word cloud rendering, add React ErrorBoundary
    status: completed
isProject: false
---

# Frontend Completion and Backend Integration Plan

## Current State Analysis

The frontend (React 19 + TypeScript + Ant Design 6 + Vite 7) already has all core pages implemented:

- Login/Register, Dashboard, Project List/Detail, Chat, Visualization, Knowledge Graph, Trend Analysis, Writing Assistant
- All 8 API service files match backend contracts
- ECharts + G6 charting is wired up

However, there are **critical functional bugs**, **missing feature pages** (where backend is ready but no UI exists), and **UI quality gaps**.

---

## Phase 1: Critical Bug Fixes (End-to-end connectivity)

### 1.1 Vite Dev Proxy Configuration

- **File**: `[frontend/vite.config.ts](frontend/vite.config.ts)`
- Add proxy for `/api/v1` -> `http://localhost:8000` to avoid CORS issues in development
- This is essential for local development without Docker

### 1.2 Chat Page Markdown Rendering

- **File**: `[frontend/src/pages/Chat/index.tsx](frontend/src/pages/Chat/index.tsx)`
- Line 153: `<Paragraph className="message-text">{msg.content}</Paragraph>` renders raw text
- Replace with `<ReactMarkdown>` for assistant messages (already installed as dependency)
- Backend RAG answers contain markdown formatting with `[1][2]` citation markers

### 1.3 Chat Route Param: projectId

- **File**: `[frontend/src/pages/Chat/index.tsx](frontend/src/pages/Chat/index.tsx)`
- Route `/chat/:projectId` exists in `App.tsx` but `ChatPage` never reads `useParams`
- Fix: Read `projectId` from params and set as `selectedProject` initial value

### 1.4 Auth State Restoration

- **File**: `[frontend/src/stores/authStore.ts](frontend/src/stores/authStore.ts)`
- On page refresh, token persists in localStorage but user object is lost
- Add `checkAuth()` action that calls `authApi.getMe()` on app initialization
- Call it from `[App.tsx](frontend/src/App.tsx)` or `[ProtectedRoute.tsx](frontend/src/components/ProtectedRoute.tsx)`

### 1.5 Authors Field Rendering Fix

- **File**: `[frontend/src/pages/Project/Detail/index.tsx](frontend/src/pages/Project/Detail/index.tsx)`
- Line 113: `render: (authors: string) => authors || '-'` but backend returns JSONB `[{name, affiliation}]`
- Fix: Parse array and display author names, e.g., `authors?.map(a => a.name).join(', ')`

### 1.6 API Base URL for Docker/Production

- **File**: `[frontend/src/services/axios.ts](frontend/src/services/axios.ts)`
- Currently hardcodes `http://localhost:8000/api/v1`
- Make configurable via `import.meta.env.VITE_API_BASE_URL` with fallback

---

## Phase 2: Missing Feature Pages (Backend ready, no frontend)

### 2.1 Conversation History Sidebar in Chat

- **File**: `[frontend/src/pages/Chat/index.tsx](frontend/src/pages/Chat/index.tsx)`
- Add left sidebar listing past conversations (API: `ragApi.getConversations()`)
- Support selecting a conversation to view its history
- Support deleting conversations
- Support creating new conversations
- Backend already has: GET `/rag/conversations`, GET `/rag/conversations/{id}`, DELETE `/rag/conversations/{id}`

### 2.2 External Paper Search Page

- **New page**: `frontend/src/pages/ExternalSearch/index.tsx`
- Search across Semantic Scholar, ArXiv, OpenAlex, CrossRef
- Show results in a table/list with: title, authors, year, venue, citation count
- Allow importing external papers into projects
- Add to sidebar navigation and App.tsx routes
- Backend: GET `/external/search`, GET `/external/paper/{id}`, GET `/external/recommendations/{id}`

### 2.3 Paper Detail Modal/Page

- **File**: `[frontend/src/pages/Project/Detail/index.tsx](frontend/src/pages/Project/Detail/index.tsx)`
- Currently papers table only shows title, authors, status
- Add a detail modal (or drawer) showing: abstract, keywords (as tags), DOI, ArXiv ID, publication date, venue, page count, chunk count
- Backend: GET `/papers/{id}` already returns all this metadata

### 2.4 Paper Upload Status Polling

- **File**: `[frontend/src/pages/Project/Detail/index.tsx](frontend/src/pages/Project/Detail/index.tsx)`
- After upload, start polling paper status with `papersApi.getStatus()`
- Show progress indicator for "processing" papers
- Auto-refresh paper list when status changes to "completed"
- Service `papersApi.pollPaperStatus()` already exists but is unused

---

## Phase 3: UI/UX Enhancement

### 3.1 Expanded Sidebar Navigation

- **File**: `[frontend/src/components/Layout/index.tsx](frontend/src/components/Layout/index.tsx)`
- Current: only Dashboard, Projects, Chat (3 items)
- Add: External Search (文献搜索), Conversation History (对话历史)
- Match UI spec layout with more items

### 3.2 Chat Page Enhancements

- Add suggested/example questions when chat is empty (e.g., "这些论文的主要贡献是什么？")
- Better message bubble styling with user/assistant differentiation
- Show typing indicator during streaming
- Render citation references `[1]` as clickable links that scroll to reference sidebar

### 3.3 Dashboard Improvements

- Add quick action buttons: "Upload Paper", "Create Project", "Search Papers"
- Show recent conversations alongside recent projects
- Better stats cards with icons and trends

### 3.4 Proper Word Cloud

- **File**: `[frontend/src/pages/Project/Visualization/index.tsx](frontend/src/pages/Project/Visualization/index.tsx)`
- Currently uses scatter chart to simulate word cloud
- Install `echarts-wordcloud` package for proper word cloud rendering

### 3.5 Global Error Boundary

- **New file**: `frontend/src/components/ErrorBoundary.tsx`
- Wrap app in React error boundary for graceful failure handling

### 3.6 Responsive Design Polish

- Ensure Chat page works on smaller screens (already has some CSS for this)
- Test and fix Layout sidebar collapse behavior
- Ensure visualization charts resize properly

---

## Implementation Order

The work should be done in this sequence:

1. Phase 1 first (fixes are small and critical for demo)
2. Phase 2.1 (conversation history) + Phase 2.3 (paper detail) - most impactful for demo
3. Phase 2.2 (external search page) - shows multi-source integration capability
4. Phase 2.4 (polling) + Phase 3 items

---

## Key Files to Modify


| File                                                   | Changes                                             |
| ------------------------------------------------------ | --------------------------------------------------- |
| `frontend/vite.config.ts`                              | Add dev proxy                                       |
| `frontend/src/services/axios.ts`                       | Env-based API URL                                   |
| `frontend/src/pages/Chat/index.tsx`                    | Markdown, params, conversation history, suggestions |
| `frontend/src/stores/authStore.ts`                     | checkAuth action                                    |
| `frontend/src/components/ProtectedRoute.tsx`           | Call checkAuth                                      |
| `frontend/src/pages/Project/Detail/index.tsx`          | Authors fix, paper detail, polling                  |
| `frontend/src/components/Layout/index.tsx`             | Expanded nav                                        |
| `frontend/src/pages/Project/Visualization/index.tsx`   | Word cloud                                          |
| `frontend/src/App.tsx`                                 | New routes                                          |
| **New**: `frontend/src/pages/ExternalSearch/index.tsx` | External search page                                |
| **New**: `frontend/src/components/ErrorBoundary.tsx`   | Error handling                                      |


