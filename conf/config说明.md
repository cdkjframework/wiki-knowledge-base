# config.json 配置项说明

本文件为知识库系统的主配置文件，采用分层嵌套结构。各节点及属性说明如下：

## 根节点

- `api_key_cipher`：API 密钥加密内容（字符串）
- `db_password_cipher`：数据库密码加密内容（字符串）
- `KB_PROJECT_ROOT`：项目根目录路径（字符串）

## server

- `host`：服务监听地址，通常为 0.0.0.0（字符串）
- `port`：服务监听端口（整数）

## search

- `default_k`：默认返回的检索结果数（整数）
- `max_search_results`：最大检索结果数（整数）
- `min_source_similarity`：最小相似度阈值（小数，0~1）

## db

- `backend`：数据库类型（如 mysql、postgresql）（字符串）
- `auto_create_database`：是否自动建库（布尔）
- `table`：主表名（字符串）
- `mysql` / `postgresql`：各自数据库连接配置
  - `host`：数据库主机
  - `port`：端口
  - `user`：用户名
  - `password`：密码
  - `database`：数据库名
  - `connect_timeout`：连接超时（秒）
  - `options`：连接选项，仅 postgresql 生效

## session

- `backend`：会话存储类型（如 redis）（字符串）
- `redis`：Redis 连接配置
  - `host`：主机
  - `port`：端口
  - `database`：数据库编号
  - `password`：密码

## knowledge_base

- `preload`：模型预加载设置
  - `embedding`：是否预加载 embedding 模型（布尔）
  - `reranker`：是否预加载 reranker 模型（布尔）
- `memory`：内存与显存管理
  - `release_gpu_cache`：是否主动释放 GPU 显存（布尔）
  - `unload_models_idle_seconds`：模型空闲多少秒后自动释放（整数，0 表示不自动释放）
- `auto_download_missing_models`：缺失模型是否自动下载（布尔）
- `storage`：存储路径配置
  - `persist_dir`：知识库存储目录
  - `model_cache_dir`：模型缓存目录
- `embedding`：向量模型配置
  - `model`：embedding 模型名
  - `dimension`：向量维度（整数或 null 自动）
  - `device`：推理设备（auto/cpu/cuda）
  - `local_files_only`：仅本地模型（布尔）
  - `use_lm_studio`：是否用 LM Studio 提供 embedding（布尔）
- `rerank`：重排序模型配置
  - `model`：reranker 模型名
  - `use_lm_studio`：是否用 LM Studio rerank（布尔）
- `chat`：对话模型配置
  - `model_type`：模型类型（如 qwen）
  - `model`：chat 模型名
  - `use_lm_studio`：是否用 LM Studio 聊天（布尔）
  - `local_files_only`：仅本地模型（布尔）
  - `temperature`：采样温度（小数）
  - `max_tokens`：最大生成 token 数（整数）
  - `system_intro`：系统介绍词（字符串）
- `lm_studio`：UniversalLLMClient 运行时配置
  - 说明：该节点当前底层基于 OpenAI Python SDK
  - 适用范围：不仅可用于 LM Studio，也可用于 OpenAI、DeepSeek、Qwen、Kimi、OneAPI、vLLM 等 OpenAI 兼容服务
  - `provider` / `model_type`：提供商类型，用于提供商识别、默认 endpoint 推断与兼容处理
  - `base_url`：服务地址；若已明确填写，则优先使用该地址
  - `api_key`：API 密钥，本地网关通常可留空
  - `chat_model`：chat 模型名
  - `timeout`：超时时间（秒）
  - 本地网关注意：如果连接的是本地 OpenAI 兼容网关，`base_url` 应填写本地地址，例如 `http://127.0.0.1:1234` 或 `http://127.0.0.1:1234/v1`；即使模型来自 qwen 或 deepseek，也不要把本地地址改成对应云厂商地址
- `chunking`：文本分块参数
  - `size`：分块大小（整数）
  - `overlap`：分块重叠（整数）
- `retrieval`：检索参数
  - `candidate_multiplier`：候选倍数（整数）
  - `min_candidates`：最小候选数（整数）
  - `embed_weight`：embedding 检索权重（小数）
  - `rerank_weight`：rerank 权重（小数）
- `ocr`：OCR 配置
  - `enabled`：是否启用 OCR（布尔）
  - `engine`：OCR 引擎，可选 `llm` 或 `paddleocr`
  - `local_files_only`：是否仅从本地缓存加载 OCR 大模型（布尔）
  - `auto_download_missing_models`：缺失 OCR 模型时是否自动下载（布尔）
  - `auto_install_missing_packages`：缺失 OCR 依赖时是否尝试自动安装（布尔）
  - `release_after_use`：每次识别后是否释放 OCR 引擎资源（布尔）
  - `pdf_ocr_dpi`：PDF 渲染为图片时的 DPI
  - `pdf_ocr_max_pages`：PDF OCR 最大页数，0 表示不限制
  - `pdf_ocr_discard_garbage`：PDF OCR 时是否丢弃疑似乱码文本（布尔）
  - `llm`：视觉大模型 OCR 配置
    - 说明：llm 专属模型参数统一放在该子节点，`ocr` 顶层不再重复配置这些字段
    - `model_name`：视觉大模型名称，当前支持 Qwen2-VL
    - `prompt`：OCR 提示词
    - `device`：推理设备（cpu/cuda/auto）
    - `dtype`：模型精度（auto/fp16/bf16/fp32）
    - `max_new_tokens`：最大生成 token 数
    - `min_pixels` / `max_pixels`：图像像素范围控制
  - `paddleocr`：PaddleOCR 配置
    - `lang`：识别语言，例如 `ch`、`en`
    - `use_textline_orientation`：新版 PaddleOCR 推荐参数，是否启用文本行方向识别
    - `use_angle_cls`：旧版兼容参数，项目仍兼容读取
    - `show_log`：是否输出 PaddleOCR 日志；若当前 PaddleOCR 版本不支持，该参数会被自动忽略
    - 依赖说明：除 `paddleocr` 外，还需要安装 `paddlepaddle`

## UniversalLLMClient 与 SDK 对应关系

- `knowledge_base.lm_studio` 节点由 `UniversalLLMClient` 读取
- `UniversalLLMClient` 当前基于 OpenAI Python SDK
- `chat_once` 对应 `OpenAI.chat.completions.create()`
- `chat_stream` 对应 `OpenAI.chat.completions.create(stream=True)`
- `embed_texts` 对应 `OpenAI.embeddings.create()`
- `rerank_scores` 对应通用 `OpenAI.post('/rerank')` 兼容端点

## OCR 引擎选择建议

- `engine=llm`：适合复杂版面、图文混排、需要结构化 Markdown 输出的场景
- `engine=paddleocr`：适合纯文本 OCR、运行开销更低的场景
- 若要求严格本地加载，请保持 `local_files_only=true`

## chat_context

- `enabled`：是否启用上下文记忆（布尔）
- `max_turns`：最大上下文轮数（整数）

## logging

- `level`：日志级别（如 INFO、DEBUG）（字符串）
- `keep_days`：日志保留天数（整数）
- `enable_debug`：是否启用 debug 日志（布尔）
- `console_level`：控制台日志级别（字符串）

---

> 注：如需详细解释某一节点或属性，请告知具体名称。
