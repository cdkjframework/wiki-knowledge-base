# Windows 服务模式使用指南

## 📌 概述

Knowledge-Base 支持作为 Windows 服务后台运行，这样应用会在系统启动时自动启动，无需手动干预。

## 🔧 系统要求

- Windows 7/8/10/11 或 Server 2016+
- Python 3.8+
- **管理员权限**（安装/卸载/启动/停止服务）

## 📦 安装依赖

已在 `requirements.txt` 中添加了 `pywin32` 依赖：

```bash
pip install -r requirements.txt
```

## 🚀 快速开始

### 方式一：使用 PowerShell（推荐）

**1. 打开 PowerShell 并以管理员身份运行**

**2. 导航到项目目录**
```powershell
cd D:\Project\code\py\knowledge-base
```

**3. 安装服务**
```powershell
.\manage_service.ps1 -Command install
```

**4. 启动服务**
```powershell
.\manage_service.ps1 -Command start
```

**5. 查看服务状态**
```powershell
.\manage_service.ps1 -Command status
```

### 方式二：使用命令提示符

**1. 以管理员身份打开命令提示符**

**2. 导航到项目目录**
```cmd
cd D:\Project\code\py\knowledge-base
```

**3. 安装服务**
```cmd
manage_service.bat install
```

**4. 启动服务**
```cmd
manage_service.bat start
```

**5. 查看服务状态**
```cmd
manage_service.bat status
```

## 📋 服务命令详解

### PowerShell 命令

```powershell
# 安装服务（首次）
.\manage_service.ps1 -Command install

# 启动服务
.\manage_service.ps1 -Command start

# 停止服务
.\manage_service.ps1 -Command stop

# 重启服务
.\manage_service.ps1 -Command restart

# 查看服务状态
.\manage_service.ps1 -Command status

# 卸载服务
.\manage_service.ps1 -Command uninstall

# 显示帮助
.\manage_service.ps1 -Command help
```

### 批处理命令

```cmd
# 安装服务
manage_service.bat install

# 启动服务
manage_service.bat start

# 停止服务
manage_service.bat stop

# 重启服务
manage_service.bat restart

# 查看服务状态
manage_service.bat status

# 卸载服务
manage_service.bat uninstall

# 显示帮助
manage_service.bat help
```

## 🔍 验证安装

安装后，可以通过以下方式验证：

### 方法1：使用管理脚本
```powershell
.\manage_service.ps1 -Command status
```

输出示例：
```
Service Name      : KnowledgeBase
Display Name      : Knowledge-Base Service
Status            : Running
Start Type        : Automatic
Process ID (PID)  : 5432
Memory Usage      : 245.67 MB
```

### 方法2：Windows 服务管理器
1. 按 `Win + R` 打开运行窗口
2. 输入 `services.msc` 并按 Enter
3. 查找 "Knowledge-Base Service"

### 方法3：任务管理器
1. 打开任务管理器（Ctrl + Shift + Esc）
2. 切换到"详细信息"标签页
3. 查找 python.exe 进程

## 🔄 启动类型设置

### 自动启动（推荐）
修改服务设置为在系统启动时自动启动：

```powershell
# 在 PowerShell 中
Set-Service -Name "KnowledgeBase" -StartupType Automatic
```

或通过 Windows 服务管理器：
1. 打开 `services.msc`
2. 右键点击 "Knowledge-Base Service"
3. 选择"属性"
4. 将"启动类型"设置为"自动"

### 手动启动
```powershell
Set-Service -Name "KnowledgeBase" -StartupType Manual
```

## 📊 日志和调试

### 查看事件日志
1. 打开事件查看器（eventvwr.msc）
2. 导航到：Windows 日志 → 应用程序
3. 查找来自 "Python Service" 的事件

### 查看服务日志
```powershell
# 获取服务相关事件
Get-EventLog -LogName Application -Source "Python Service" -Newest 10
```

### 调试模式
如果服务无法启动，可以直接运行应用程序以查看错误：

```powershell
# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 直接运行应用
python -m src.main
```

## ❌ 常见问题

### 问题1：安装时收到"Access Denied"错误

**原因**：未以管理员身份运行

**解决方案**：
1. 右键点击 PowerShell/CMD
2. 选择"以管理员身份运行"

### 问题2：pywin32 安装失败

**原因**：缺少必要的编译工具或权限

**解决方案**：
```powershell
# 重新安装 pywin32
pip install --upgrade pywin32

# 运行 post-install 脚本
python -m Scripts.pywin32_postinstall -install
```

### 问题3：服务启动后立即停止

**原因**：应用启动时发生错误

**解决方案**：
1. 直接运行应用检查错误信息：
   ```powershell
   .\.venv\Scripts\Activate.ps1
   python -m src.main
   ```
2. 检查 `config.json` 配置是否正确
3. 查看事件日志中的错误信息

### 问题4：无法停止服务

**解决方案**：
```powershell
# 强制停止
Stop-Service -Name "KnowledgeBase" -Force

# 如果仍无法停止，杀死进程
Get-Process python | Where-Object {$_.CommandLine -like "*windows_service*"} | Stop-Process -Force
```

### 问题5：端口被占用

**原因**：服务使用的端口被其他应用占用

**解决方案**：
```powershell
# 查找占用端口 5000 的进程
netstat -ano | findstr :5000

# 杀死该进程（假设 PID 为 12345）
taskkill /PID 12345 /F

# 或编辑 config.json 更改端口
```

## 🔐 权限和安全

### 服务账户
默认情况下，服务使用 **Local System** 账户运行。

如果需要使用特定用户账户：
```powershell
# 通过 services.msc 修改
# 或使用命令：
$serviceName = "KnowledgeBase"
$username = ".\YourUsername"
$password = "YourPassword"

# 设置服务账户
sc config $serviceName obj= $username password= $password
```

### 文件权限
确保服务账户对以下目录有读写权限：
- 项目目录
- `./kb_store` （知识库数据目录）
- `./models/hf_cache` （模型缓存目录）

## 🛠️ 故障排查步骤

1. **检查服务状态**
   ```powershell
   .\manage_service.ps1 -Command status
   ```

2. **查看事件日志**
   ```powershell
   eventvwr.msc
   ```

3. **测试直接运行**
   ```powershell
   .\.venv\Scripts\Activate.ps1
   python -m src.main
   ```

4. **检查配置文件**
   - 验证 `config.json` 中的数据库和 Redis 连接信息

5. **检查网络连接**
   - 确保数据库和 Redis 服务可访问

6. **查看虚拟环境**
   - 确保虚拟环境已正确创建和配置

## 📝 完整使用示例

```powershell
# 1. 打开 PowerShell 并以管理员身份运行

# 2. 导航到项目目录
cd D:\Project\code\py\knowledge-base

# 3. 首次安装时，安装依赖
pip install -r requirements.txt

# 4. 安装 Windows 服务
.\manage_service.ps1 -Command install

# 5. 启动服务
.\manage_service.ps1 -Command start

# 6. 验证服务正在运行
.\manage_service.ps1 -Command status

# 7. 设置自动启动（可选）
Set-Service -Name "KnowledgeBase" -StartupType Automatic

# 8. 访问应用
# 打开浏览器访问：
# - Web UI: http://127.0.0.1:5000/ui/
# - API: http://127.0.0.1:5000/docs/

# 9. 停止服务（如需）
.\manage_service.ps1 -Command stop

# 10. 卸载服务（如需）
.\manage_service.ps1 -Command uninstall
```

## 🔗 相关文件

- `src/windows_service.py` - Windows 服务主文件
- `manage_service.ps1` - PowerShell 管理脚本
- `manage_service.bat` - 批处理管理脚本
- `requirements.txt` - 包含 pywin32 依赖

## 📚 更多信息

- Windows 服务文档：https://docs.microsoft.com/en-us/windows/win32/services/services
- pywin32 文档：https://pypi.org/project/pywin32/
- Python 服务编程：https://docs.python.org/3/library/

---

**最后更新**：2026-03-09  
**平台**：Windows 7/8/10/11/Server 2016+  
**Python**：3.8+
