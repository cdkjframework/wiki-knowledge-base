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
