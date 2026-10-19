# 运行配置目录（UTF-8）
#
# 加载优先级：
# 1. 环境变量 KB_CONFIG_PATH
# 2. conf/config.json
# 3. 仓库根目录 config.json（兼容旧布局）
#
# 可选覆盖：设置 KB_ENV=dev|prod 时合并 conf/config.{KB_ENV}.json
# 请优先编辑本目录下的配置；根目录 config.json 仅作兼容保留。
#
# 商业 License（仅商业版）：
# - 产品路径：控制台上传厂商下发的证书文件（.lic），接口 POST /api/license（multipart field=file）
# - 本地落盘：conf/license.key（已 gitignore，勿提交）；或 KB_LICENSE_PATH / KB_LICENSE_KEY
# - HMAC 密钥：KB_LICENSE_HMAC_SECRET（生产必填；未设则用演示密钥）
# - 本地调试旁路：KB_LICENSE_DEV_BYPASS=1（切勿用于生产）
# - 签发证书：KB_EDITION=commercial python -m src.commercial.cli --issue --customer 客户 --cert out.lic
# - 本机立刻生效可加 --write（写入 conf/license.key）
#
# 检索评测集（KB-10，社商共有）：
# - 默认题集：conf/eval/golden-default.jsonl（针对本仓库 docs/ 语料；换语料请整体替换）
# - 题集覆盖：KB_EVAL_DATASET 指向自己的 JSONL
# - 报告目录：默认 kb_store/eval/（已 gitignore），可用 KB_EVAL_REPORT_DIR 覆盖
# - 跑分：python -m src.eval.cli；只校验题集格式用 python -m src.eval.cli --validate
# - 详见 docs/检索评测集使用说明.md
#
# 指标看板（KB-11，社商共有）：
# - 数据源：上面评测报告目录里的 latest.json；没跑过评测则看板显示空态，不编假数
# - 接口：GET /api/metrics（KPI + 最近一次 + 历史）、GET /api/metrics/reports（历史列表）
# - 验收线覆盖（可选）：config.json 里加
#   "metrics": { "targets": { "recall@5": 0.85, "recall@3": 0.75, "ndcg@10": 0.70, "latency_p95_ms": 300 } }
#
# 检索配置（KB-20，社商共有，v1.1.2+）：
# - 面板：控制台「知识库管理 → 检索与分片」；接口 GET/PUT /api/kb/settings
# - 可热更新：search.default_k / max_search_results / min_source_similarity，
#   knowledge_base.chunking.size / overlap（分片仅对新导入或重建生效）
# - 默认建议：default_k=5、max_search_results=10、min_source_similarity=0（关闭硬阈）
# - 评测：python -m src.eval.cli 省略 --top-k 时跟当前 default_k（并盖住指标所需 k）
#
# 混合检索（KB-01，社商共有，v1.1.3）：
# - 默认开启：search.hybrid_enabled=true、search.rrf_k=60（亦可写在 knowledge_base.retrieval）
# - 流程：BM25 字面召回 ∪ 向量 ANN → RRF 融合 → Rerank（max_rerank_candidates 默认 8）；单通道失败自动降级
# - 面板可关 hybrid_enabled 回退「仅向量 + 重排」；rrf_k 越大排名差影响越小
# - 检索 p95<300ms：验收测混合召回路径（eval --no-rerank --warmup）；交叉编码器重排依赖 GPU/远端才宜计入端到端
#
# Windows iGPU DirectML（可选，AMD/Intel/NVIDIA 核显）：
# - 主环境 torch>=2.7 与 torch-directml（锁 torch 2.4.1）冲突，请用独立 venv：
#     python -m venv .venv-dml
#     .venv-dml\Scripts\pip install -r requirements.directml.txt
#     .venv-dml\Scripts\pip install -r requirements.common.txt
#     set KB_DEVICE=directml
#     .venv-dml\Scripts\python -m src.main
# - 或在 conf 里 knowledge_base.embedding.device = "directml"
# - 探测：python -c "from src.device_runtime import probe_directml; print(probe_directml())"
# - 本机已验证：ORT DmlExecutionProvider + torch-directml 可见「AMD Radeon 890M」
