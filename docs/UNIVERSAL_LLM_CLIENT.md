# Universal LLM Client 使用指南

## 概述

`UniversalLLMClient` 是一个通用的 LLM（大语言模型）客户端，支持多个主流 AI 模型提供商的 API 接口。

## 支持的模型提供商

### 1. OpenAI (GPT)
- **模型**: GPT-3.5-Turbo, GPT-4, GPT-4-Turbo 等
- **官网**: https://openai.com

### 2. DeepSeek
- **模型**: deepseek-chat, deepseek-coder
- **官网**: https://www.deepseek.com

### 3. Qwen / 通义千问 (阿里云)
- **模型**: qwen-turbo, qwen-plus, qwen-max, qwen-long
- **官网**: https://dashscope.aliyun.com

### 4. Doubao / 豆包 (字节跳动)
- **模型**: doubao-pro-32k, doubao-lite-32k
- **官网**: https://www.volcengine.com

### 5. xAI (Grok)
- **模型**: grok-beta, grok-vision-beta
- **官网**: https://x.ai

### 6. Google Gemini
- **模型**: gemini-pro, gemini-ultra, gemini-vision-pro
- **官网**: https://ai.google.dev

### 7. Kimi / Moonshot (月之暗面)
- **模型**: moonshot-v1-8k, moonshot-v1-32k, moonshot-v1-128k
- **官网**: https://www.moonshot.cn

### 8. LM Studio (本地部署)
- **模型**: 支持本地部署的任何开源模型
- **官网**: https://lmstudio.ai

## 快速开始

### 基础用法

```python
from src.universal_llm_client import UniversalLLMClient

# 方法 1: 直接指定 base_url
client = UniversalLLMClient(
    base_url="https://api.openai.com/v1",
    api_key="sk-your-api-key",
    timeout=30
)

# 方法 2: 使用 from_provider 便捷方法
client = UniversalLLMClient.from_provider(
    provider="openai",
    api_key="sk-your-api-key"
)

# 聊天对话（非流式）
response = client.chat_once(
    messages=[
        {"role": "user", "content": "你好，请介绍一下你自己"}
    ],
    model="gpt-4",
    temperature=0.7,
    max_tokens=2000
)
print(response)

# 聊天对话（流式）
for chunk in client.chat_stream(
    messages=[
        {"role": "user", "content": "写一首关于春天的诗"}
    ],
    model="gpt-4",
    temperature=0.8
):
    print(chunk, end="", flush=True)
```

## 各提供商配置示例

### OpenAI (GPT)

```python
from src.universal_llm_client import UniversalLLMClient

client = UniversalLLMClient(
    base_url="https://api.openai.com/v1",
    api_key="sk-your-openai-api-key",
    timeout=30
)

# 或使用便捷方法
client = UniversalLLMClient.from_provider(
    provider="openai",
    api_key="sk-your-openai-api-key"
)

response = client.chat_once(
    messages=[{"role": "user", "content": "Hello!"}],
    model="gpt-4-turbo",
    temperature=0.7
)
```

### DeepSeek

```python
client = UniversalLLMClient(
    base_url="https://api.deepseek.com/v1",
    api_key="sk-your-deepseek-api-key",
    timeout=60
)

response = client.chat_once(
    messages=[{"role": "user", "content": "编写一个快速排序算法"}],
    model="deepseek-chat",
    temperature=0.5
)
```

### Qwen / 通义千问

```python
client = UniversalLLMClient(
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    api_key="sk-your-dashscope-api-key",
    timeout=60
)

# 或使用 from_provider
client = UniversalLLMClient.from_provider(
    provider="qwen",
    api_key="sk-your-dashscope-api-key"
)

response = client.chat_once(
    messages=[{"role": "user", "content": "解释一下量子计算"}],
    model="qwen-max",
    temperature=0.7
)
```

### Doubao / 豆包

```python
client = UniversalLLMClient(
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    api_key="your-doubao-api-key",
    timeout=60
)

response = client.chat_once(
    messages=[{"role": "user", "content": "介绍一下人工智能的发展历程"}],
    model="doubao-pro-32k",
    temperature=0.7
)
```

### xAI (Grok)

```python
client = UniversalLLMClient(
    base_url="https://api.x.ai/v1",
    api_key="xai-your-api-key",
    timeout=60
)

response = client.chat_once(
    messages=[{"role": "user", "content": "What's happening in the world?"}],
    model="grok-beta",
    temperature=0.8
)
```

### Google Gemini

```python
client = UniversalLLMClient(
    base_url="https://generativelanguage.googleapis.com/v1beta",
    api_key="your-google-api-key",
    timeout=60
)

# 注意: Gemini API key 使用查询参数而非 header
response = client.chat_once(
    messages=[{"role": "user", "content": "Explain quantum physics"}],
    model="gemini-pro",
    temperature=0.7
)
```

### Kimi / Moonshot

```python
client = UniversalLLMClient(
    base_url="https://api.moonshot.cn/v1",
    api_key="sk-your-moonshot-api-key",
    timeout=60
)

# 或使用 from_provider
client = UniversalLLMClient.from_provider(
    provider="kimi",
    api_key="sk-your-moonshot-api-key"
)

response = client.chat_once(
    messages=[{"role": "user", "content": "总结一下这篇文章的要点"}],
    model="moonshot-v1-32k",
    temperature=0.5
)
```

### LM Studio (本地部署)

```python
client = UniversalLLMClient(
    base_url="http://localhost:1234/v1",
    api_key=None,  # 本地部署通常不需要 API key
    timeout=120
)

response = client.chat_once(
    messages=[{"role": "user", "content": "Hello, local model!"}],
    model="local-model-name",
    temperature=0.7
)
```

## 高级功能

### 1. 嵌入向量生成 (Embeddings)

```python
import numpy as np

# 生成文本嵌入向量
texts = [
    "这是第一段文本",
    "这是第二段文本",
    "这是第三段文本"
]

embeddings = client.embed_texts(
    texts=texts,
    model="text-embedding-ada-002"  # OpenAI
    # model="text-embedding-v1"      # Qwen
)

print(f"Shape: {embeddings.shape}")  # (3, embedding_dim)
print(f"Type: {embeddings.dtype}")   # float32
```

### 2. 文档重排序 (Reranking)

```python
# 对文档进行相关性重排序
query = "什么是人工智能？"
documents = [
    "人工智能是计算机科学的一个分支",
    "今天天气很好",
    "机器学习是人工智能的子领域",
    "我喜欢吃苹果"
]

scores = client.rerank_scores(
    query=query,
    docs=documents,
    model="rerank-model-name"
)

if scores:
    # 按相关性排序
    ranked = sorted(zip(documents, scores), key=lambda x: x[1], reverse=True)
    for doc, score in ranked:
        print(f"Score: {score:.4f} - {doc}")
else:
    print("Reranking not supported by this provider")
```

### 3. 流式对话

```python
messages = [
    {"role": "system", "content": "你是一个有帮助的助手"},
    {"role": "user", "content": "请写一篇关于人工智能的短文"}
]

print("AI: ", end="", flush=True)
for chunk in client.chat_stream(
    messages=messages,
    model="gpt-4",
    temperature=0.7,
    max_tokens=500
):
    print(chunk, end="", flush=True)
print()
```

### 4. 多轮对话

```python
conversation = [
    {"role": "system", "content": "你是一个Python编程助手"}
]

while True:
    user_input = input("User: ")
    if user_input.lower() in ["exit", "quit", "bye"]:
        break
    
    conversation.append({"role": "user", "content": user_input})
    
    response = client.chat_once(
        messages=conversation,
        model="gpt-4",
        temperature=0.7
    )
    
    conversation.append({"role": "assistant", "content": response})
    print(f"AI: {response}\n")
```

### 5. 自定义请求头

```python
client = UniversalLLMClient(
    base_url="https://api.example.com/v1",
    api_key="your-api-key",
    extra_headers={
        "X-Custom-Header": "custom-value",
        "X-Request-ID": "unique-request-id"
    }
)
```

## 配置文件示例

### config.json 配置

```json
{
  "knowledge_base": {
    "chat": {
      "model_type": "openai",
      "model": "gpt-4",
      "use_lm_studio": false,
      "temperature": 0.7,
      "max_tokens": 2000
    },
    "lm_studio": {
      "provider": "openai",
      "base_url": "https://api.openai.com/v1",
      "api_key": "sk-your-api-key",
      "timeout": 60
    }
  }
}
```

### 支持多个提供商配置

```json
{
  "llm_providers": {
    "openai": {
      "base_url": "https://api.openai.com/v1",
      "api_key": "sk-openai-key",
      "models": {
        "chat": "gpt-4",
        "embedding": "text-embedding-ada-002"
      }
    },
    "deepseek": {
      "base_url": "https://api.deepseek.com/v1",
      "api_key": "sk-deepseek-key",
      "models": {
        "chat": "deepseek-chat",
        "coder": "deepseek-coder"
      }
    },
    "qwen": {
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "api_key": "sk-qwen-key",
      "models": {
        "chat": "qwen-max",
        "embedding": "text-embedding-v1",
        "rerank": "qwen-rerank"
      }
    },
    "kimi": {
      "base_url": "https://api.moonshot.cn/v1",
      "api_key": "sk-kimi-key",
      "models": {
        "chat": "moonshot-v1-32k"
      }
    }
  },
  "default_provider": "openai"
}
```

## 错误处理

```python
from src.universal_llm_client import UniversalLLMClient, UniversalLLMError

client = UniversalLLMClient.from_provider(
    provider="openai",
    api_key="sk-your-api-key"
)

try:
    response = client.chat_once(
        messages=[{"role": "user", "content": "Hello"}],
        model="gpt-4"
    )
    print(response)
except UniversalLLMError as e:
    print(f"Error: {e}")
    if e.status_code:
        print(f"Status Code: {e.status_code}")
```

## API 兼容性说明

所有支持的提供商都遵循 OpenAI 兼容的 API 格式：

- **Chat Completions**: `POST /v1/chat/completions`
- **Embeddings**: `POST /v1/embeddings`
- **Rerank**: `POST /v1/rerank`

这确保了代码的可移植性和一致性。

## 性能优化建议

### 1. 超时设置

```python
# 短文本生成
client = UniversalLLMClient(
    base_url="...",
    api_key="...",
    timeout=30  # 30秒超时
)

# 长文本生成或复杂任务
client = UniversalLLMClient(
    base_url="...",
    api_key="...",
    timeout=120  # 120秒超时
)
```

### 2. 流式响应

对于长文本生成，使用流式响应可以提供更好的用户体验：

```python
for chunk in client.chat_stream(...):
    print(chunk, end="", flush=True)
```

### 3. 连接复用

如果需要发送多个请求，复用同一个客户端实例：

```python
client = UniversalLLMClient.from_provider("openai", api_key="...")

# 多次调用使用同一个 client
for i in range(10):
    response = client.chat_once(...)
```

## 向后兼容性

如果你的代码使用了旧的 `LmStudioClient`，无需修改：

```python
# 旧代码仍然可以工作
from src.lm_studio_client import LmStudioClient

client = LmStudioClient(
    base_url="http://localhost:1234/v1",
    api_key=None
)
```

但我们建议新代码使用 `UniversalLLMClient`：

```python
# 推荐的新代码
from src.universal_llm_client import UniversalLLMClient

client = UniversalLLMClient(
    base_url="http://localhost:1234/v1",
    api_key=None
)
```

## 常见问题

### Q: 如何切换不同的模型提供商？

A: 只需更改 `base_url` 和 `api_key` 即可：

```python
# 从 OpenAI 切换到 DeepSeek
client = UniversalLLMClient.from_provider(
    provider="deepseek",  # 改变这里
    api_key="sk-new-key"
)
```

### Q: 是否支持自定义的 OpenAI 兼容 API？

A: 是的，只需提供正确的 `base_url`：

```python
client = UniversalLLMClient(
    base_url="https://your-custom-api.com/v1",
    api_key="your-api-key"
)
```

### Q: 如何处理速率限制？

A: 捕获异常并实现重试逻辑：

```python
import time
from src.universal_llm_client import UniversalLLMError

max_retries = 3
for attempt in range(max_retries):
    try:
        response = client.chat_once(...)
        break
    except UniversalLLMError as e:
        if e.status_code == 429:  # Rate limit
            wait_time = 2 ** attempt  # 指数退避
            time.sleep(wait_time)
        else:
            raise
```

### Q: 支持哪些消息格式？

A: 标准的 OpenAI 消息格式：

```python
messages = [
    {"role": "system", "content": "系统提示"},
    {"role": "user", "content": "用户消息"},
    {"role": "assistant", "content": "助手回复"},
    {"role": "user", "content": "用户继续提问"}
]
```

## 更多资源

- [OpenAI API 文档](https://platform.openai.com/docs)
- [DeepSeek API 文档](https://platform.deepseek.com/docs)
- [通义千问 API 文档](https://help.aliyun.com/zh/dashscope/)
- [豆包 API 文档](https://www.volcengine.com/docs/82379)
- [Kimi API 文档](https://platform.moonshot.cn/docs)

---

**版本**: 1.0.0  
**最后更新**: 2026-03-09  
**兼容性**: Python 3.8+
