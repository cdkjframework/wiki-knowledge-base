# Windows 服务启动 - 实现完成

## 📋 已生成的文件

### 核心服务文件
| 文件 | 说明 |
|------|------|
| `src/windows_service.py` | Windows 服务的 Python 实现 |
| `manage_service.ps1` | PowerShell 服务管理脚本 |
| `manage_service.bat` | 批处理服务管理脚本 |

### 文档指南
| 文件 | 说明 |
|------|------|
| `QUICK_START.md` | 5分钟快速开始指南 |
| `WINDOWS_SERVICE_GUIDE.md` | 详细的 Windows 服务使用指南 |
| `WINDOWS_DEPLOYMENT_GUIDE.md` | 部署打包指南 |

### 依赖更新
- ✅ `requirements.txt` 已添加 `pywin32>=307`

---

## 🚀 立即开始使用

### 快速 3 步启动

**第 1 步：以管理员身份打开 PowerShell**
```
按 Win + X → 选择"Windows PowerShell（管理员）"
```

**第 2 步：执行安装命令**
```powershell
cd D:\Project\code\py\knowledge-base
.\manage_service.ps1 -Command install
```

**第 3 步：启动服务**
```powershell
.\manage_service.ps1 -Command start
```

✅ 完成！访问 http://127.0.0.1:5000/ui/

---

## 📖 文档速查

### 我想...

| 需求 | 说明 | 参考文档 |
|------|------|---------|
| 快速上手 | 5 分钟内启动服务 | `QUICK_START.md` |
| 详细指南 | 了解所有服务命令和配置 | `WINDOWS_SERVICE_GUIDE.md` |
| 打包部署 | 打包项目为可部署版本 | `WINDOWS_DEPLOYMENT_GUIDE.md` |
| 项目概览 | 了解项目结构和功能 | `README.md` |

---

## 🎯 核心功能

### ✨ Windows 服务管理
```powershell
# 查看所有命令
.\manage_service.ps1 -Command help

# 安装（首次）
.\manage_service.ps1 -Command install

# 启动/停止/重启
.\manage_service.ps1 -Command start
.\manage_service.ps1 -Command stop
.\manage_service.ps1 -Command restart

# 查看状态
.\manage_service.ps1 -Command status

# 卸载
.\manage_service.ps1 -Command uninstall
```

### 🔄 批处理支持
同样支持使用 `.bat` 脚本在 CMD 中执行：
```cmd
manage_service.bat install
manage_service.bat start
manage_service.bat status
```

### 🖥️ Windows 服务特性
- ✅ 自动启动（可配置）
- ✅ 后台运行
- ✅ 系统启动时自动启动
- ✅ 自动重启失败的服务
- ✅ 日志记录到 Windows 事件查看器

---

## 📊 服务信息

```
服务名称：        KnowledgeBase
显示名称：        Knowledge-Base Service
描述：           Local-first knowledge base service with vector search and conversational QA
启动类型：        手动（可改为自动）
账户：           Local System
状态：           默认为停止（install 后）
```

---

## 🔐 权限要求

| 操作 | 权限要求 |
|------|---------|
| 安装服务 | 管理员 |
| 启动/停止服务 | 管理员 |
| 卸载服务 | 管理员 |
| 查看状态 | 管理员 |
| 使用应用 | 无特殊要求 |

---

## ✅ 验证清单

安装后，验证以下项目：

- [ ] 以管理员身份运行脚本
- [ ] 虚拟环境已激活（.venv 存在）
- [ ] pywin32 已安装（`pip list | grep pywin32`）
- [ ] 服务安装成功（`manage_service.ps1 -Command status`）
- [ ] 服务启动成功
- [ ] 可访问 http://127.0.0.1:5000
- [ ] 配置文件有效（config.json）
- [ ] 数据库连接正常

---

## 🆘 常见问题速解

### 权限不足
```
解决：以管理员身份打开 PowerShell
```

### pywin32 不可用
```
解决：pip install pywin32
```

### 服务无法启动
```
1. 检查：.\manage_service.ps1 -Command status
2. 直接运行：python -m src.main
3. 查看错误信息并调整配置
```

### 端口被占用
```
解决：编辑 config.json 更改端口号
```

---

## 📚 技术实现

### 使用的技术

| 技术 | 用途 |
|------|------|
| pywin32 | Windows API 绑定 |
| win32serviceutil | 服务管理 |
| subprocess | 进程管理 |
| PowerShell | 脚本管理 |

### 服务架构

```
Windows Service (KnowledgeBaseService)
    ↓
    ├─ 虚拟环境激活
    ├─ 启动 Python 进程
    ├─ 运行 src.main (Knowledge-Base 应用)
    └─ 监控进程状态
```

---

## 🔄 生命周期

1. **安装** → 服务注册到 Windows
2. **启动** → Python 应用启动运行
3. **运行** → 监听 HTTP 请求
4. **停止** → 优雅关闭应用
5. **卸载** → 从 Windows 移除服务

---

## 💾 数据安全

### 数据位置
- 知识库数据：`./kb_store`
- 模型缓存：`./models/hf_cache`
- 配置文件：`config.json`

### 备份建议
定期备份 `./kb_store` 目录以保护数据。

---

## 🎓 学习路径

1. **快速开始** → 阅读 `QUICK_START.md`
2. **实际操作** → 按步骤执行 install/start
3. **深入学习** → 阅读 `WINDOWS_SERVICE_GUIDE.md`
4. **故障排查** → 查看 GUIDE 中的故障排查章节
5. **高级配置** → 修改 `config.json` 自定义功能

---

## 🔗 快速链接

- 项目目录：`D:\Project\code\py\knowledge-base`
- Web UI：http://127.0.0.1:5000/ui/
- API 文档：http://127.0.0.1:5000/docs/
- Windows 日志：`eventvwr.msc`
- 服务管理器：`services.msc`

---

## 📞 获取帮助

| 问题类型 | 查看文件 |
|---------|---------|
| 快速开始问题 | QUICK_START.md |
| 服务相关问题 | WINDOWS_SERVICE_GUIDE.md |
| 部署问题 | WINDOWS_DEPLOYMENT_GUIDE.md |
| 应用问题 | README.md |

---

**完成日期**：2026-03-09  
**支持平台**：Windows 7/8/10/11/Server 2016+  
**Python 版本**：3.8+  
**虚拟环境**：✅ 已创建并配置
