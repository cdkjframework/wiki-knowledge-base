<div align="center">
 <img src="assets/logo2.png" alt="维基本地知识库" width="320" />
 <p><a href="https://framewiki.com/">https://framewiki.com/</a></p>
 <p>
  <img src="https://img.shields.io/badge/License-MulanPSL2-blue" alt="License" />
  <img src="https://img.shields.io/badge/Chat-SSE-ff8c00" alt="SSE" />
  <img src="https://img.shields.io/badge/Vector-FAISS-6f42c1" alt="FAISS" />
  <img src="https://img.shields.io/badge/Status-Active-2e7d32" alt="Status" />
 </p>
</div>

# 维基本地知识库

一个本地优先的开源知识库服务，融合向量检索、重排与对话式问答能力。内置轻量 HTTP API、简洁 Web UI，并支持流式回答，适合构建交互式知识问答应用。

## 亮点

- 本地存储，FAISS 向量索引与分片持久化。
- 检索 + 重排流程，提升回答相关性。
- SSE 流式响应，适配聊天场景。
- 支持 `user_id` 与 `session_id` 的上下文会话。
- 文档导入（单文件、批量上传、目录重建）。
- 分片管理（列表、编辑、删除、重建）。
- **✨ 多模型支持**：兼容 OpenAI、DeepSeek、Qwen、Doubao、xAI、Gemini、Kimi 等主流 LLM API。

## 功能点对比表

| 功能模块         | 开源社区版         | 商业授权版（计划/已实现）         |
|------------------|-------------------|-----------------------------------|
| 本地知识库存储   | ✔️                | ✔️                                |
| FAISS 向量检索   | ✔️                | ✔️                                |
| 文档导入/批量上传 | ✔️                | ✔️                                |
| 文档分片         | 固定长度分片      | 语义分片（按内容语义自动切分）    |
| 重排（Rerank）   | ✔️                | ✔️                                |
| 多模型支持       | ✔️                | ✔️                                |
| SSE流式响应      | ✔️                | ✔️                                |
| Web UI           | ✔️                | ✔️                                |
| API接口          | ✔️                | ✔️                                |
| 用户/会话上下文  | ✔️                | ✔️                                |
| Redis高并发支持  | ✔️                | ✔️                                |
| 权限与多用户     | -                 | ✔️（企业/团队多用户与权限管理）   |
| 文档语义分片     | -                 | ✔️（按语义自动切分，提升检索效果）|
| MCP能力（模型上下文协议） | -         | ✔️（支持多模型/多后端统一调度）   |
| 插件/扩展机制    | -                 | ✔️（支持自定义插件与扩展）        |
| 企业级安全       | -                 | ✔️（更细粒度权限、审计、加密等）  |
| 商业技术支持     | -                 | ✔️                                |
| SLA服务保障      | -                 | ✔️                                |
| 专属定制开发     | -                 | ✔️                                |

## 架构

```
client (web/app.js)
 |
 v
HTTP API (src/api.py)
 |
 +-- store (src/store)
 |     +-- db (history, session)
 |     +-- redis (session)
 |
 +-- knowledge base (src/knowledge_base.py)
        +-- embeddings
        +-- FAISS index
        +-- reranker
        +-- LLM chat
```

## 快速开始

### 1) 安装依赖

```bash
pip install -r requirements.txt
```

### 自定义 FAISS GPU Wheel

如果目标环境需要自定义构建的 FAISS GPU wheel，可以使用仓库内置脚本：

```powershell
.\build_faiss_gpu_wheel.ps1 -GpuSupport CUDA
```

或者在打包部署包时一并构建并带入部署目录：

```powershell
.\build_wheel.ps1 -BuildCustomFaissGpuWheel -FaissGpuSupport CUDA
```

详细参数与前置要求见 [docs/FAISS_GPU_WHEEL.md](docs/FAISS_GPU_WHEEL.md)。

### 2) 配置

按需修改 config.json，包括数据库、Redis、模型与上下文配置。

### 3) 启动服务

```bash
python -m src.main
```

默认监听 `http://127.0.0.1:5000`。

## Web UI

访问 `http://127.0.0.1:5000/ui/` 使用内置网页端。

## API 文档

接口文档地址：

- `http://127.0.0.1:5000/docs/`

## 配置说明

config.json 关键字段：

- `knowledge_base`：Embedding/Rerank 模型、分片、检索、LM Studio。
- `db`：历史记录存储后端。
- `session`：会话 ID 存储后端（高并发推荐 redis）。
- `chat`：对话模型设置。
- `lm_studio`：LM Studio 连接与超时配置以及模型设置。
- `chat_context`：上下文开关与最大轮数。

### 配置字段说明

- `search.default_k`：默认检索条数。
- `search.max_search_results`：最大返回结果数。
- `db.backend`：历史存储后端，支持 `memory` / `mysql` / `postgresql`。
- `db.table`：历史表名。
- `db.mysql` / `db.postgresql`：数据库连接信息。
- `session.backend`：会话存储后端，支持 `memory` / `redis`。
- `session.redis`：Redis 连接信息（host/port/database/password）。
- `knowledge_base.storage.persist_dir`：知识库数据目录。
- `knowledge_base.storage.model_cache_dir`：模型缓存目录。
- `knowledge_base.embedding`：Embedding 模型及设备设置。
- `knowledge_base.rerank`：Reranker 模型及推理设置。
- `knowledge_base.chat`：对话模型设置（温度/最大 token）。
- `knowledge_base.lm_studio`：Universal LLM 连接配置（支持多种 AI 模型服务）。
- `knowledge_base.chunking`：分片大小与重叠。
- `knowledge_base.retrieval`：召回/重排权重与候选数。
- `chat_context.enabled`：是否启用上下文。
- `chat_context.max_turns`：上下文最大轮数。

## 🤖 支持的 AI 模型

本项目通过 `UniversalLLMClient` 支持多种主流 AI 模型服务：

| 提供商 | 模型示例 | 配置示例 |
|--------|---------|---------|
| **OpenAI** | GPT-4, GPT-3.5-Turbo | `base_url: https://api.openai.com/v1` |
| **DeepSeek** | deepseek-chat, deepseek-coder | `base_url: https://api.deepseek.com/v1` |
| **Qwen（通义千问）** | qwen-max, qwen-plus, qwen-turbo | `base_url: https://dashscope.aliyuncs.com/compatible-mode/v1` |
| **Doubao（豆包）** | doubao-pro-32k | `base_url: https://ark.cn-beijing.volces.com/api/v3` |
| **xAI** | grok-beta | `base_url: https://api.x.ai/v1` |
| **Google Gemini** | gemini-pro | `base_url: https://generativelanguage.googleapis.com/v1beta` |
| **Kimi（月之暗面）** | moonshot-v1-32k | `base_url: https://api.moonshot.cn/v1` |
| **LM Studio** | 本地部署模型 | `base_url: http://localhost:1234/v1` |

详细配置说明请参考：[docs/UNIVERSAL_LLM_CLIENT.md](docs/UNIVERSAL_LLM_CLIENT.md)

配置示例文件：[config.multi-provider.example.json](config.multi-provider.example.json)

## Embedding/Reranker 推荐配置

下表为 0.6B / 4B / 8B 模型的推荐部署配置，便于选择合适硬件与参数：

| 规模 | CPU | 内存 | GPU | 适用场景 | 备注 |
| --- | --- | --- | --- | --- | --- |
| 0.6B | 8 核 | 16GB | 可选（>= 6GB） | 开发/测试、中小数据 | 本地默认规模 |
| 4B | 16 核 | 32GB | 建议 >= 12GB | 生产单机、中等并发 | 建议开启 GPU |
| 8B | 24 核 | 64GB | 建议 >= 24GB | 高质量检索/高并发 | GPU 必开 |

配置建议：

- 规模越大，GPU 越关键；显存不足时会回退 CPU，响应显著变慢。
- 模型缓存与向量索引建议放 SSD，降低加载和检索延迟。
- 多实例部署时配合 Redis 作为 session 后端。

### config.json 示例

0.6B（轻量默认）：

```json
{
 "knowledge_base": {
  "embedding": {
   "model": "Qwen/Qwen3-Embedding-0.6B",
   "device": "auto",
   "local_files_only": true
  },
  "rerank": {
   "model": "Qwen/Qwen3-Reranker-0.6B",
   "use_lm_studio": false
  },
  "retrieval": {
   "candidate_multiplier": 8,
   "min_candidates": 30,
   "embed_weight": 0.35,
   "rerank_weight": 0.65
  }
 }
}
```

4B（中等规模）：

```json
{
 "knowledge_base": {
  "embedding": {
   "model": "Qwen/Qwen3-Embedding-4B",
   "device": "cuda",
   "local_files_only": true
  },
  "rerank": {
   "model": "Qwen/Qwen3-Reranker-4B",
   "use_lm_studio": false
  },
  "retrieval": {
   "candidate_multiplier": 6,
   "min_candidates": 24,
   "embed_weight": 0.4,
   "rerank_weight": 0.6
  }
 }
}
```

8B（高质量/高并发）：

```json
{
 "knowledge_base": {
  "embedding": {
   "model": "Qwen/Qwen3-Embedding-8B",
   "device": "cuda",
   "local_files_only": true
  },
  "rerank": {
   "model": "Qwen/Qwen3-Reranker-8B",
   "use_lm_studio": false
  },
  "retrieval": {
   "candidate_multiplier": 5,
   "min_candidates": 20,
   "embed_weight": 0.45,
   "rerank_weight": 0.55
  }
 }
}
```

## Session ID 唯一性

当 `session.backend=redis` 时，会话 ID 由 Redis 原子自增生成，可保证同一用户在高并发与多实例部署下不重复。若 Redis 不可用，会回退为内存生成（仅保证进程内唯一）。

## 数据与存储

- 默认存放在 `kb_store/`。
- 文档会被分片、向量化并写入 FAISS。
- 元信息以 JSON 形式保存并用于检索。

## 安全说明

- 建议仅在可信网络内开放 API。
- 使用 `encrypt_secret.py` 加密 config.json 中的密钥。

## 工具脚本

- `encrypt_secret.py`：加密配置密钥。
- `tune_threshold.py`：评估阈值扫描。

## 评估数据集格式

JSONL，每行一个样本：

```json
{"query":"reset password","positive_filenames":["account_guide.md"]}
```

可接受的正例字段：

- `positive_filenames` (list[str])
- `expected_filenames` (list[str])
- `expected_filename` (str)
- `filename` (str)

## 打包与发布

### 源码发布

- 直接打包当前仓库代码并发布到源码仓库或发行版页面。
- 建议保留 `requirements.txt` 与 `config.json` 示例。

### 构建 whl

```bash
python -m build
```

构建产物位于 `dist/` 目录中。

### 构建 exe

```bash
pyinstaller -F src/main.py -n kb-server
```

可执行文件位于 `dist/` 目录中。

### Linux 打包

```bash
pyinstaller -F src/main.py -n kb-server
```

输出可执行文件位于 `dist/`。

### macOS 打包

```bash
pyinstaller -F src/main.py -n kb-server
```

输出可执行文件位于 `dist/`。

## 问题反馈与建议

- 请优先提交 issue，写清楚系统环境、复现步骤、期望结果与实际结果。
- 如涉及日志，请脱敏后粘贴关键片段。
- 性能问题建议附上数据规模、并发量与硬件信息。

## PR 规范

- PR 需描述改动目的、影响范围与测试方式。
- 功能性变更请补充或更新文档。
- 若引入新依赖，请在说明中注明原因与替代方案。

## 贡献

欢迎提交贡献。较大的改动请先开 issue，并附上可复现步骤。

## 许可证

MulanPSL2
