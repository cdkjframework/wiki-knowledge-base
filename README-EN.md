<div align="center">
 <img src="assets/logo2.png" alt="WIKI Knowledge Base" width="320" />
 <p><a href="https://framewiki.com/">https://framewiki.com/</a></p>
 <p>
  <img src="https://img.shields.io/badge/License-MulanPSL2-blue" alt="License" />
  <img src="https://img.shields.io/badge/Chat-SSE-ff8c00" alt="SSE" />
  <img src="https://img.shields.io/badge/Vector-FAISS-6f42c1" alt="FAISS" />
  <img src="https://img.shields.io/badge/Status-Active-2e7d32" alt="Status" />
 </p>
</div>

# WIKI Knowledge Base

A local-first open-source knowledge base service that combines vector retrieval, reranking, and conversational Q&A. It ships with a lightweight HTTP API and a built-in Web console, supports SSE streaming, and is ideal for private knowledge Q&A applications.

## Highlights

- Local private storage with persistent vector indexing and sharding.
- Retrieval + rerank pipeline for better answer relevance.
- SSE streaming responses for chat scenarios.
- Contextual sessions via `user_id` and `session_id`.
- Document ingestion (single, batch, directory rebuild).
- Chunk management (view, edit, delete, rebuild).
- Multi-model support for OpenAI, DeepSeek, Qwen, Doubao, xAI, Gemini, Kimi, LM Studio, and more.

## Feature Comparison

| Feature | Open-Source Edition | Commercial Edition (Planned/Available) |
| --- | --- | --- |
| Local knowledge storage | ✅ | ✅ |
| FAISS vector retrieval | ✅ | ✅ |
| Document import/batch upload | ✅ | ✅ |
| Document recognition | Text-only | DOC support + OCR for images/PDF/OFD (paddleOCR or Qwen/Qwen2-VL-2B-Instruct) |
| Document chunking | Fixed-length chunking | Semantic chunking (auto by content) |
| Rerank | ✅ | ✅ |
| Multi-model support | ✅ | ✅ |
| SSE streaming | ✅ | ✅ |
| Web UI | ✅ | ✅ |
| API | ✅ | ✅ |
| User/session context | ✅ | ✅ |
| Redis high concurrency | ✅ | ✅ |
| Permissions & multi-user | - | ✅ (enterprise/team, permission control) |
| Semantic chunking | - | ✅ (auto by semantics, better retrieval) |
| MCP (Model Context Protocol) | - | ✅ (multi-model/backend unified scheduling) |
| Plugin/extension system | - | ✅ (custom plugins/extensions) |
| Enterprise security | - | ✅ (fine-grained access, audit, encryption, etc.) |
| Commercial support | - | ✅ |
| SLA guarantee | - | ✅ |
| Custom development | - | ✅ |

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

### 2) Configuration

Edit `config.json` as needed (database, Redis, models, and context settings).

### 3) Start the service

```bash
python -m src.main
```

Default: `http://127.0.0.1:5000`

## Web Console

Visit `http://127.0.0.1:5000/ui/` to use the built-in Web UI.

Feature overview (from `web/`):

- Chat: new sessions, history, SSE streaming answers, deep-think toggle, copy answers, source viewer.

**Chat**
![](assets/chat.png)

- Knowledge base: add text docs, upload files, batch upload, list filters, chunk manager (edit/delete/rebuild), retrieval settings, stats.

**Knowledge Base**
![](assets/kb.png)

**Chunk Management**
![](assets/kb-fp.png)

- Model management: add/edit configs, enable/disable, set default, connectivity test, bootstrap presets.

**Model Management**
![](assets/model.png)

Entry points:

- `GET /ui/` Chat
- `GET /ui/kb.html` Knowledge base
- `GET /ui/model.html` Model management

## API Documentation

- Online docs: `http://127.0.0.1:5000/api-docs` or `http://127.0.0.1:5000/docs/`
- Repo API guide: `docs/API-EN.md`
- Chinese API guide: `docs/API.md`

## Supported Document Formats

| Format | Open-Source Edition | Commercial Edition | Notes |
| --- | --- | --- | --- |
| docx | ✅ | ✅ | Text parsing |
| doc | - | ✅ | Commercial-only |
| xls | ✅ | ✅ | Text parsing |
| xlsx | ✅ | ✅ | Text parsing |
| txt | ✅ | ✅ | Text parsing |
| log | ✅ | ✅ | Text parsing |
| images | - | ✅ | OCR in commercial edition |
| PDF | Text-only | ✅ | OCR in commercial edition |
| OFD | Text-only | ✅ | OCR in commercial edition |

**API Docs**
![](assets/api.png)

## Configuration Overview

Common `config.json` fields:

- `knowledge_base`: Embedding/Rerank models and retrieval settings.
- `db`: History backend (`memory` / `mysql` / `postgresql`).
- `session`: Session backend (`memory` / `redis`).
- `chat_context`: Context switch and max turns.
- `lm_studio`: LM Studio connection and timeout.

## Supported AI Models

Supported via `UniversalLLMClient`:

| Provider | Example Models | Example Config |
| --- | --- | --- |
| OpenAI | GPT-4, GPT-3.5-Turbo | `base_url: https://api.openai.com/v1` |
| DeepSeek | deepseek-chat, deepseek-coder | `base_url: https://api.deepseek.com/v1` |
| Qwen | qwen-max, qwen-plus | `base_url: https://dashscope.aliyuncs.com/compatible-mode/v1` |
| Doubao | doubao-pro-32k | `base_url: https://ark.cn-beijing.volces.com/api/v3` |
| xAI | grok-beta | `base_url: https://api.x.ai/v1` |
| Gemini | gemini-pro | `base_url: https://generativelanguage.googleapis.com/v1beta` |
| Kimi | moonshot-v1-32k | `base_url: https://api.moonshot.cn/v1` |
| LM Studio | Local models | `base_url: http://localhost:1234/v1` |

See `config.multi-provider.example.json` for a full example.

## Optional Parsing and OCR

Install `requirements.optional-parser.txt` when you need OCR or PDF Marker features.

## Data & Storage

- Default data directory: `kb_store/`
- Documents are chunked, vectorized, and stored in FAISS
- Metadata is saved as JSON for retrieval

## Security

- Expose API only in trusted networks.
- Use `encrypt_secret.py` to protect secrets in `config.json`.

## Utility Scripts

- `encrypt_secret.py`: Encrypt secrets
- `tune_threshold.py`: Threshold evaluation

## Build & Release

```bash
python -m build
```

Artifacts are created in `dist/`.

## Contribution

Issues and PRs are welcome. Update docs when features change.

## License

MulanPSL2
