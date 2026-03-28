<div align="center">
 <img src="assets/logo2.png" alt="Knowledge Base" width="320" />
 <p><a href="https://framewiki.com/">https://framewiki.com/</a></p>
 <p>
  <img src="https://img.shields.io/badge/License-MulanPSL2-blue" alt="License" />
  <img src="https://img.shields.io/badge/Chat-SSE-ff8c00" alt="SSE" />
  <img src="https://img.shields.io/badge/Vector-FAISS-6f42c1" alt="FAISS" />
  <img src="https://img.shields.io/badge/Status-Active-2e7d32" alt="Status" />
 </p>
</div>

# Knowledge Base

A local-first open-source knowledge base service integrating vector retrieval, reranking, and conversational Q&A. It features a lightweight HTTP API, a simple Web UI, and supports streaming responses, making it ideal for building interactive knowledge Q&A applications.

## Features

- Local storage with FAISS vector index and persistent sharding.
- Retrieval + rerank pipeline for improved answer relevance.
- SSE streaming responses for chat scenarios.
- Contextual sessions with `user_id` and `session_id`.
- Document import (single, batch, directory rebuild).
- Shard management (list, edit, delete, rebuild).
- **✨ Multi-model support**: Compatible with OpenAI, DeepSeek, Qwen, Doubao, xAI, Gemini, Kimi, and other mainstream LLM APIs.

## Feature Comparison Table

| Feature Module           | Community Edition      | Commercial Edition (Planned/Available)         |
|-------------------------|------------------------|-----------------------------------------------|
| Local Knowledge Storage | ✔️                     | ✔️                                            |
| FAISS Vector Retrieval  | ✔️                     | ✔️                                            |
| Document Import/Batch   | ✔️                     | ✔️                                            |
| Document Chunking       | Fixed-length chunking  | Semantic chunking (auto by content)           |
| Rerank                  | ✔️                     | ✔️                                            |
| Multi-model Support     | ✔️                     | ✔️                                            |
| SSE Streaming           | ✔️                     | ✔️                                            |
| Web UI                  | ✔️                     | ✔️                                            |
| API                     | ✔️                     | ✔️                                            |
| User/Session Context    | ✔️                     | ✔️                                            |
| Redis High Concurrency  | ✔️                     | ✔️                                            |
| Permissions & Multi-user| -                      | ✔️ (Enterprise/team, permission control)       |
| Semantic Chunking       | -                      | ✔️ (auto by semantics, better retrieval)       |
| MCP (Model Context Protocol) | -                | ✔️ (multi-model/backend unified scheduling)    |
| Plugin/Extension System | -                      | ✔️ (custom plugins/extensions)                 |
| Enterprise Security     | -                      | ✔️ (fine-grained, audit, encryption, etc.)     |
| Commercial Support      | -                      | ✔️                                            |
| SLA Guarantee           | -                      | ✔️                                            |
| Custom Development      | -                      | ✔️                                            |

## Architecture

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

## Quick Start

### 1) Install dependencies

```bash
pip install -r requirements.txt
```

### Custom FAISS GPU Wheel

If you need a custom-built FAISS GPU wheel, use the provided script:

```powershell
.\build_faiss_gpu_wheel.ps1 -GpuSupport CUDA
```

Or build and include it during deployment:

```powershell
.\build_wheel.ps1 -BuildCustomFaissGpuWheel -FaissGpuSupport CUDA
```

See [docs/FAISS_GPU_WHEEL.md](docs/FAISS_GPU_WHEEL.md) for details.

### 2) Configuration

Edit `config.json` as needed (database, Redis, models, context, etc).

### 3) Start the service

```bash
python -m src.main
```

Default: `http://127.0.0.1:5000`

## Web UI

Visit `http://127.0.0.1:5000/ui/` for the built-in web interface.

## API Documentation

- `http://127.0.0.1:5000/docs/`

## Configuration Overview

Key fields in `config.json`:

- `knowledge_base`: Embedding/Rerank models, sharding, retrieval, LM Studio.
- `db`: History storage backend.
- `session`: Session ID backend (Redis recommended for high concurrency).
- `chat`: Chat model settings.
- `lm_studio`: LM Studio connection and timeout.
- `chat_context`: Context switch and max turns.

### Field Details

- `search.default_k`: Default retrieval count.
- `search.max_search_results`: Max results.
- `db.backend`: History backend (`memory` / `mysql` / `postgresql`).
- `db.table`: History table name.
- `db.mysql` / `db.postgresql`: DB connection info.
- `session.backend`: Session backend (`memory` / `redis`).
- `session.redis`: Redis connection info.
- `knowledge_base.storage.persist_dir`: Data directory.
- `knowledge_base.storage.model_cache_dir`: Model cache directory.
- `knowledge_base.embedding`: Embedding model/device.
- `knowledge_base.rerank`: Reranker model/inference.
- `knowledge_base.chat`: Chat model (temperature/max tokens).
- `knowledge_base.lm_studio`: Universal LLM connection.
- `knowledge_base.chunking`: Chunk size/overlap.
- `knowledge_base.retrieval`: Retrieval/rerank weights and candidates.
- `chat_context.enabled`: Enable context.
- `chat_context.max_turns`: Max context turns.

## 🤖 Supported AI Models

Supported via `UniversalLLMClient`:

| Provider      | Example Models         | Example Config                        |
|---------------|-----------------------|---------------------------------------|
| **OpenAI**    | GPT-4, GPT-3.5-Turbo  | `base_url: https://api.openai.com/v1` |
| **DeepSeek**  | deepseek-chat, coder  | `base_url: https://api.deepseek.com/v1` |
| **Qwen**      | qwen-max, turbo, plus | `base_url: https://dashscope.aliyuncs.com/compatible-mode/v1` |
| **Doubao**    | doubao-pro-32k        | `base_url: https://ark.cn-beijing.volces.com/api/v3` |
| **xAI**       | grok-beta             | `base_url: https://api.x.ai/v1`       |
| **Gemini**    | gemini-pro            | `base_url: https://generativelanguage.googleapis.com/v1beta` |
| **Kimi**      | moonshot-v1-32k       | `base_url: https://api.moonshot.cn/v1`|
| **LM Studio** | Local models          | `base_url: http://localhost:1234/v1`  |

See [docs/UNIVERSAL_LLM_CLIENT.md](docs/UNIVERSAL_LLM_CLIENT.md) for details.

Example config: [config.multi-provider.example.json](config.multi-provider.example.json)

## Embedding/Reranker Recommended Configurations

| Size | CPU   | RAM   | GPU (VRAM) | Scenario         | Note           |
|------|-------|-------|------------|------------------|----------------|
| 0.6B | 8C    | 16GB  | Optional 6GB+ | Dev/test, small | Default        |
| 4B   | 16C   | 32GB  | 12GB+      | Production, med. | GPU advised    |
| 8B   | 24C   | 64GB  | 24GB+      | High QPS/quality | GPU required   |

- Larger models need GPU; fallback to CPU is slow.
- Use SSD for model cache and vector index.
- Use Redis for session backend in multi-instance deployments.

### Example config.json

(See original for JSON examples.)

## Session ID Uniqueness

With `session.backend=redis`, session IDs are generated atomically in Redis for uniqueness across instances.

## Data & Storage

- Default: `kb_store/`
- Documents are chunked, vectorized, and stored in FAISS.
- Metadata is saved as JSON for retrieval.

## Security

- Expose API only in trusted networks.
- Use `encrypt_secret.py` to encrypt secrets in config.json.

## Utility Scripts

- `encrypt_secret.py`: Encrypt config secrets.
- `tune_threshold.py`: Evaluate threshold.

## Evaluation Dataset Format

JSONL, one sample per line:

```json
{"query":"reset password","positive_filenames":["account_guide.md"]}
```

Accepted fields: `positive_filenames`, `expected_filenames`, `expected_filename`, `filename`.

## Packaging & Release

- Source: Package and release code, keep `requirements.txt` and config samples.
- Build wheel: `python -m build` (output in `dist/`)
- Build exe: `pyinstaller -F src/main.py -n kb-server` (output in `dist/`)
- Linux/macOS: Same as above.

## Feedback & Contribution

- Please file issues with environment, steps, expected/actual results.
- PRs: Describe purpose, scope, and testing. Update docs for features.
- New dependencies: explain reason/alternatives.
- Large changes: open an issue first.

## License

MulanPSL2
