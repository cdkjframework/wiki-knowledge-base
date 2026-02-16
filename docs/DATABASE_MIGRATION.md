# 数据库结构升级说明

## 概述

知识库系统的历史记录存储已从单表结构升级为**主表+子表**结构，提供更好的数据组织和查询性能。

## 新的数据库结构

### 主表：kb_sessions
存储会话（session）的元数据信息。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT | 主键，自增 |
| session_id | VARCHAR(128) | 会话ID，唯一索引 |
| user_id | VARCHAR(128) | 用户ID |
| title | TEXT | 会话标题（第一个问题的内容） |
| created_at | TIMESTAMP | 会话创建时间 |
| updated_at | TIMESTAMP | 最后更新时间 |
| message_count | INT | 消息数量 |

**索引：**
- PRIMARY KEY (id)
- UNIQUE (session_id)
- INDEX (user_id)
- INDEX (created_at)
- INDEX (updated_at)

### 子表：kb_session_messages (或继续使用 kb_history)
存储每条消息的详细记录。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT | 主键，自增 |
| session_id | VARCHAR(128) | 会话ID，外键 |
| timestamp | VARCHAR(64) | 消息时间戳 |
| action | VARCHAR(64) | 操作类型（如：query） |
| user_id | VARCHAR(128) | 用户ID |
| request_json | TEXT/LONGTEXT | 请求数据（JSON） |
| response_json | TEXT/LONGTEXT | 响应数据（JSON） |
| error | TEXT/LONGTEXT | 错误信息 |
| created_at | TIMESTAMP | 入库时间 |

**索引：**
- PRIMARY KEY (id)
- INDEX (session_id)
- INDEX (action)
- INDEX (timestamp)
- INDEX (user_id)
- FOREIGN KEY (session_id) REFERENCES kb_sessions(session_id) ON DELETE CASCADE

## 主要变更

### 1. 数据库层面

**旧结构（单表）：**
```sql
kb_history:
  - id, timestamp, action, session_id, user_id, 
    request_json, response_json, error, created_at
```

**新结构（主子表）：**
```sql
kb_sessions:
  - id, session_id, user_id, title, created_at, updated_at, message_count

kb_session_messages:
  - id, session_id, timestamp, action, user_id,
    request_json, response_json, error, created_at
  - FOREIGN KEY (session_id) -> kb_sessions(session_id)
```

### 2. 代码变更

#### history_store.py
- `__init__`: 添加 `self.sessions_table` 和 `self.messages_table`
- `_ensure_table()`: 创建两个表
- `append()`: 插入消息时自动维护主表（创建/更新session）
- `get()`: 从子表查询
- `get_by_sessions()`: 利用主表优化查询性能
- `delete()`: 删除消息时更新主表计数
- `delete_session()`: 新增方法，删除整个会话

#### memory_store.py
- `delete_session()`: 新增方法，支持内存存储

#### api.py
- `delete_session()`: 新增API方法
- HTTP DELETE /session/{session_id}: 新增路由

#### app.js
- 删除会话改为调用 `DELETE /session/{session_id}` API
- 一次性删除整个会话，而非循环删除每条消息

### 3. 功能改进

✅ **性能提升**
- 查询会话列表时直接从主表获取，无需 GROUP BY
- 主表的 updated_at 字段有索引，倒序排列更快

✅ **数据一致性**
- 外键约束确保数据完整性
- CASCADE DELETE 自动清理关联数据
- 主表自动维护消息计数

✅ **操作优化**
- 删除会话只需一次 DELETE 操作
- 新增会话时自动创建主表记录
- 更新时间自动维护

## 迁移指南

### 自动迁移（推荐）

使用提供的迁移脚本：

```bash
# 1. 备份数据库（重要！）
mysqldump -u root -p knowledge_base > backup.sql
# 或 PostgreSQL
pg_dump knowledge_base > backup.sql

# 2. 运行迁移脚本
python migrate_to_sessions_table.py

# 3. 测试应用功能

# 4. 确认无误后删除备份表
# DROP TABLE kb_history_backup;
```

### 手动迁移

如果需要手动迁移，可以参考以下步骤：

```sql
-- 1. 创建主表
CREATE TABLE kb_sessions (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(128) UNIQUE NOT NULL,
    user_id VARCHAR(128),
    title TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    message_count INT NOT NULL DEFAULT 0
);

-- 2. 将旧表重命名为子表（或创建新子表）
ALTER TABLE kb_history RENAME TO kb_session_messages;

-- 3. 从子表数据生成主表记录
INSERT INTO kb_sessions (session_id, user_id, title, created_at, updated_at, message_count)
SELECT 
    session_id,
    MIN(user_id) as user_id,
    LEFT(MIN(request_json::json->>'query'), 200) as title,
    MIN(created_at) as created_at,
    MAX(created_at) as updated_at,
    COUNT(*) as message_count
FROM kb_session_messages
WHERE session_id IS NOT NULL
GROUP BY session_id;

-- 4. 添加外键约束
ALTER TABLE kb_session_messages
ADD CONSTRAINT fk_session
FOREIGN KEY (session_id) 
REFERENCES kb_sessions(session_id) 
ON DELETE CASCADE;
```

## 兼容性说明

### 向后兼容
- 所有现有 API 接口保持不变
- 前端无需修改（除了删除会话的优化）
- 内存存储仍然可用

### 新特性
- `DELETE /session/{session_id}` - 删除整个会话
- `get_by_sessions()` 查询性能提升

## 注意事项

⚠️ **迁移前必做：**
1. 完整备份数据库
2. 在测试环境先验证
3. 确保应用程序已停止

⚠️ **迁移后检查：**
1. 验证主表记录数 = 会话数
2. 验证子表记录数 = 原始消息数
3. 测试查询、插入、删除功能
4. 检查 message_count 是否正确

## 常见问题

### Q1: 是否必须迁移？
**A:** 不是必须的。新代码会自动创建新表结构，旧数据保留在原表中。但为了获得最佳性能，建议迁移。

### Q2: 迁移会丢失数据吗？
**A:** 不会。迁移脚本会保留原表作为备份（重命名为 kb_history_backup）。

### Q3: 迁移需要多长时间？
**A:** 取决于数据量。通常每1万条记录约需1-5秒。

### Q4: 可以回滚吗？
**A:** 可以。如果备份表还在，可以执行：
```sql
DROP TABLE kb_sessions;
DROP TABLE kb_session_messages;
ALTER TABLE kb_history_backup RENAME TO kb_history;
```

### Q5: 内存存储受影响吗？
**A:** 不影响。内存存储会自动适配新的 API，无需迁移。

## 技术细节

### 外键级联删除
设置了 `ON DELETE CASCADE`，删除主表记录时会自动删除所有关联的子表记录：

```sql
DELETE FROM kb_sessions WHERE session_id = 'xxx';
-- 自动删除 kb_session_messages 中所有 session_id = 'xxx' 的记录
```

### 时间戳管理
- MySQL: 使用触发器自动更新 `updated_at`
  ```sql
  ON UPDATE CURRENT_TIMESTAMP
  ```
- PostgreSQL: 在 UPDATE 时手动设置
  ```sql
  UPDATE kb_sessions SET updated_at = CURRENT_TIMESTAMP WHERE ...
  ```

### 事务保证
所有插入、更新、删除操作都在事务中执行，确保数据一致性：
```python
try:
    # 1. 更新/创建主表
    # 2. 插入子表
    conn.commit()
except:
    conn.rollback()
    raise
```

## 更新日志

### 2026-02-15
- ✅ 实现主表+子表结构
- ✅ 添加 delete_session API
- ✅ 优化 get_by_sessions 查询性能
- ✅ 创建数据迁移脚本
- ✅ 更新前端删除逻辑

---

如有疑问，请查看源代码或联系开发团队。
