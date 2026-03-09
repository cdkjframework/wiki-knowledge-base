# Windows 打包与部署指南

## 📦 项目打包完成

已为你的 knowledge-base 项目生成了完整的 Windows 部署包。

## 🚀 快速开始

### 方式一：使用命令提示符 (推荐)

```cmd
cd dist
setup.ps1
run.bat
```

### 方式二：使用 PowerShell

```powershell
cd dist
.\setup.ps1
.\run.ps1
```

## 📋 文件说明

打包后 `dist/` 目录包含：

| 文件/目录 | 说明 |
|-----------|------|
| `src/` | 项目源代码 |
| `web/` | Web UI 前端文件 |
| `config.json` | 配置文件（数据库、Redis等） |
| `requirements.txt` | Python 依赖包列表 |
| `run.bat` | Windows 批处理启动脚本 |
| `run.ps1` | PowerShell 启动脚本 |
| `setup.ps1` | 初始化脚本（创建虚拟环境，安装依赖） |
| `MANIFEST.json` | 构建信息清单 |
| `BUILD_README.md` | 详细部署说明 |

## ⚙️ 初始化步骤

首次使用时执行 `setup.ps1`：

1. **创建虚拟环境** - 在 `.venv` 文件夹中创建 Python 虚拟环境
2. **激活虚拟环境** - 自动激活虚拟环境
3. **安装依赖** - 根据 `requirements.txt` 安装所有 Python 包

```powershell
.\setup.ps1
```

## ▶️ 启动服务

初始化完成后，使用以下任一方式启动服务：

**选项 A - 批处理文件（推荐）：**
```cmd
run.bat
```

**选项 B - PowerShell：**
```powershell
.\run.ps1
```

## 🌐 访问服务

服务启动后，访问以下地址：

- **Web UI**: http://127.0.0.1:5000/ui/
- **API 文档**: http://127.0.0.1:5000/docs/
- **服务地址**: http://127.0.0.1:5000

## 🔧 配置说明

编辑 `config.json` 配置以下内容：

### 数据库配置
```json
"db": {
  "backend": "mysql",  // 或 "postgresql"
  "mysql": {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "your_password",
    "database": "knowledge_base"
  }
}
```

### Redis 会话存储
```json
"session": {
  "backend": "redis",
  "redis": {
    "host": "127.0.0.1",
    "port": 6379,
    "password": ""
  }
}
```

### 模型配置
```json
"knowledge_base": {
  "embedding": {
    "model": "Qwen/Qwen3-Embedding-0.6B",
    "device": "auto"
  },
  "rerank": {
    "model": "Qwen/Qwen3-Reranker-0.6B"
  }
}
```

## 🛠️ 故障排查

### 问题：无法找到虚拟环境

**解决方案：**
1. 确保 Python 3.8+ 已安装：`python --version`
2. 删除 `.venv` 文件夹
3. 重新运行 `setup.ps1`

### 问题：依赖安装失败

**解决方案：**
1. 检查网络连接
2. 升级 pip：`python -m pip install --upgrade pip`
3. 重新运行 `setup.ps1`

### 问题：端口被占用

**解决方案：**
1. 编辑 `config.json` 更改端口号
2. 或关闭占用该端口的其他应用

### 问题：数据库连接失败

**解决方案：**
1. 确保 MySQL/PostgreSQL 服务正在运行
2. 验证 `config.json` 中的数据库连接信息
3. 检查防火墙设置

## 📊 构建脚本参数

### PowerShell 版本 (build.ps1)

```powershell
# 基础构建
.\build.ps1

# 清理并重新构建
.\build.ps1 -Clean

# 指定输出目录
.\build.ps1 -OutputDir "./my-dist"

# 指定版本号
.\build.ps1 -Version "2.0.0"

# 组合使用
.\build.ps1 -Clean -OutputDir "./release" -Version "2.0.0"
```

### 批处理版本 (build.bat)

```cmd
REM 基础构建
build.bat

REM 清理并重新构建
build.bat --clean

REM 指定输出目录
build.bat --output my-dist

REM 指定版本号
build.bat --version 2.0.0
```

## 📝 项目结构说明

```
knowledge-base/
├── src/                          # 源代码
│   ├── main.py                  # 应用入口
│   ├── api.py                   # HTTP API 服务
│   ├── knowledge_base.py         # 知识库核心逻辑
│   ├── chat_model.py             # 聊天模型
│   ├── lm_studio_client.py       # LM Studio 客户端
│   ├── logger_config.py          # 日志配置
│   └── store/                    # 数据存储层
│       ├── memory_store.py       # 内存存储
│       ├── db/                   # 数据库存储
│       └── redis/                # Redis 缓存
├── web/                          # Web UI
│   ├── index.html               # 主页
│   ├── app.js                   # 前端逻辑
│   └── app.css                  # 样式表
├── config.json                  # 配置文件
├── requirements.txt             # Python 依赖
└── dist/                        # 打包输出目录 (自动生成)
```

## 🔐 安全建议

1. **修改密钥** - 更改 `config.json` 中的加密密钥
2. **数据库密码** - 使用强密码，不要在代码中存储明文密码
3. **API 密钥** - 为 API 访问设置密钥认证
4. **防火墙** - 仅在内部网络中暴露服务

## 📚 更多信息

- 详细 API 文档：见 `docs/API.html`
- 数据库迁移：见 `docs/DATABASE_MIGRATION.md`
- 日志配置：见 `docs/LOGGING.md`
- 完整说明：见 `README.md` 和 `dist/BUILD_README.md`

## 💡 提示

- 首次启动时模型会自动下载和缓存，可能需要较长时间
- 建议在网络稳定的环境下进行初始化
- 可以在后台持续运行服务，支持多用户并发访问
- 查看日志输出了解系统运行状态

---

**构建日期**: 2026-03-09  
**项目**: knowledge-base  
**版本**: 1.0.0  
**平台**: Windows
