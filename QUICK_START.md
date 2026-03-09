# 🚀 Windows 服务快速启动指南

## 📝 5 分钟快速开始

### 步骤 1：以管理员身份打开 PowerShell

**方法 A：右键菜单**
1. 按 `Win + X` 或右键点击开始菜单
2. 选择"Windows PowerShell（管理员）"或"终端（管理员）"

**方法 B：直接搜索**
1. 按 `Win` 键
2. 输入 "powershell"
3. 右键点击结果，选择"以管理员身份运行"

### 步骤 2：导航到项目目录

```powershell
cd D:\Project\code\py\knowledge-base
```

### 步骤 3：安装 Windows 服务

```powershell
.\manage_service.ps1 -Command install
```

**输出示例：**
```
[*] Installing Knowledge-Base Service...
[*] Service Name: KnowledgeBase
[*] Project Root: D:\Project\code\py\knowledge-base
...
[+] Service installed successfully

Service Details:
  - Name: KnowledgeBase
  - Display Name: Knowledge-Base Service
  - Status: Stopped

Next steps:
  1. Run: .\manage_service.ps1 -Command start
  2. Monitor: .\manage_service.ps1 -Command status
```

### 步骤 4：启动服务

```powershell
.\manage_service.ps1 -Command start
```

**输出示例：**
```
[*] Starting KnowledgeBase...
[+] Service started (Status: Running)
```

### 步骤 5：访问应用

打开浏览器访问：
- **Web UI**: http://127.0.0.1:5000/ui/
- **API 文档**: http://127.0.0.1:5000/docs/

✅ **完成！** 你的 Knowledge-Base 现在作为 Windows 服务运行。

---

## 🎯 常用命令速查

### 查看服务状态
```powershell
.\manage_service.ps1 -Command status
```

### 停止服务
```powershell
.\manage_service.ps1 -Command stop
```

### 重启服务
```powershell
.\manage_service.ps1 -Command restart
```

### 卸载服务
```powershell
.\manage_service.ps1 -Command uninstall
```

---

## ⚡ 其他启动方式

### 使用批处理脚本（CMD）

```cmd
REM 以管理员身份打开 CMD，然后：
cd D:\Project\code\py\knowledge-base
manage_service.bat install
manage_service.bat start
manage_service.bat status
```

### 使用 Windows 服务管理器

1. 按 `Win + R`
2. 输入 `services.msc`
3. 在列表中找到 "Knowledge-Base Service"
4. 右键选择"启动"

### 使用任务计划程序设置自启动

1. 按 `Win + R`
2. 输入 `taskmgr`
3. 选择"服务"标签页
4. 找到 "KnowledgeBase"
5. 右键选择"启动"

---

## 🔧 配置修改

### 更改端口号

编辑 `config.json`：

```json
{
  "api_server": {
    "host": "127.0.0.1",
    "port": 8000  // 改成你需要的端口
  }
}
```

然后重启服务：
```powershell
.\manage_service.ps1 -Command restart
```

### 更改数据库配置

编辑 `config.json` 中的 `db` 部分：

```json
{
  "db": {
    "backend": "mysql",
    "mysql": {
      "host": "your-host",
      "port": 3306,
      "user": "username",
      "password": "password",
      "database": "knowledge_base"
    }
  }
}
```

---

## ✅ 验证清单

- [ ] 以管理员身份打开 PowerShell
- [ ] 成功运行 `manage_service.ps1 -Command install`
- [ ] 成功运行 `manage_service.ps1 -Command start`
- [ ] 服务状态显示为 "Running"
- [ ] 能访问 http://127.0.0.1:5000/ui/
- [ ] 已配置正确的数据库和 Redis 连接

---

## 🆘 快速故障排查

### ❌ 问题：权限不足
```
[!] Error: This script requires Administrator privileges
```
**解决**：以管理员身份运行 PowerShell

### ❌ 问题：服务已存在
```
[!] Service 'KnowledgeBase' already exists
```
**解决**：卸载旧服务后重新安装
```powershell
.\manage_service.ps1 -Command uninstall
.\manage_service.ps1 -Command install
```

### ❌ 问题：无法访问应用
1. 检查服务是否运行：
   ```powershell
   .\manage_service.ps1 -Command status
   ```
2. 检查防火墙是否阻止 5000 端口
3. 尝试访问 http://localhost:5000/docs/

### ❌ 问题：服务启动后立即停止
1. 检查配置文件 `config.json` 是否正确
2. 验证数据库连接是否可用
3. 直接运行应用查看错误：
   ```powershell
   .\.venv\Scripts\Activate.ps1
   python -m src.main
   ```

---

## 📚 更多帮助

- 详细使用指南：参考 `WINDOWS_SERVICE_GUIDE.md`
- 部署指南：参考 `WINDOWS_DEPLOYMENT_GUIDE.md`
- 项目文档：参考 `README.md`

---

## 💡 提示

💾 **定期备份**：备份 `./kb_store` 目录以保护你的知识库数据

🔒 **安全**：定期更新密码和 API 密钥，不要在代码中存储敏感信息

📊 **监控**：定期检查服务状态和系统资源使用情况

🔄 **更新**：有新版本时，重新运行 `.\manage_service.ps1 -Command restart`

---

**最后更新**：2026-03-09  
**支持平台**：Windows 7/8/10/11/Server 2016+
