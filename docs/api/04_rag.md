# API接口文档 - RAG问答模块

> 模块路径: `/api/v1/rag`  
> 更新日期: 2026-01-20  
> 认证: ✅ 需要Bearer Token

---

## 1. 同步问答

**POST** `/api/v1/rag/ask`

### 请求

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| question | string | ✅ | 用户问题 |
| project_id | int | ❌ | 限定项目范围 |
| paper_ids | int[] | ❌ | 指定文献ID列表 |
| top_k | int | ❌ | 检索数量(默认5) |

```json
{
  "question": "请总结这篇论文的主要贡献",
  "project_id": 1,
  "top_k": 5
}
```

### 响应

```json
{
  "answer": "根据文献[1][2]，该论文的主要贡献包括...",
  "references": [
    {
      "paper_id": 1,
      "paper_title": "论文标题",
      "chunk_index": 3,
      "page_number": 5,
      "text": "原文片段内容...",
      "score": 0.85
    }
  ],
  "conversation_id": 1,
  "method": "rag"
}
```

---

## 2. 流式问答 ⭐

**POST** `/api/v1/rag/stream`

> 返回Server-Sent Events流

### 请求

同同步问答请求

### 响应 (SSE)

```
data: {"type": "references", "data": [...]}

data: {"type": "chunk", "data": "根据"}
data: {"type": "chunk", "data": "文献"}
data: {"type": "chunk", "data": "[1]..."}

data: {"type": "done", "data": {"answer": "完整答案..."}}
```

### 事件类型

| type | 说明 |
|------|------|
| references | 检索到的参考文献 |
| chunk | 答案片段 |
| done | 完成，包含完整答案 |
| error | 错误信息 |

---

## 3. 获取对话历史

**GET** `/api/v1/rag/conversations`

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| project_id | int | ❌ | 按项目筛选 |
| limit | int | ❌ | 数量限制(默认20) |

### 响应

```json
[
  {
    "id": 1,
    "project_id": 1,
    "messages": [
      {"role": "user", "content": "问题", "created_at": "..."},
      {"role": "assistant", "content": "答案", "created_at": "..."}
    ],
    "created_at": "2026-01-20T06:30:00Z"
  }
]
```

---

## 4. 获取对话详情

**GET** `/api/v1/rag/conversations/{conversation_id}`

---

## 5. 删除对话

**DELETE** `/api/v1/rag/conversations/{conversation_id}`

**响应**: 204 No Content

---

## 前端集成示例

### 流式问答组件

```typescript
// services/rag.ts
export const ragApi = {
  ask: (data: { question: string; project_id?: number; top_k?: number }) =>
    authAxios.post('/rag/ask', data),

  stream: async (
    data: { question: string; project_id?: number },
    onChunk: (chunk: string) => void,
    onReferences: (refs: any[]) => void,
    onDone: (answer: string) => void
  ) => {
    const token = localStorage.getItem('token');
    const response = await fetch('http://localhost:8000/api/v1/rag/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify(data),
    });

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader!.read();
      if (done) break;

      const text = decoder.decode(value);
      const lines = text.split('\n').filter(line => line.startsWith('data:'));

      for (const line of lines) {
        const json = JSON.parse(line.replace('data: ', ''));
        switch (json.type) {
          case 'references':
            onReferences(json.data);
            break;
          case 'chunk':
            onChunk(json.data);
            break;
          case 'done':
            onDone(json.data.answer);
            break;
        }
      }
    }
  },

  getConversations: (projectId?: number, limit = 20) =>
    authAxios.get('/rag/conversations', { params: { project_id: projectId, limit } }),
};
```

### React流式对话组件

```tsx
// components/Chat/ChatInterface.tsx
const ChatInterface: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSend = async () => {
    if (!input.trim()) return;
    
    const userMessage = { role: 'user', content: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    let assistantContent = '';
    
    await ragApi.stream(
      { question: input, project_id: currentProjectId },
      (chunk) => {
        assistantContent += chunk;
        setMessages(prev => {
          const updated = [...prev];
          if (updated[updated.length - 1]?.role === 'assistant') {
            updated[updated.length - 1].content = assistantContent;
          } else {
            updated.push({ role: 'assistant', content: assistantContent });
          }
          return updated;
        });
      },
      (refs) => setReferences(refs),
      () => setIsLoading(false)
    );
  };

  return (
    <div className="chat-container">
      <MessageList messages={messages} />
      <InputBox value={input} onChange={setInput} onSend={handleSend} />
    </div>
  );
};
```
