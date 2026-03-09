# 日志配置文档

## 概述

知识库系统提供了完善的分级日志功能，支持通过 `config.json` 配置日志级别、保留天数和 DEBUG 日志开关。

## 日志文件分类

系统会自动生成以下日志文件：

### 1. debug.log（可选）
- **内容**：包含所有 DEBUG 级别的详细调试信息
- **用途**：开发调试、问题诊断、性能分析
- **启用方式**：在 config.json 中设置 `"enable_debug": true`
- **文件大小**：可能较大，包含详细的方法调用、参数、执行步骤等

### 2. info.log
- **内容**：INFO 和 WARNING 级别的日志
- **用途**：记录正常运行状态、警告信息
- **默认启用**：是
- **典型内容**：
  - 系统启动/停止
  - 模型加载状态
  - API 请求处理
  - 配置加载信息

### 3. error.log
- **内容**：ERROR 和 CRITICAL 级别的日志
- **用途**：记录错误和严重问题
- **默认启用**：是
- **典型内容**：
  - 模块加载失败
  - 数据库连接错误
  - 未捕获的全局异常
  - API 请求错误

## 配置说明

### config.json 配置项

在 `config.json` 中添加 `logging` 配置段：

```json
{
  "logging": {
    "level": "INFO",           // 全局日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL
    "keep_days": 7,            // 日志保留天数（自动清理）
    "enable_debug": false,     // 是否启用 debug.log 文件
    "console_level": "INFO"    // 控制台输出级别（可与文件级别不同）
  }
}
```

### 配置参数详解

#### level（全局日志级别）
- **可选值**：`"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`, `"CRITICAL"`
- **默认值**：`"INFO"`
- **说明**：
  - `DEBUG`：最详细，包含所有调试信息（建议仅开发环境使用）
  - `INFO`：常规信息，推荐生产环境使用
  - `WARNING`：仅警告和错误
  - `ERROR`：仅错误和严重错误
  - `CRITICAL`：仅严重错误

#### keep_days（日志保留天数）
- **类型**：整数
- **默认值**：`7`
- **说明**：系统会在启动时自动清理超过指定天数的日志文件
- **建议值**：
  - 开发环境：3-7 天
  - 生产环境：14-30 天

#### enable_debug（DEBUG 日志开关）
- **类型**：布尔值
- **默认值**：`false`
- **说明**：
  - `true`：创建 debug.log 文件，记录详细的调试信息
  - `false`：不创建 debug.log 文件，节省磁盘空间
- **注意**：即使设为 `false`，若 `level` 设为 `"DEBUG"`，调试信息仍会输出到 info.log

#### console_level（控制台日志级别）
- **可选值**：`"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`, `"CRITICAL"`
- **默认值**：与 `level` 相同
- **说明**：控制终端/控制台输出的日志级别，可与文件日志级别分离

## 日志文件管理

### 文件命名规则

当前日志文件：
- `debug.log`
- `info.log`
- `error.log`

备份日志文件（按日期后缀）：
- `debug.log.20260216`
- `info.log.20260216`
- `error.log.20260216`

### 自动轮转

- **轮转时间**：每天午夜（00:00）
- **轮转方式**：当前日志重命名为带日期后缀，创建新的当前日志
- **保留数量**：根据 `keep_days` 配置自动清理

### 手动清理

如需手动清理日志：

```bash
# Windows PowerShell
Remove-Item logs\*.log.* -Force

# Linux/Mac
rm -f logs/*.log.*
```

## 使用场景

### 场景 1：生产环境（默认配置）

```json
{
  "logging": {
    "level": "INFO",
    "keep_days": 14,
    "enable_debug": false,
    "console_level": "WARNING"
  }
}
```

**特点**：
- 仅记录重要信息
- 控制台输出较少（仅警告和错误）
- 日志文件较小
- 保留 2 周日志

### 场景 2：开发调试

```json
{
  "logging": {
    "level": "DEBUG",
    "keep_days": 3,
    "enable_debug": true,
    "console_level": "DEBUG"
  }
}
```

**特点**：
- 记录所有调试信息
- 控制台输出详细
- 生成独立的 debug.log 文件
- 仅保留 3 天（节省空间）

### 场景 3：问题诊断

```json
{
  "logging": {
    "level": "INFO",
    "keep_days": 7,
    "enable_debug": true,
    "console_level": "INFO"
  }
}
```

**特点**：
- 正常运行使用 INFO 级别
- 启用 debug.log 用于详细分析
- 平衡性能和调试需求

## DEBUG 日志内容示例

启用 DEBUG 日志后，系统会记录详细的执行过程：

### 查询流程

```
2026-02-16 10:30:45 | DEBUG | api | 查询详细参数:
2026-02-16 10:30:45 | DEBUG | api |   query: 如何使用知识库
2026-02-16 10:30:45 | DEBUG | api |   k: 3
2026-02-16 10:30:45 | DEBUG | api |   relevance_threshold: None
2026-02-16 10:30:45 | DEBUG | api |   deep_think: True
2026-02-16 10:30:45 | DEBUG | api | 开始执行知识库检索...
2026-02-16 10:30:45 | DEBUG | knowledge_base | 开始搜索: query='如何使用知识库', k=3, relevance_threshold=None
2026-02-16 10:30:45 | DEBUG | knowledge_base | 实际搜索参数: k=3, 总分片数=156
2026-02-16 10:30:45 | DEBUG | knowledge_base | 编码查询文本...
2026-02-16 10:30:45 | DEBUG | knowledge_base | 查询编码完成，向量维度: (1, 768)
2026-02-16 10:30:45 | DEBUG | knowledge_base | 开始候选召回，召回数量: 24 (k=3, multiplier=8)
2026-02-16 10:30:45 | DEBUG | knowledge_base | 召回 24 个候选结果
2026-02-16 10:30:45 | DEBUG | knowledge_base | 开始重排序，rerank_weight=0.65
2026-02-16 10:30:46 | DEBUG | knowledge_base | 重排序完成，得到 24 个结果
2026-02-16 10:30:46 | DEBUG | knowledge_base | 结果排序完成
2026-02-16 10:30:46 | DEBUG | knowledge_base | 开始过滤和去重，阈值=None
2026-02-16 10:30:46 | DEBUG | knowledge_base | 添加结果 #1: filename=README.md, distance=0.3245
2026-02-16 10:30:46 | DEBUG | knowledge_base | 添加结果 #2: filename=API.html, distance=0.4521
2026-02-16 10:30:46 | DEBUG | knowledge_base | 添加结果 #3: filename=guide.md, distance=0.5234
2026-02-16 10:30:46 | DEBUG | knowledge_base | 搜索完成，返回 3 个结果
2026-02-16 10:30:46 | DEBUG | api | 检索到 3 个原始结果
2026-02-16 10:30:46 | DEBUG | api | 加载聊天上下文...
2026-02-16 10:30:46 | DEBUG | api | 加载了 4 条历史消息
2026-02-16 10:30:46 | DEBUG | api | 构建聊天提示词...
2026-02-16 10:30:46 | DEBUG | api | 系统提示词长度: 234, 用户提示词长度: 1523
2026-02-16 10:30:46 | DEBUG | api | 开始生成答案，使用 3 个检索结果
2026-02-16 10:30:48 | DEBUG | api | 答案生成完成，长度: 456
2026-02-16 10:30:48 | DEBUG | api | 思考摘要长度: 123
```

### 文档添加流程

```
2026-02-16 10:31:00 | DEBUG | knowledge_base | 开始添加文档: filename='tutorial.md', text_length=5234
2026-02-16 10:31:00 | DEBUG | knowledge_base | 规范化文件名: 'tutorial.md' -> 'tutorial.md'
2026-02-16 10:31:00 | DEBUG | knowledge_base | 开始文本分块...
2026-02-16 10:31:00 | DEBUG | knowledge_base | 文本分块完成，得到 7 个分块
2026-02-16 10:31:00 | DEBUG | knowledge_base | 开始生成向量嵌入...
2026-02-16 10:31:01 | DEBUG | knowledge_base | 向量生成完成，shape=(7, 768)
2026-02-16 10:31:01 | DEBUG | knowledge_base | 合并新向量到现有嵌入矩阵
2026-02-16 10:31:01 | DEBUG | knowledge_base | 总分块数: 163, 总向量数: 163
2026-02-16 10:31:01 | DEBUG | knowledge_base | 重建向量索引...
2026-02-16 10:31:01 | DEBUG | knowledge_base | 保存到磁盘...
2026-02-16 10:31:01 | INFO | knowledge_base | 文档添加完成: filename='tutorial.md', chunks=7
```

## 性能影响

### DEBUG 日志对性能的影响

| 场景 | INFO 级别 | DEBUG 级别 | 影响 |
|------|----------|-----------|------|
| CPU 使用 | 基线 | +2-5% | 轻微 |
| 内存使用 | 基线 | +10-20MB | 轻微 |
| 磁盘写入 | 1-10MB/天 | 50-200MB/天 | 中等 |
| 日志延迟 | <1ms | 1-3ms | 可忽略 |

**建议**：
- 生产环境：使用 INFO 或 WARNING 级别
- 开发环境：可使用 DEBUG 级别
- 问题诊断：临时启用 DEBUG，诊断完毕后关闭

## 全局异常处理

系统实现了全局异常捕获，所有未处理的异常都会被记录到 **error.log**：

```
2026-02-16 10:32:15 | ERROR | logger_config | ================================================================================
2026-02-16 10:32:15 | ERROR | logger_config | 🔥 捕获到未处理的全局异常 🔥
2026-02-16 10:32:15 | ERROR | logger_config | ================================================================================
2026-02-16 10:32:15 | ERROR | logger_config | 异常类型: ValueError
2026-02-16 10:32:15 | ERROR | logger_config | 异常消息: invalid literal for int()
2026-02-16 10:32:15 | ERROR | logger_config | 异常发生位置:
2026-02-16 10:32:15 | ERROR | logger_config |   文件: /path/to/api.py
2026-02-16 10:32:15 | ERROR | logger_config |   函数: query
2026-02-16 10:32:15 | ERROR | logger_config |   行号: 567
2026-02-16 10:32:15 | ERROR | logger_config | --------------------------------------------------------------------------------
2026-02-16 10:32:15 | ERROR | logger_config | 完整堆栈跟踪:
... (详细堆栈信息)
2026-02-16 10:32:15 | ERROR | logger_config | --------------------------------------------------------------------------------
2026-02-16 10:32:15 | ERROR | logger_config | 调用链详细信息:
... (局部变量等详细信息)
```

## 常见问题

### Q1: 如何临时启用 DEBUG 日志？

修改 `config.json`：

```json
{
  "logging": {
    "enable_debug": true,
    "level": "DEBUG"
  }
}
```

然后重启应用。

### Q2: 日志文件过大怎么办？

1. 减少 `keep_days` 值
2. 提高日志级别（如从 DEBUG 改为 INFO）
3. 关闭 `enable_debug`
4. 手动清理旧日志

### Q3: 控制台输出太多怎么办？

设置 `console_level` 为更高级别：

```json
{
  "logging": {
    "level": "DEBUG",
    "console_level": "WARNING"  // 控制台仅显示警告和错误
  }
}
```

### Q4: 如何查看历史日志？

日志文件位于 `logs/` 目录：

```bash
# 查看当前 INFO 日志
cat logs/info.log

# 查看昨天的 ERROR 日志
cat logs/error.log.20260215

# 搜索特定错误
grep "ValueError" logs/error.log*
```

## 最佳实践

1. **生产环境**：
   - 使用 INFO 级别
   - 保留 14-30 天日志
   - 禁用 debug.log
   - 定期检查 error.log

2. **开发环境**：
   - 使用 DEBUG 级别
   - 启用 debug.log
   - 保留 3-7 天
   - 频繁查看日志定位问题

3. **日志监控**：
   - 定期检查 error.log 文件大小
   - 设置 error.log 告警
   - 归档重要日志
   - 使用日志分析工具

4. **问题诊断**：
   - 临时启用 DEBUG 级别
   - 复现问题
   - 分析 debug.log
   - 恢复原日志级别

## 相关文件

- `src/logger_config.py` - 日志配置模块
- `src/main.py` - 应用启动入口，初始化日志
- `config.json` - 配置文件
- `logs/` - 日志文件目录
