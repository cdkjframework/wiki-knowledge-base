# 更新日志 - Universal LLM Client

## 版本 1.1.0 - 2026-03-09

### 🎉 新增功能

#### 1. Universal LLM Client（通用大语言模型客户端）

新增 `UniversalLLMClient` 类，支持多种主流 AI 模型服务提供商：

**支持的提供商：**
- ✅ **OpenAI** - GPT-4, GPT-3.5-Turbo 等
- ✅ **DeepSeek** - deepseek-chat, deepseek-coder
- ✅ **Qwen / 通义千问** - qwen-max, qwen-plus, qwen-turbo
- ✅ **Doubao / 豆包** - doubao-pro-32k（字节跳动）
- ✅ **xAI** - grok-beta（Grok 模型）
- ✅ **Google Gemini** - gemini-pro, gemini-ultra
- ✅ **Kimi / Moonshot** - moonshot-v1-32k（月之暗面）
- ✅ **LM Studio** - 本地部署的开源模型

**核心特性：**
- 统一的 API 接口，兼容 OpenAI 格式
- 自动提供商检测
- 便捷的 `from_provider()` 工厂方法
- 支持流式和非流式对话
- 支持文本嵌入（Embeddings）
- 支持文档重排序（Reranking）
- 灵活的错误处理机制
- 自定义请求头支持

**新增文件：**
- `src/universal_llm_client.py` - 通用 LLM 客户端实现
- `docs/UNIVERSAL_LLM_CLIENT.md` - 详细使用文档
- `config.multi-provider.example.json` - 多提供商配置示例

### 🔄 向后兼容性

- ✅ 保持 `LmStudioClient` 完全向后兼容
- ✅ 现有代码无需修改即可继续使用
- ✅ `LmStudioClient` 现在是 `UniversalLLMClient` 的别名

### 📝 文档更新

- 新增详细的 Universal LLM Client 使用指南
- 更新 README.md，添加支持的模型列表
- 新增多提供商配置示例文件
- 提供各提供商的配置示例和最佳实践

### 🛠️ 技术改进

#### API 兼容性
- 标准化 OpenAI 兼容的 API 格式
- 支持多种响应格式的智能解析
- 特殊提供商（如 Gemini）的适配处理

#### 错误处理
- 新增 `UniversalLLMError` 异常类
- 提供详细的错误信息和状态码
- 支持优雅的错误恢复

#### 代码质量
- 完整的类型注解
- 详细的代码注释和文档字符串
- 遵循 Python 最佳实践

### 📋 使用示例

#### 快速开始

```python
from src.universal_llm_client import UniversalLLMClient

# 方法 1: 使用 provider 名称
client = UniversalLLMClient.from_provider(
    provider="openai",
    api_key="sk-your-api-key"
)

# 方法 2: 直接指定 base_url
client = UniversalLLMClient(
    base_url="https://api.openai.com/v1",
    api_key="sk-your-api-key"
)

# 对话
response = client.chat_once(
    messages=[{"role": "user", "content": "Hello!"}],
    model="gpt-4"
)
```

#### 切换提供商

```python
# OpenAI
client = UniversalLLMClient.from_provider("openai", api_key="sk-...")

# DeepSeek
client = UniversalLLMClient.from_provider("deepseek", api_key="sk-...")

# Qwen
client = UniversalLLMClient.from_provider("qwen", api_key="sk-...")

# Kimi
client = UniversalLLMClient.from_provider("kimi", api_key="sk-...")
```

### 🔧 配置更新

#### config.json 新增字段

```json
{
  "knowledge_base": {
    "lm_studio": {
      "provider": "qwen",
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "api_key": "sk-your-api-key",
      "chat_model": "qwen-max",
      "timeout": 60
    }
  }
}
```

### 🚀 迁移指南

#### 从 LmStudioClient 迁移

**不需要任何更改！** 现有代码继续工作：

```python
# 旧代码（仍然有效）
from src.lm_studio_client import LmStudioClient

client = LmStudioClient(
    base_url="http://localhost:1234/v1",
    api_key=None
)
```

**推荐的新代码：**

```python
# 新代码（推荐）
from src.universal_llm_client import UniversalLLMClient

client = UniversalLLMClient(
    base_url="http://localhost:1234/v1",
    api_key=None
)

# 或使用更简洁的方式
client = UniversalLLMClient.from_provider(
    provider="lm_studio",
    api_key=None
)
```

### 📊 性能优化

- 保持与原 `LmStudioClient` 相同的性能特性
- 高效的 HTTP 请求处理
- 流式响应支持，降低延迟
- 向量归一化优化

### 🔒 安全性

- 支持 API key 认证
- 支持自定义请求头
- 安全的错误消息处理
- 敏感信息保护

### 🐛 已知问题

无

### 📚 相关资源

- [Universal LLM Client 文档](docs/UNIVERSAL_LLM_CLIENT.md)
- [配置示例](config.multi-provider.example.json)
- [OpenAI API 文档](https://platform.openai.com/docs)
- [DeepSeek API 文档](https://platform.deepseek.com/docs)
- [通义千问 API 文档](https://help.aliyun.com/zh/dashscope/)

### 🙏 致谢

感谢所有贡献者和用户的支持！

---

## 历史版本

### 版本 1.0.0
- 初始版本
- LM Studio 客户端支持
- 基础的聊天、嵌入和重排序功能

---

**下一步计划：**
- [ ] 添加更多提供商支持（Claude, Cohere 等）
- [ ] 支持函数调用（Function Calling）
- [ ] 支持视觉模型（Vision Models）
- [ ] 添加速率限制和重试机制
- [ ] 性能监控和日志增强
- [ ] 批量请求优化

**反馈和建议：**
欢迎通过 Issue 或 Pull Request 提供反馈和建议！
